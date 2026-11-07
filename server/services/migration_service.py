"""Startup schema migrations for Pantau Server."""

import logging
from sqlalchemy import inspect, text

try:
    from models import (
        Base, MaintenanceWindow, ProbeLog, ProbeTarget, Server, ServerExtras,
        ServerProblem, Service, User,
    )
    from core.database import SessionLocal, engine
    from core.utils import KEY_PREFIX, hash_api_key
except ImportError:
    from server.models import (
        Base, MaintenanceWindow, ProbeLog, ProbeTarget, Server, ServerExtras,
        ServerProblem, Service, User,
    )
    from server.core.database import SessionLocal, engine
    from server.core.utils import KEY_PREFIX, hash_api_key

logger = logging.getLogger("pantau.migrations")


def migrate_api_keys() -> None:
    """Sekali pakai: hash API key plaintext lama yang tersisa di DB."""
    db = SessionLocal()
    try:
        migrated = 0
        for srv in db.query(Server).filter(~Server.api_key.like(KEY_PREFIX + "%")).all():
            srv.api_key = hash_api_key(srv.api_key)
            migrated += 1
        if migrated:
            db.commit()
            logger.info("[startup] API key lama di-hash: %d server", migrated)
    finally:
        db.close()


def migrate_log_request_input() -> None:
    """Sekali pakai: tambah kolom input admin ke log_requests (mode interaktif)."""
    inspector = inspect(engine)
    if "log_requests" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("log_requests")}
    wanted = {
        "input_data": "VARCHAR(500) NULL",
        "input_at": "DATETIME NULL",
        "input_queue": "TEXT NULL",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    if not missing:
        return
    db = SessionLocal()
    try:
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE log_requests ADD COLUMN {col} {ddl}"))
        db.commit()
        logger.info("[startup] Kolom baru log_requests: %s", ", ".join(missing))
    except Exception as exc:
        db.rollback()
        logger.warning("[startup] Migrasi kolom input gagal: %s", exc)
    finally:
        db.close()


def migrate_server_problem_ignored() -> None:
    """Migrasi penambahan kolom status abaikan masalah pada tabel server_problems."""
    inspector = inspect(engine)
    if "server_problems" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("server_problems")}
    wanted = {
        "is_ignored": "TINYINT(1) DEFAULT 0",
        "ignored_until": "DATETIME NULL",
        "ignored_by": "VARCHAR(100) NULL",
        "ignored_reason": "VARCHAR(255) NULL",
        "ignore_mode": "VARCHAR(20) DEFAULT 'permanent'",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    if not missing:
        return
    db = SessionLocal()
    try:
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE server_problems ADD COLUMN {col} {ddl}"))
        db.commit()
        logger.info("[startup] Kolom baru server_problems (abaikan masalah): %s", ", ".join(missing))
    except Exception as exc:
        db.rollback()
        logger.warning("[startup] Migrasi kolom ignored gagal: %s", exc)
    finally:
        db.close()


def migrate_service_ignored() -> None:
    """Migrasi penambahan kolom status abaikan layanan pada tabel services."""
    inspector = inspect(engine)
    if "services" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("services")}
    wanted = {
        "is_ignored": "TINYINT(1) DEFAULT 0",
        "ignored_until": "DATETIME NULL",
        "ignored_by": "VARCHAR(100) NULL",
        "ignored_reason": "VARCHAR(255) NULL",
        "ignore_mode": "VARCHAR(20) DEFAULT 'permanent'",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    if not missing:
        return
    db = SessionLocal()
    try:
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE services ADD COLUMN {col} {ddl}"))
        db.commit()
        logger.info("[startup] Kolom baru services (abaikan layanan): %s", ", ".join(missing))
    except Exception as exc:
        db.rollback()
        logger.warning("[startup] Migrasi kolom service ignored gagal: %s", exc)
    finally:
        db.close()


def migrate_user_created_by() -> None:
    """Migrasi penambahan kolom created_by pada tabel users."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("users")}
    if "created_by" in existing:
        return
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN created_by VARCHAR(100) NULL AFTER created_at"))
        db.execute(
            text(
                "UPDATE users SET created_by = 'Sistem (Setup Awal)' WHERE username = 'master-admin' AND (created_by IS NULL OR created_by = '')"
            )
        )
        db.execute(
            text(
                "UPDATE users SET created_by = 'master-admin' WHERE username IN ('sysadmin_sadri', 'viewer-1') AND (created_by IS NULL OR created_by = '')"
            )
        )
        db.commit()
        logger.info("[startup] Kolom baru users.created_by berhasil ditambahkan dan diinisialisasi")
    except Exception as exc:
        db.rollback()
        logger.warning("[startup] Migrasi kolom users.created_by gagal: %s", exc)
    finally:
        db.close()


def migrate_server_extras_specs() -> None:
    """Migrasi penambahan kolom spesifikasi perangkat keras pada tabel server_extras."""
    inspector = inspect(engine)
    if "server_extras" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("server_extras")}
    wanted = {
        "hardware_specs": "TEXT NULL",
        "installed_packages": "MEDIUMTEXT NULL",
        "systemd_units": "MEDIUMTEXT NULL",
        "system_groups": "MEDIUMTEXT NULL",
        "kernel_events": "MEDIUMTEXT NULL",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    db = SessionLocal()
    try:
        if missing:
            for col, ddl in missing.items():
                db.execute(text(f"ALTER TABLE server_extras ADD COLUMN {col} {ddl}"))
            db.commit()
            logger.info("[startup] Kolom baru server_extras: %s", ", ".join(missing))
        try:
            db.execute(text("ALTER TABLE server_extras MODIFY COLUMN accounts MEDIUMTEXT NULL"))
            db.commit()
        except Exception:
            db.rollback()
    except Exception as exc:
        db.rollback()
        logger.warning("[startup] Migrasi kolom server_extras gagal: %s", exc)
    finally:
        db.close()


def migrate_server_groups_and_thresholds() -> None:
    """Migrasi penambahan kolom group_name, tags, custom_thresholds, dll pada tabel servers."""
    inspector = inspect(engine)
    if "servers" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("servers")}
    wanted = {
        "group_name": "VARCHAR(64) NULL DEFAULT NULL",
        "tags": "VARCHAR(255) NULL",
        "custom_thresholds": "TEXT NULL",
        "is_proxmox_ha": "TINYINT NOT NULL DEFAULT 0",
        "platform_override": "VARCHAR(20) NULL DEFAULT NULL",
        "is_isolated_net": "TINYINT NOT NULL DEFAULT 0",
        "allow_web_terminal": "TINYINT NOT NULL DEFAULT 0",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    db = SessionLocal()
    try:
        if missing:
            for col, ddl in missing.items():
                db.execute(text(f"ALTER TABLE servers ADD COLUMN {col} {ddl}"))
            logger.info("[startup] Kolom baru servers: %s", ", ".join(missing))
        db.execute(text("UPDATE servers SET group_name = NULL WHERE group_name = 'Default' OR group_name = ''"))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("[startup] Migrasi kolom servers gagal: %s", exc)
    finally:
        db.close()


def migrate_probing_system() -> None:
    """Migrasi tabel probe_targets & probe_logs serta perbarui kolom server_problems untuk synthetic probing."""
    Base.metadata.create_all(bind=engine, tables=[ProbeTarget.__table__, ProbeLog.__table__])

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if "server_problems" in existing_tables:
        cols = {c["name"]: c for c in inspector.get_columns("server_problems")}
        db = SessionLocal()
        try:
            if "server_id" in cols and not cols["server_id"].get("nullable", True):
                try:
                    db.execute(text("ALTER TABLE server_problems MODIFY COLUMN server_id INT UNSIGNED NULL"))
                    db.commit()
                    logger.info("[startup] Kolom server_problems.server_id diubah menjadi NULLABLE")
                except Exception as e:
                    db.rollback()
                    logger.warning("[startup] Gagal ubah server_problems.server_id: %s", e)

            if "probe_id" not in cols:
                try:
                    db.execute(
                        text(
                            "ALTER TABLE server_problems ADD COLUMN probe_id INT UNSIGNED NULL DEFAULT NULL AFTER server_id"
                        )
                    )
                    db.execute(
                        text(
                            "ALTER TABLE server_problems ADD CONSTRAINT fk_problems_probe FOREIGN KEY (probe_id) REFERENCES probe_targets(id) ON DELETE CASCADE"
                        )
                    )
                    db.commit()
                    logger.info("[startup] Kolom server_problems.probe_id berhasil ditambahkan")
                except Exception as e:
                    db.rollback()
                    logger.warning("[startup] Gagal tambah probe_id: %s", e)
        finally:
            db.close()

    if "probe_targets" in existing_tables:
        cols_pt = {c["name"]: c for c in inspector.get_columns("probe_targets")}
        if "tier" not in cols_pt:
            db = SessionLocal()
            try:
                db.execute(text("ALTER TABLE probe_targets ADD COLUMN tier SMALLINT NOT NULL DEFAULT 2 AFTER server_id"))
                db.commit()
                logger.info("[startup] Kolom probe_targets.tier berhasil ditambahkan")
            except Exception as e:
                db.rollback()
                logger.warning("[startup] Gagal tambah probe_targets.tier: %s", e)
            finally:
                db.close()

        db = SessionLocal()
        try:
            db.execute(text("UPDATE servers SET tier = 2 WHERE tier > 2"))
            db.execute(text("UPDATE probe_targets SET tier = 2 WHERE tier > 2"))
            db.commit()
        except Exception as e:
            db.rollback()
            logger.debug("[startup] Normalisasi 2-level tier: %s", e)
        finally:
            db.close()


def migrate_maintenance_windows_system() -> None:
    """Migrasi tabel maintenance_windows dan index terkait untuk sistem jendela pemeliharaan terjadwal."""
    Base.metadata.create_all(bind=engine, tables=[MaintenanceWindow.__table__])
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "maintenance_windows" in existing_tables:
        cols = {c["name"]: c for c in inspector.get_columns("maintenance_windows")}
        if "server_ids" not in cols:
            db = SessionLocal()
            try:
                db.execute(text("ALTER TABLE maintenance_windows ADD COLUMN server_ids TEXT NULL AFTER server_id"))
                db.commit()
                logger.info("[startup] Kolom maintenance_windows.server_ids berhasil ditambahkan")
            except Exception as e:
                db.rollback()
                logger.warning("[startup] Gagal tambah server_ids: %s", e)
            finally:
                db.close()
        logger.info("[startup] Tabel maintenance_windows siap")


def run_all_migrations() -> None:
    """Jalankan semua migrasi schema saat server startup."""
    migrate_server_groups_and_thresholds()
    migrate_server_extras_specs()
    migrate_server_problem_ignored()
    migrate_service_ignored()
    migrate_user_created_by()
    migrate_log_request_input()
    migrate_api_keys()
    migrate_probing_system()
    migrate_maintenance_windows_system()

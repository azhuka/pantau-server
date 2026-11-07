"""Hardware inventory, platform classification, and specification extraction service."""

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple, Any
from sqlalchemy.orm import Session

try:
    from models import Server, ServerExtras, SystemSnapshot
except ImportError:
    from server.models import Server, ServerExtras, SystemSnapshot

logger = logging.getLogger('pantau.hardware')

# ---------------------------------------------------------------------------
def _format_bytes_gb(b: int | float | None) -> str:
    if b is None or b <= 0:
        return "—"
    gb = b / (1024 ** 3)
    if gb >= 1000:
        return f"{round(gb / 1024, 1)} TB"
    return f"{round(gb, 1)} GB"


def _format_uptime_str(secs: int | None) -> str:
    if secs is None or secs <= 0:
        return "—"
    days = secs // 86400
    hours = (secs % 86400) // 3600
    mins = (secs % 3600) // 60
    if days > 0:
        return f"{days}h {hours}j" if hours else f"{days} hari"
    if hours > 0:
        return f"{hours}j {mins}m"
    return f"{mins} mnt"


def _extract_disk_stats(disks_raw):
    if not disks_raw:
        return "—", "—", None
    try:
        data = json.loads(disks_raw) if isinstance(disks_raw, str) else disks_raw
        if not isinstance(data, list) or not data:
            return "—", "—", None
        root_d = next((d for d in data if d.get("mount") == "/"), data[0])
        tot = root_d.get("total", 0)
        used = root_d.get("used", 0)
        pct = root_d.get("pct", 0.0)
        avail = max(0, tot - used)
        return _format_bytes_gb(tot), _format_bytes_gb(avail), round(float(pct), 1)
    except Exception:
        return "—", "—", None


def _clean_cpu_model(m: str | None) -> str:
    if not m or m == "—":
        return "—"
    s = re.sub(r"\(R\)|\(TM\)", "", m, flags=re.I)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*CPU\s*@.*$", "", s, flags=re.I)
    s = re.sub(r"\s*v?CPU\s*$", "", s, flags=re.I)
    return s.strip() or "—"


def _extract_disks_summary(disks: list | None) -> str:
    if not disks or not isinstance(disks, list):
        return "—"
    parts = []
    for d in disks:
        if isinstance(d, dict):
            sz = str(d.get("size", "")).strip()
            nm = str(d.get("name", "")).strip()
            if sz:
                parts.append(f"{sz} ({nm})" if nm else sz)
    return ", ".join(parts) if parts else "—"


def _extract_hw_model(plat_dict: dict | None) -> str:
    if not plat_dict or not isinstance(plat_dict, dict):
        return "—"
    vendor = str(plat_dict.get("vendor", "")).strip()
    prod = str(plat_dict.get("product", "")).strip()
    s = f"{vendor} {prod}".strip()
    if "Standard PC" in s:
        return "QEMU KVM Guest"
    return s or "—"


def _extract_primary_interface(net_dict: dict | None) -> str:
    if not net_dict or not isinstance(net_dict, dict):
        return ""
    ifaces = net_dict.get("interfaces", [])
    if isinstance(ifaces, list) and ifaces:
        for iface in ifaces:
            if isinstance(iface, dict):
                name = str(iface.get("name", "")).strip()
                if (
                    name
                    and not name.startswith("br-")
                    and not name.startswith("docker")
                    and not name.startswith("veth")
                    and name != "lo"
                    and name != "bonding_masters"
                ):
                    return name
        return str(ifaces[0].get("name", "")).strip()
    return ""


def _classify_platform(platform_dict: dict | None, override: str | None = None) -> dict:
    """Klasifikasi tipe platform host: LXC Container, VM (KVM/QEMU/dll), atau Baremetal."""
    if override in ("baremetal", "vm", "lxc"):
        if override == "baremetal":
            return {
                "type": "baremetal",
                "virt": "Baremetal",
                "label": "Baremetal",
                "short_label": "Baremetal",
                "badge_color": "#34d399",
                "badge_bg": "rgba(16,185,129,0.15)",
                "badge_border": "rgba(16,185,129,0.3)",
            }
        elif override == "vm":
            return {
                "type": "vm",
                "virt": "VM",
                "label": "Mesin Virtual (VM)",
                "short_label": "VM",
                "badge_color": "#c084fc",
                "badge_bg": "rgba(168,85,247,0.15)",
                "badge_border": "rgba(168,85,247,0.3)",
            }
        elif override == "lxc":
            return {
                "type": "lxc",
                "virt": "LXC",
                "label": "LXC Container",
                "short_label": "LXC",
                "badge_color": "#22d3ee",
                "badge_bg": "rgba(6,182,212,0.15)",
                "badge_border": "rgba(6,182,212,0.3)",
            }

    if not isinstance(platform_dict, dict) or not platform_dict:
        return {
            "type": "pending",
            "virt": "Menunggu Laporan Agen",
            "label": "Auto Deteksi (Menunggu Agen)",
            "short_label": "Auto",
            "badge_color": "#94a3b8",
            "badge_bg": "rgba(148,163,184,0.15)",
            "badge_border": "rgba(148,163,184,0.3)",
        }

    virt = str(platform_dict.get("virt") or "").strip().upper()
    vendor = str(platform_dict.get("vendor") or "").strip()
    product = str(platform_dict.get("product") or "").strip()

    if platform_dict.get("platform_type") == "pending" or virt in ("VIRTUAL / HOST LINUX", "MENUNGGU LAPORAN AGEN"):
        return {
            "type": "pending",
            "virt": "Menunggu Laporan Agen",
            "label": "Auto Deteksi (Menunggu Agen)",
            "short_label": "Auto",
            "badge_color": "#94a3b8",
            "badge_bg": "rgba(148,163,184,0.15)",
            "badge_border": "rgba(148,163,184,0.3)",
        }

    # Kontainer (LXC / Docker / WSL / etc.)
    if virt in ("LXC", "LXC-LIBVIRT", "DOCKER", "PODMAN", "CONTAINER", "WSL", "SYSTEMD-NSPAWN") or platform_dict.get("platform_type") == "lxc":
        label = "LXC Container" if virt in ("LXC", "LXC-LIBVIRT") or platform_dict.get("platform_type") == "lxc" else f"Container ({virt})"
        return {
            "type": "lxc",
            "virt": virt or "LXC",
            "label": label,
            "short_label": "LXC" if virt in ("LXC", "LXC-LIBVIRT") or platform_dict.get("platform_type") == "lxc" else virt,
            "badge_color": "#22d3ee",
            "badge_bg": "rgba(6,182,212,0.15)",
            "badge_border": "rgba(6,182,212,0.3)",
        }

    # Mesin Virtual (KVM, QEMU, VMware, VirtualBox, etc.)
    vm_types = ("KVM", "QEMU", "VMWARE", "XEN", "VIRTUALBOX", "ORACLE", "HYPERV", "BOCHS", "BHYVE")
    is_vm = virt in vm_types or any(x in (vendor + product).upper() for x in ("QEMU", "KVM", "VMWARE", "VIRTUALBOX"))
    if is_vm:
        v_name = virt if virt in vm_types else "KVM"
        return {
            "type": "vm",
            "virt": v_name,
            "label": f"VM ({v_name})" if v_name != "VM" else "Virtual Machine",
            "short_label": f"VM ({v_name})" if v_name != "VM" else "VM",
            "badge_color": "#c084fc",
            "badge_bg": "rgba(168,85,247,0.15)",
            "badge_border": "rgba(168,85,247,0.3)",
        }

    # Baremetal / Server Fisik
    return {
        "type": "baremetal",
        "virt": "Baremetal",
        "label": "Baremetal",
        "short_label": "Baremetal",
        "badge_color": "#34d399",
        "badge_bg": "rgba(16,185,129,0.15)",
        "badge_border": "rgba(16,185,129,0.3)",
    }


def _get_hardware_specs_dict(server: Server, extra: ServerExtras | None, latest: SystemSnapshot | None) -> dict:
    if extra and extra.hardware_specs:
        try:
            parsed = json.loads(extra.hardware_specs)
            if isinstance(parsed, dict) and parsed.get("cpu"):
                # Koreksi Storage untuk LXC Container:
                # Kontainer LXC tidak memiliki block storage fisik host (mis. HPE DL380 sda 7.6T).
                # Bila terdeteksi LXC dan disk masih melaporkan disk host, koreksi dengan kuota rootfs dari snapshot.
                plat = parsed.get("platform", {})
                plat_ovr = getattr(server, "platform_override", None)
                has_lxc_disk = any(d.get("type") == "Virtual (LXC)" or d.get("model") == "Container Allocation" for d in parsed.get("disks", []))
                if has_lxc_disk and (not plat_ovr or plat_ovr == "auto"):
                    if plat.get("virt") in ("Bare Metal / Physical", "None", "", "Virtual / Host Linux") or plat.get("platform_type") != "lxc":
                        plat["virt"] = "LXC"
                        plat["platform_type"] = "lxc"
                        plat["platform_label"] = "LXC Container"
                # Fail-Safe Storage: Jika agen secara definitif mendeteksi kontainer (LXC/Docker),
                # kuota virtual rootfs selalu dipaksakan agar disk host fisik tidak bocor ke tampilan kontainer,
                # sekalipun operator keliru memilih override 'baremetal'.
                is_lxc = (
                    plat_ovr == "lxc"
                    or str(plat.get("virt", "")).upper() in ("LXC", "LXC-LIBVIRT", "DOCKER", "PODMAN", "CONTAINER")
                    or plat.get("platform_type") == "lxc"
                )
                if is_lxc:
                    has_host_disk = any(d.get("name", "").startswith("sd") or "T" in str(d.get("size", "")) for d in parsed.get("disks", []))
                    if has_host_disk or not parsed.get("disks"):
                        root_total = 0
                        if latest and latest.disks:
                            try:
                                d_raw = json.loads(latest.disks) if isinstance(latest.disks, str) else latest.disks
                                for d in (d_raw if isinstance(d_raw, list) else []):
                                    if d.get("mount") == "/":
                                        root_total = d.get("total", 0)
                                        break
                            except Exception:
                                pass
                        if root_total > 0:
                            gb = root_total / (1024 ** 3)
                            sz_str = f"{round(gb / 1024, 1)}T" if gb >= 1024 else f"{round(gb, 1)}G"
                            parsed["disks"] = [{
                                "name": "rootfs",
                                "size": sz_str,
                                "type": "Virtual (LXC)",
                                "model": "Container Allocation",
                                "smart": {
                                    "is_virtual": True,
                                    "health": "healthy",
                                    "status_label": "Virtual (Host)",
                                    "temp_c": None,
                                    "wearout_pct": None,
                                    "wearout_remaining": None,
                                    "reallocated_sectors": None,
                                    "power_on_hours": None,
                                    "device_type": "virtual",
                                    "serial": "",
                                    "firmware": "",
                                    "detail": "Virtual (Host Managed)",
                                },
                            }]
                plat_virt = str(plat.get("virt", "")).upper()
                plat_type = str(plat.get("platform_type", "")).lower()
                plat_vendor = str(plat.get("vendor", "")).upper()
                plat_prod = str(plat.get("product", "")).upper()
                is_node_virt = (
                    plat_type in ("vm", "lxc")
                    or plat_virt in ("KVM", "QEMU", "VMWARE", "XEN", "VIRTUALBOX", "LXC", "CONTAINER")
                    or any(vk in plat_vendor for vk in ("QEMU", "VMWARE", "ORACLE", "XEN"))
                    or any(vk in plat_prod for vk in ("QEMU", "VMWARE", "VIRTUAL"))
                )

                for d in parsed.get("disks", []):
                    if isinstance(d, dict) and "smart" not in d:
                        model_u = str(d.get("model", "")).upper()
                        dtype_u = str(d.get("type", "")).upper()
                        name_u = str(d.get("name", "")).lower()
                        is_disk_virt = (
                            is_node_virt
                            or "LXC" in dtype_u
                            or name_u == "rootfs"
                            or any(vk in model_u for vk in ("QEMU", "VBOX", "VMWARE", "VIRTIO", "XEN", "KVM", "HARDDISK", "VIRTUAL"))
                        )
                        d["smart"] = {
                            "is_virtual": is_disk_virt,
                            "health": "healthy",
                            "status_label": "Virtual (Host)" if is_disk_virt else "PASSED",
                            "temp_c": None,
                            "wearout_pct": None,
                            "wearout_remaining": None,
                            "reallocated_sectors": None,
                            "power_on_hours": None,
                            "device_type": "virtual" if is_disk_virt else "disk",
                            "serial": "",
                            "firmware": "",
                            "detail": "Virtual (Host Managed)" if is_disk_virt else "Normal",
                        }
                if parsed.get("network") and isinstance(parsed["network"].get("interfaces"), list):
                    parsed["network"]["interfaces"] = [
                        it for it in parsed["network"]["interfaces"]
                        if isinstance(it, dict) and it.get("name") not in ("lo", "bonding_masters")
                    ]
                return parsed
        except Exception:
            pass

    has_reported = bool(server.last_seen or latest)
    # Baseline fallback apabila agen belum mengirim hardware_specs (versi lama)
    disks_baseline = []
    if latest and latest.disks:
        try:
            disks_raw = json.loads(latest.disks) if isinstance(latest.disks, str) else latest.disks
            for d in (disks_raw if isinstance(disks_raw, list) else []):
                total_b = d.get("total", 0)
                sz_str = f"{round(total_b / (1024**3), 1)}G" if total_b > 0 else "-"
                disks_baseline.append({
                    "name": d.get("mount", "/"),
                    "size": sz_str,
                    "type": d.get("type", "Disk"),
                    "model": "Storage Partition",
                    "smart": {
                        "is_virtual": True,
                        "health": "healthy",
                        "status_label": "Virtual (Host)",
                        "temp_c": None,
                        "wearout_pct": None,
                        "wearout_remaining": None,
                        "reallocated_sectors": None,
                        "power_on_hours": None,
                        "device_type": "virtual",
                        "serial": "",
                        "firmware": "",
                        "detail": "Virtual (Host Managed)",
                    },
                })
        except Exception:
            pass

    net_interfaces = []
    if latest and latest.net:
        try:
            net_raw = json.loads(latest.net) if isinstance(latest.net, str) else latest.net
            for n in (net_raw if isinstance(net_raw, list) else []):
                net_interfaces.append({
                    "name": n.get("iface", "eth0"),
                    "mac": "-",
                    "speed": ""
                })
        except Exception:
            pass
    if not net_interfaces and has_reported:
        net_interfaces = [{"name": "primary", "mac": "-", "speed": ""}]

    return {
        "cpu": {
            "model": f"Prosesor ({extra.arch if extra and extra.arch else 'x86_64'})" if has_reported else "—",
            "cores": 1 if has_reported else None,
            "arch": extra.arch if extra and extra.arch else ("x86_64" if has_reported else "—"),
            "mhz": "",
            "cache": "",
        },
        "platform": {
            "virt": "Virtual / Host Linux" if has_reported else "Menunggu Laporan Agen",
            "vendor": "-",
            "product": server.hostname,
            "bios_version": "-",
            "bios_date": "-",
            "platform_type": ("lxc" if server.platform_override == "lxc" else ("vm" if server.platform_override == "vm" else ("baremetal" if server.platform_override == "baremetal" else "pending"))) if not has_reported else ("lxc" if server.platform_override == "lxc" else ("vm" if server.platform_override == "vm" else "baremetal")),
            "platform_label": "Menunggu Laporan Agen" if not has_reported and not server.platform_override else ("LXC Container" if server.platform_override == "lxc" else ("Mesin Virtual (VM)" if server.platform_override == "vm" else "Baremetal")),
        },
        "memory": {
            "ram_total": latest.mem_total if latest else 0,
            "swap_total": latest.swap_total if latest else 0,
        },
        "disks": disks_baseline,
        "network": {
            "gateway": "-",
            "dns": [],
            "interfaces": net_interfaces,
        },
        "os": {
            "os_name": extra.os_label if extra and extra.os_label else "Linux",
            "kernel": extra.kernel if extra and extra.kernel else "-",
            "hostname": server.hostname,
            "boot_time": "-",
        }
    }


# ---------------------------------------------------------------------------
# Format pesan insiden yang diabaikan (mencegah redundansi alasan operator)
# ---------------------------------------------------------------------------
def _format_ignored_prob_msg(p: dict) -> str:
    msg = (p.get("message") or "").strip()
    ign = (p.get("ignored_reason") or "").strip()
    if not ign:
        return msg
    msg_l = msg.lower()
    ign_l = ign.lower()
    if ign_l == msg_l or ign_l in msg_l or msg_l in ign_l:
        return msg
    op_phrases = (
        "dimatikan oleh operator",
        "dihentikan oleh operator",
        "di-reboot oleh operator",
        "di-restart oleh operator",
    )
    if any(phrase in ign_l for phrase in op_phrases) and any(phrase in msg_l for phrase in op_phrases):
        return msg
    return f"{msg} ({ign})"


def _format_bytes_compact(b: int | float | None) -> str:
    """Format bita ringkas untuk indikator pertumbuhan laju storage (MB/GB/TB)."""
    if b is None:
        return "—"
    b = float(b)
    if b >= 1024 ** 4:
        return f"{b / (1024 ** 4):.1f} TB"
    if b >= 1024 ** 3:
        return f"{b / (1024 ** 3):.1f} GB"
    if b >= 1024 ** 2:
        return f"{b / (1024 ** 2):.1f} MB"
    if b >= 1024:
        return f"{b / 1024:.0f} KB"
    return f"{int(b)} B"


_storage_runway_cache: dict[int, tuple[float, dict]] = {}


def _get_storage_runway_for_server(db: Session, sid: int, disks: list[dict]) -> list[dict]:
    """Menghitung estimasi laju konsumsi penyimpanan (Runway) berbasis telemetri 24 jam terakhir.
    Murni analitis sekunder pada halaman rincian server (zero dependency, zero client overhead).
    Hasil di-cache in-memory selama 5 menit per server guna menjaga latensi polling 0 ms.
    """
    if not disks:
        return disks
    now_ts = time.time()
    cached = _storage_runway_cache.get(sid)
    runway_map = None
    if cached and (now_ts - cached[0] < 300):
        runway_map = cached[1]
    else:
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
            snap_old = (
                db.query(SystemSnapshot.timestamp, SystemSnapshot.disks)
                .filter(
                    SystemSnapshot.server_id == sid,
                    SystemSnapshot.timestamp >= cutoff,
                    SystemSnapshot.disks.isnot(None),
                )
                .order_by(SystemSnapshot.timestamp.asc())
                .first()
            )
            snap_latest = (
                db.query(SystemSnapshot.timestamp)
                .filter(
                    SystemSnapshot.server_id == sid,
                    SystemSnapshot.disks.isnot(None),
                )
                .order_by(SystemSnapshot.timestamp.desc())
                .first()
            )
            if snap_old and snap_latest:
                dt_hours = (snap_latest.timestamp - snap_old.timestamp).total_seconds() / 3600.0
                if dt_hours >= 0.5:
                    old_disks_list = json.loads(snap_old.disks) if isinstance(snap_old.disks, str) else snap_old.disks
                    old_map = {d.get("mount"): d for d in (old_disks_list or []) if isinstance(d, dict)}
                    runway_map = {}
                    for d in disks:
                        if not isinstance(d, dict):
                            continue
                        mount = d.get("mount")
                        old_d = old_map.get(mount)
                        if not old_d:
                            continue
                        cur_used = d.get("used", 0) or 0
                        old_used = old_d.get("used", 0) or 0
                        cur_tot = d.get("total", 0) or 0
                        cur_avail = max(0, cur_tot - cur_used)
                        growth = cur_used - old_used
                        rate = int((growth / dt_hours) * 24.0)

                        if abs(rate) < 5 * 1024 * 1024:
                            status = "stable"
                            text = "Stabil (0 B/hari)"
                            days = None
                            days_txt = None
                        elif rate <= -5 * 1024 * 1024:
                            status = "shrinking"
                            rate_abs = abs(rate)
                            text = f"Berkurang ({_format_bytes_compact(rate_abs)}/hari)"
                            days = None
                            days_txt = None
                        else:
                            days = cur_avail / rate if rate > 0 else 9999
                            days_int = int(days)
                            if days_int <= 0:
                                days_txt = "< 1 Hari"
                                status = "danger"
                            elif days_int < 7:
                                days_txt = f"~{days_int} Hari"
                                status = "danger"
                            elif days_int <= 30:
                                days_txt = f"~{days_int} Hari"
                                status = "warning"
                            elif days_int <= 90:
                                days_txt = f"~{days_int} Hari"
                                status = "normal"
                            else:
                                days_txt = "> 90 Hari"
                                status = "normal"
                            text = f"+{_format_bytes_compact(rate)}/hari · Est. {days_txt}"

                        runway_map[mount] = {
                            "status": status,
                            "rate_bytes_day": rate,
                            "days": round(days, 1) if days is not None else None,
                            "days_text": days_txt,
                            "text": text,
                        }
                    _storage_runway_cache[sid] = (now_ts, runway_map)
        except Exception as e:
            logger.debug("Gagal menghitung storage runway server %s: %s", sid, e)

    if runway_map:
        for d in disks:
            if isinstance(d, dict):
                mount = d.get("mount")
                if mount in runway_map:
                    d["runway"] = runway_map[mount]

    return disks


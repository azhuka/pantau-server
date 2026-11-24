#!/usr/bin/env python3
"""Uji Otomatis Zero-Knowledge Master Admin & Penegakan RBAC 3-Tier (v0.1.46)."""

import os
import sys
import unittest

sys.path.insert(0, "/home/bos/pantau-server/server")
os.environ["PYTHONPATH"] = "/home/bos/pantau-server/server"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from main import app
from core.database import get_db, Base
from core.security import create_access_token, get_password_hash
from models.user import User
from models.misc import AuditLog

client = TestClient(app)
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestZeroKnowledgeAndRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()

        # Pastikan master-admin ada
        cls.master = cls.db.query(User).filter(User.username == "master-admin").first()
        if not cls.master:
            cls.master = User(
                username="master-admin",
                password_hash=get_password_hash("MasterAdmin@123"),
                role="master_admin",
                is_active=1
            )
            cls.db.add(cls.master)
            cls.db.commit()
            cls.db.refresh(cls.master)

        # Buat operator uji coba (operator_test_sadri)
        cls.operator = cls.db.query(User).filter(User.username == "op_test_zk").first()
        if not cls.operator:
            cls.operator = User(
                username="op_test_zk",
                password_hash=get_password_hash("OperatorPass@123"),
                role="operator",
                is_active=1,
                permissions='{"can_manage_users": true, "can_audit": true}'
            )
            cls.db.add(cls.operator)
            cls.db.commit()
            cls.db.refresh(cls.operator)
        else:
            cls.operator.permissions = '{"can_manage_users": true, "can_audit": true}'
            cls.db.commit()

        # Buat operator kedua untuk uji target
        cls.operator2 = cls.db.query(User).filter(User.username == "op_target_zk").first()
        if not cls.operator2:
            cls.operator2 = User(
                username="op_target_zk",
                password_hash=get_password_hash("OperatorTarget@123"),
                role="operator",
                is_active=1,
                permissions='{"can_terminal": true}'
            )
            cls.db.add(cls.operator2)
            cls.db.commit()
            cls.db.refresh(cls.operator2)

        # Buat viewer uji coba
        cls.viewer = cls.db.query(User).filter(User.username == "vw_test_zk").first()
        if not cls.viewer:
            cls.viewer = User(
                username="vw_test_zk",
                password_hash=get_password_hash("ViewerPass@123"),
                role="viewer",
                is_active=1
            )
            cls.db.add(cls.viewer)
            cls.db.commit()
            cls.db.refresh(cls.viewer)

        # Buat audit log dari master admin untuk uji masking
        audit_entry = cls.db.query(AuditLog).filter(AuditLog.username == cls.master.username).first()
        if not audit_entry:
            cls.db.add(AuditLog(
                user_id=cls.master.id,
                username=cls.master.username,
                action="system_config",
                target=f"Configured by {cls.master.username} (master_admin)",
                result="SUCCESS",
                server_name="system"
            ))
            cls.db.commit()

        cls.master_token = create_access_token({"sub": cls.master.username, "role": cls.master.role, "uid": cls.master.id})
        cls.operator_token = create_access_token({"sub": cls.operator.username, "role": cls.operator.role, "uid": cls.operator.id})
        cls.viewer_token = create_access_token({"sub": cls.viewer.username, "role": cls.viewer.role, "uid": cls.viewer.id})

    @classmethod
    def tearDownClass(cls):
        # Bersihkan user testing
        cls.db.query(User).filter(User.username.in_(["op_test_zk", "op_target_zk", "vw_test_zk"])).delete(synchronize_session=False)
        cls.db.commit()
        cls.db.close()

    def test_01_operator_cannot_see_master_admin_in_list(self):
        """1. Operator di GET /api/users TIDAK BOLEH melihat akun master_admin sama sekali."""
        res = client.get("/api/users", headers={"Authorization": f"Bearer {self.operator_token}"})
        self.assertEqual(res.status_code, 200)
        users = res.json()
        roles = [u["role"] for u in users]
        usernames = [u["username"] for u in users]

        self.assertNotIn("master_admin", roles)
        self.assertNotIn("master-admin", roles)
        self.assertNotIn(self.master.username, usernames)
        print(f"[PASS] Operator list_users disaring bersih: {len(users)} users, 0 master_admin.")

    def test_02_master_admin_sees_all_users_in_list(self):
        """2. Master Admin di GET /api/users melihat seluruh akun termasuk dirinya sendiri."""
        res = client.get("/api/users", headers={"Authorization": f"Bearer {self.master_token}"})
        self.assertEqual(res.status_code, 200)
        usernames = [u["username"] for u in res.json()]
        self.assertIn(self.master.username, usernames)
        print(f"[PASS] Master Admin list_users melihat seluruh {len(usernames)} akun.")

    def test_03_zero_knowledge_stealth_returns_404_on_master_admin_probe(self):
        """3. Operator mencoba menyentuh ID Master Admin -> Wajib netral 404 Not Found (Anti-Enumeration)."""
        # A. Update User
        res_put = client.put(
            f"/api/users/{self.master.id}",
            json={"username": "hacked-master"},
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res_put.status_code, 404, f"Harus 404, got {res_put.status_code}")

        # B. Status Toggle
        res_status = client.put(
            f"/api/users/{self.master.id}/status",
            json={"is_active": 0},
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res_status.status_code, 404, f"Harus 404, got {res_status.status_code}")

        # C. Reset Password
        res_reset = client.put(
            f"/api/users/{self.master.id}/reset-password",
            json={"new_password": "HackedPassword@123"},
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res_reset.status_code, 404, f"Harus 404, got {res_reset.status_code}")

        # D. Delete User
        res_del = client.delete(
            f"/api/users/{self.master.id}",
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res_del.status_code, 404, f"Harus 404, got {res_del.status_code}")

        print("[PASS] Seluruh probe operator ke ID Master Admin berhasil disilumankan dengan respons 404 Not Found.")

    def test_04_operator_cannot_edit_permissions_of_other_operators(self):
        """4. Operator DILARANG KERAS mengedit matriks permissions operator lain (Hanya Master Admin)."""
        res = client.put(
            f"/api/users/{self.operator2.id}",
            json={"permissions": {"can_terminal": True, "can_firewall": True}},
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res.status_code, 403, f"Harus 403 Forbidden, got {res.status_code}")
        print("[PASS] Operator ditolak saat mencoba mengedit wewenang operator lain (403 Forbidden).")

    def test_05_operator_cannot_promote_to_master_admin(self):
        """5. Operator DILARANG mempromosikan user mana pun menjadi master_admin."""
        res = client.put(
            f"/api/users/{self.operator2.id}",
            json={"role": "master_admin"},
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res.status_code, 400)
        print("[PASS] Upaya promosi akun ke master_admin berhasil digagalkan (400 Bad Request).")

    def test_06_operator_cannot_delete_or_deactivate_self(self):
        """6. Operator DILARANG menghapus atau menonaktifkan akun dirinya sendiri."""
        # A. Delete Self
        res_del = client.delete(
            f"/api/users/{self.operator.id}",
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res_del.status_code, 400)

        # B. Toggle Self
        res_toggle = client.put(
            f"/api/users/{self.operator.id}/status",
            json={"is_active": 0},
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res_toggle.status_code, 400)
        print("[PASS] Proteksi integritas diri operator terbukti aktif (dilarang hapus/lock diri sendiri).")

    def test_07_audit_trail_masks_master_admin_to_sistem_for_operator(self):
        """7. Pada Audit Trail, aktivitas Master Admin disamarkan otomatis sebagai 'Sistem'."""
        res = client.get("/api/audit", headers={"Authorization": f"Bearer {self.operator_token}"})
        self.assertEqual(res.status_code, 200)
        logs = res.json()

        for log in logs:
            self.assertNotEqual(log["username"], self.master.username, "Username master-admin bocor di audit!")
            self.assertNotIn(self.master.username, log["target"], "Nama master-admin bocor di target audit!")

        # Uji filter explicit pencarian master-admin -> Wajib mengembalikan list kosong
        res_filtered = client.get(
            f"/api/audit?user={self.master.username}",
            headers={"Authorization": f"Bearer {self.operator_token}"}
        )
        self.assertEqual(res_filtered.status_code, 200)
        self.assertEqual(len(res_filtered.json()), 0, "Filter user master-admin harus mengembalikan list kosong")
        print("[PASS] Audit trail berhasil menyamarkan identitas Master Admin menjadi 'Sistem'.")

    def test_08_viewer_isolation_blocks_all_mutations_and_management(self):
        """8. Akun Viewer diisolasi total: Dilarang akses user management, audit, dan self-credentials."""
        # A. List users
        res_list = client.get("/api/users", headers={"Authorization": f"Bearer {self.viewer_token}"})
        self.assertEqual(res_list.status_code, 403)

        # B. Self-change password
        res_pwd = client.put(
            "/api/users/me/password",
            json={"current_password": "ViewerPass@123", "new_password": "NewPass@12345"},
            headers={"Authorization": f"Bearer {self.viewer_token}"}
        )
        self.assertEqual(res_pwd.status_code, 403)

        # C. 2FA Setup
        res_2fa = client.post("/api/users/2fa/init", headers={"Authorization": f"Bearer {self.viewer_token}"})
        self.assertEqual(res_2fa.status_code, 403)

        # D. Audit Trail
        res_audit = client.get("/api/audit", headers={"Authorization": f"Bearer {self.viewer_token}"})
        self.assertEqual(res_audit.status_code, 403)

        print("[PASS] Akun Viewer terisolasi mutlak (seluruh akses manajemen dan mutasi ditolak 403).")


if __name__ == "__main__":
    unittest.main(verbosity=2)

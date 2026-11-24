#!/usr/bin/env python3
"""
Test Suite: Full-Stack RBAC Hardening & Scope Isolation Verification
Validates that:
1. /api/auth/me returns permissions dict and allowed_server_ids list.
2. /api/servers strictly filters results by user.can_access_server(s.id).
3. Sub-resource inspection endpoints (/services, /processes, /firewall, /cron, /packages, /ssl, etc.)
   strictly enforce scope (HTTP 403 if server not allowed) and granular permissions (HTTP 403 if permission missing).
4. Terminal exec and server control actions strictly enforce scope and permissions.
"""

import sys
import os
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath("server"))
from core.security import create_access_token
from core.database import SessionLocal
from models.user import User

BASE_URL = "http://127.0.0.1:8401"

def http_req(path, method="GET", body=None, token=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"detail": raw}
        return e.code, parsed

def main():
    print("=== [1] Generating Master Admin Token ===")
    db = SessionLocal()
    admin_user = db.query(User).filter(User.role == "master_admin").first()
    assert admin_user, "No master_admin found in database"
    admin_token = create_access_token(data={"sub": admin_user.username, "role": admin_user.role, "uid": admin_user.id})
    db.close()
    print(f"Master admin token generated for {admin_user.username} (id={admin_user.id})")

    print("\n=== [2] Checking Admin Profile Envelope (/api/auth/me) ===")
    status, me = http_req("/api/auth/me", token=admin_token)
    assert status == 200, f"Failed /api/auth/me: {me}"
    assert "permissions" in me, "me endpoint missing 'permissions'"
    assert "allowed_server_ids" in me, "me endpoint missing 'allowed_server_ids'"
    assert me["is_master_admin"] is True, "Admin is_master_admin should be True"
    print(f"Admin /api/auth/me OK: {me['username']} (permissions count: {len(me['permissions'])})")

    print("\n=== [3] Creating Restricted Operator (test_scoped_op) ===")
    scoped_user = "test_scoped_op"
    scoped_pass = "ScopedPass123!"

    # Clean up if existing
    status, users_res = http_req("/api/users", token=admin_token)
    if status == 200:
        user_list = users_res if isinstance(users_res, list) else users_res.get("users", [])
        for u in user_list:
            if u["username"] == scoped_user:
                http_req(f"/api/users/{u['id']}", method="DELETE", token=admin_token)
                print(f"Cleaned up pre-existing user {scoped_user}")

    create_payload = {
        "username": scoped_user,
        "password": scoped_pass,
        "role": "operator",
        "allowed_server_ids": [1],
        "permissions": {
            "can_services": True,
            "can_processes": False,
            "can_firewall": False,
            "can_terminal": False,
            "can_server_control": False,
            "can_manage_servers": False,
            "can_apt": False
        }
    }
    status, created_res = http_req("/api/users", method="POST", body=create_payload, token=admin_token)
    assert status == 200, f"Failed creating restricted operator: {created_res}"
    created_id = created_res.get("id") or created_res.get("user", {}).get("id")
    print(f"Created {scoped_user} (id={created_id}) with allowed_server_ids=[1], can_services=True, others=False")

    print("\n=== [4] Logging in as Restricted Operator ===")
    status, scoped_data = http_req("/api/auth/login", method="POST", body={"username": scoped_user, "password": scoped_pass})
    assert status == 200, f"Login failed for {scoped_user}: {scoped_data}"
    scoped_token = scoped_data["access_token"]
    print(f"Restricted operator login OK: permissions={scoped_data['user'].get('permissions')}, allowed_server_ids={scoped_data['user'].get('allowed_server_ids')}")

    print("\n=== [5] Testing Server Inventory Scoping (/api/servers) ===")
    status, servers_res = http_req("/api/servers", token=scoped_token)
    assert status == 200, f"Failed /api/servers: {servers_res}"
    servers = servers_res.get("servers", [])
    server_ids = [s["id"] for s in servers]
    print(f"Servers visible to restricted operator: {server_ids}")
    assert server_ids == [1], f"Expected only server [1], but got {server_ids}"
    print("[PASS] Inventory scoping verified: Only server 1 visible to scoped user.")

    print("\n=== [6] Testing Sub-Resource Granular Permissions on Allowed Server (id=1) ===")
    # 6a. GET /api/servers/1/services -> Should SUCCEED (can_services=True)
    status, resp = http_req("/api/servers/1/services", token=scoped_token)
    assert status == 200, f"Expected 200 for services on allowed server, got {status}: {resp}"
    print("[PASS] GET /api/servers/1/services -> 200 OK (Allowed)")

    # 6b. GET /api/servers/1/processes -> Should FAIL 403 (can_processes=False)
    status, resp = http_req("/api/servers/1/processes", token=scoped_token)
    assert status == 403, f"Expected 403 for processes (lacks can_processes), got {status}: {resp}"
    print(f"[PASS] GET /api/servers/1/processes -> 403 Forbidden ({resp.get('detail')})")

    # 6c. GET /api/servers/1/firewall -> Should FAIL 403 (can_firewall=False)
    status, resp = http_req("/api/servers/1/firewall", token=scoped_token)
    assert status == 403, f"Expected 403 for firewall (lacks can_firewall), got {status}: {resp}"
    print(f"[PASS] GET /api/servers/1/firewall -> 403 Forbidden ({resp.get('detail')})")

    # 6d. POST /api/servers/1/terminal/exec -> Should FAIL 403 (can_terminal=False)
    status, resp = http_req("/api/servers/1/terminal/exec", method="POST", body={"cmd": "whoami"}, token=scoped_token)
    assert status == 403, f"Expected 403 for terminal exec (lacks can_terminal), got {status}: {resp}"
    print(f"[PASS] POST /api/servers/1/terminal/exec -> 403 Forbidden ({resp.get('detail')})")

    # 6e. POST /api/servers/1/maintenance -> Should FAIL 403 (can_manage_servers=False)
    status, resp = http_req("/api/servers/1/maintenance", method="POST", body={"action": "toggle"}, token=scoped_token)
    assert status == 403, f"Expected 403 for maintenance (lacks permission), got {status}: {resp}"
    print(f"[PASS] POST /api/servers/1/maintenance -> 403 Forbidden ({resp.get('detail')})")

    print("\n=== [7] Testing Scope Enforcement on Forbidden Server (id=7) ===")
    # 7a. GET /api/servers/7 -> Should FAIL 403
    status, resp = http_req("/api/servers/7", token=scoped_token)
    assert status == 403, f"Expected 403 for detail on server 7, got {status}"
    print(f"[PASS] GET /api/servers/7 -> 403 Forbidden ({resp.get('detail')})")

    # 7b. GET /api/servers/7/services -> Should FAIL 403 (even though can_services=True, server 7 is forbidden)
    status, resp = http_req("/api/servers/7/services", token=scoped_token)
    assert status == 403, f"Expected 403 for services on forbidden server 7, got {status}"
    print(f"[PASS] GET /api/servers/7/services -> 403 Forbidden ({resp.get('detail')})")

    # 7c. GET /api/servers/7/ports -> Should FAIL 403
    status, resp = http_req("/api/servers/7/ports", token=scoped_token)
    assert status == 403, f"Expected 403 for ports on forbidden server 7, got {status}"
    print(f"[PASS] GET /api/servers/7/ports -> 403 Forbidden ({resp.get('detail')})")

    # 7d. POST /api/servers/7/actions -> Should FAIL 403
    status, resp = http_req("/api/servers/7/actions", method="POST", body={"action": "restart_service", "params": {"service": "nginx"}}, token=scoped_token)
    assert status == 403, f"Expected 403 for action on forbidden server 7, got {status}"
    print(f"[PASS] POST /api/servers/7/actions -> 403 Forbidden ({resp.get('detail')})")

    # 7e. PUT /api/servers/7 -> Should FAIL 403
    status, resp = http_req("/api/servers/7", method="PUT", body={"notes": "Hacked"}, token=scoped_token)
    assert status == 403, f"Expected 403 for update on forbidden server 7, got {status}"
    print(f"[PASS] PUT /api/servers/7 -> 403 Forbidden ({resp.get('detail')})")

    # 7f. DELETE /api/servers/7 -> Should FAIL 403
    status, resp = http_req("/api/servers/7", method="DELETE", token=scoped_token)
    assert status == 403, f"Expected 403 for delete on forbidden server 7, got {status}"
    print(f"[PASS] DELETE /api/servers/7 -> 403 Forbidden ({resp.get('detail')})")

    print("\n=== [8] Cleaning Up Test User ===")
    status, resp = http_req(f"/api/users/{created_id}", method="DELETE", token=admin_token)
    assert status == 200, f"Failed cleanup: {resp}"
    print(f"Cleaned up {scoped_user} successfully.")

    print("\n=======================================================")
    print(">>> ALL 12 RBAC & SCOPE HARDENING TESTS PASSED 100%! <<<")
    print("=======================================================")

if __name__ == "__main__":
    main()

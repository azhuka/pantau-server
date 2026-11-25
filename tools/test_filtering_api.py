#!/usr/bin/env python3
"""API verification suite for v0.1.63 Blueprint Unified Filtering & Telemetry Contracts."""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/home/bos/pantau-server/server")
from core.database import SessionLocal
from core.security import create_access_token
from models.user import User

BASE_URL = "http://127.0.0.1:8401"


def get_token(username: str) -> str:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        assert u is not None, f"User {username} not found in DB"
        return create_access_token({"sub": u.username, "role": u.role, "uid": u.id})
    finally:
        db.close()


def api_get(path: str, token: str):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return res.status, json.loads(res.read().decode("utf-8"))


def main():
    admin_tok = get_token("master-admin")

    # Find an operator account to test Zero-Knowledge Master Admin masking
    db = SessionLocal()
    try:
        op_user = db.query(User).filter(User.role == "operator").first()
        op_name = op_user.username if op_user else None
    finally:
        db.close()

    # 1. Audit Metadata & Zero-Knowledge Masking
    st, meta = api_get("/api/audit/meta", admin_tok)
    assert st == 200 and "categories" in meta and "users" in meta and "servers" in meta, f"Bad audit meta: {meta}"
    cat_ids = {c["id"] for c in meta["categories"]}
    assert {"cat:auth", "cat:service", "cat:firewall", "cat:server"}.issubset(cat_ids), f"Missing categories: {cat_ids}"
    print(f"[PASS] /api/audit/meta: {len(meta['categories'])} categories, {len(meta['users'])} users, {len(meta['servers'])} servers")

    if op_name:
        op_tok = get_token(op_name)
        _, op_meta = api_get("/api/audit/meta", op_tok)
        assert "master-admin" not in op_meta["users"], f"Leak! master-admin exposed to operator {op_name}"
        _, op_logs = api_get("/api/audit?period=all&limit=100", op_tok)
        assert all(r["username"] != "master-admin" for r in op_logs), "Leak! master-admin username visible in audit logs"
        print(f"[PASS] Zero-Knowledge Master Admin masking verified for operator {op_name}")

    # 2. Audit Multi-Criteria Filtering
    _, logs_all = api_get("/api/audit?period=all&limit=100", admin_tok)
    assert isinstance(logs_all, list)
    _, logs_cat = api_get("/api/audit?period=all&action=cat:server&status=SUCCESS&limit=100", admin_tok)
    assert isinstance(logs_cat, list) and all(r["result"] == "SUCCESS" for r in logs_cat)
    _, logs_date = api_get("/api/audit?period=custom&start_date=2026-11-24&end_date=2026-11-25&limit=100", admin_tok)
    assert isinstance(logs_date, list)
    print(f"[PASS] /api/audit multi-filter queries OK (all={len(logs_all)}, cat:server={len(logs_cat)}, date={len(logs_date)})")

    # 3. Problems Enrichment (res_type, component, empty ungrouped)
    _, prob_res = api_get("/api/problems?active_only=false&period=30d&limit=50", admin_tok)
    assert prob_res["ok"]
    if prob_res["problems"]:
        sample = prob_res["problems"][0]
        assert "res_type" in sample and "component" in sample, f"Missing enrichment on resolved problem: {sample}"
    _, prob_ungrp = api_get("/api/problems?active_only=true&group_name=__none__", admin_tok)
    assert prob_ungrp["ok"] and all((p["group_name"] or "") == "" for p in prob_ungrp["problems"])
    print(f"[PASS] /api/problems enriched with component & res_type; ungrouped filter verified ({len(prob_ungrp['problems'])} active ungrouped)")

    # 4. Servers, Services (boot), Ports (is_public), Packages (installed+upgradable), Logs (available_logs)
    _, srv_res = api_get("/api/servers", admin_tok)
    assert srv_res["ok"] and len(srv_res["servers"]) >= 1
    first_srv = srv_res["servers"][0]
    assert "tags" in first_srv and "group_name" in first_srv
    assert any((s["group_name"] or "") == "" for s in srv_res["servers"]), "Ungrouped servers must have empty group_name"
    sid = first_srv["id"]

    _, svc_res = api_get(f"/api/servers/{sid}/services", admin_tok)
    assert svc_res["ok"] and len(svc_res["services"]) > 0 and "boot" in svc_res["services"][0], "Services must include boot field"

    _, port_res = api_get(f"/api/servers/{sid}/ports", admin_tok)
    assert port_res["ok"] and len(port_res["ports"]) > 0
    loopback_ports = [p for p in port_res["ports"] if str(p.get("ip", "")).startswith("127.")]
    assert all(not p["is_public"] for p in loopback_ports), f"Loopback ports misclassified as public: {loopback_ports}"

    _, pkg_res = api_get(f"/api/servers/{sid}/packages", admin_tok)
    assert pkg_res["ok"] and len(pkg_res["packages"]) > 50, f"Expected full package inventory, got {len(pkg_res['packages'])}"

    _, log_res = api_get(f"/api/servers/{sid}/logs", admin_tok)
    assert log_res["ok"] and len(log_res.get("available_logs", [])) >= 4, "Missing available_logs in /logs endpoint"

    print(
        f"[PASS] Telemetry filter fields verified on host #{sid}: "
        f"services={len(svc_res['services'])} (boot OK), "
        f"ports={len(port_res['ports'])} (loopback accuracy OK), "
        f"packages={len(pkg_res['packages'])}, "
        f"log_sources={len(log_res['available_logs'])}"
    )
    print("\n=== ALL BACKEND FILTERING API CHECKS PASSED! ===")


if __name__ == "__main__":
    main()

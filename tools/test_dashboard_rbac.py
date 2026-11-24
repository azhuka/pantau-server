import sys
import os
import json
import urllib.request
import urllib.error

sys.path.insert(0, '/home/bos/pantau-server/server')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings
from models.user import User
from models.problem import ServerProblem
from routers.auth import create_access_token

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
db = Session()

admin_token = create_access_token({"sub": "master-admin", "role": "master_admin"})
op_token = create_access_token({"sub": "op-sadri", "role": "operator"})
guest_token = create_access_token({"sub": "guest", "role": "viewer"})
scoped_token = create_access_token({"sub": "test", "role": "operator"})

BASE_URL = "http://127.0.0.1:8401/api"

def api_call(endpoint, method="GET", token=None, body=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = None
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            pass
        return e.code, err_body

print("--- 1. Testing GET /api/problems ---")
status, res_admin = api_call("/problems", token=admin_token)
print(f"Admin problems status={status}, count={len(res_admin.get('problems', []))}")
assert status == 200

status, res_guest = api_call("/problems", token=guest_token)
print(f"Guest problems status={status}, count={len(res_guest.get('problems', []))}")
assert status == 200

status, res_scoped = api_call("/problems", token=scoped_token)
print(f"Scoped operator problems status={status}, count={len(res_scoped.get('problems', []))}")
assert status == 200

# Get an active problem
active_prob = db.query(ServerProblem).filter(ServerProblem.resolved_at == None).first()
if not active_prob:
    active_prob = ServerProblem(
        server_id=1,
        key="test_incident:dummy",
        severity="warning",
        message="Test Incident for RBAC Audit",
        tip="Verify RBAC test"
    )
    db.add(active_prob)
    db.commit()
    db.refresh(active_prob)

pid = active_prob.id
print(f"\n--- 2. Testing POST /api/problems/{pid}/ignore for Viewer vs Admin ---")
# Viewer attempt -> MUST BE 403
status, res_guest_ignore = api_call(f"/problems/{pid}/ignore", method="POST", token=guest_token, body={"duration": "2h", "reason": "test"})
print(f"Viewer ignore status: {status} (Expected 403) -> {res_guest_ignore}")
assert status == 403

# Scoped operator on server 1 (outside scope) -> MUST BE 403
status, res_scoped_ignore = api_call(f"/problems/{pid}/ignore", method="POST", token=scoped_token, body={"duration": "2h", "reason": "test"})
print(f"Scoped operator (outside scope) ignore status: {status} (Expected 403) -> {res_scoped_ignore}")
assert status == 403

print(f"\n--- 3. Testing POST /api/problems/{pid}/terminate-ssh for Viewer ---")
# Viewer attempt terminate-ssh -> MUST BE 403
status, res_guest_term = api_call(f"/problems/{pid}/terminate-ssh", method="POST", token=guest_token)
print(f"Viewer terminate-ssh status: {status} (Expected 403) -> {res_guest_term}")
assert status == 403

print(f"\n--- 4. Testing POST /api/problems/{pid}/unignore for Viewer ---")
status, res_guest_unign = api_call(f"/problems/{pid}/unignore", method="POST", token=guest_token)
print(f"Viewer unignore status: {status} (Expected 403) -> {res_guest_unign}")
assert status == 403

print("\nALL RBAC API CHECKS PASSED PERFECTLY!")

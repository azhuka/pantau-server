import sys
sys.path.insert(0, '/home/bos/pantau-server/server')

from core.database import SessionLocal
from models.user import User
from models.problem import ServerProblem
from core.security import create_access_token
import urllib.request
import json

db = SessionLocal()
u = db.query(User).filter(User.username == 'master-admin').first()
token = create_access_token({'sub': u.username, 'role': u.role, 'uid': u.id})
db.close()

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

def get_json(url):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def post_json(url, data=None):
    payload = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

print("[1] Testing GET /api/problems (active_only=True)...")
res_active = get_json('http://127.0.0.1:8401/api/problems?active_only=true')
print(f"  -> Active problems count: {len(res_active.get('problems', []))}")
assert res_active.get('ok') is True

print("[2] Testing GET /api/problems/stats...")
res_stats = get_json('http://127.0.0.1:8401/api/problems/stats')
print(f"  -> Stats: active={res_stats.get('active')}, resolved={res_stats.get('resolved')}")
assert res_stats.get('ok') is True
assert 'avg_mttr_formatted' in res_stats.get('resolved', {})

print("[3] Testing GET /api/problems/thresholds...")
res_th = get_json('http://127.0.0.1:8401/api/problems/thresholds')
print(f"  -> Thresholds: cpu_danger={res_th.get('thresholds', {}).get('cpu_danger')}")
assert res_th.get('ok') is True

print("[4] Testing GET /api/problems (active_only=False)...")
res_resolved = get_json('http://127.0.0.1:8401/api/problems?active_only=false&limit=10')
print(f"  -> Resolved problems sample: {len(res_resolved.get('problems', []))}")
assert res_resolved.get('ok') is True

# If there's an active problem, test ack
if res_active.get('problems'):
    p0 = res_active['problems'][0]
    pid = p0['id']
    print(f"[5] Testing POST /api/problems/{pid}/ack...")
    res_ack = post_json(f'http://127.0.0.1:8401/api/problems/{pid}/ack')
    print(f"  -> Ack result: {res_ack}")
    assert res_ack.get('ok') is True
    assert res_ack.get('acknowledged_by') == 'master-admin'

print("[OK] All Problem API endpoints passed successfully 100%!")

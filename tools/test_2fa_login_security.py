import sys
import os
import json
sys.path.insert(0, '/home/bos/pantau-server/server')

from config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.user import User
import security_auth
from core.security import get_password_hash, create_access_token

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
db = Session()

# 1. Test user setup
test_user = db.query(User).filter(User.username == 'test_2fa_user').first()
if not test_user:
    test_user = User(
        username='test_2fa_user',
        password_hash=get_password_hash('Password123!'),
        role='operator',
        is_active=1
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)

print("[1] Testing Login without 2FA...")
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)

# Login step 1 without 2FA
test_user.totp_enabled = 0
test_user.totp_secret = None
test_user.recovery_codes = None
db.commit()

resp = client.post("/api/auth/login", json={"username": "test_2fa_user", "password": "Password123!"})
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
data = resp.json()
assert not data.get("requires_2fa"), "Expected requires_2fa to be False"
assert data.get("access_token"), "Expected access_token"
print("  -> Passed: Direct token issue when 2FA disabled.")

# 2. Enable 2FA on test user
print("[2] Enabling 2FA on user...")
raw_secret = security_auth.generate_totp_secret()
plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
test_user.totp_secret = raw_secret
test_user.totp_enabled = 1
test_user.recovery_codes = json.dumps(hashed_codes)
db.commit()

# Login step 1 with 2FA
resp = client.post("/api/auth/login", json={"username": "test_2fa_user", "password": "Password123!"})
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
data = resp.json()
assert data.get("requires_2fa") == True, "Expected requires_2fa to be True"
assert data.get("preauth_token"), "Expected preauth_token"
assert not data.get("access_token"), "Must NOT issue access_token on step 1"
preauth_token = data["preauth_token"]
print("  -> Passed: Step 1 requires 2FA and returns preauth_token without access_token.")

# 3. Test Invalid TOTP code
print("[3] Testing Invalid 2FA Code...")
resp = client.post("/api/auth/login-2fa", json={"preauth_token": preauth_token, "code": "000000"})
assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
print("  -> Passed: Invalid code rejected.")

# 4. Test Valid TOTP Code
print("[4] Testing Valid TOTP Code...")
valid_totp = security_auth.compute_totp(raw_secret)
resp = client.post("/api/auth/login-2fa", json={"preauth_token": preauth_token, "code": valid_totp})
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
data = resp.json()
assert data.get("access_token"), "Expected access_token on successful 2FA"
assert data["user"]["username"] == "test_2fa_user"
print("  -> Passed: Valid TOTP grants access token.")

# 5. Test Recovery Code
print("[5] Testing Emergency Recovery Code...")
# Generate new preauth_token
resp = client.post("/api/auth/login", json={"username": "test_2fa_user", "password": "Password123!"})
preauth_token_rec = resp.json()["preauth_token"]
recovery_code_to_use = plain_codes[0]

resp = client.post("/api/auth/login-2fa", json={"preauth_token": preauth_token_rec, "code": recovery_code_to_use})
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
print("  -> Passed: Recovery code grants access token.")

# Verify code was consumed
db.refresh(test_user)
next_hashes = json.loads(test_user.recovery_codes)
assert len(next_hashes) == 7, f"Expected 7 recovery codes remaining, got {len(next_hashes)}"
print("  -> Passed: Recovery code consumed (7 remaining).")

# Cleanup test user
db.delete(test_user)
db.commit()
db.close()

print("\nALL 2FA LOGIN PIPELINE TESTS PASSED 100%!")

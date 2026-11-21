import os
import sys
import json
import urllib.request
import urllib.error

# Add server directory to path to generate valid admin token directly
sys.path.insert(0, "/home/bos/pantau-server/server")
from core.security import create_access_token

BASE_URL = "http://127.0.0.1:8401"

def make_req(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read()
            return response.status, res_body
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def test_file_manager_lifecycle():
    print("[1] Generating valid admin token...")
    token = create_access_token({"sub": "master-admin"})
    print("-> Token acquired successfully.")

    # 1. List /tmp
    print("\n[2] Testing GET /api/servers/1/files?path=/tmp ...")
    status, body = make_req("/api/servers/1/files?path=/tmp", method="GET", token=token)
    assert status == 200, f"List failed ({status}): {body.decode('utf-8')}"
    data = json.loads(body.decode("utf-8"))
    assert data.get("ok") is True
    print(f"-> Directory listing successful. Found {len(data.get('items', []))} items in /tmp.")

    # 2. Touch new file /tmp/pantau_test_fm.txt
    test_file_path = "/tmp/pantau_test_fm.txt"
    if os.path.exists(test_file_path):
        os.remove(test_file_path)
    if os.path.exists(test_file_path + ".bak"):
        os.remove(test_file_path + ".bak")

    print(f"\n[3] Testing POST /api/servers/1/files/touch ({test_file_path}) ...")
    status, body = make_req("/api/servers/1/files/touch", method="POST", data={"path": test_file_path}, token=token)
    assert status == 200, f"Touch failed ({status}): {body.decode('utf-8')}"
    assert os.path.exists(test_file_path), "File does not exist on disk after touch!"
    print(f"-> File touch verified. File created physically on disk.")

    # 3. Save / edit content with make_backup=True
    print(f"\n[4] Testing POST /api/servers/1/files/save (with auto .bak) ...")
    init_content = "Hello from Pantau Server v0.1.6 Remote File Manager!"
    status, body = make_req("/api/servers/1/files/save", method="POST", data={
        "path": test_file_path,
        "content": init_content,
        "make_backup": True
    }, token=token)
    assert status == 200, f"Save initial failed ({status}): {body.decode('utf-8')}"

    # Now edit again to trigger backup
    updated_content = "Hello from Pantau Server v0.1.6 Remote File Manager! (Updated Version)"
    status, body = make_req("/api/servers/1/files/save", method="POST", data={
        "path": test_file_path,
        "content": updated_content,
        "make_backup": True
    }, token=token)
    assert status == 200, f"Save update failed ({status}): {body.decode('utf-8')}"
    assert os.path.exists(test_file_path + ".bak"), "Backup .bak was not created on edit!"
    with open(test_file_path + ".bak", "r") as f:
        bak_content = f.read()
    assert bak_content == init_content, "Backup content mismatch!"
    print(f"-> Auto .bak backup successfully verified! Backup content matches original state.")

    # 4. Download file
    print(f"\n[5] Testing GET /api/servers/1/files/download ...")
    status, body = make_req(f"/api/servers/1/files/download?path={test_file_path}", method="GET", token=token)
    assert status == 200, f"Download failed ({status}): {body.decode('utf-8')}"
    assert body.decode("utf-8") == updated_content, "Downloaded content mismatch!"
    print(f"-> Download verified via FileResponse. Content size: {len(body)} bytes.")

    # 5. Mkdir /tmp/pantau_test_dir
    test_dir_path = "/tmp/pantau_test_dir"
    if os.path.exists(test_dir_path):
        import shutil
        shutil.rmtree(test_dir_path)

    print(f"\n[6] Testing POST /api/servers/1/files/mkdir ({test_dir_path}) ...")
    status, body = make_req("/api/servers/1/files/mkdir", method="POST", data={"path": test_dir_path}, token=token)
    assert status == 200, f"Mkdir failed ({status}): {body.decode('utf-8')}"
    assert os.path.isdir(test_dir_path), "Directory does not exist on disk after mkdir!"
    print(f"-> Directory mkdir verified.")

    # 6. Rm file and rm dir
    print(f"\n[7] Testing POST /api/servers/1/files/rm (file & directory) ...")
    status, body = make_req("/api/servers/1/files/rm", method="POST", data={"path": test_file_path}, token=token)
    assert status == 200, f"Rm file failed ({status}): {body.decode('utf-8')}"
    assert not os.path.exists(test_file_path), "File still exists after rm!"

    status, body = make_req("/api/servers/1/files/rm", method="POST", data={"path": test_dir_path}, token=token)
    assert status == 200, f"Rm dir failed ({status}): {body.decode('utf-8')}"
    assert not os.path.exists(test_dir_path), "Directory still exists after rm!"

    # Clean up backup
    if os.path.exists(test_file_path + ".bak"):
        os.remove(test_file_path + ".bak")

    print(f"-> Rm verified for both files and directories.")

    print("\n========================================================")
    print("  ALL FILE MANAGER LIFECYCLE TESTS PASSED PERFECTLY")
    print("========================================================")

if __name__ == "__main__":
    test_file_manager_lifecycle()

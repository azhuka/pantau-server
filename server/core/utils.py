import hashlib

KEY_PREFIX = "sha256:"

def hash_api_key(raw: str) -> str:
    """Hash raw API key using SHA-256 with sha256: prefix."""
    if not raw:
        return ""
    raw = raw.strip()
    return KEY_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def api_key_fingerprint(api_key: str) -> str:
    h = api_key
    if h.startswith(KEY_PREFIX):
        h = h[len(KEY_PREFIX):]
    return h[:8] + "…" + h[-8:] if len(h) > 16 else h

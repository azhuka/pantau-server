import hashlib

KEY_PREFIX = "sha256:"

def hash_api_key(raw: str) -> str:
    """Hash raw API key menggunakan SHA-256 ber-prefix sha256:"""
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith(KEY_PREFIX):
        return raw
    return KEY_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def api_key_fingerprint(api_key: str) -> str:
    h = api_key
    if h.startswith(KEY_PREFIX):
        h = h[len(KEY_PREFIX):]
    return h[:8] + "…" + h[-8:] if len(h) > 16 else h

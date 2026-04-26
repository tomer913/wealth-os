"""
Symmetric encryption for connector configs stored in DB.
Uses Fernet (AES-128-CBC + HMAC-SHA256) from cryptography library.

Format: {"_encrypted": "<fernet_token>"}
The entire config dict is JSON-serialised then encrypted as one blob.

Railway env var: CONNECTOR_ENCRYPTION_KEY
Generate with:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Backward compat:
  • Legacy field-level   — {"api_key": "enc:gAAAAA...", ...}  → decrypts each field
  • Plain text (no key)  — {"api_key": "abc", ...}            → returns as-is
  • New whole-config     — {"_encrypted": "gAAAAA..."}        → decrypts blob
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Fields that should be masked in display responses
SENSITIVE_KEYS = {"api_key", "api_secret", "password", "token", "secret"}

_LEGACY_PREFIX = "enc:"
_ENCRYPTED_KEY = "_encrypted"

_fernet_instance = None


def _get_fernet():
    global _fernet_instance
    if _fernet_instance is None:
        key = os.environ.get("CONNECTOR_ENCRYPTION_KEY")
        if not key:
            return None
        from cryptography.fernet import Fernet
        _fernet_instance = Fernet(key.encode())
    return _fernet_instance


def encrypt_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Encrypt entire config dict as a Fernet blob."""
    fernet = _get_fernet()
    if fernet is None:
        log.warning("CONNECTOR_ENCRYPTION_KEY not set — storing connector config as plain text")
        return config
    try:
        encrypted = fernet.encrypt(json.dumps(config).encode()).decode()
        return {_ENCRYPTED_KEY: encrypted}
    except Exception as e:
        log.error("Encryption failed: %s", e)
        raise ValueError(f"Encryption failed: {e}") from e


def decrypt_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decrypt a connector config dict.

    Handles three stored formats (in priority order):
      1. New whole-config:  {"_encrypted": "gAAAAA..."}
      2. Legacy field-level: {"api_key": "enc:...", "api_secret": "enc:..."}
      3. Plain text:         {"api_key": "abc", ...}
    """
    if not config:
        return {}

    fernet = _get_fernet()

    # ── Format 1: new whole-config ────────────────────────────────────────────
    if _ENCRYPTED_KEY in config:
        if fernet is None:
            raise ValueError(
                "Config is encrypted but CONNECTOR_ENCRYPTION_KEY is not set. "
                "Set this env var in Railway to decrypt connector configs."
            )
        try:
            decrypted = fernet.decrypt(config[_ENCRYPTED_KEY].encode()).decode()
            return json.loads(decrypted)
        except Exception as e:
            log.error("Decryption failed: %s", e)
            raise ValueError(
                f"Decryption failed — CONNECTOR_ENCRYPTION_KEY may have changed: {e}"
            ) from e

    # ── Format 2: legacy field-level enc: prefix ──────────────────────────────
    if any(isinstance(v, str) and v.startswith(_LEGACY_PREFIX)
           for v in config.values()):
        if fernet is None:
            log.warning("Config has legacy enc: fields but no encryption key — returning raw")
            return config
        try:
            from cryptography.fernet import InvalidToken
            result: Dict[str, Any] = {}
            for k, v in config.items():
                if isinstance(v, str) and v.startswith(_LEGACY_PREFIX):
                    try:
                        result[k] = fernet.decrypt(v[len(_LEGACY_PREFIX):].encode()).decode()
                    except InvalidToken:
                        log.warning("Failed to decrypt field '%s' — treating as empty", k)
                        result[k] = ""
                else:
                    result[k] = v
            return result
        except Exception as e:
            log.error("Legacy field decryption failed: %s", e)
            return config

    # ── Format 3: plain text (no encryption was applied) ─────────────────────
    return config


def mask_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return config with sensitive values masked: last 4 chars visible."""
    result: Dict[str, Any] = {}
    for key, value in config.items():
        if key in SENSITIVE_KEYS and isinstance(value, str) and value:
            result[key] = "••••••••" + value[-4:]
        else:
            result[key] = value
    return result


def get_config_keys(config: Dict[str, Any]) -> List[str]:
    """Return config keys — tries to decrypt if whole-config format."""
    if _ENCRYPTED_KEY in config:
        try:
            return list(decrypt_config(config).keys())
        except Exception:
            return [_ENCRYPTED_KEY]
    return list(config.keys())

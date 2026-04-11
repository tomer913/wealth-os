"""
Symmetric encryption for connector API keys stored in DB.
Uses Fernet (AES-128-CBC + HMAC-SHA256) from cryptography library.

Railway env var: CONNECTOR_ENCRYPTION_KEY
Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

_fernet: Fernet | None = None

ENCRYPTED_PREFIX = "enc:"
# Fields in connector config that should be encrypted
SENSITIVE_KEYS = {"api_key", "api_secret", "password", "token", "secret"}


def _get_fernet() -> Optional[Fernet]:
    global _fernet
    if _fernet is None:
        key = os.environ.get("CONNECTOR_ENCRYPTION_KEY")
        if not key:
            return None  # Encryption disabled — store as plain text
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_value(value: str) -> str:
    """Encrypt a string value. Returns 'enc:<base64>' or plain if no key set."""
    if value.startswith(ENCRYPTED_PREFIX):
        return value  # Already encrypted
    fernet = _get_fernet()
    if fernet is None:
        return value  # No encryption key — store as plain text
    token = fernet.encrypt(value.encode())
    return f"{ENCRYPTED_PREFIX}{token.decode()}"


def decrypt_value(value: str) -> str:
    """Decrypt an encrypted string. Returns plain text."""
    if not value.startswith(ENCRYPTED_PREFIX):
        return value  # Not encrypted or no key, return as-is
    fernet = _get_fernet()
    if fernet is None:
        return value  # Can't decrypt without key
    token = value[len(ENCRYPTED_PREFIX):]
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt value — invalid key or corrupted data")


def encrypt_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Encrypt all sensitive fields in a config dict."""
    result = {}
    for key, value in config.items():
        if key in SENSITIVE_KEYS and isinstance(value, str) and value:
            result[key] = encrypt_value(value)
        else:
            result[key] = value
    return result


def decrypt_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypt all sensitive fields in a config dict."""
    result = {}
    for key, value in config.items():
        if key in SENSITIVE_KEYS and isinstance(value, str):
            result[key] = decrypt_value(value)
        else:
            result[key] = value
    return result


def mask_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return config with sensitive values masked for API responses."""
    result = {}
    for key, value in config.items():
        if key in SENSITIVE_KEYS and value:
            result[key] = "••••••••"
        else:
            result[key] = value
    return result


def get_config_keys(config: Dict[str, Any]) -> list[str]:
    """Return list of config keys (for safe display in API response)."""
    return list(config.keys())

import base64, hashlib
from cryptography.fernet import Fernet
from .config import settings

def _key() -> bytes:
    digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)

fernet = Fernet(_key())

def encrypt(value: str) -> str:
    if not value:
        return ""
    return fernet.encrypt(value.encode()).decode()

def decrypt(token: str) -> str:
    if not token:
        return ""
    return fernet.decrypt(token.encode()).decode()

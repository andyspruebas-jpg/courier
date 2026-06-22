from cryptography.fernet import Fernet
from django.conf import settings

# Usa la clave segura del .env
fernet = Fernet(settings.MEDIA_SECRET_KEY.encode())


def encrypt_bytes(data: bytes) -> bytes:
    """Cifra bytes usando Fernet AES."""
    return fernet.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """Descifra bytes usando Fernet AES."""
    return fernet.decrypt(data)

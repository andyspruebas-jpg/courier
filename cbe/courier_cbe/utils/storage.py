from django.core.files.storage import FileSystemStorage
from django.conf import settings
from utils.crypto import encrypt_bytes, decrypt_bytes
from django.core.files.base import ContentFile
import os

class PrivateEncryptedStorage(FileSystemStorage):
    """
    Cifra al guardar y descifra al abrir. Usa PROTECTED_MEDIA_ROOT.
    """
    def __init__(self, *args, **kwargs):
        location = getattr(
            settings,
            'PROTECTED_MEDIA_ROOT',
            os.path.join(settings.BASE_DIR, 'protected_media')
        )
        # base_url no se usa para servir (lo hacemos por vista), pero lo dejamos neutro
        super().__init__(location=location, base_url='/protected_media/', *args, **kwargs)

    def _save(self, name, content):
        encrypted = encrypt_bytes(content.read())
        return super()._save(name, ContentFile(encrypted))

    def _open(self, name, mode='rb'):
        fileobj = super()._open(name, mode)
        decrypted = decrypt_bytes(fileobj.read())
        return ContentFile(decrypted, name=name)

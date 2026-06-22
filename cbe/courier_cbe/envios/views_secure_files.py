import os
from django.http import HttpResponse, Http404, HttpResponseForbidden
from django.conf import settings
from cryptography.fernet import InvalidToken
from utils.crypto import decrypt_bytes
from django.contrib.auth.decorators import login_required

@login_required
def serve_protected_file(request, path):
    """Sirve archivos cifrados solo a usuarios autenticados (admin o staff)."""
    full_path = os.path.join(settings.PROTECTED_MEDIA_ROOT, path)

    if not os.path.exists(full_path):
        raise Http404("Archivo no encontrado")

    # Restringir acceso
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("No autorizado")

    try:
        with open(full_path, "rb") as f:
            encrypted = f.read()
        data = decrypt_bytes(encrypted)
    except InvalidToken:
        raise Http404("Error al descifrar el archivo")

    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"

    return HttpResponse(data, content_type=mime)

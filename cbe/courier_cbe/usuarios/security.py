from functools import wraps
import json

from django.http import JsonResponse
from django.shortcuts import redirect
from rest_framework_simplejwt.tokens import AccessToken

from .models import Usuario


def usuario_from_bearer(request):
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = AccessToken(token)
        user_id = payload.get("user_id")
        return Usuario.objects.select_related("rol", "empresa").filter(pk=user_id, is_active=True).first()
    except Exception:
        return None


def usuario_from_request(request, allow_legacy_params=True):
    session_id = request.session.get("usuario_id")
    if session_id:
        user = Usuario.objects.select_related("rol", "empresa").filter(pk=session_id, is_active=True).first()
        if user:
            return user

    user = usuario_from_bearer(request)
    if user:
        return user

    if not allow_legacy_params:
        return None

    user_id = request.GET.get("usuario_id") or request.POST.get("usuario_id")
    if not user_id and request.body and request.content_type == "application/json":
        try:
            user_id = json.loads(request.body.decode("utf-8")).get("usuario_id")
        except Exception:
            user_id = None
    if user_id:
        return Usuario.objects.select_related("rol", "empresa").filter(pk=user_id, is_active=True).first()
    return None


def is_admin(usuario):
    return bool(usuario and usuario.rol and usuario.rol.nombre.lower() == "administrador")


def is_cliente(usuario):
    return bool(usuario and usuario.rol and usuario.rol.nombre.lower() == "cliente")


def is_mensajero(usuario):
    return bool(usuario and usuario.rol and usuario.rol.nombre.lower() == "mensajero")


def require_session(view_fn):
    @wraps(view_fn)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            return redirect("usuarios:login")
        return view_fn(request, *args, **kwargs)

    return _wrapped


def require_roles(*roles):
    roles_norm = {r.lower() for r in roles}

    def decorator(view_fn):
        @wraps(view_fn)
        def _wrapped(request, *args, **kwargs):
            usuario = usuario_from_request(request, allow_legacy_params=False)
            if not usuario or usuario.rol.nombre.lower() not in roles_norm:
                if request.headers.get("Accept", "").lower().find("application/json") >= 0:
                    return JsonResponse({"error": "No autorizado"}, status=403)
                return redirect("usuarios:login")
            request.usuario_actual = usuario
            return view_fn(request, *args, **kwargs)

        return _wrapped

    return decorator

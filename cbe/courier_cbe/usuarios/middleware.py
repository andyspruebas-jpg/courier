from django.http import JsonResponse
from django.shortcuts import redirect

from .models import Usuario
from .security import is_admin, is_cliente, usuario_from_bearer


PUBLIC_PREFIXES = (
    "/usuarios/login/",
    "/usuarios/api/login/",
    "/usuarios/password-reset/",
    "/usuarios/restablecer/",
    "/api/token/",
    "/api/token/refresh/",
    "/envios/seguimiento/",
    "/envios/api/seguimiento/",
    "/zonas/cobertura/",
    "/static/",
    "/media/",
    "/protected/",
)

ASSET_PREFIXES = (
    "/static/",
    "/media/",
    "/protected/",
)

API_PREFIXES = (
    "/usuarios/api/",
    "/usuarios/perfil/",
    "/usuarios/actualizar_ubicacion/",
    "/rutas/api/",
    "/rutas/alimentar-ml/",
    "/envios/api/envios/crear/",
    "/envios/api/entregas/",
    "/envios/api/incidentes/",
)

CLIENT_BLOCKED_PREFIXES = (
    "/usuarios/listar/",
    "/usuarios/crear/",
    "/usuarios/ver/",
    "/usuarios/editar/",
    "/usuarios/eliminar/",
    "/usuarios/empresas/",
    "/usuarios/mensajeros/",
    "/usuarios/home_data/",
    "/usuarios/mensajeros-json/",
    "/usuarios/rutas_mensajeros/",
    "/usuarios/obtener_",
    "/rutas/",
    "/zonas/",
    "/envios/reportes/",
    "/envios/entregas/",
    "/envios/entregas-json/",
    "/envios/envios-pendientes-json/",
    "/envios/api/entregas/",
    "/envios/api/incidentes/",
    "/envios/envios/crear/",
)

CLIENT_BLOCKED_SEGMENTS = (
    "/editar/",
    "/eliminar/",
    "/reasignar/",
    "/historial/",
    "/incidentes/",
)

ADMIN_ONLY_PREFIXES = (
    "/usuarios/listar/",
    "/usuarios/crear/",
    "/usuarios/ver/",
    "/usuarios/editar/",
    "/usuarios/eliminar/",
    "/usuarios/empresas/",
    "/usuarios/mensajeros/",
    "/usuarios/home_data/",
    "/usuarios/mensajeros-json/",
    "/usuarios/rutas_mensajeros/",
    "/usuarios/obtener_",
    "/zonas/",
    "/envios/reportes/",
    "/envios/entregas/",
    "/envios/envios/crear/",
    "/rutas/",
)

ADMIN_ONLY_SEGMENTS = (
    "/editar/",
    "/eliminar/",
    "/reasignar/",
    "/historial/",
)

ADMIN_ONLY_EXCEPTIONS = (
    "/zonas/cobertura/",
    "/rutas/api/",
    "/rutas/alimentar-ml/",
)


class AutenticacionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(ASSET_PREFIXES):
            return self.get_response(request)

        usuario = self._usuario_from_session(request) or usuario_from_bearer(request)

        if not usuario:
            if path.startswith(PUBLIC_PREFIXES):
                return self.get_response(request)
            if path.startswith(API_PREFIXES):
                return self.get_response(request)
            return redirect("usuarios:login")

        request.usuario_actual = usuario

        if path.startswith("/usuarios/login/"):
            return redirect("usuarios:home")

        if not is_admin(usuario) and self._admin_only(path):
            if self._wants_json(request):
                return JsonResponse({"error": "Solo administradores"}, status=403)
            return redirect("usuarios:home")

        if is_cliente(usuario) and self._cliente_bloqueado(path):
            if self._wants_json(request):
                return JsonResponse({"error": "No autorizado para clientes"}, status=403)
            return redirect("usuarios:home")

        return self.get_response(request)

    def _cliente_bloqueado(self, path):
        if path.startswith("/zonas/cobertura/"):
            return False
        return path.startswith(CLIENT_BLOCKED_PREFIXES) or any(
            segment in path for segment in CLIENT_BLOCKED_SEGMENTS
        )

    def _admin_only(self, path):
        if path.startswith(ADMIN_ONLY_EXCEPTIONS):
            return False
        return path.startswith(ADMIN_ONLY_PREFIXES) or any(
            segment in path for segment in ADMIN_ONLY_SEGMENTS
        )

    def _wants_json(self, request):
        accept = request.headers.get("Accept", "").lower()
        authorization = request.headers.get("Authorization", "").lower()
        return (
            "application/json" in accept
            or authorization.startswith("bearer ")
            or request.path.startswith(API_PREFIXES)
        )

    def _usuario_from_session(self, request):
        usuario_id = request.session.get("usuario_id")
        if not usuario_id:
            return None
        usuario = Usuario.objects.select_related("rol", "empresa").filter(
            pk=usuario_id,
            is_active=True,
        ).first()
        if not usuario:
            request.session.flush()
        return usuario

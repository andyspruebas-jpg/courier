# rutas/api.py (ejemplo)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Ruta
from usuarios.security import is_admin, usuario_from_request

@api_view(["POST"])
def marcar_evento_ruta(request, ruta_id):
    """
    Body ejemplo:
    {
      "evento": "start" | "finish",
      "timestamp": "2025-10-01T09:32:00-04:00"
    }
    """
    try:
        ruta = Ruta.objects.get(pk=ruta_id)
    except Ruta.DoesNotExist:
        return Response({"detail": "No existe"}, status=status.HTTP_404_NOT_FOUND)

    usuario = usuario_from_request(request._request, allow_legacy_params=False)
    if not usuario:
        return Response({"detail": "Token requerido"}, status=status.HTTP_401_UNAUTHORIZED)
    if not is_admin(usuario) and ruta.mensajero_id != usuario.id:
        return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

    ev = request.data.get("evento")
    ts = request.data.get("timestamp")
    if not ev or not ts:
        return Response({"detail": "Faltan datos"}, status=status.HTTP_400_BAD_REQUEST)

    # Parseo simple:
    from django.utils.dateparse import parse_datetime
    ts_dt = parse_datetime(ts)

    if ev == "start":
        ruta.started_at = ts_dt
    elif ev == "finish":
        ruta.finished_at = ts_dt
        # auto calcular real
        ruta.recompute_real_duration_from_timestamps()
        # actualizar etiqueta simple
        ruta.infer_retraso_simple()
    else:
        return Response({"detail": "Evento inválido"}, status=status.HTTP_400_BAD_REQUEST)

    ruta.save()
    return Response({"ok": True})

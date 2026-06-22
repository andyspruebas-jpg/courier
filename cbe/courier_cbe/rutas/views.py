from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseBadRequest, JsonResponse
import json
import os
from datetime import date, datetime
from django.db import DatabaseError
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import traceback
import joblib

from rest_framework.decorators import api_view
from rest_framework.response import Response

# MODELOS
from .models import MLTrainingState, Ruta, RutaParada
from usuarios.models import Usuario, PerfilMensajero, UbicacionMensajero
from envios.models import Envio

# SERVICIOS Y UTILIDADES
from .services.google_maps import (
    encode_polyline,
    fallback_distance,
    get_route_metrics,
    geocode_address,
    get_polyline_from_ordered_coords
)
from .routing import (
    compute_algorithmic_route,
    load_delay_model,
    build_time_matrix_with_google,
    build_time_matrix_haversine,
    haversine_distance_m,
)
from .services.ml_trainer import feed_new_ubicaciones_and_train as train_ml_incremental
from .services.optimization import rebuild_route_for_messenger
from usuarios.security import is_admin, usuario_from_request

# =======================================================
# FUNCIÓN SEGURA DE ENTRENAMIENTO ML
# =======================================================
def feed_new_ubicaciones_and_train():
    """
    Ejecuta el entrenamiento incremental real y conserva una respuesta tolerante
    para el panel si faltan datos etiquetados.
    """
    try:
        return train_ml_incremental()
    except DatabaseError as e:
        return {"ok": False, "msg": f"DB error: {e}", "new": 0, "processed_count": 0, "last_processed_datetime": None}
    except Exception as e:
        return {"ok": False, "msg": str(e), "new": 0, "processed_count": 0, "last_processed_datetime": None}


# =======================================================
# VISTAS HTML
# =======================================================
def lista_rutas(request):
    # Obtener búsqueda
    search_query = request.GET.get('search', '')
    
    # Obtener solo MENSAJEROS (filtrar por rol)
    mensajeros = Usuario.objects.filter(
        rol__nombre__iexact='mensajero'
    )
    
    # Filtrar por búsqueda
    if search_query:
        mensajeros = mensajeros.filter(nombre__icontains=search_query)
    
    # Ordenar alfabéticamente
    mensajeros = mensajeros.order_by('nombre')
    
    # Para cada mensajero, agregar conteo de envíos pendientes
    mensajeros_data = []
    for mensajero in mensajeros:
        envios_pendientes = Envio.objects.filter(
            mensajero=mensajero,
            estado='Pendiente'
        )
        
        mensajeros_data.append({
            'mensajero': mensajero,
            'envios_count': envios_pendientes.count(),
            'envios': envios_pendientes
        })
    
    return render(request, "rutas/lista_rutas.html", {
        "mensajeros_data": mensajeros_data,
        "search_query": search_query,
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
    })



def optimizar_rutas(request, mensajero_id):
    if request.method != "GET":
        return HttpResponseBadRequest("Método no soportado")

    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not is_admin(usuario) and usuario.id != mensajero_id:
        return JsonResponse({"error": "No autorizado"}, status=403)

    mensajero = get_object_or_404(Usuario, pk=mensajero_id)
    result = rebuild_route_for_messenger(mensajero)

    return render(request, "rutas/optimizar_rutas.html", {
        "ruta_google": result.get("ruta_google", {"polyline": "", "duracion": None, "distancia": None}),
        "ruta_algo": result.get("ruta_algo", {"polyline": "", "duracion": None, "distancia": None}),
        "puntos": json.dumps(result.get("puntos", []), ensure_ascii=False),
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
        "ml_notice": None if result.get("ok") else result.get("msg"),
    })


@csrf_exempt
def api_optimizar_ruta(request, mensajero_id):
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"error": "Token requerido"}, status=401)
    if not is_admin(usuario) and usuario.id != mensajero_id:
        return JsonResponse({"error": "No autorizado"}, status=403)

    mensajero = Usuario.objects.filter(pk=mensajero_id, rol__nombre__iexact="mensajero").first()
    if not mensajero:
        return JsonResponse({"error": "Mensajero no encontrado"}, status=404)

    result = rebuild_route_for_messenger(mensajero)
    if not result.get("ok"):
        return JsonResponse({"ok": False, "msg": result.get("msg")}, status=400)

    ruta = result["ruta"]
    return JsonResponse({
        "ok": True,
        "ruta_id": ruta.id,
        "ordered_envio_ids": result.get("ordered_envio_ids", []),
        "ruta_google": result.get("ruta_google"),
        "ruta_algo": result.get("ruta_algo"),
        "puntos": result.get("puntos", []),
    })


def ver_ruta(request, ruta_id):
    ruta = get_object_or_404(Ruta, id=ruta_id)
    return render(request, "rutas/ver_ruta.html", {"ruta": ruta})


# =======================================================
# ENDPOINTS JSON PARA FLUTTER
# =======================================================
def rutas_json(request, mensajero_id):
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"error": "Token requerido"}, status=401)
    if not is_admin(usuario) and usuario.id != mensajero_id:
        return JsonResponse({"error": "No autorizado"}, status=403)
    rutas = Ruta.objects.filter(mensajero_id=mensajero_id).order_by('-fecha')
    data = [{
        "id": ruta.id,
        "mensajero": ruta.mensajero.nombre if ruta.mensajero else None,
        "fecha": ruta.fecha.isoformat() if ruta.fecha else None,
        "latitud_inicio": str(ruta.latitud_inicio) if ruta.latitud_inicio else None,
        "longitud_inicio": str(ruta.longitud_inicio) if ruta.longitud_inicio else None,
        "latitud_fin": str(ruta.latitud_fin) if ruta.latitud_fin else None,
        "longitud_fin": str(ruta.longitud_fin) if ruta.longitud_fin else None,
        "distancia": float(ruta.distancia_google_m) if ruta.distancia_google_m else None,
        "duracion_estimada": float(ruta.duracion_google_min) if ruta.duracion_google_min else None,
        "duracion_real": float(ruta.duracion_algo_min) if ruta.duracion_algo_min else None,
        "polyline": ruta.polyline_google or "",
    } for ruta in rutas]
    return JsonResponse(data, safe=False)


def rutas_api_json(request):
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"error": "Token requerido"}, status=401)
    if not is_admin(usuario):
        return JsonResponse({"error": "Solo administradores"}, status=403)
    rutas = Ruta.objects.select_related('mensajero').order_by('-fecha')
    data = [{
        "id": ruta.id,
        "mensajero": ruta.mensajero.nombre if ruta.mensajero else None,
        "fecha": ruta.fecha.isoformat() if ruta.fecha else None,
        "latitud_inicio": str(ruta.latitud_inicio) if ruta.latitud_inicio else None,
        "longitud_inicio": str(ruta.longitud_inicio) if ruta.longitud_inicio else None,
        "latitud_fin": str(ruta.latitud_fin) if ruta.latitud_fin else None,
        "longitud_fin": str(ruta.longitud_fin) if ruta.longitud_fin else None,
        "distancia": float(ruta.distancia_google_m) if ruta.distancia_google_m else None,
        "duracion_estimada": float(ruta.duracion_google_min) if ruta.duracion_google_min else None,
        "duracion_real": float(ruta.duracion_algo_min) if ruta.duracion_algo_min else None,
        "polyline": ruta.polyline_google or "",
    } for ruta in rutas]
    return JsonResponse(data, safe=False)


@csrf_exempt
def alimentar_ml(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "msg": "Se esperaba POST"}, status=400)
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"ok": False, "msg": "Token requerido"}, status=401)
    if not is_admin(usuario):
        return JsonResponse({"ok": False, "msg": "Solo administradores"}, status=403)
    try:
        result = feed_new_ubicaciones_and_train()
        if isinstance(result.get("last_processed_datetime"), datetime):
            result["last_processed_datetime"] = result["last_processed_datetime"].isoformat()
        return JsonResponse(result, safe=True)
    except Exception as e:
        tb = traceback.format_exc()
        return JsonResponse({"ok": False, "msg": str(e), "error": tb}, status=500)


def mensajeros_json(request):
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"error": "Token requerido"}, status=401)
    if not is_admin(usuario):
        return JsonResponse({"error": "Solo administradores"}, status=403)
    mensajeros = Usuario.objects.filter(
        rol__nombre__iexact="mensajero",
        is_active=True,
    ).values("id", "nombre")
    return JsonResponse(list(mensajeros), safe=False)


# =======================================================
# 🔹 NUEVO ENDPOINT: MENSAJEROS CON RUTAS
# =======================================================
@csrf_exempt
def mensajeros_con_rutas(request):
    """
    Devuelve la lista de mensajeros que tienen al menos una ruta creada.
    """
    try:
        usuario = usuario_from_request(request, allow_legacy_params=False)
        if not usuario:
            return JsonResponse({"error": "Token requerido"}, status=401)
        if not is_admin(usuario):
            return JsonResponse({"error": "Solo administradores"}, status=403)
        # Obtener mensajeros que tienen rutas
        mensajeros_ids = Ruta.objects.values_list('mensajero_id', flat=True).distinct()
        mensajeros = Usuario.objects.filter(
            id__in=mensajeros_ids,
            rol__nombre__iexact='mensajero',
            is_active=True,
        ).values('id', 'nombre', 'email')
        
        # Para cada mensajero, obtener info de su última ruta
        data = []
        for mensajero in mensajeros:
            ultima_ruta = Ruta.objects.filter(mensajero_id=mensajero['id']).order_by('-fecha').first()
            data.append({
                'id': mensajero['id'],
                'nombre': mensajero['nombre'],
                'email': mensajero['email'],
                'tiene_ruta': True,
                'fecha_ultima_ruta': ultima_ruta.fecha.isoformat() if ultima_ruta and ultima_ruta.fecha else None,
            })
        
        return JsonResponse(data, safe=False)
    except Exception as e:
        print("⚠️ Error en mensajeros_con_rutas:", e)
        return JsonResponse({"error": str(e)}, status=500)


# =======================================================
# 🔹 ENDPOINT PARA FLUTTER (RUTA DETALLE)
# =======================================================
@csrf_exempt
def _ordenar_y_estimar_eta(paradas, start_lat, start_lng, avg_speed_kmh: float = 30.0):
    """
    Ordena las paradas por vecino más cercano (Nearest Neighbor) partiendo del
    inicio de la ruta y añade a cada una:
      - 'orden'   : posición de visita (1-based)
      - 'eta_min' : minutos acumulados estimados desde el inicio (Haversine).

    Las paradas sin coordenadas se dejan al final, sin ETA.
    """
    from rutas.routing import haversine_distance_m

    con_coords = [p for p in paradas if p.get('lat') is not None and p.get('lng') is not None]
    sin_coords = [p for p in paradas if p.get('lat') is None or p.get('lng') is None]

    if start_lat is None or start_lng is None:
        # Sin punto de inicio no podemos ordenar por proximidad; devolvemos tal cual.
        for i, p in enumerate(paradas, start=1):
            p['orden'] = i
            p['eta_min'] = None
        return paradas

    restantes = list(con_coords)
    ordenadas = []
    cur_lat, cur_lng = start_lat, start_lng
    eta_acumulada = 0.0
    orden = 1
    while restantes:
        # parada más cercana a la posición actual
        nearest = min(
            restantes,
            key=lambda p: haversine_distance_m(cur_lat, cur_lng, p['lat'], p['lng']),
        )
        dist_m = haversine_distance_m(cur_lat, cur_lng, nearest['lat'], nearest['lng'])
        eta_acumulada += (dist_m / 1000.0) / avg_speed_kmh * 60.0  # minutos
        nearest['orden'] = orden
        nearest['eta_min'] = round(eta_acumulada, 1)
        ordenadas.append(nearest)
        restantes.remove(nearest)
        cur_lat, cur_lng = nearest['lat'], nearest['lng']
        orden += 1

    for p in sin_coords:
        p['orden'] = orden
        p['eta_min'] = None
        orden += 1

    return ordenadas + sin_coords


def ruta_detalle_flutter(request, mensajero_id):
    """
    Devuelve la última ruta asignada a un mensajero con las dos polylines
    (Google y Algoritmo) para mostrar en el mapa comparativo Flutter.
    """
    try:
        if request.method != "GET":
            return HttpResponseBadRequest("Método no permitido")
        usuario = usuario_from_request(request, allow_legacy_params=False)
        if not usuario:
            return JsonResponse({"error": "Token requerido"}, status=401)
        if not is_admin(usuario) and usuario.id != mensajero_id:
            return JsonResponse({"error": "No autorizado"}, status=403)

        # 🔹 Filtrar por la ruta resumen (sin envío específico) igual que la web
        ruta = Ruta.objects.filter(mensajero_id=mensajero_id, envio__isnull=True).order_by("-fecha").first()
        if not ruta:
            return JsonResponse({"error": "No se encontró ruta"}, status=404)

        envios_list = []
        paradas_persistidas = RutaParada.objects.filter(ruta=ruta).select_related("envio").order_by("orden")
        if paradas_persistidas.exists():
            for parada in paradas_persistidas:
                e = parada.envio
                if e.tipo == 'Recojo':
                    lat, lng, direccion = e.latitud_origen, e.longitud_origen, e.origen_direccion
                else:
                    lat, lng, direccion = e.latitud_destino, e.longitud_destino, e.destino_direccion
                envios_list.append({
                    'id': e.id,
                    'numero_seguimiento': e.numero_seguimiento,
                    'tipo': e.tipo,
                    'lat': float(lat) if lat is not None else None,
                    'lng': float(lng) if lng is not None else None,
                    'direccion': direccion,
                    'destinatario_nombre': e.destinatario_nombre,
                    'destinatario_telefono': e.destinatario_telefono,
                    'estado': e.estado,
                    'tipo_pago': e.tipo_pago,
                    'monto_pago': float(e.monto_pago) if e.monto_pago is not None else None,
                    'orden': parada.orden,
                    'eta_min': parada.eta_min,
                })
        else:
            # Obtener envíos PENDIENTES asociados a este mensajero
            envios = Envio.objects.filter(mensajero_id=mensajero_id, estado='Pendiente').values(
                'id', 'numero_seguimiento', 'tipo', 'latitud_origen', 'longitud_origen',
                'latitud_destino', 'longitud_destino', 'origen_direccion', 'destino_direccion',
                'destinatario_nombre', 'destinatario_telefono', 'estado',
                'tipo_pago', 'monto_pago',
            )

            for e in envios:
                # La parada de un 'Recojo' es el origen; la de un 'Envío' es el destino.
                if e['tipo'] == 'Recojo':
                    lat, lng, direccion = e['latitud_origen'], e['longitud_origen'], e['origen_direccion']
                else:
                    lat, lng, direccion = e['latitud_destino'], e['longitud_destino'], e['destino_direccion']
                envios_list.append({
                    'id': e['id'],
                    'numero_seguimiento': e['numero_seguimiento'],
                    'tipo': e['tipo'],
                    'lat': float(lat) if lat is not None else None,
                    'lng': float(lng) if lng is not None else None,
                    'direccion': direccion,
                    'destinatario_nombre': e['destinatario_nombre'],
                    'destinatario_telefono': e['destinatario_telefono'],
                    'estado': e['estado'],
                    'tipo_pago': e['tipo_pago'],
                    'monto_pago': float(e['monto_pago']) if e['monto_pago'] is not None else None,
                })

            # 🔹 Ordenar las paradas por vecino más cercano desde el inicio de la ruta
            #    y calcular una ETA acumulada (Haversine a 30 km/h, igual que el fallback
            #    del motor de rutas) para mostrar "Mis entregas" en orden de visita.
            envios_list = _ordenar_y_estimar_eta(
                envios_list,
                float(ruta.latitud_inicio) if ruta.latitud_inicio is not None else None,
                float(ruta.longitud_inicio) if ruta.longitud_inicio is not None else None,
            )

        if not envios_list:
            return JsonResponse({"error": "No hay paradas activas"}, status=404)

        data = {
            "id": ruta.id,
            "fecha": ruta.fecha.isoformat() if ruta.fecha else None,
            "latitud_inicio": ruta.latitud_inicio,
            "longitud_inicio": ruta.longitud_inicio,
            "latitud_fin": ruta.latitud_fin,
            "longitud_fin": ruta.longitud_fin,
            "distancia_google": float(ruta.distancia_google_m or 0),
            "duracion_google": float(ruta.duracion_google_min or 0),
            "distancia_algoritmo": float(ruta.distancia_algo_m or 0),
            "duracion_algoritmo": float(ruta.duracion_algo_min or 0),
            "polyline_google": ruta.polyline_google or "",
            "polyline_algoritmo": ruta.polyline_algo or "",
            "envios": envios_list,
        }
        return JsonResponse(data, safe=False)

    except Exception as e:
        print("⚠️ Error en ruta_detalle_flutter:", e)
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def tramo_navegacion_flutter(request):
    """
    Devuelve solo el tramo activo de navegación: ubicación actual -> parada.
    Mantiene la API key de Google en backend para no exponerla en Flutter.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"error": "Token requerido"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        origin = payload.get("origin") or {}
        destination = payload.get("destination") or {}
        origin_lat = float(origin.get("lat"))
        origin_lng = float(origin.get("lng"))
        dest_lat = float(destination.get("lat"))
        dest_lng = float(destination.get("lng"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Coordenadas inválidas"}, status=400)

    duracion_min, distancia_m, polyline = get_route_metrics(
        origin_lat,
        origin_lng,
        dest_lat,
        dest_lng,
    )
    if not polyline:
        polyline = encode_polyline([(origin_lat, origin_lng), (dest_lat, dest_lng)])
        duracion_min, distancia_m = fallback_distance(origin_lat, origin_lng, dest_lat, dest_lng)

    return JsonResponse({
        "polyline": polyline or "",
        "duracion_min": float(duracion_min or 0),
        "distancia_m": float(distancia_m or 0),
    })


# =======================================================
# URLPATTERNS
# =======================================================
from django.urls import path

urlpatterns = [
    path("", lista_rutas, name="lista_rutas"),
    path("optimizar/<int:mensajero_id>/", optimizar_rutas, name="optimizar_rutas"),
    path("<int:ruta_id>/", ver_ruta, name="ver_ruta"),

    # JSON para Flutter
    path("api/mensajeros-json/", mensajeros_json, name="mensajeros_json"),
    path("api/mensajeros-con-rutas/", mensajeros_con_rutas, name="mensajeros_con_rutas"),  # ← NUEVO
    path("api/rutas-json/<int:mensajero_id>/", rutas_json, name="rutas_json"),
    path("api/rutas-json/", rutas_api_json, name="rutas_api_json"),

    # ML Endpoint
    path("alimentar-ml/", alimentar_ml, name="alimentar_ml"),

    # 🔹 Endpoint para mapa Flutter (comparativo)
    path("api/ruta-detalle/<int:mensajero_id>/", ruta_detalle_flutter, name="ruta_detalle_flutter"),
]

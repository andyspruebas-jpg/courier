import os

import joblib
from django.conf import settings

from envios.models import Envio
from rutas.models import MLTrainingState, Ruta, RutaParada
from rutas.routing import (
    build_time_matrix_haversine,
    compute_algorithmic_route,
    haversine_distance_m,
    load_delay_model,
)
from rutas.services.google_maps import encode_polyline, get_polyline_from_ordered_coords, get_route_metrics
from usuarios.models import PerfilMensajero, UbicacionMensajero


def _origen_mensajero(mensajero):
    ultima = UbicacionMensajero.objects.filter(mensajero=mensajero).order_by("-fecha_hora").first()
    if ultima:
        try:
            return float(ultima.latitud), float(ultima.longitud), "Mensajero (última)"
        except (TypeError, ValueError):
            pass

    perfil = PerfilMensajero.objects.filter(usuario=mensajero).first()
    if perfil and perfil.latitud is not None and perfil.longitud is not None:
        try:
            return float(perfil.latitud), float(perfil.longitud), "Mensajero (perfil)"
        except (TypeError, ValueError):
            pass
    return None


def _stop_from_envio(envio):
    if envio.tipo == "Recojo":
        lat, lng, direccion = envio.latitud_origen, envio.longitud_origen, envio.origen_direccion
    else:
        lat, lng, direccion = envio.latitud_destino, envio.longitud_destino, envio.destino_direccion
    if lat is None or lng is None:
        return None
    return {
        "id": envio.id,
        "lat": float(lat),
        "lng": float(lng),
        "tipo": envio.tipo,
        "tipo_servicio": envio.tipo_servicio,
        "direccion": direccion,
    }


def _load_models():
    kmeans_model = None
    delay_model = None
    try:
        state = MLTrainingState.objects.order_by("-updated_at").first()
        base_models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models_ai")
        k_path = getattr(state, "kmeans_path", None) if state else None
        d_path = getattr(state, "delay_path", None) if state else None
        default_k = os.path.join(base_models_dir, "kmeans.joblib")
        default_tree = os.path.join(base_models_dir, "delay_tree.joblib")
        default_sgd = os.path.join(base_models_dir, "delay_sgd.joblib")
        default_d = default_tree if os.path.exists(default_tree) else default_sgd
        if d_path and os.path.basename(d_path) == "delay_sgd.joblib" and os.path.exists(default_tree):
            d_path = default_tree

        if k_path and os.path.exists(k_path):
            kmeans_model = joblib.load(k_path)
        elif os.path.exists(default_k):
            kmeans_model = joblib.load(default_k)

        if d_path and os.path.exists(d_path):
            delay_model = load_delay_model(d_path)
        elif os.path.exists(default_d):
            delay_model = load_delay_model(default_d)
    except Exception:
        pass
    return kmeans_model, delay_model


def rebuild_route_for_messenger(mensajero, limit=50):
    origen = _origen_mensajero(mensajero)
    if not origen:
        return {"ok": False, "msg": "El mensajero no tiene ubicación disponible."}

    origin_lat, origin_lng, origin_label = origen
    origen_mensajero = (origin_lat, origin_lng)
    puntos_json = [{
        "id": f"mensajero-{mensajero.id}",
        "tipo": origin_label,
        "lat": origin_lat,
        "lng": origin_lng,
        "direccion": "Ubicación del mensajero",
    }]

    perfil = PerfilMensajero.objects.filter(usuario=mensajero).first()
    envios_qs = Envio.objects.filter(mensajero=mensajero, estado="Pendiente")
    zona_ids = perfil.zona_ids if perfil else []
    if zona_ids:
        # Una ruta operativa solo puede contener paradas de la zona asignada
        # al mensajero. Los envíos mal asignados no deben contaminar su ruta.
        envios_qs = envios_qs.filter(zona_id__in=zona_ids)
    envios = list(envios_qs.order_by("orden_ruta", "creado_en")[:limit])
    stops = []
    for envio in envios:
        stop = _stop_from_envio(envio)
        if not stop:
            continue
        puntos_json.append({
            "id": envio.id,
            "tipo": stop["tipo"],
            "lat": stop["lat"],
            "lng": stop["lng"],
            "direccion": stop["direccion"],
        })
        stops.append(stop)

    if not stops:
        ruta = Ruta.objects.filter(mensajero=mensajero, envio__isnull=True).order_by("-fecha").first()
        if ruta:
            RutaParada.objects.filter(ruta=ruta).delete()
            ruta.latitud_inicio = origin_lat
            ruta.longitud_inicio = origin_lng
            ruta.latitud_fin = origin_lat
            ruta.longitud_fin = origin_lng
            ruta.polyline_google = ""
            ruta.polyline_algo = ""
            ruta.distancia_google_m = 0
            ruta.duracion_google_min = 0
            ruta.distancia_algo_m = 0
            ruta.duracion_algo_min = 0
            ruta.duracion_estimada = 0
            ruta.save(update_fields=[
                "latitud_inicio",
                "longitud_inicio",
                "latitud_fin",
                "longitud_fin",
                "polyline_google",
                "polyline_algo",
                "distancia_google_m",
                "duracion_google_min",
                "distancia_algo_m",
                "duracion_algo_min",
                "duracion_estimada",
            ])
        return {"ok": False, "msg": "No hay envíos pendientes con coordenadas."}

    kmeans_model, delay_model = _load_models()
    coords_for_matrix = [origen_mensajero] + [(s["lat"], s["lng"]) for s in stops]
    algo = compute_algorithmic_route(
        origin=origen_mensajero,
        stops=stops,
        time_matrix=build_time_matrix_haversine(coords_for_matrix),
        delay_model=delay_model,
        kmeans_model=kmeans_model,
    )
    ordered_stops = algo.get("ordered_stops") or stops
    ordered_coords = [origen_mensajero] + [(s["lat"], s["lng"]) for s in ordered_stops]

    try:
        poly_algo, dist_algo, dur_algo = get_polyline_from_ordered_coords(
            ordered_coords,
            settings.GOOGLE_MAPS_API_KEY,
        )
    except Exception:
        poly_algo, dist_algo, dur_algo = None, 0.0, float(algo.get("end_time_min") or 0)
    if not poly_algo:
        poly_algo = encode_polyline(ordered_coords)

    try:
        waypoints = [f"{s['lat']},{s['lng']}" for s in stops]
        destination = waypoints[-1]
        wp = waypoints[:-1]
        dest_lat, dest_lng = destination.split(",")
        dur_google, dist_google, poly_google = get_route_metrics(
            str(origin_lat),
            str(origin_lng),
            dest_lat,
            dest_lng,
            waypoints=wp,
        )
    except Exception:
        poly_google, dist_google, dur_google = None, None, None
    if not poly_google:
        poly_google = encode_polyline(ordered_coords)

    ruta = Ruta.objects.filter(mensajero=mensajero, envio__isnull=True).order_by("-fecha").first()
    if not ruta:
        ruta = Ruta(mensajero=mensajero, envio=None)
    ruta.latitud_inicio = origin_lat
    ruta.longitud_inicio = origin_lng
    ruta.latitud_fin = ordered_stops[-1]["lat"]
    ruta.longitud_fin = ordered_stops[-1]["lng"]
    ruta.polyline_google = poly_google
    ruta.polyline_algo = poly_algo
    ruta.distancia_google_m = dist_google
    ruta.duracion_google_min = dur_google
    ruta.distancia_algo_m = dist_algo
    ruta.duracion_algo_min = dur_algo
    ruta.duracion_estimada = dur_google
    ruta.zona_asignada = zona_ids[0] if zona_ids else None
    ruta.save()

    RutaParada.objects.filter(ruta=ruta).delete()
    cur_lat, cur_lng = origen_mensajero
    eta_acum = 0.0
    envio_ids = []
    for orden, stop in enumerate(ordered_stops, start=1):
        envio_stop = Envio.objects.filter(pk=stop.get("id")).first()
        if not envio_stop:
            continue
        dist_m = haversine_distance_m(cur_lat, cur_lng, stop["lat"], stop["lng"])
        eta_acum += (dist_m / 1000.0) / 30.0 * 60.0
        RutaParada.objects.create(
            ruta=ruta,
            envio=envio_stop,
            orden=orden,
            eta_min=round(eta_acum, 1),
            distancia_desde_anterior_m=round(dist_m, 2),
        )
        envio_stop.orden_ruta = orden
        envio_stop.eta_min = round(eta_acum, 1)
        envio_stop.ruta_id = ruta.id
        envio_stop.save(update_fields=["orden_ruta", "eta_min", "ruta_id"])
        envio_ids.append(envio_stop.id)
        cur_lat, cur_lng = stop["lat"], stop["lng"]

    return {
        "ok": True,
        "ruta": ruta,
        "puntos": puntos_json,
        "ordered_envio_ids": envio_ids,
        "ruta_google": {"polyline": poly_google, "duracion": dur_google, "distancia": dist_google},
        "ruta_algo": {
            "polyline": poly_algo,
            "duracion": dur_algo,
            "distancia": dist_algo,
            "cluster_labels": algo.get("cluster_labels", []),
            "delay_priorities": algo.get("delay_priorities", []),
        },
    }

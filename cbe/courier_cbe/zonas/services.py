import json

from .models import Zona


def _coord_pair(raw):
    if isinstance(raw, dict):
        lat = raw.get("lat") or raw.get("latitude")
        lng = raw.get("lng") or raw.get("lon") or raw.get("longitude")
    else:
        try:
            lat, lng = raw[0], raw[1]
        except (TypeError, IndexError):
            return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def _point_in_polygon(lat, lng, polygon):
    # Ray-casting. x=longitud, y=latitud.
    x, y = float(lng), float(lat)
    inside = False
    points = [_coord_pair(p) for p in polygon]
    points = [p for p in points if p is not None]
    if len(points) < 3:
        return False

    j = len(points) - 1
    for i, (lat_i, lng_i) in enumerate(points):
        lat_j, lng_j = points[j]
        xi, yi = lng_i, lat_i
        xj, yj = lng_j, lat_j
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def zona_para_punto(lat, lng):
    if lat is None or lng is None:
        return None

    for zona in Zona.objects.all():
        try:
            polygon = json.loads(zona.area or "[]")
        except (TypeError, ValueError):
            continue
        if _point_in_polygon(lat, lng, polygon):
            return zona
    return None


def zona_para_envio(envio):
    coords = None
    if envio.tipo == "Recojo":
        coords = (envio.latitud_origen, envio.longitud_origen)
    if not coords or coords[0] is None or coords[1] is None:
        coords = (envio.latitud_destino, envio.longitud_destino)
    if coords[0] is None or coords[1] is None:
        coords = (envio.latitud_origen, envio.longitud_origen)
    return zona_para_punto(coords[0], coords[1])

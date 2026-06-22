import math
import requests  # type: ignore
from django.conf import settings  # type: ignore


def encode_polyline(coords: list) -> str:
    """Encode a list of (lat, lng) tuples to Google encoded polyline format."""
    def _enc(v: float) -> str:
        i = round(v * 1e5)
        i = i << 1
        if i < 0:
            i = ~i
        out = []
        while i >= 0x20:
            out.append(chr((0x20 | (i & 0x1f)) + 63))
            i >>= 5
        out.append(chr(i + 63))
        return "".join(out)

    result, prev_lat, prev_lng = [], 0.0, 0.0
    for lat, lng in coords:
        result.append(_enc(lat - prev_lat))
        result.append(_enc(lng - prev_lng))
        prev_lat, prev_lng = lat, lng
    return "".join(result)

# URLs de Google Maps APIs
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


# ============================================================
# 🔹 Función de respaldo: calcula distancia Haversine (sin Google)
# ============================================================
def fallback_distance(lat1, lng1, lat2, lng2):
    """
    Calcula distancia (m) y duración estimada (min) usando fórmula Haversine.
    Asume velocidad promedio de 30 km/h.
    """
    try:
        R = 6371000  # Radio de la Tierra (m)
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lng2 - lng1)

        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        distancia_f: float = float(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
        duracion_calc: float = distancia_f / (30_000.0 / 60.0)  # 30 km/h -> min
        duracion_min: float = float(round(float(duracion_calc), 2))  # type: ignore
        distancia_round: float = float(round(float(distancia_f), 2))  # type: ignore
        return duracion_min, distancia_round
    except Exception as e:
        print(f"[ERROR] fallback_distance: {e}")
        return None, None


# ============================================================
# 🔹 Geocodificación: dirección → coordenadas
# ============================================================
def geocode_address(address: str):
    """
    Convierte una dirección (texto) en coordenadas (lat, lng) usando Google Maps Geocoding API.
    Retorna (lat, lng) o (None, None) si falla.
    """
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None)
    if not api_key or not address:
        return (None, None)

    params = {"address": address, "key": api_key}
    try:
        r = requests.get(GEOCODE_URL, params=params, timeout=10)
        data = r.json()
        if data.get("status") != "OK":
            print(f"[WARNING] Geocode API fallo: {data.get('status')}")
            return (None, None)

        location = data["results"][0]["geometry"]["location"]
        return (location["lat"], location["lng"])
    except Exception as e:
        print(f"[ERROR] geocode_address: {e}")
        return (None, None)


# ============================================================
# 🔹 Métricas de ruta: duración, distancia, polyline
# ============================================================
def get_route_metrics(origin_lat, origin_lng, dest_lat, dest_lng, waypoints=None):
    """
    Obtiene distancia, duración y polyline de Directions API con waypoints opcionales.
    Detecta errores de Google (403, 400, billing, etc.)
    """
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None)
    if not api_key:
        print("[ERROR] No se encontró GOOGLE_MAPS_API_KEY en settings.")
        return (None, None, None)

    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{dest_lat},{dest_lng}",
        "mode": "driving",
        "key": api_key,
    }
    if waypoints:
        params["waypoints"] = "|".join(waypoints)

    try:
        r = requests.get(DIRECTIONS_URL, params=params, timeout=10)

        # 🔍 Si no responde JSON, mostrar mensaje completo
        if r.status_code != 200:
            print(f"[ERROR] Google Directions API status {r.status_code}: {r.text[:300]}")
            return (None, None, None)

        data = r.json()
        if data.get("status") != "OK":
            msg = data.get("error_message", "Respuesta inválida de Directions API")
            print(f"[ERROR] Google Directions API: {msg}")
            return (None, None, None)

        route = data["routes"][0]
        legs = route["legs"]
        duration_sec = sum(leg["duration"]["value"] for leg in legs)
        distance_m = sum(leg["distance"]["value"] for leg in legs)
        polyline = route.get("overview_polyline", {}).get("points")

        print(f"[DEBUG] Directions API OK: {int(distance_m)} m, {int(duration_sec // 60)} min")
        return (int(duration_sec // 60), int(distance_m), polyline)

    except Exception as e:
        print(f"[ERROR] Exception en get_route_metrics: {e}")
        return (None, None, None)



# ============================================================
# 🔹 Genera polyline desde lista de coordenadas ordenadas
# ============================================================
def get_polyline_from_ordered_coords(coords: list[tuple[float, float]], api_key: str):
    """
    Dibuja una ruta en el orden exacto de coords usando Directions API.
    coords: [(lat, lng), ...] en el orden de la ruta
    Retorna: polyline, distancia (m), duración (min)
    """
    if not api_key or len(coords) < 2:
        return None, None, None

    origin = f"{coords[0][0]},{coords[0][1]}"
    destination = f"{coords[-1][0]},{coords[-1][1]}"
    waypoints = [f"{lat},{lng}" for lat, lng in coords[1:-1]]  # type: ignore

    params = {
        "origin": origin,
        "destination": destination,
        "key": api_key,
        "mode": "driving",
        "waypoints": "|".join(waypoints) if waypoints else None
    }
    params = {k: v for k, v in params.items() if v is not None}

    try:
        r = requests.get(DIRECTIONS_URL, params=params, timeout=10).json()
        if r.get("status") != "OK":
            print(f"[WARNING] Error en polyline API: {r.get('status')}")
            # fallback con suma simple
            total_dist, total_dur = 0.0, 0.0
            for i in range(len(coords) - 1):
                dur, dist = fallback_distance(coords[i][0], coords[i][1],
                                              coords[i+1][0], coords[i+1][1])
                if dur and dist:
                    total_dur += dur  # type: ignore
                    total_dist += dist  # type: ignore
            return None, total_dist, total_dur

        route = r["routes"][0]
        legs = route["legs"]
        dur = sum(leg["duration"]["value"] for leg in legs) // 60  # minutos
        dist = sum(leg["distance"]["value"] for leg in legs)       # metros
        polyline = route.get("overview_polyline", {}).get("points")

        return polyline, dist, dur
    except Exception as e:
        print(f"[ERROR] get_polyline_from_ordered_coords: {e}")
        # Fallback básico sin Google
        total_dist, total_dur = 0.0, 0.0
        for i in range(len(coords) - 1):
            dur, dist = fallback_distance(coords[i][0], coords[i][1],
                                          coords[i+1][0], coords[i+1][1])
            if dur and dist:
                total_dur += dur  # type: ignore
                total_dist += dist  # type: ignore
        return None, total_dist, total_dur

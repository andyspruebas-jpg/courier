import math
from typing import List, Dict, Tuple, Optional
from sklearn.cluster import KMeans
from joblib import load
from django.conf import settings
import numpy as np
import os
import requests

# ============================================================
# 🔹 K-MEANS CLUSTERING
# ============================================================
def kmeans_cluster(points: List[Tuple[float, float]], k: Optional[int] = None) -> np.ndarray:
    """
    Agrupa puntos en clusters usando K-Means.
    points: [(lat, lng), ...]
    """
    if not points:
        return np.array([])
    X = np.array(points)
    if not k:
        k = max(1, round(len(points) / 8))  # Regla: ~8 paradas por cluster
    if k >= len(points):
        return np.arange(len(points))  # Cada punto es su propio cluster
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    return km.fit_predict(X)


# ============================================================
# 🔹 MODELO DE RETRASO (árbol de decisión)
# ============================================================
def load_delay_model(filename: str):
    """
    Carga el modelo .joblib desde rutas/models_ai/
    """
    try:
        path = filename if os.path.isabs(filename) else os.path.join(os.path.dirname(__file__), "models_ai", filename)
        print(f"[DEBUG] Intentando cargar modelo desde: {path}")
        return load(path)
    except Exception as e:
        print(f"[WARNING] No se pudo cargar el modelo {filename}: {e}")
        return None


def score_priority(model, feature_rows: List[Dict]) -> List[float]:
    """
    Usa el árbol de decisión para estimar probabilidad de retraso.
    Convierte lista de dicts en matriz numérica.
    """
    if not feature_rows:
        return []
    if model is None:
        return [0.5] * len(feature_rows)  # Prioridad media si no hay modelo

    try:
        # Features = ubicación (lat, lng). Coinciden con las usadas al entrenar
        # el clasificador de retraso (ver rutas/services/ml_trainer.py).
        X = []
        for f in feature_rows:
            lat = float(f.get("lat", 0.0) or 0.0)
            lng = float(f.get("lng", 0.0) or 0.0)
            X.append([lat, lng])
        X = np.array(X)

        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            return proba[:, 1].tolist() if getattr(proba, "ndim", 1) == 2 else model.predict(X).tolist()
        return [float(p) for p in model.predict(X)]

    except Exception as e:
        print(f"[WARNING] Fallo al predecir prioridad: {e}")
        return [0.5] * len(feature_rows)


def _clamp_probability(value, default=0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if math.isnan(number) or math.isinf(number):
        number = default
    return max(0.0, min(1.0, number))


def build_ml_adjusted_cost_matrix(
    time_matrix: np.ndarray,
    labels,
    priorities: List[float],
    priority_weight: float = 0.80,
    cluster_switch_penalty: float = 0.10,
) -> np.ndarray:
    """
    Convierte la matriz de tiempos en una matriz de costo para el optimizador.

    La duración real se sigue calculando con la matriz original; esta matriz solo
    guía el orden: destinos con mayor probabilidad de retraso se vuelven más
    atractivos y los cambios innecesarios de cluster quedan levemente penalizados.
    """
    C = np.array(time_matrix, dtype=float, copy=True)
    if C.ndim != 2 or C.shape[0] != C.shape[1] or C.shape[0] <= 1:
        return C

    n_stops = C.shape[0] - 1
    normalized_priorities = [
        _clamp_probability(priorities[i] if i < len(priorities) else 0.5)
        for i in range(n_stops)
    ]

    for destination_idx, probability in enumerate(normalized_priorities, start=1):
        factor = max(0.20, 1.0 - (priority_weight * probability))
        C[:, destination_idx] *= factor
        C[destination_idx, destination_idx] = 0.0

    if labels is not None:
        labels_list = list(labels)
        if len(labels_list) >= n_stops:
            for origin_idx in range(1, n_stops + 1):
                for destination_idx in range(1, n_stops + 1):
                    if origin_idx == destination_idx:
                        continue
                    if labels_list[origin_idx - 1] != labels_list[destination_idx - 1]:
                        C[origin_idx, destination_idx] *= (1.0 + cluster_switch_penalty)

    return C


# ============================================================
# 🔹 MATRIZ DE TIEMPOS (Google Distance Matrix)
# ============================================================
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

def build_time_matrix_with_google(coords, api_key=None):
    """
    Construye una matriz NxN de tiempos (minutos) entre puntos con Google Distance Matrix API.
    Si hay demasiados puntos, divide en lotes pequeños (máx 10x10).
    """
    if not coords or len(coords) < 2:
        print("[WARNING] build_time_matrix_with_google: muy pocos puntos.")
        return np.zeros((len(coords), len(coords)))

    if not api_key:
        api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None)
    if not api_key:
        print("[ERROR] No se encontró GOOGLE_MAPS_API_KEY en settings.")
        return np.zeros((len(coords), len(coords)))

    n = len(coords)
    M = np.zeros((n, n))
    max_batch = 10  # 🔹 Google recomienda 10x10 o menos para mantener <100 celdas

    for i in range(0, n, max_batch):
        for j in range(0, n, max_batch):
            origins = "|".join([f"{lat},{lng}" for lat, lng in coords[i:i+max_batch]])
            destinations = "|".join([f"{lat},{lng}" for lat, lng in coords[j:j+max_batch]])

            params = {
                "origins": origins,
                "destinations": destinations,
                "mode": "driving",
                "key": api_key,
            }

            try:
                r = requests.get(DISTANCE_MATRIX_URL, params=params, timeout=15)
                if r.status_code != 200:
                    print(f"[ERROR] Distance Matrix API status {r.status_code}: {r.text[:200]}")
                    for ii in range(i, min(i+max_batch, n)):
                        for jj in range(j, min(j+max_batch, n)):
                            M[ii, jj] = 1e6
                    continue

                data = r.json()
                if data.get("status") != "OK":
                    msg = data.get("error_message", data.get("status", "Respuesta inválida"))
                    print(f"[ERROR] Distance Matrix API: {msg}")
                    for ii in range(i, min(i+max_batch, n)):
                        for jj in range(j, min(j+max_batch, n)):
                            M[ii, jj] = 1e6
                    continue

                rows = data.get("rows", [])
                for ii, row in enumerate(rows):
                    for jj, element in enumerate(row["elements"]):
                        if element.get("status") == "OK":
                            M[i+ii, j+jj] = element["duration"]["value"] / 60.0
                        else:
                            M[i+ii, j+jj] = 1e6

            except Exception as e:
                print(f"[ERROR] Excepción en Distance Matrix batch ({i}:{j}): {e}")
                for ii in range(i, min(i+max_batch, n)):
                    for jj in range(j, min(j+max_batch, n)):
                        M[ii, jj] = 1e6

    print(f"[DEBUG] Distance Matrix OK: {n}x{n} elementos (procesado en lotes)")
    return M

# -------------------------------------------------
# Nueva: construir matriz de tiempos usando Haversine
# -------------------------------------------------
def haversine_distance_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def build_time_matrix_haversine(coords: List[Tuple[float, float]], avg_speed_kmh: float = 30.0):
    """
    Crea matriz de tiempos (minutos) aproximada usando distancia Haversine y una velocidad media.
    No llama a Google: rápido y robusto para cálculo del algoritmo local.
    """
    n = len(coords)
    if n == 0:
        return np.zeros((0, 0))
    speed_m_per_min = (avg_speed_kmh * 1000.0) / 60.0
    M = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                M[i, j] = 0.0
            else:
                dist_m = haversine_distance_m(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
                M[i, j] = dist_m / speed_m_per_min
    return M

# ============================================================
# 🔹 HEURÍSTICA TSP: NEAREST NEIGHBOR + 2-OPT
# ============================================================
def nearest_neighbor_route(cost_matrix: np.ndarray) -> List[int]:
    """
    Construye una ruta inicial con Nearest Neighbor.
    Retorna: orden de índices [0, i1, i2, ..., in]
    """
    n = cost_matrix.shape[0]
    if n == 0:
        return []
    unvisited = set(range(1, n))
    route = [0]
    cur = 0
    while unvisited:
        nxt = min(unvisited, key=lambda j: cost_matrix[cur, j])
        route.append(nxt)
        unvisited.remove(nxt)
        cur = nxt
    return route


def two_opt(route: List[int], dist: np.ndarray, max_iter: int = 200) -> List[int]:
    """
    Mejora la ruta aplicando 2-Opt.
    """
    if not route or len(route) < 4:
        return route
    improved = True
    it = 0
    while improved and it < max_iter:
        improved = False
        it += 1
        for a in range(1, len(route) - 2):
            for b in range(a + 1, len(route) - 1):
                i, j, k, l = route[a - 1], route[a], route[b], route[b + 1]
                if i >= dist.shape[0] or j >= dist.shape[0] or k >= dist.shape[0] or l >= dist.shape[0]:
                    continue
                old = dist[i, j] + dist[k, l]
                new = dist[i, k] + dist[j, l]
                if new + 1e-6 < old:
                    route[a:b + 1] = reversed(route[a:b + 1])
                    improved = True
    return route


# ============================================================
# 🔹 PIPELINE PRINCIPAL: COMPUTE ALGORITHMIC ROUTE
# ============================================================
def compute_algorithmic_route(
    origin: Tuple[float, float],
    stops: List[Dict],
    time_matrix: np.ndarray,
    delay_model=None,
    kmeans_model=None
):
    """
    Calcula ruta optimizada:
    - usa kmeans_model.predict si está disponible
    - usa delay_model para prioridades si está
    - time_matrix debe ser provista (puede venir de build_time_matrix_haversine)
    """
    try:
        if not stops or len(stops) < 1:
            return {"order_indices": [], "ordered_stops": [], "end_time_min": 0}

        # 1️⃣ Clustering: usar kmeans_model.predict si está disponible
        pts = [(s["lat"], s["lng"]) for s in stops]
        if kmeans_model is not None:
            try:
                X = np.array(pts)
                labels = kmeans_model.predict(X)
            except Exception as e:
                print(f"[WARN] kmeans.predict falló, fallback clustering: {e}")
                labels = kmeans_cluster(pts)
        else:
            labels = kmeans_cluster(pts) if len(stops) >= 3 else np.zeros(len(stops), dtype=int)

        # 2️⃣ Prioridades (modelo predictivo)
        features = [
            {"lat": s["lat"], "lng": s["lng"], "zona": int(labels[i]),
             "tipo_servicio": s.get("tipo_servicio", "Estandar")}
            for i, s in enumerate(stops)
        ]
        priorities = score_priority(delay_model, features)

        # 3️⃣ Matrices: costo ML para ordenar, tiempo real para métricas
        C = np.array(time_matrix, dtype=float, copy=True)
        if C.size == 0:
            print("[WARNING] Matriz vacía, no se puede calcular ruta.")
            return {"order_indices": [], "ordered_stops": [], "end_time_min": 0}
        C_cost = build_ml_adjusted_cost_matrix(C, labels, priorities)

        # 4️⃣ Ruta inicial y refinamiento
        route0 = nearest_neighbor_route(C_cost)
        route = two_opt(route0, C_cost)

        # 5️⃣ Calcular tiempo total
        total_time = 0.0
        for i in range(len(route) - 1):
            a, b = route[i], route[i + 1]
            if a < C.shape[0] and b < C.shape[0]:
                total_time += C[a, b]

        # 6️⃣ Lista de paradas ordenadas (seguro contra índices)
        ordered_stops = []
        for idx in route[1:]:
            if 0 < idx <= len(stops):
                ordered_stops.append(stops[idx - 1])

        print(f"[DEBUG] compute_algorithmic_route OK: {len(route)} puntos, {int(total_time)} min totales")

        return {
            "order_indices": route,
            "ordered_stops": ordered_stops,
            "end_time_min": int(total_time),
            "cluster_labels": [int(label) for label in labels],
            "delay_priorities": [round(_clamp_probability(p), 4) for p in priorities],
            "ml_cost_applied": True,
        }

    except Exception as e:
        print(f"[ERROR] compute_algorithmic_route(): {e}")
        return {"order_indices": [], "ordered_stops": [], "end_time_min": 0}

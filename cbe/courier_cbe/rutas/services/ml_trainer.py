import os
from datetime import datetime
import numpy as np
from joblib import dump, load
from sklearn.cluster import MiniBatchKMeans
from sklearn.tree import DecisionTreeClassifier
from django.db import transaction


def _build_delay_dataset():
    """Construye (X, y) para el clasificador de retraso a partir de las rutas
    etiquetadas. Features = [lat_inicio, lng_inicio]; etiqueta = 1 si la
    duración real superó la estimada por más de 10 minutos."""
    X, y = [], []
    qs = Ruta.objects.exclude(duracion_real__isnull=True).exclude(duracion_estimada__isnull=True)
    for r in qs:
        if r.latitud_inicio is None or r.longitud_inicio is None:
            continue
        X.append([float(r.latitud_inicio), float(r.longitud_inicio)])
        y.append(1 if (r.duracion_real > (r.duracion_estimada + 10)) else 0)
    return X, y


def _train_delay_classifier():
    """Entrena el árbol de decisión de retrasos. Devuelve True si entrenó."""
    X, y = _build_delay_dataset()
    if len(set(y)) < 2:
        return False  # se necesitan ambas clases (retraso / sin retraso)
    clf = DecisionTreeClassifier(
        max_depth=5,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(np.array(X, dtype=float), np.array(y))
    dump(clf, DELAY_PATH)
    return True

# Importación correcta de `MLTrainingState`
from rutas.models import MLTrainingState
from usuarios.models import UbicacionMensajero
from rutas.models import Ruta  # para extraer etiquetas si existen (duracion_real vs duracion_estimada)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models_ai")
os.makedirs(MODELS_DIR, exist_ok=True)

KMEANS_PATH = os.path.join(MODELS_DIR, "kmeans.joblib")
DELAY_TREE_PATH = os.path.join(MODELS_DIR, "delay_tree.joblib")
DELAY_PATH = DELAY_TREE_PATH

# Heurística: cuantos puntos por cluster (igual que tu regla ~8 paradas por cluster)
def guess_k(n_points):
    return min(64, max(1, round(n_points / 8)))

def get_or_create_state():
    state, _ = MLTrainingState.objects.get_or_create(pk=1)  # single-row state
    return state

def _load_model(path, default=None):
    try:
        return load(path)
    except Exception:
        return default

def _save_model(model, path):
    dump(model, path)

def feed_new_ubicaciones_and_train(minibatch_size=256, min_labelled_for_delay=30):
    """
    Alimenta el ML con las nuevas filas de UbicacionMensajero desde last_processed_datetime/id.
    Actualiza KMeans incrementalmente. Si hay suficientes datos etiquetados
    (rutas con duracion_real), entrena un árbol de decisión para predecir
    retraso (0=no, 1=si).
    Retorna dict con resumen.
    """
    state = get_or_create_state()
    qs = UbicacionMensajero.objects.order_by("fecha_hora")
    if state.last_processed_datetime:
        qs = qs.filter(fecha_hora__gt=state.last_processed_datetime)
    # alternativamente por id si lo prefieres:
    if state.last_processed_id:
        qs = qs.filter(pk__gt=state.last_processed_id)

    total_new = qs.count()
    if total_new == 0:
        # Sin nuevas ubicaciones — aún así reentrenar el clasificador si hay datos suficientes
        X, y = _build_delay_dataset()
        if len(y) >= min_labelled_for_delay and _train_delay_classifier():
            with transaction.atomic():
                state.kmeans_path = state.kmeans_path or KMEANS_PATH
                state.delay_path = DELAY_PATH
                state.save(update_fields=["kmeans_path", "delay_path", "updated_at"])
            return {
                "ok": True,
                "msg": "Sin nuevas ubicaciones. Árbol de decisión de retraso actualizado.",
                "new": 0,
                "delay_model_trained": True,
                "delay_path": DELAY_PATH,
                "delay_model_type": "DecisionTreeClassifier",
            }
        return {"ok": True, "msg": "No hay nuevas ubicaciones para alimentar.", "new": 0}

    # cargar/crear KMeans
    kmeans = _load_model(KMEANS_PATH, None)
    coords = []
    last_dt = state.last_processed_datetime
    last_id = state.last_processed_id
    last_processed = None

    for u in qs.iterator():
        coords.append([float(u.latitud), float(u.longitud)])
        last_dt = u.fecha_hora if (not last_dt or u.fecha_hora > last_dt) else last_dt
        last_id = u.pk
        last_processed = u

    X_new = np.array(coords)
    n_total_points_est = (state.processed_count or 0) + len(X_new)
    k = guess_k(max(1, n_total_points_est))

    # Si no hay modelo, crearlo con k inicial usando el batch completo
    if kmeans is not None and getattr(kmeans, "n_clusters", k) != k:
        kmeans = None

    if not kmeans:
        kmeans = MiniBatchKMeans(n_clusters=k, batch_size=minibatch_size, random_state=42)
        # Si tenemos muchos puntos, inicial fit con una muestra
        if X_new.shape[0] >= k:
            kmeans.partial_fit(X_new)
        else:
            # si aún no hay suficientes puntos, fit con X_new (aceptable para inicio)
            kmeans = MiniBatchKMeans(n_clusters=max(1, X_new.shape[0]), batch_size=minibatch_size, random_state=42)
            kmeans.fit(X_new)
    else:
        # Si k cambió, re-init el modelo (opcional). Aquí hacemos partial_fit.
        try:
            kmeans.partial_fit(X_new)
        except Exception:
            # fallback: reentrenar desde cero con todos los datos si tienes acceso (costoso)
            kmeans = MiniBatchKMeans(n_clusters=k, batch_size=minibatch_size, random_state=42)
            kmeans.partial_fit(X_new)

    _save_model(kmeans, KMEANS_PATH)

    # --- Supervisado: árbol de decisión de retraso ---
    # Features = [lat_inicio, lng_inicio]; etiqueta = retraso > 10 min.
    _, labeled_y = _build_delay_dataset()

    delay_trained = False
    if len(labeled_y) >= min_labelled_for_delay:
        delay_trained = _train_delay_classifier()
    else:
        # no hay suficientes etiquetas; no entrenamos el modelo supervisado
        pass

    # actualizar estado
    with transaction.atomic():
        state.last_processed_datetime = last_dt
        state.last_processed_id = last_id
        state.processed_count = (state.processed_count or 0) + len(X_new)
        state.kmeans_path = KMEANS_PATH
        state.delay_path = DELAY_PATH
        state.save()

    return {
        "ok": True,
        "new": len(X_new),
        "k": k,
        "kmeans_path": KMEANS_PATH,
        "delay_model_trained": delay_trained,
        "delay_path": DELAY_PATH,
        "delay_model_type": "DecisionTreeClassifier" if delay_trained else None,
        "processed_count": state.processed_count,
        "last_processed_datetime": state.last_processed_datetime,
        "last_processed_id": state.last_processed_id,
    }

def load_model_route_ai():
    try:
        # Suponiendo que el modelo esté guardado en el directorio 'models_ai'
        model_path = 'models_ai/your_model_name.joblib'
        model = load(model_path)
        return model
    except Exception as e:
        print(f"Error al cargar el modelo: {e}")
        return None

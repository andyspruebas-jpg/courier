# rutas/ml/cluster_zonas.py (opcional)
import numpy as np
from sklearn.cluster import KMeans
from rutas.models import Ruta

def run_kmeans(n_clusters=6):
    data = Ruta.objects.exclude(latitud_fin__isnull=True).values_list("latitud_fin","longitud_fin")
    X = np.array(list(data))
    if len(X) < n_clusters:
        return
    km = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42).fit(X)
    # Asignar cluster
    for idx, (lat, lng) in enumerate(X):
        Ruta.objects.filter(
            latitud_fin=lat, longitud_fin=lng
        ).update(zona_asignada=int(km.labels_[idx]))

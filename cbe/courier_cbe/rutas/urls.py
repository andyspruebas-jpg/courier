from django.urls import path
from . import views
from .api import marcar_evento_ruta

app_name = 'rutas'

urlpatterns = [
    # ===============================
    # 🌐 VISTAS HTML
    # ===============================
    path("", views.lista_rutas, name="lista_rutas"),
    path("optimizar/<int:mensajero_id>/", views.optimizar_rutas, name="optimizar_rutas"),
    path("<int:ruta_id>/", views.ver_ruta, name="ver_ruta"),

    # ===============================
    # 🟢 ENDPOINTS JSON PARA FLUTTER
    # ===============================

    # 🔹 Listado de mensajeros activos
    path("api/mensajeros-json/", views.mensajeros_json, name="mensajeros_json"),

    # 🔹 Listado de mensajeros que tienen rutas creadas
    path("api/mensajeros-con-rutas/", views.mensajeros_con_rutas, name="mensajeros_con_rutas"),

    # 🔹 Rutas de un mensajero específico (por ID)
    path("api/rutas-json/<int:mensajero_id>/", views.rutas_json, name="rutas_json"),

    # 🔹 Todas las rutas registradas (sin ID)
    path("api/rutas-json/", views.rutas_api_json, name="rutas_api_json"),

    # 🔹 Nueva API de detalle de ruta (comparación Google vs Algoritmo)
    path("api/ruta-detalle/<int:mensajero_id>/", views.ruta_detalle_flutter, name="ruta_detalle_flutter"),
    path("api/tramo/", views.tramo_navegacion_flutter, name="tramo_navegacion_flutter"),
    path("api/optimizar/<int:mensajero_id>/", views.api_optimizar_ruta, name="api_optimizar_ruta"),

    # ===============================
    # 🤖 ENDPOINT DE MODELO ML
    # ===============================
    path("alimentar-ml/", views.alimentar_ml, name="alimentar_ml"),
    path("api/<int:ruta_id>/evento/", marcar_evento_ruta, name="marcar_evento_ruta"),
]

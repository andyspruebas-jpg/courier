from django.urls import path
from . import views
from .views import ver_firma

app_name = 'envios'

urlpatterns = [
    # ========================================================
    # Rutas para envíos
    # ========================================================
    path('', views.lista_envios, name='lista_envios'),  # Lista de envíos (página principal)
    path('envios/crear/', views.crear_envio, name='crear_envio'),  # Crear un nuevo envío
    path('envios/<int:envio_id>/', views.ver_envio, name='ver_envio'),  # Ver detalles de un envío
    path('envios/<int:envio_id>/editar/', views.editar_envio, name='editar_envio'),  # Editar un envío
    path('envios/<int:envio_id>/eliminar/', views.eliminar_envio, name='eliminar_envio'),  # Eliminar un envío
    path('solicitar/', views.solicitar_envio, name='solicitar_envio'),
    path('seguimiento/', views.seguimiento_envio, name='seguimiento_envio'),
    path('seguimiento/<str:numero>/', views.seguimiento_detalle, name='seguimiento_detalle'),
    path('api/seguimiento/<str:numero>/', views.seguimiento_api, name='seguimiento_api'),
    path('envios/<int:envio_id>/reasignar/', views.reasignar_envio, name='reasignar_envio'),
    path('reportes/', views.reportes_operativos, name='reportes_operativos'),
    path('reportes/excel/', views.reportes_excel, name='reportes_excel'),
    path('reportes/pdf/', views.reportes_pdf, name='reportes_pdf'),

    # ========================================================
    # Rutas para entregas
    # ========================================================
    path('entregas/', views.lista_entregas, name='lista_entregas'),  # Lista de entregas
    path('entregas/crear/<int:envio_id>/', views.registrar_entrega, name='registrar_entrega'),  # Registrar nueva entrega
    path('entregas/<int:entrega_id>/', views.ver_entrega, name='ver_entrega'),  # Ver detalles de una entrega
    path('entregas/<int:entrega_id>/editar/', views.editar_entrega, name='editar_entrega'),  # Editar una entrega
    path('entregas/<int:entrega_id>/eliminar/', views.eliminar_entrega, name='eliminar_entrega'),  # Eliminar una entrega

    # ========================================================
    # Firma cifrada (descifrada al vuelo)
    # ========================================================
    path('entregas/<int:entrega_id>/firma/', views.ver_firma, name='ver_firma'),

    # ========================================================
    # 🔹 Nueva ruta: Detalle de entrega (API / web)
    # ========================================================
    path('api/entregas/<int:entrega_id>/', views.ver_entrega, name='api_ver_entrega'),

    # ========================================================
    # Rutas para historial
    # ========================================================
    path('envios/<int:envio_id>/historial/', views.historial_envio, name='historial_envio'),  # Ver historial de un envío
    path('envios/<int:envio_id>/historial/<int:evento_id>/', views.ver_evento_historial, name='ver_evento_historial'),

    # ========================================================
    # Rutas para incidentes
    # ========================================================
    path('envios/<int:envio_id>/incidentes/', views.registrar_incidente, name='registrar_incidente'),
    path('envios/<int:envio_id>/incidentes/<int:incidente_id>/', views.ver_incidente, name='ver_incidente'),
    path('envios/<int:envio_id>/incidentes/<int:incidente_id>/editar/', views.editar_incidente, name='editar_incidente'),
    path('envios/<int:envio_id>/incidentes/<int:incidente_id>/eliminar/', views.eliminar_incidente, name='eliminar_incidente'),

    # ========================================================
    # API JSON endpoints
    # ========================================================
    path('entregas-json/', views.entregas_api_json, name='entregas_api_json'),
    path('envios-pendientes-json/', views.envios_pendientes_json, name='envios_pendientes_json'),
    path('envios-json/', views.envios_json, name='envios_json'),
    path('api/envios/crear/', views.api_crear_envio, name='api_crear_envio'),  # ✅ NUEVO ENDPOINT CREAR ENVÍO
    # 📱 Confirmación de entrega desde la app móvil (foto/firma/observaciones)
    path('api/entregas/registrar/<int:envio_id>/', views.api_registrar_entrega, name='api_registrar_entrega'),
    # 📱 Registro de incidencias desde la app móvil (tipo/descripción/foto)
    path('api/incidentes/registrar/<int:envio_id>/', views.api_registrar_incidente, name='api_registrar_incidente'),
]

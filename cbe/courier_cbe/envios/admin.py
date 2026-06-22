from django.contrib import admin
from .models import Envio, Entrega, HistorialEnvio, Incidente, NotificacionEnvio, ReasignacionEnvio

# Registrar los modelos en el panel de administración
admin.site.register(Envio)
admin.site.register(Entrega)
admin.site.register(HistorialEnvio)
admin.site.register(Incidente)
admin.site.register(NotificacionEnvio)
admin.site.register(ReasignacionEnvio)

from django.contrib import admin
from .models import MLTrainingState, Ruta, RutaParada

admin.site.register(Ruta)
admin.site.register(RutaParada)
admin.site.register(MLTrainingState)

from django.db import models
from usuarios.models import Usuario
from rutas.models import Ruta

# Modelo de Ubicaciones de Mensajeros
class UbicacionMensajero(models.Model):
    mensajero = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    ruta = models.ForeignKey(Ruta, on_delete=models.SET_NULL, null=True, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)
    fecha_hora = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ubicación Mensajero {self.mensajero.nombre} - Ruta {self.ruta}"

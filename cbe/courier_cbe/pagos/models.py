from django.db import models
from envios.models import Envio
from usuarios.models import Usuario

# Modelo de Métodos de Pago
class MetodoPago(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

# Modelo de Pagos
class Pago(models.Model):
    envio = models.OneToOneField(Envio, on_delete=models.CASCADE)
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=[('Pendiente', 'Pendiente'), ('Pagado', 'Pagado')])
    fecha_pago = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagos_registrados",
    )

    def __str__(self):
        return f"Pago {self.id} - Envío {self.envio.id}"

from django.db import models
from django.core.files import File
from io import BytesIO
import qrcode
import uuid
from usuarios.models import Usuario
from utils.storage import PrivateEncryptedStorage  # ✅ Se importa la clase real, no un string


def generar_numero_seguimiento():
    return f"CBE-{uuid.uuid4().hex[:10].upper()}"


# ===============================
# 📦 MODELO ENVÍO
# ===============================
class Envio(models.Model):
    numero_seguimiento = models.CharField(
        max_length=24,
        unique=True,
        default=generar_numero_seguimiento,
        db_index=True,
    )

    tipo = models.CharField(
        max_length=15,
        choices=[('Recojo', 'Recojo'), ('Envío', 'Envío')],
        default='Envío'
    )

    remitente = models.ForeignKey(
        Usuario,
        related_name='remitente',
        on_delete=models.CASCADE,
        null=True, blank=True
    )

    remitente_nombre = models.CharField(max_length=150)
    remitente_telefono = models.CharField(max_length=20)

    destinatario_nombre = models.CharField(max_length=150)
    destinatario_telefono = models.CharField(max_length=20)

    origen_direccion = models.TextField()
    destino_direccion = models.TextField()

    peso = models.DecimalField(max_digits=10, decimal_places=2)
    tipo_servicio = models.CharField(
        max_length=15,
        choices=[('Estándar', 'Estándar'), ('Express', 'Express')]
    )

    estado = models.CharField(
        max_length=15,
        default='Pendiente',
        choices=[
            ('Pendiente', 'Pendiente'),
            ('En Ruta', 'En Ruta'),
            ('Entregado', 'Entregado'),
            ('Rechazado', 'Rechazado'),
            ('Fallido', 'Fallido'),
            ('Reintentado', 'Reintentado'),
            ('Cancelado', 'Cancelado'),
        ]
    )

    observaciones = models.TextField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    ruta_id = models.IntegerField(null=True, blank=True)

    latitud_origen = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    longitud_origen = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    latitud_destino = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    longitud_destino = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)

    monto_pago = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tipo_pago = models.CharField(
        max_length=15,
        choices=[('Origen', 'Origen'), ('Destino', 'Destino'), ('Pendiente', 'Pendiente')]
    )

    mensajero = models.ForeignKey(
        Usuario,
        related_name='mensajero',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    zona = models.ForeignKey(
        "zonas.Zona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="envios",
    )
    orden_ruta = models.PositiveIntegerField(null=True, blank=True)
    eta_min = models.FloatField(null=True, blank=True)

    # 🆕 Código QR generado automáticamente
    qr_code = models.ImageField(upload_to='qrcodes/', null=True, blank=True)

    def __str__(self):
        return f"Envío {self.numero_seguimiento} - {self.destinatario_nombre}"

    @property
    def estado_publico(self):
        estado = (self.estado or "").lower()
        if estado == "pendiente":
            return "En recepción"
        if estado in ("en ruta", "reintentado"):
            return "En tránsito"
        if estado == "entregado":
            return "Entregado"
        if estado in ("rechazado", "fallido", "cancelado"):
            return self.estado
        return "Registrado"

    # 🔹 Generar código QR automáticamente al guardar
    def save(self, *args, **kwargs):
        if not self.numero_seguimiento:
            self.numero_seguimiento = generar_numero_seguimiento()

        if self.latitud_destino or self.latitud_origen:
            try:
                from zonas.services import zona_para_envio

                zona = zona_para_envio(self)
                if zona and self.zona_id != zona.id:
                    self.zona = zona
                    update_fields = kwargs.get("update_fields")
                    if update_fields is not None:
                        kwargs["update_fields"] = list(set(update_fields) | {"zona"})
            except Exception:
                pass

        super().save(*args, **kwargs)  # Guarda primero para obtener ID

        if not self.qr_code:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=8,
                border=3,
            )
            qr.add_data(f"http://127.0.0.1:8000/envios/{self.id}/")
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            file_name = f'envio_{self.id}_qr.png'
            self.qr_code.save(file_name, File(buffer), save=False)

            super().save(update_fields=['qr_code'])


# ===============================
# 📬 MODELO ENTREGA
# ===============================
class Entrega(models.Model):
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE)
    mensajero = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    fecha_entrega = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=15,
        choices=[('Entregado', 'Entregado'), ('Rechazado', 'Rechazado')]
    )

    # 🔐 Firma protegida con almacenamiento cifrado
    firma = models.ImageField(
        upload_to='entregas/',
        null=True,
        blank=True,
        storage=PrivateEncryptedStorage(),  # ✅ Instancia real, no string
    )

    # 📷 Fotografía de evidencia de la entrega (también cifrada)
    foto = models.ImageField(
        upload_to='entregas/',
        null=True,
        blank=True,
        storage=PrivateEncryptedStorage(),
    )

    # 📝 Observaciones/notas que registra el mensajero al cerrar la entrega
    observaciones = models.TextField(null=True, blank=True)

    pagado = models.BooleanField(default=False)

    def __str__(self):
        return f"Entrega {self.id} - {self.envio.destinatario_nombre}"


# ===============================
# 🕓 MODELO HISTORIAL DE ENVÍOS
# ===============================
class HistorialEnvio(models.Model):
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE)
    tipo_evento = models.CharField(
        max_length=20,
        choices=[
            ('Actualizado', 'Actualizado'),
            ('Creado', 'Creado'),
            ('Asignado', 'Asignado'),
            ('Recogido', 'Recogido'),
            ('Entregado', 'Entregado'),
            ('Incidente', 'Incidente'),
            ('Reasignado', 'Reasignado'),
            ('Notificado', 'Notificado'),
            ('Cancelado', 'Cancelado'),
        ]
    )
    fecha_evento = models.DateTimeField(auto_now_add=True)
    ubicacion_latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    ubicacion_longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_envio",
    )
    observaciones = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Evento {self.tipo_evento} - Envío {self.envio.id}"


# ===============================
# ⚠️ MODELO INCIDENTE
# ===============================
class Incidente(models.Model):
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE)
    tipo = models.CharField(
        max_length=20,
        choices=[
            ('Retraso', 'Retraso'),
            ('Daño', 'Daño'),
            ('Pérdida', 'Pérdida'),
            ('Otro', 'Otro')
        ],
        null=True,
        blank=True
    )
    descripcion = models.TextField(null=True, blank=True)
    # 📷 Fotografía de evidencia del incidente (cifrada en disco)
    foto = models.ImageField(
        upload_to='incidentes/',
        null=True,
        blank=True,
        storage=PrivateEncryptedStorage(),
    )
    fecha_reporte = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=15,
        default='Pendiente',
        choices=[
            ('Pendiente', 'Pendiente'),
            ('Resuelto', 'Resuelto')
        ],
        null=True,
        blank=True
    )

    def __str__(self):
        return f"Incidente {self.tipo or 'Sin tipo'} - Envío {self.envio.id}"


class NotificacionEnvio(models.Model):
    CANALES = [
        ("email", "Correo"),
        ("push", "Push"),
        ("sms", "SMS"),
        ("sistema", "Sistema"),
    ]
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("enviada", "Enviada"),
        ("fallida", "Fallida"),
    ]

    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name="notificaciones")
    destinatario = models.CharField(max_length=180)
    canal = models.CharField(max_length=20, choices=CANALES, default="sistema")
    asunto = models.CharField(max_length=180)
    mensaje = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    creado_en = models.DateTimeField(auto_now_add=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.canal} {self.estado} - {self.envio.numero_seguimiento}"


class ReasignacionEnvio(models.Model):
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name="reasignaciones")
    mensajero_anterior = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reasignaciones_salientes",
    )
    mensajero_nuevo = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="reasignaciones_entrantes",
    )
    responsable = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reasignaciones_realizadas",
    )
    motivo = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reasignación {self.envio.numero_seguimiento} -> {self.mensajero_nuevo.nombre}"

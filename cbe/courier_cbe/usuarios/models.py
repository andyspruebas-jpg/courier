import uuid
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class Empresa(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    nit = models.CharField(max_length=30, unique=True)
    direccion = models.CharField(max_length=255)
    contacto = models.CharField(max_length=150, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    activa = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Rol(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

class Usuario(models.Model):
    nombre = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    contrasena = models.CharField(max_length=255)  # Contraseña cifrada
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE)
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="usuarios",
    )
    is_active = models.BooleanField(default=True)  # Usuario activo

    def __str__(self):
        return self.nombre

    def check_password(self, password):
        # Verifica si la contraseña proporcionada coincide con la almacenada
        return check_password(password, self.contrasena)

    def set_password(self, password):
        # Cifra la contraseña antes de guardarla
        self.contrasena = make_password(password)

class PerfilMensajero(models.Model):
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.CASCADE,
        related_name="perfil_mensajero"
    )
    foto = models.ImageField(upload_to="mensajeros/", null=True, blank=True)
    latitud = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    longitud = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    vehiculo = models.CharField(max_length=80, blank=True, null=True)
    zona_cobertura = models.ForeignKey(
        "zonas.Zona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensajeros",
    )
    zona_cobertura_secundaria = models.ForeignKey(
        "zonas.Zona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensajeros_secundarios",
    )
    disponible = models.BooleanField(default=True)

    @property
    def zona_ids(self):
        return [
            zona_id
            for zona_id in (
                self.zona_cobertura_id,
                self.zona_cobertura_secundaria_id,
            )
            if zona_id is not None
        ]

    def __str__(self):
        return f"Perfil de {self.usuario.nombre} (Mensajero)"


class UbicacionMensajero(models.Model):
    mensajero = models.ForeignKey(
        'Usuario', on_delete=models.CASCADE, related_name="ubicaciones"
    )
    latitud = models.DecimalField(max_digits=20, decimal_places=15)
    longitud = models.DecimalField(max_digits=20, decimal_places=15)
    fecha_hora = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mensajero.nombre} - {self.fecha_hora}"


class PasswordResetToken(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.expira_en:
            self.expira_en = timezone.now() + timedelta(minutes=30)  # 30 min
        if not self.token:
            self.token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def expirado(self):
        return timezone.now() > self.expira_en

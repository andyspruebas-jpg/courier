from __future__ import annotations
from typing import Optional
from django.db import models  # type: ignore
from usuarios.models import Usuario  # type: ignore
from envios.models import Envio  # type: ignore


class MLTrainingState(models.Model):
    """
    Estado del entrenamiento incremental de rutas. La migración inicial ya crea
    esta tabla; mantener el modelo aquí hace que Django lo registre.
    """
    last_processed_id = models.BigIntegerField(null=True, blank=True)
    last_processed_datetime = models.DateTimeField(null=True, blank=True)
    processed_count = models.PositiveIntegerField(default=0)
    kmeans_path = models.CharField(max_length=255, null=True, blank=True)
    delay_path = models.CharField(max_length=255, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"MLState processed={self.processed_count} updated={self.updated_at}"


class Ruta(models.Model):
    mensajero = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, null=True, blank=True)
    latitud_inicio = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    longitud_inicio = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    latitud_fin = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    longitud_fin = models.DecimalField(max_digits=20, decimal_places=15, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    # Campos para métricas / polylines (necesarios para persistir la ruta algoritmo)
    polyline_google = models.TextField(null=True, blank=True)
    polyline_algo = models.TextField(null=True, blank=True)
    distancia_google_m = models.FloatField(null=True, blank=True)
    duracion_google_min = models.FloatField(null=True, blank=True)
    distancia_algo_m = models.FloatField(null=True, blank=True)
    duracion_algo_min = models.FloatField(null=True, blank=True)

    # campo para almacenar la diferencia (minutos) algoritmo - google
    retraso_estimado = models.FloatField(null=True, blank=True, help_text="Minutos: algoritmo - google")
    zona_asignada = models.IntegerField(null=True, blank=True)
    duracion_estimada = models.FloatField(null=True, blank=True)
    duracion_real = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.envio:
            return f"Ruta {self.id} - Mensajero {self.mensajero} (Envio {self.envio.id})"
        return f"Ruta {self.id} - Mensajero {self.mensajero} (Resumen)"

    def set_coords_from_envio(self):
        """
        Rellena latitud_inicio/longitud_inicio y latitud_fin/longitud_fin desde el envio
        si están disponibles (no persiste; se espera que el save lo haga).
        """
        try:
            if not self.envio:
                return
            # Origen (recojo) / Destino (entrega)
            if getattr(self.envio, "latitud_origen", None) and getattr(self.envio, "longitud_origen", None):
                self.latitud_inicio = self.envio.latitud_origen
                self.longitud_inicio = self.envio.longitud_origen
            if getattr(self.envio, "latitud_destino", None) and getattr(self.envio, "longitud_destino", None):
                self.latitud_fin = self.envio.latitud_destino
                self.longitud_fin = self.envio.longitud_destino
        except Exception:
            pass

    def infer_retraso_simple(self) -> Optional[float]:
        """
        Devuelve diferencia de retraso en minutos. Prioriza duración real vs.
        estimada; si no existe, usa algoritmo vs. Google.
        """
        try:
            g: Optional[float] = self.duracion_estimada or self.duracion_google_min
            a: Optional[float] = self.duracion_real or self.duracion_algo_min
            if g is None or a is None:
                return None
            diff: float = a - g
            result: float = round(diff, 2)
            return result
        except Exception:
            return None

    def recompute_real_duration_from_timestamps(self) -> Optional[float]:
        if not self.started_at or not self.finished_at:
            return None
        seconds = (self.finished_at - self.started_at).total_seconds()
        self.duracion_real = round(max(seconds, 0) / 60.0, 2)
        return self.duracion_real


class RutaParada(models.Model):
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name="paradas")
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name="paradas_ruta")
    orden = models.PositiveIntegerField()
    eta_min = models.FloatField(null=True, blank=True)
    distancia_desde_anterior_m = models.FloatField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["orden"]
        unique_together = ("ruta", "envio")

    def __str__(self):
        return f"Ruta {self.ruta_id} parada {self.orden} envio {self.envio_id}"

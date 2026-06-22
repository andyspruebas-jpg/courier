# rutas/signals.py
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Ruta
from .services.google_maps import get_route_metrics

def model_has_field(instance, name):
    try:
        return any(getattr(f, "name", None) == name for f in instance._meta.get_fields())
    except Exception:
        return False

@receiver(pre_save, sender=Ruta)
def rutas_set_coords_and_google_estimate(sender, instance: Ruta, **kwargs):
    # Si viene con Envio, llena coords (si están vacías)
    if instance.envio:
        # Solo si no están definidas aún
        if instance.latitud_inicio is None or instance.longitud_inicio is None \
           or instance.latitud_fin is None or instance.longitud_fin is None:
            # método del modelo (si existe)
            if hasattr(instance, "set_coords_from_envio"):
                try:
                    instance.set_coords_from_envio()
                except Exception:
                    pass

    # Si hay coords completas, pide métricas a Google (asigna solo si el modelo tiene esos campos)
    if all([
        instance.latitud_inicio is not None, instance.longitud_inicio is not None,
        instance.latitud_fin is not None, instance.longitud_fin is not None
    ]):
        try:
            dur_min, dist_m, poly = get_route_metrics(
                str(instance.latitud_inicio), str(instance.longitud_inicio),
                str(instance.latitud_fin), str(instance.longitud_fin)
            )
        except Exception:
            dur_min, dist_m, poly = None, None, None

        if dur_min is not None:
            if model_has_field(instance, "duracion_google_min"):
                setattr(instance, "duracion_google_min", dur_min)
            else:
                # guarda en atributo temporal para debugging (no se persiste si no existe columna)
                instance._duracion_google_min = dur_min

        if dist_m is not None:
            if model_has_field(instance, "distancia_google_m"):
                setattr(instance, "distancia_google_m", dist_m)
            else:
                instance._distancia_google_m = dist_m

        if poly:
            # polyline_google suele existir pero comprobamos
            if model_has_field(instance, "polyline_google"):
                setattr(instance, "polyline_google", poly)
            else:
                instance._polyline_google = poly

@receiver(post_save, sender=Ruta)
def rutas_infer_delay(sender, instance: Ruta, **kwargs):
    # Llamar al infer simple si existe (de forma segura)
    retraso = None
    if hasattr(instance, "infer_retraso_simple"):
        try:
            retraso = instance.infer_retraso_simple()
        except Exception:
            retraso = None

    # Si se obtuvo un retraso, guardarlo solo si el modelo tiene la columna correspondiente
    if retraso is not None and model_has_field(instance, "retraso_estimado"):
        try:
            Ruta.objects.filter(pk=instance.pk).update(retraso_estimado=retraso)
        except Exception:
            # no hacer nada si la actualización falla
            pass

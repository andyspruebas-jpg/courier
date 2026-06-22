from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from rutas.services.optimization import rebuild_route_for_messenger
from usuarios.models import Usuario

from .models import Envio


ROUTE_INTERNAL_FIELDS = {"orden_ruta", "eta_min", "ruta_id", "qr_code", "zona"}
ROUTE_RELEVANT_FIELDS = {
    "mensajero",
    "mensajero_id",
    "estado",
    "tipo",
    "origen_direccion",
    "destino_direccion",
    "latitud_origen",
    "longitud_origen",
    "latitud_destino",
    "longitud_destino",
}


def _update_fields_set(update_fields):
    if update_fields is None:
        return None
    return {str(field) for field in update_fields}


def mensajero_disponible_para_zona(zona_id):
    if not zona_id:
        return None
    return (
        Usuario.objects.filter(
            rol__nombre__iexact="mensajero",
            is_active=True,
        )
        .filter(
            Q(perfil_mensajero__zona_cobertura_id=zona_id)
            | Q(perfil_mensajero__zona_cobertura_secundaria_id=zona_id)
        )
        .annotate(
            carga_activa=Count(
                "mensajero",
                filter=Q(mensajero__estado__in=["Pendiente", "En Ruta"]),
            )
        )
        .order_by("carga_activa", "id")
        .first()
    )


@receiver(pre_save, sender=Envio)
def recordar_mensajero_anterior(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_mensajero_id = None
        return
    instance._previous_mensajero_id = (
        Envio.objects.filter(pk=instance.pk)
        .values_list("mensajero_id", flat=True)
        .first()
    )


@receiver(post_save, sender=Envio)
def recalcular_ruta_por_envio(sender, instance, created, update_fields=None, **kwargs):
    if getattr(settings, "DISABLE_ROUTE_RECALCULATION_SIGNALS", False):
        return

    # La zona manda sobre la asignación: un mensajero nunca debe recibir
    # recojos o entregas fuera de su zona de cobertura.
    if instance.mensajero_id:
        zonas_mensajero = set(
            Usuario.objects.filter(pk=instance.mensajero_id)
            .values_list(
                "perfil_mensajero__zona_cobertura_id",
                "perfil_mensajero__zona_cobertura_secundaria_id",
            )
            .first()
            or []
        )
    else:
        zonas_mensajero = set()
    zonas_mensajero.discard(None)
    if instance.zona_id and instance.zona_id not in zonas_mensajero:
        mensajero_correcto = mensajero_disponible_para_zona(instance.zona_id)
        if mensajero_correcto:
            Envio.objects.filter(pk=instance.pk).update(mensajero=mensajero_correcto)
            instance.mensajero = mensajero_correcto

    fields = _update_fields_set(update_fields)
    if fields is not None:
        if fields and fields.issubset(ROUTE_INTERNAL_FIELDS):
            return
        if fields and fields.isdisjoint(ROUTE_RELEVANT_FIELDS):
            return

    mensajero_ids = {
        instance.mensajero_id,
        getattr(instance, "_previous_mensajero_id", None),
    }
    mensajero_ids.discard(None)
    if not mensajero_ids:
        return

    def _rebuild_routes():
        for mensajero in Usuario.objects.filter(
            pk__in=mensajero_ids,
            rol__nombre__iexact="mensajero",
            is_active=True,
        ):
            try:
                rebuild_route_for_messenger(mensajero)
            except Exception:
                pass

    transaction.on_commit(_rebuild_routes)

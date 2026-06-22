from decimal import Decimal, InvalidOperation

from django.utils import timezone

from pagos.models import MetodoPago, Pago
from usuarios.security import is_admin
from usuarios.models import Usuario

from .models import (
    Entrega,
    Envio,
    HistorialEnvio,
    Incidente,
    NotificacionEnvio,
    ReasignacionEnvio,
)


MODALIDADES_PAGO = {"Origen", "Destino", "Pendiente"}
ESTADOS_ENTREGA = {"Entregado", "Rechazado"}
TIPOS_INCIDENTE = {"Retraso", "Daño", "Pérdida", "Otro"}


def normalizar_modalidad_pago(value):
    raw = (value or "").strip().lower()
    for modalidad in MODALIDADES_PAGO:
        if raw == modalidad.lower():
            return modalidad
    return None


def crear_notificacion(envio, asunto, mensaje, destinatario="", canal="sistema", usuario=None):
    notif = NotificacionEnvio.objects.create(
        envio=envio,
        destinatario=destinatario or envio.destinatario_nombre,
        canal=canal,
        asunto=asunto,
        mensaje=mensaje,
        estado="enviada" if canal == "sistema" else "pendiente",
        enviado_en=timezone.now() if canal == "sistema" else None,
    )
    HistorialEnvio.objects.create(
        envio=envio,
        tipo_evento="Notificado",
        usuario=usuario,
        observaciones=f"{asunto}: {mensaje[:180]}",
    )
    return notif


def usuario_puede_operar_envio(usuario, envio):
    if not usuario:
        return False
    if is_admin(usuario):
        return True
    return envio.mensajero_id == usuario.id


def _resolver_mensajero(envio, usuario=None, mensajero_id=None):
    if usuario and not is_admin(usuario):
        return usuario
    if envio.mensajero_id:
        return envio.mensajero
    if mensajero_id:
        return Usuario.objects.filter(pk=mensajero_id, rol__nombre__iexact="mensajero", is_active=True).first()
    return None


def _parse_monto(value, fallback):
    try:
        if value in (None, ""):
            return fallback if fallback is not None else Decimal("0")
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return fallback if fallback is not None else Decimal("0")


def registrar_entrega_operativa(
    *,
    envio,
    usuario=None,
    estado,
    mensajero_id=None,
    modalidad_pago=None,
    monto=None,
    observaciones="",
    firma=None,
    foto=None,
    latitud=None,
    longitud=None,
):
    estado = (estado or "").strip()
    if estado not in ESTADOS_ENTREGA:
        raise ValueError("El estado debe ser 'Entregado' o 'Rechazado'.")

    mensajero = _resolver_mensajero(envio, usuario=usuario, mensajero_id=mensajero_id)
    if mensajero is None:
        raise ValueError("No se pudo determinar el mensajero de la entrega.")

    modalidad = normalizar_modalidad_pago(modalidad_pago)
    if estado == "Entregado" and modalidad is None:
        raise ValueError("Debe definir la modalidad de pago: Origen, Destino o Pendiente.")

    observaciones = (observaciones or "").strip()
    pagado = modalidad in {"Origen", "Destino"}

    entrega = Entrega(
        envio=envio,
        mensajero=mensajero,
        estado=estado,
        pagado=pagado,
        observaciones=observaciones or None,
    )
    if firma:
        entrega.firma = firma
    if foto:
        entrega.foto = foto
    entrega.save()

    envio.estado = "Entregado" if estado == "Entregado" else "Rechazado"
    update_fields = ["estado"]
    if observaciones:
        envio.observaciones = observaciones
        update_fields.append("observaciones")

    if modalidad:
        monto_final = _parse_monto(monto, envio.monto_pago)
        metodo, _ = MetodoPago.objects.get_or_create(nombre="Efectivo")
        Pago.objects.update_or_create(
            envio=envio,
            defaults={
                "metodo_pago": metodo,
                "monto": monto_final,
                "estado": "Pagado" if pagado else "Pendiente",
                "registrado_por": usuario,
            },
        )
        envio.tipo_pago = modalidad
        update_fields.append("tipo_pago")
        if envio.monto_pago != monto_final:
            envio.monto_pago = monto_final
            update_fields.append("monto_pago")

    envio.save(update_fields=list(dict.fromkeys(update_fields)))

    HistorialEnvio.objects.create(
        envio=envio,
        tipo_evento="Entregado" if estado == "Entregado" else "Incidente",
        ubicacion_latitud=latitud or None,
        ubicacion_longitud=longitud or None,
        usuario=usuario,
        observaciones=observaciones or None,
    )
    crear_notificacion(
        envio,
        "Estado de envío actualizado",
        f"El envío {envio.numero_seguimiento} cambió a {envio.estado}.",
        usuario=usuario,
    )

    try:
        from rutas.services.optimization import rebuild_route_for_messenger

        rebuild_route_for_messenger(mensajero)
    except Exception:
        pass

    return entrega


def registrar_incidente_operativo(
    *,
    envio,
    usuario=None,
    tipo=None,
    descripcion="",
    foto=None,
    latitud=None,
    longitud=None,
):
    tipo = (tipo or "Otro").strip()
    if tipo not in TIPOS_INCIDENTE:
        tipo = "Otro"
    descripcion = (descripcion or "").strip()

    incidente = Incidente(envio=envio, tipo=tipo, descripcion=descripcion or None)
    if foto:
        incidente.foto = foto
    incidente.save()

    HistorialEnvio.objects.create(
        envio=envio,
        tipo_evento="Incidente",
        ubicacion_latitud=latitud or envio.latitud_origen,
        ubicacion_longitud=longitud or envio.longitud_origen,
        usuario=usuario,
        observaciones=descripcion or tipo,
    )
    crear_notificacion(
        envio,
        "Incidencia registrada",
        f"Se registró una incidencia de tipo {tipo} para {envio.numero_seguimiento}.",
        usuario=usuario,
    )
    return incidente


def reasignar_envio_operativo(*, envio, nuevo_mensajero, responsable=None, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("El motivo de reasignación es obligatorio.")

    anterior = envio.mensajero
    envio.mensajero = nuevo_mensajero
    envio.estado = "Pendiente" if envio.estado == "Rechazado" else envio.estado
    envio.orden_ruta = None
    envio.eta_min = None
    envio.save(update_fields=["mensajero", "estado", "orden_ruta", "eta_min"])

    reasignacion = ReasignacionEnvio.objects.create(
        envio=envio,
        mensajero_anterior=anterior,
        mensajero_nuevo=nuevo_mensajero,
        responsable=responsable if responsable and is_admin(responsable) else None,
        motivo=motivo,
    )
    HistorialEnvio.objects.create(
        envio=envio,
        tipo_evento="Reasignado",
        usuario=responsable,
        observaciones=f"De {anterior.nombre if anterior else 'sin asignar'} a {nuevo_mensajero.nombre}. Motivo: {motivo}",
    )
    crear_notificacion(
        envio,
        "Envío reasignado",
        f"El envío {envio.numero_seguimiento} fue reasignado a {nuevo_mensajero.nombre}.",
        destinatario=nuevo_mensajero.email,
        usuario=responsable,
    )

    try:
        from rutas.services.optimization import rebuild_route_for_messenger

        if anterior:
            rebuild_route_for_messenger(anterior)
        rebuild_route_for_messenger(nuevo_mensajero)
    except Exception:
        pass

    return reasignacion

import base64
import qrcode
import json
import math
from io import BytesIO
import mimetypes
import os
import googlemaps
from django.conf import settings
from django.db.models import Count, Q, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.utils import timezone
from .models import (
    Envio,
    Incidente,
    HistorialEnvio,
    Entrega,
    NotificacionEnvio,
    ReasignacionEnvio,
)
from .forms import EnvioForm, IncidenteForm, EntregaForm, SolicitudEnvioForm
from .services import (
    crear_notificacion,
    reasignar_envio_operativo,
    registrar_entrega_operativa,
    registrar_incidente_operativo,
    usuario_puede_operar_envio,
)
from usuarios.models import Empresa, Usuario
from usuarios.security import is_admin, is_cliente, is_mensajero, usuario_from_request
from pagos.models import Pago, MetodoPago
from zonas.models import Zona
from django.core.serializers.json import DjangoJSONEncoder
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from django.views.decorators.csrf import csrf_exempt

# ===============================
# 🔑 CONFIGURACIÓN GOOGLE MAPS
# ===============================
gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY) if settings.GOOGLE_MAPS_API_KEY else None


# ===============================
# 📍 FUNCIONES AUXILIARES PARA JSON
# ===============================
def _normalize_value(v):
    """
    Normaliza valores para serializar a JSON:
    - Decimals -> str
    - date/datetime -> isoformat
    - otros -> se devuelven tal cual (DjangoJSONEncoder hará el resto)
    """
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime, date)):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    return v


def _normalize_item(d):
    """
    Normaliza un dict (por ejemplo resultado de .values()) aplicando _normalize_value.
    """
    return {k: _normalize_value(v) for k, v in d.items()}


def _cliente_envio_filter(usuario):
    filtro = Q(remitente=usuario)
    if usuario and usuario.empresa_id:
        filtro |= Q(remitente__empresa_id=usuario.empresa_id)
    return filtro


def _envios_para_usuario(qs, usuario):
    if not usuario or is_admin(usuario):
        return qs
    if is_cliente(usuario):
        return qs.filter(_cliente_envio_filter(usuario))
    return qs.filter(Q(mensajero=usuario) | Q(remitente=usuario))


def _usuario_puede_ver_envio(usuario, envio):
    if not usuario or is_admin(usuario):
        return True
    if is_cliente(usuario):
        return (
            envio.remitente_id == usuario.id
            or bool(usuario.empresa_id and envio.remitente_id and envio.remitente.empresa_id == usuario.empresa_id)
        )
    return envio.mensajero_id == usuario.id or envio.remitente_id == usuario.id


def _filtrar_por_actor(request, qs):
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if usuario and not is_admin(usuario):
        return _envios_para_usuario(qs, usuario)

    usuario_id = request.GET.get("usuario_id")
    rol = request.GET.get("rol")
    if usuario and is_admin(usuario) and usuario_id and rol and rol.lower() != "administrador":
        usuario_param = Usuario.objects.select_related("rol", "empresa").filter(pk=usuario_id).first()
        return _envios_para_usuario(qs, usuario_param)
    return qs


def _crear_notificacion(envio, asunto, mensaje, destinatario="", canal="sistema"):
    return crear_notificacion(envio, asunto, mensaje, destinatario=destinatario, canal=canal)


def _datos_cuenta_envio(usuario):
    if not usuario:
        return {"nombre": "", "telefono": "", "direccion": ""}
    empresa = getattr(usuario, "empresa", None)
    return {
        "nombre": (empresa.nombre if empresa else usuario.nombre) or "",
        "telefono": (empresa.telefono if empresa and empresa.telefono else usuario.telefono) or "",
        "direccion": (empresa.direccion if empresa else "") or "",
    }


def _distance_meters(lat1, lng1, lat2, lng2):
    try:
        lat1 = float(lat1)
        lng1 = float(lng1)
        lat2 = float(lat2)
        lng2 = float(lng2)
    except (TypeError, ValueError):
        return None

    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _tracking_stage_from_estado(estado_value):
    estado = (estado_value or "").lower()
    if estado == "pendiente":
        return {
            "label": "En recepción",
            "description": "La solicitud fue registrada y está en preparación operativa.",
            "step": 1,
        }
    if estado in ("en ruta", "reintentado"):
        return {
            "label": "En tránsito",
            "description": "El envío está asignado a un mensajero y se encuentra en ruta.",
            "step": 2,
        }
    if estado == "entregado":
        return {
            "label": "Entregado",
            "description": "El envío fue entregado correctamente.",
            "step": 3,
        }
    if estado in ("rechazado", "fallido", "cancelado"):
        return {
            "label": estado_value,
            "description": "El envío requiere revisión o ya no está en curso.",
            "step": 3,
        }
    return {
        "label": "Registrado",
        "description": "La guía existe en el sistema.",
        "step": 0,
    }


def _tracking_stage(envio):
    return _tracking_stage_from_estado(envio.estado)


def _tracking_steps(current_step):
    labels = [
        ("Registrado", "Solicitud creada"),
        ("En recepción", "Preparación y asignación"),
        ("En tránsito", "Mensajero en ruta"),
        ("Entregado", "Entrega confirmada"),
    ]
    return [
        {
            "label": label,
            "description": description,
            "completed": idx <= current_step,
            "current": idx == current_step,
        }
        for idx, (label, description) in enumerate(labels)
    ]


def _tracking_payload(envio):
    historial = HistorialEnvio.objects.filter(envio=envio).select_related("usuario").order_by("fecha_evento")
    pago = Pago.objects.filter(envio=envio).select_related("metodo_pago").first()
    ultimo_evento = historial.order_by("-fecha_evento").first()
    entrega_en_curso = envio.estado not in ("Entregado", "Cancelado", "Rechazado", "Fallido")
    mensajero = envio.mensajero if entrega_en_curso else None
    perfil = getattr(mensajero, "perfil_mensajero", None) if mensajero else None
    foto_url = None
    if perfil and perfil.foto:
        try:
            foto_url = perfil.foto.url
        except Exception:
            foto_url = None
    stage = _tracking_stage(envio)
    distancia_destino_m = None
    ubicacion_visible = False
    if perfil and envio.latitud_destino is not None and envio.longitud_destino is not None:
        distancia_destino_m = _distance_meters(
            perfil.latitud,
            perfil.longitud,
            envio.latitud_destino,
            envio.longitud_destino,
        )
        ubicacion_visible = (
            entrega_en_curso
            and (envio.estado or "").lower() in ("en ruta", "reintentado")
            and distancia_destino_m is not None
            and distancia_destino_m <= 700
        )

    return {
        "id": envio.id,
        "numero_seguimiento": envio.numero_seguimiento,
        "poll_interval_seconds": 10,
        "creado_en": envio.creado_en.isoformat() if envio.creado_en else None,
        "actualizado_en": ultimo_evento.fecha_evento.isoformat() if ultimo_evento else (envio.creado_en.isoformat() if envio.creado_en else None),
        "estado": envio.estado,
        "estado_publico": stage["label"],
        "estado_descripcion": stage["description"],
        "etapas": _tracking_steps(stage["step"]),
        "origen_direccion": envio.origen_direccion,
        "destino_direccion": envio.destino_direccion,
        "destinatario_nombre": envio.destinatario_nombre,
        "tipo_servicio": envio.tipo_servicio,
        "tipo_pago": envio.tipo_pago,
        "monto_pago": float(envio.monto_pago) if envio.monto_pago is not None else None,
        "pago": {
            "estado": pago.estado,
            "monto": float(pago.monto),
            "metodo": pago.metodo_pago.nombre,
            "fecha_pago": pago.fecha_pago.isoformat() if pago.fecha_pago else None,
        } if pago else None,
        "mensajero": {
            "id": mensajero.id,
            "nombre": mensajero.nombre,
            "telefono": mensajero.telefono,
            "vehiculo": perfil.vehiculo if perfil else None,
            "foto_url": foto_url,
            "ubicacion_visible": ubicacion_visible,
            "distancia_destino_m": round(distancia_destino_m) if distancia_destino_m is not None else None,
            "latitud": float(perfil.latitud) if ubicacion_visible and perfil and perfil.latitud is not None else None,
            "longitud": float(perfil.longitud) if ubicacion_visible and perfil and perfil.longitud is not None else None,
            "mensaje_ubicacion": (
                "El mensajero está cerca del destino."
                if ubicacion_visible
                else "La ubicación exacta se mostrará cuando el mensajero esté cerca del destino."
            ),
        } if mensajero else None,
        "timeline": [
            {
                "tipo": h.tipo_evento,
                "fecha": h.fecha_evento.isoformat() if h.fecha_evento else None,
                "latitud": float(h.ubicacion_latitud) if ubicacion_visible and h.ubicacion_latitud is not None else None,
                "longitud": float(h.ubicacion_longitud) if ubicacion_visible and h.ubicacion_longitud is not None else None,
                "usuario": h.usuario.nombre if h.usuario else None,
                "observaciones": h.observaciones,
            }
            for h in historial
        ],
    }


# ===============================
# 📍 FUNCIONES AUXILIARES DE GEOCODING
# ===============================
def obtener_coordenadas(direccion):
    """Obtiene latitud y longitud a partir de una dirección usando Google Maps API."""
    if not gmaps:
        return None, None
    direccion_completa = f"{direccion}, La Paz, Bolivia"
    try:
        geocode_result = gmaps.geocode(direccion_completa)
        if geocode_result:
            latitud = geocode_result[0]['geometry']['location']['lat']
            longitud = geocode_result[0]['geometry']['location']['lng']
            return latitud, longitud
    except Exception as e:
        # evitar que errores externos rompan la vista
        print("⚠️ Error en geocoding:", e)
    return None, None


# ===============================
# 📦 ENVÍOS
# ===============================
def lista_envios(request):
    usuario = usuario_from_request(request, allow_legacy_params=False)
    # Obtener búsqueda
    search_query = request.GET.get('search', '')
    
    # Filtrar envíos por búsqueda
    envios = _envios_para_usuario(
        Envio.objects.select_related("remitente", "mensajero"),
        usuario,
    )
    if search_query:
        filters = (
            Q(remitente_nombre__icontains=search_query)
            | Q(destinatario_nombre__icontains=search_query)
            | Q(estado__icontains=search_query)
            | Q(destino_direccion__icontains=search_query)
            | Q(origen_direccion__icontains=search_query)
        )
        if search_query.isdigit():
            filters |= Q(id=int(search_query))
        envios = envios.filter(filters)
    
    # Ordenar por fecha
    envios = envios.order_by('-creado_en')
    
    # Paginación
    from django.core.paginator import Paginator
    paginator = Paginator(envios, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'envios/lista_envios.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'es_cliente': is_cliente(usuario),
    })


def crear_envio(request):
    if request.method == 'POST':
        form = EnvioForm(request.POST)
        if form.is_valid():
            envio = form.save(commit=False)

            # Si vienen coordenadas en el formulario, las usamos
            if request.POST.get("latitud_origen") and request.POST.get("longitud_origen"):
                envio.latitud_origen = request.POST.get("latitud_origen")
                envio.longitud_origen = request.POST.get("longitud_origen")

            if request.POST.get("latitud_destino") and request.POST.get("longitud_destino"):
                envio.latitud_destino = request.POST.get("latitud_destino")
                envio.longitud_destino = request.POST.get("longitud_destino")

            envio.save()
            HistorialEnvio.objects.create(
                envio=envio,
                tipo_evento="Creado",
                usuario=usuario_from_request(request, allow_legacy_params=False),
                observaciones="Envío creado desde panel administrativo.",
            )

            return redirect('envios:lista_envios')
    else:
        form = EnvioForm()
    return render(request, 'envios/crear_envio.html', {
        'form': form,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    })


def solicitar_envio(request):
    usuario = usuario_from_request(request, allow_legacy_params=False)
    datos_cuenta = _datos_cuenta_envio(usuario)
    initial = {
        "tipo": "Envío",
        "tipo_servicio": "Estándar",
        "tipo_pago": "Pendiente",
        "peso": "1.00",
        "monto_pago": "0.00",
        "remitente_nombre": datos_cuenta["nombre"],
        "remitente_telefono": datos_cuenta["telefono"],
        "origen_direccion": datos_cuenta["direccion"],
    }
    data = None
    if request.method == "POST":
        data = request.POST.copy()
        tipo = data.get("tipo") or "Envío"
        if usuario:
            if tipo == "Recojo":
                data["destinatario_nombre"] = data.get("destinatario_nombre") or datos_cuenta["nombre"]
                data["destinatario_telefono"] = data.get("destinatario_telefono") or datos_cuenta["telefono"]
                data["destino_direccion"] = data.get("destino_direccion") or datos_cuenta["direccion"]
            else:
                data["remitente_nombre"] = data.get("remitente_nombre") or datos_cuenta["nombre"]
                data["remitente_telefono"] = data.get("remitente_telefono") or datos_cuenta["telefono"]
                data["origen_direccion"] = data.get("origen_direccion") or datos_cuenta["direccion"]
    form = SolicitudEnvioForm(data or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        envio = form.save(commit=False)
        envio.estado = "Pendiente"
        if usuario:
            envio.remitente = usuario
        if envio.origen_direccion and not envio.latitud_origen:
            envio.latitud_origen, envio.longitud_origen = obtener_coordenadas(envio.origen_direccion)
        if envio.destino_direccion and not envio.latitud_destino:
            envio.latitud_destino, envio.longitud_destino = obtener_coordenadas(envio.destino_direccion)
        envio.save()
        HistorialEnvio.objects.create(
            envio=envio,
            tipo_evento="Creado",
            usuario=usuario,
            observaciones="Solicitud registrada por cliente.",
        )
        _crear_notificacion(
            envio,
            "Solicitud de envío registrada",
            f"Se registró la solicitud {envio.numero_seguimiento}.",
        )
        return render(request, "envios/solicitud_confirmada.html", {"envio": envio})
    return render(request, "envios/solicitar_envio.html", {
        "form": form,
        "datos_cuenta": datos_cuenta,
    })


def ver_envio(request, envio_id):
    """Muestra la guía del envío con QR dinámico y mapa."""
    usuario = usuario_from_request(request, allow_legacy_params=False)
    envio = get_object_or_404(Envio.objects.select_related("remitente", "mensajero"), id=envio_id)
    if not _usuario_puede_ver_envio(usuario, envio):
        raise Http404("Envío no encontrado.")

    # Generar QR dinámico sin almacenarlo
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=6,
        border=2,
    )
    tracking_url = request.build_absolute_uri(
        f"/envios/seguimiento/{envio.numero_seguimiento}/"
    )
    qr.add_data(tracking_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return render(request, 'envios/ver_envio.html', {
        'envio': envio,
        'qr_base64': qr_base64,
        'tracking_url': tracking_url,
        'es_cliente': is_cliente(usuario),
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    })


def editar_envio(request, envio_id):
    envio = get_object_or_404(Envio, id=envio_id)
    usuario = usuario_from_request(request)

    if request.method == 'POST':
        form = EnvioForm(request.POST, instance=envio)
        if form.is_valid():
            envio = form.save(commit=False)

            lat_origen = request.POST.get("latitud_origen")
            lng_origen = request.POST.get("longitud_origen")
            lat_destino = request.POST.get("latitud_destino")
            lng_destino = request.POST.get("longitud_destino")

            if lat_origen and lng_origen:
                envio.latitud_origen = float(lat_origen)
                envio.longitud_origen = float(lng_origen)
            else:
                envio.latitud_origen, envio.longitud_origen = obtener_coordenadas(envio.origen_direccion)

            if lat_destino and lng_destino:
                envio.latitud_destino = float(lat_destino)
                envio.longitud_destino = float(lng_destino)
            else:
                envio.latitud_destino, envio.longitud_destino = obtener_coordenadas(envio.destino_direccion)

            envio.save()

            HistorialEnvio.objects.create(
                envio=envio,
                tipo_evento='Actualizado',
                ubicacion_latitud=envio.latitud_origen,
                ubicacion_longitud=envio.longitud_origen
            )

            messages.success(request, "Envío actualizado correctamente.")
            return redirect('envios:lista_envios')
    else:
        form = EnvioForm(instance=envio)

    return render(request, 'envios/editar_envio.html', {
        'form': form,
        'envio': envio,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    })


def eliminar_envio(request, envio_id):
    envio = get_object_or_404(Envio, id=envio_id)
    if request.method == 'POST':
        envio.delete()
        return redirect('envios:lista_envios')
    return render(request, 'envios/eliminar_envio.html', {'envio': envio})


# ===============================
# ⚠️ INCIDENTES
# ===============================
def registrar_incidente(request, envio_id):
    envio = get_object_or_404(Envio, id=envio_id)
    if request.method == 'POST':
        form = IncidenteForm(request.POST)
        if form.is_valid():
            incidente = form.save(commit=False)
            incidente.envio = envio
            incidente.save()

            HistorialEnvio.objects.create(
                envio=envio,
                tipo_evento='Incidente',
                ubicacion_latitud=envio.latitud_origen,
                ubicacion_longitud=envio.longitud_origen
            )
            return redirect('envios:ver_envio', envio_id=envio.id)
    else:
        form = IncidenteForm()
    return render(request, 'envios/registrar_incidente.html', {'form': form, 'envio': envio})


def ver_incidente(request, envio_id, incidente_id):
    envio = get_object_or_404(Envio, id=envio_id)
    incidente = get_object_or_404(Incidente, id=incidente_id)
    return render(request, 'envios/ver_incidente.html', {'incidente': incidente, 'envio': envio})


def editar_incidente(request, envio_id, incidente_id):
    envio = get_object_or_404(Envio, id=envio_id)
    incidente = get_object_or_404(Incidente, id=incidente_id)
    if request.method == 'POST':
        form = IncidenteForm(request.POST, instance=incidente)
        if form.is_valid():
            form.save()
            messages.success(request, "Incidente actualizado correctamente.")
            return redirect('envios:ver_incidente', envio_id=envio.id, incidente_id=incidente.id)
    else:
        form = IncidenteForm(instance=incidente)
    return render(request, 'envios/editar_incidente.html', {'form': form, 'envio': envio})


def eliminar_incidente(request, envio_id, incidente_id):
    envio = get_object_or_404(Envio, id=envio_id)
    incidente = get_object_or_404(Incidente, id=incidente_id)
    if request.method == 'POST':
        incidente.delete()
        return redirect('envios:ver_envio', envio_id=envio.id)
    return render(request, 'envios/eliminar_incidente.html', {'incidente': incidente, 'envio': envio})


# ===============================
# 📬 ENTREGAS
# ===============================
def lista_entregas(request):
    # Obtener búsqueda
    search_query = request.GET.get('search', '')
    
    # Filtrar entregas por búsqueda
    entregas = Entrega.objects.all()
    if search_query:
        filters = (
            Q(envio__destinatario_nombre__icontains=search_query)
            | Q(mensajero__nombre__icontains=search_query)
            | Q(estado__icontains=search_query)
        )
        if search_query.isdigit():
            filters |= Q(envio__id=int(search_query))
        entregas = entregas.filter(filters)
    
    # Ordenar por fecha
    entregas = entregas.order_by('-fecha_entrega')
    
    # Paginación
    from django.core.paginator import Paginator
    paginator = Paginator(entregas, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'envios/lista_entregas.html', {
        'page_obj': page_obj,
        'search_query': search_query
    })


def ver_entrega(request, entrega_id):
    entrega = get_object_or_404(Entrega, id=entrega_id)
    return render(request, 'envios/ver_entrega.html', {'entrega': entrega})


def registrar_entrega(request, envio_id):
    envio = get_object_or_404(Envio, id=envio_id)
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if request.method == 'POST':
        form = EntregaForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                registrar_entrega_operativa(
                    envio=envio,
                    usuario=usuario,
                    estado=form.cleaned_data["estado"],
                    modalidad_pago=form.cleaned_data.get("modalidad_pago"),
                    monto=form.cleaned_data.get("monto") or envio.monto_pago,
                    observaciones=form.cleaned_data.get("observaciones") or "",
                    firma=request.FILES.get("firma"),
                    foto=request.FILES.get("foto"),
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(request, 'envios/registrar_entrega.html', {'form': form, 'envio': envio})

            # Si el formulario incluye incidente
            tipo = request.POST.get('tipo_incidente')
            descripcion = request.POST.get('descripcion_incidente')
            if tipo or descripcion:
                registrar_incidente_operativo(
                    envio=envio,
                    usuario=usuario,
                    tipo=tipo or 'Otro',
                    descripcion=descripcion or ''
                )

            messages.success(request, "Entrega registrada correctamente.")
            return redirect('envios:ver_envio', envio.id)
        else:
            print("❌ ERRORES DE FORMULARIO:", form.errors)
            messages.error(request, "Hubo un error en el formulario.")
    else:
        form = EntregaForm(initial={"modalidad_pago": envio.tipo_pago, "monto": envio.monto_pago})
    return render(request, 'envios/registrar_entrega.html', {'form': form, 'envio': envio})


@csrf_exempt
def api_registrar_entrega(request, envio_id):
    """
    POST multipart  /envios/api/entregas/registrar/<envio_id>/

    Endpoint para la app móvil (mensajero). Registra la confirmación de entrega:
      - crea una Entrega (con foto y/o firma cifradas y observaciones),
      - actualiza Envio.estado ('Entregado' o 'Rechazado'),
      - registra un evento en HistorialEnvio (con ubicación si se envía).

    Campos del formulario (multipart/form-data):
      estado        : 'Entregado' | 'Rechazado'   (obligatorio)
      mensajero_id  : id del mensajero             (opcional; si el envío ya tiene mensajero)
      observaciones : texto libre                  (opcional)
      pagado        : 'true' | 'false'             (opcional, por defecto false)
      latitud       : decimal                      (opcional, para el historial)
      longitud      : decimal                      (opcional, para el historial)
      firma         : archivo de imagen            (opcional)
      foto          : archivo de imagen            (opcional)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    envio = get_object_or_404(Envio, id=envio_id)
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({'error': 'No autenticado'}, status=401)
    if not usuario_puede_operar_envio(usuario, envio):
        return JsonResponse({'error': 'No autorizado para registrar esta entrega.'}, status=403)

    estado = (request.POST.get('estado') or '').strip()
    try:
        entrega = registrar_entrega_operativa(
            envio=envio,
            usuario=usuario,
            estado=estado,
            mensajero_id=request.POST.get('mensajero_id') if is_admin(usuario) else None,
            modalidad_pago=request.POST.get('modalidad_pago'),
            monto=request.POST.get('monto'),
            observaciones=request.POST.get('observaciones') or '',
            firma=request.FILES.get('firma'),
            foto=request.FILES.get('foto'),
            latitud=request.POST.get('latitud'),
            longitud=request.POST.get('longitud'),
        )
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    return JsonResponse(
        {
            'ok': True,
            'entrega_id': entrega.id,
            'envio_id': envio.id,
            'numero_seguimiento': envio.numero_seguimiento,
            'estado': envio.estado,
            'pagado': entrega.pagado,
        },
        status=201,
    )


@csrf_exempt
def api_registrar_incidente(request, envio_id):
    """
    POST multipart  /envios/api/incidentes/registrar/<envio_id>/

    Registra una incidencia desde la app móvil (mensajero):
      - crea un Incidente (tipo, descripción y foto opcional cifrada),
      - registra un evento 'Incidente' en HistorialEnvio.

    Campos (multipart/form-data):
      tipo        : 'Retraso' | 'Daño' | 'Pérdida' | 'Otro'  (por defecto 'Otro')
      descripcion : texto libre        (opcional)
      latitud     : decimal            (opcional)
      longitud    : decimal            (opcional)
      foto        : archivo de imagen  (opcional)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    envio = get_object_or_404(Envio, id=envio_id)
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({'error': 'No autenticado'}, status=401)
    if not usuario_puede_operar_envio(usuario, envio):
        return JsonResponse({'error': 'No autorizado para registrar esta incidencia.'}, status=403)

    incidente = registrar_incidente_operativo(
        envio=envio,
        usuario=usuario,
        tipo=request.POST.get('tipo') or 'Otro',
        descripcion=request.POST.get('descripcion') or '',
        foto=request.FILES.get('foto'),
        latitud=request.POST.get('latitud'),
        longitud=request.POST.get('longitud'),
    )

    return JsonResponse(
        {'ok': True, 'incidente_id': incidente.id, 'envio_id': envio.id},
        status=201,
    )


def editar_entrega(request, entrega_id):
    entrega = get_object_or_404(Entrega, id=entrega_id)
    if request.method == 'POST':
        form = EntregaForm(request.POST, request.FILES, instance=entrega)
        if form.is_valid():
            form.save()
            messages.success(request, "Entrega actualizada correctamente.")
            return redirect('envios:lista_entregas')
    else:
        form = EntregaForm(instance=entrega)
    return render(request, 'envios/editar_entrega.html', {'form': form, 'entrega': entrega})


def eliminar_entrega(request, entrega_id):
    entrega = get_object_or_404(Entrega, id=entrega_id)
    if request.method == 'POST':
        entrega.delete()
        return redirect('envios:lista_entregas')
    return render(request, 'envios/eliminar_entrega.html', {'entrega': entrega})


# ===============================
# 🕓 HISTORIAL
# ===============================
def historial_envio(request, envio_id):
    envio = get_object_or_404(Envio, id=envio_id)
    historial = HistorialEnvio.objects.filter(envio=envio)
    return render(request, 'envios/historial_envio.html', {'envio': envio, 'historial': historial})


def ver_evento_historial(request, envio_id, evento_id):
    envio = get_object_or_404(Envio, id=envio_id)
    evento = get_object_or_404(HistorialEnvio, id=evento_id)
    return render(request, 'envios/ver_evento_historial.html', {'evento': evento, 'envio': envio})


def seguimiento_envio(request):
    numero = (request.GET.get("numero") or "").strip()
    envio = None
    usuario = usuario_from_request(request, allow_legacy_params=False)
    envios_cliente = []
    if usuario and is_cliente(usuario):
        envios_cliente = _envios_para_usuario(
            Envio.objects.select_related("remitente", "mensajero"),
            usuario,
        ).order_by("-creado_en")[:20]
    if numero:
        envio = Envio.objects.filter(Q(numero_seguimiento__iexact=numero) | Q(id=numero if numero.isdigit() else 0)).first()
        if envio:
            return redirect("envios:seguimiento_detalle", numero=envio.numero_seguimiento)
        messages.error(request, "No se encontró un envío con ese número de seguimiento.")
    return render(request, "envios/seguimiento.html", {
        "numero": numero,
        "envios_cliente": envios_cliente,
    })


def seguimiento_detalle(request, numero):
    envio = get_object_or_404(Envio, numero_seguimiento__iexact=numero)
    return render(request, "envios/seguimiento_detalle.html", {"envio": envio, "tracking": _tracking_payload(envio)})


def seguimiento_api(request, numero):
    envio = get_object_or_404(Envio, numero_seguimiento__iexact=numero)
    return JsonResponse(_tracking_payload(envio), json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def reasignar_envio(request, envio_id):
    envio = get_object_or_404(Envio, pk=envio_id)
    if request.method != "POST":
        mensajeros = Usuario.objects.filter(rol__nombre__iexact="mensajero", is_active=True).select_related("rol")
        return render(request, "envios/reasignar_envio.html", {"envio": envio, "mensajeros": mensajeros})

    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"error": "No autenticado."}, status=401)
    if not is_admin(usuario):
        return JsonResponse({"error": "Solo administradores pueden reasignar envíos."}, status=403)

    nuevo_id = request.POST.get("mensajero_id")
    motivo = (request.POST.get("motivo") or "").strip()
    nuevo = Usuario.objects.filter(pk=nuevo_id, rol__nombre__iexact="mensajero", is_active=True).first()
    if not nuevo:
        return JsonResponse({"error": "Mensajero nuevo inválido."}, status=400)
    try:
        reasignar_envio_operativo(
            envio=envio,
            nuevo_mensajero=nuevo,
            responsable=usuario,
            motivo=motivo,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if request.headers.get("Accept", "").lower().find("application/json") >= 0:
        return JsonResponse({"ok": True, "envio_id": envio.id, "mensajero_id": nuevo.id})
    messages.success(request, "Envío reasignado correctamente.")
    return redirect("envios:ver_envio", envio_id=envio.id)


def _report_qs(request):
    qs = Envio.objects.select_related("mensajero", "zona").all()
    fecha_inicio = request.GET.get("desde")
    fecha_fin = request.GET.get("hasta")
    estado = request.GET.get("estado")
    mensajero_id = request.GET.get("mensajero_id")
    zona_id = request.GET.get("zona_id")
    if fecha_inicio:
        qs = qs.filter(creado_en__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(creado_en__date__lte=fecha_fin)
    if estado:
        qs = qs.filter(estado=estado)
    if mensajero_id:
        qs = qs.filter(mensajero_id=mensajero_id)
    if zona_id:
        qs = qs.filter(zona_id=zona_id)
    return qs.order_by("-creado_en")


def _report_filters(request):
    return {
        "Desde": request.GET.get("desde") or "Todos",
        "Hasta": request.GET.get("hasta") or "Todos",
        "Estado": request.GET.get("estado") or "Todos",
        "Mensajero": (
            Usuario.objects.filter(pk=request.GET.get("mensajero_id")).values_list("nombre", flat=True).first()
            or "Todos"
        ),
        "Zona": (
            Zona.objects.filter(pk=request.GET.get("zona_id")).values_list("nombre", flat=True).first()
            or "Todas"
        ),
    }


def _report_metrics(qs):
    pagos = Pago.objects.filter(envio__in=qs)
    total = qs.count()
    entregados = qs.filter(estado="Entregado").count()
    pendientes = qs.filter(estado="Pendiente").count()
    en_ruta = qs.filter(estado="En Ruta").count()
    reintentos = qs.filter(estado="Reintentado").count()
    fallidos = qs.filter(estado__in=["Rechazado", "Fallido"]).count()
    completion_rate = round((entregados / total * 100), 1) if total else 0

    def pct(value):
        return round((value / total * 100), 1) if total else 0

    def chart_rows(rows, label_key):
        rows = list(rows)
        max_count = max([row["total"] for row in rows] or [1])
        return [
            {
                "label": row[label_key] or "Sin dato",
                "total": row["total"],
                "percent": round((row["total"] / max_count) * 100, 1),
            }
            for row in rows
        ]

    por_mensajero = qs.values("mensajero__nombre").annotate(total=Count("id")).order_by("-total", "mensajero__nombre")
    por_zona = qs.values("zona__nombre").annotate(total=Count("id")).order_by("-total", "zona__nombre")
    return {
        "total_envios": total,
        "entregados": entregados,
        "pendientes": pendientes,
        "en_ruta": en_ruta,
        "reintentos": reintentos,
        "fallidos": fallidos,
        "completion_rate": completion_rate,
        "ventas": pagos.filter(estado="Pagado").aggregate(total=Sum("monto"))["total"] or Decimal("0"),
        "estado_resumen": [
            {"label": "Entregados", "total": entregados, "percent": pct(entregados), "kind": "success"},
            {"label": "Pendientes", "total": pendientes, "percent": pct(pendientes), "kind": "warning"},
            {"label": "En ruta", "total": en_ruta, "percent": pct(en_ruta), "kind": "info"},
            {"label": "Reintentos", "total": reintentos, "percent": pct(reintentos), "kind": "retry"},
            {"label": "Fallidos", "total": fallidos, "percent": pct(fallidos), "kind": "danger"},
        ],
        "por_mensajero": chart_rows(por_mensajero, "mensajero__nombre"),
        "por_zona": chart_rows(por_zona, "zona__nombre"),
    }


def reportes_operativos(request):
    qs = _report_qs(request)
    metrics = _report_metrics(qs)
    mensajeros = Usuario.objects.filter(rol__nombre__iexact="mensajero").order_by("nombre")
    zonas = Zona.objects.order_by("nombre")
    return render(request, "envios/reportes_operativos.html", {
        "envios": qs[:200],
        "metrics": metrics,
        "mensajeros": mensajeros,
        "zonas": zonas,
        "filtros_aplicados": _report_filters(request),
    })


def reportes_excel(request):
    qs = _report_qs(request)
    metrics = _report_metrics(qs)
    filtros = _report_filters(request)
    rows = [
        ["Reporte operativo Courier Bolivian Express"],
        [],
        ["Filtros aplicados"],
        *[[key, value] for key, value in filtros.items()],
        [],
        ["Métricas generales"],
        ["Total envíos", metrics["total_envios"]],
        ["Entregados", metrics["entregados"]],
        ["Pendientes", metrics["pendientes"]],
        ["En ruta", metrics["en_ruta"]],
        ["Reintentos", metrics["reintentos"]],
        ["Fallidos", metrics["fallidos"]],
        ["Ventas pagadas", str(metrics["ventas"])],
        [],
        ["Por estado"],
        ["Estado", "Total", "%"],
        *[[item["label"], item["total"], item["percent"]] for item in metrics["estado_resumen"]],
        [],
        ["Por mensajero"],
        ["Mensajero", "Total"],
        *[[item["label"], item["total"]] for item in metrics["por_mensajero"]],
        [],
        ["Por zona"],
        ["Zona", "Total"],
        *[[item["label"], item["total"]] for item in metrics["por_zona"]],
        [],
        ["Seguimiento", "Estado", "Mensajero", "Zona", "Destino", "Servicio", "Monto", "Fecha"],
    ]
    for envio in qs[:2000]:
        rows.append([
            envio.numero_seguimiento,
            envio.estado,
            envio.mensajero.nombre if envio.mensajero else "",
            envio.zona.nombre if envio.zona else "",
            envio.destino_direccion,
            envio.tipo_servicio,
            str(envio.monto_pago or ""),
            envio.creado_en.strftime("%Y-%m-%d %H:%M") if envio.creado_en else "",
        ])
    body = "\n".join(
        "<tr>" + "".join(f"<td>{str(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    response = HttpResponse(f"<table>{body}</table>", content_type="application/vnd.ms-excel; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="reporte_cbe.xls"'
    return response


def _simple_pdf(lines):
    content = ["BT", "/F1 11 Tf", "50 790 Td"]
    for idx, line in enumerate(lines[:45]):
        safe = str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx:
            content.append("0 -16 Td")
        content.append(f"({safe}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        b"5 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj",
    ]
    pdf = [b"%PDF-1.4\n"]
    offsets = []
    for obj in objects:
        offsets.append(sum(len(p) for p in pdf))
        pdf.append(obj + b"\n")
    xref = sum(len(p) for p in pdf)
    pdf.append(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        pdf.append(f"{off:010d} 00000 n \n".encode())
    pdf.append(f"trailer << /Root 1 0 R /Size {len(objects)+1} >>\nstartxref\n{xref}\n%%EOF".encode())
    return b"".join(pdf)


def reportes_pdf(request):
    qs = _report_qs(request)
    metrics = _report_metrics(qs)
    filtros = _report_filters(request)
    lines = [
        "Reporte operativo Courier Bolivian Express",
        "Filtros aplicados:",
        *[f"{key}: {value}" for key, value in filtros.items()],
        "",
        f"Total envios: {metrics['total_envios']}",
        f"Entregados: {metrics['entregados']}",
        f"Pendientes: {metrics['pendientes']}",
        f"En ruta: {metrics['en_ruta']}",
        f"Reintentos: {metrics['reintentos']}",
        f"Fallidos: {metrics['fallidos']}",
        f"Ventas pagadas: Bs. {metrics['ventas']}",
        "",
        "Por mensajero:",
        *[f"{item['label']}: {item['total']}" for item in metrics["por_mensajero"][:8]],
        "",
        "Por zona:",
        *[f"{item['label']}: {item['total']}" for item in metrics["por_zona"][:8]],
        "",
        "Ultimos envios:",
    ]
    for envio in qs[:30]:
        lines.append(f"{envio.numero_seguimiento} | {envio.estado} | {envio.destinatario_nombre}")
    response = HttpResponse(_simple_pdf(lines), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="reporte_cbe.pdf"'
    return response


# ===============================
# 🟢 ENDPOINTS JSON (API)
# ===============================
def entregas_api_json(request):
    """
    Devuelve entregas filtradas por rol:
    - Admin: todas las entregas
    - Mensajero: solo sus entregas
    """
    qs = Entrega.objects.select_related("envio", "mensajero").all()
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if usuario and not is_admin(usuario):
        qs = qs.filter(mensajero=usuario)
    elif usuario and is_admin(usuario):
        usuario_id = request.GET.get("usuario_id")
        rol = request.GET.get("rol")
        if usuario_id and rol and rol.lower() != "administrador":
            qs = qs.filter(mensajero_id=usuario_id)
    
    data = []
    for entrega in qs:
        data.append({
            "id": entrega.id,
            "envio": entrega.envio.id if entrega.envio else None,
            "numero_seguimiento": entrega.envio.numero_seguimiento if entrega.envio else None,
            "mensajero": entrega.mensajero.nombre if entrega.mensajero else None,
            "mensajero_id": entrega.mensajero.id if entrega.mensajero else None,
            "estado": entrega.estado,
            "fecha_entrega": entrega.fecha_entrega.isoformat() if entrega.fecha_entrega else None,
        })
    return JsonResponse(data, safe=False)


def envios_pendientes_json(request):
    """
    Devuelve en formato JSON todos los envíos cuyo estado sea 'Pendiente'.
    Filtrado por rol:
    - Admin: todos los pendientes
    - Mensajero: solo sus pendientes
    """
    qs = _filtrar_por_actor(request, Envio.objects.filter(estado='Pendiente'))
    
    data = []

    for envio in qs:
        data.append({
            "id": envio.id,
            "numero_seguimiento": envio.numero_seguimiento,
            "tipo": envio.tipo,
            "remitente_nombre": envio.remitente_nombre,
            "remitente_telefono": envio.remitente_telefono,
            "destinatario_nombre": envio.destinatario_nombre,
            "destinatario_telefono": envio.destinatario_telefono,
            "origen_direccion": envio.origen_direccion,
            "destino_direccion": envio.destino_direccion,
            "latitud_origen": str(envio.latitud_origen) if envio.latitud_origen else None,
            "longitud_origen": str(envio.longitud_origen) if envio.longitud_origen else None,
            "latitud_destino": str(envio.latitud_destino) if envio.latitud_destino else None,
            "longitud_destino": str(envio.longitud_destino) if envio.longitud_destino else None,
            "peso": float(envio.peso) if envio.peso is not None else None,
            "tipo_servicio": envio.tipo_servicio,
            "estado": envio.estado,
            "monto_pago": float(envio.monto_pago) if envio.monto_pago else None,
            "tipo_pago": envio.tipo_pago,
            "mensajero": envio.mensajero.nombre if envio.mensajero else None,
            "mensajero_id": envio.mensajero_id,
            "orden_ruta": envio.orden_ruta,
            "eta_min": envio.eta_min,
            "fecha_creado": envio.creado_en.strftime("%Y-%m-%d %H:%M:%S") if envio.creado_en else None,
        })

    return JsonResponse(data, safe=False)


def envios_json(request):
    """
    /envios/envios-json/
    Devuelve TODOS los envíos (o filtrados por ?estado=..., ?usuario_id=..., ?rol=... si se pasan).
    
    Filtrado por rol:
    - Si rol='Administrador': retorna todos los envíos
    - Si rol diferente de 'Administrador': retorna solo envíos del mensajero especificado
    """
    qs = _filtrar_por_actor(request, Envio.objects.all()).order_by("-creado_en")
    
    # Filtro por estado (ya existente)
    estado_q = request.GET.get("estado")
    if estado_q:
        qs = qs.filter(estado__iexact=estado_q)
    
    fields = [
        "id",
        "numero_seguimiento",
        "tipo",
        "origen_direccion",
        "destino_direccion",
        "destinatario_nombre",
        "destinatario_telefono",
        "peso",
        "tipo_servicio",
        "estado",
        "observaciones",
        "creado_en",
        "ruta_id",
        "remitente_id",
        "remitente_nombre",
        "remitente_telefono",
        "latitud_destino",
        "longitud_destino",
        "latitud_origen",
        "longitud_origen",
        "monto_pago",
        "tipo_pago",
        "mensajero_id",
        "mensajero__nombre",
        "zona_id",
        "orden_ruta",
        "eta_min",
    ]
    vals = qs.values(*fields)
    data = []
    for value in vals:
        item = _normalize_item(value)
        item["estado_publico"] = _tracking_stage_from_estado(value.get("estado"))["label"]
        data.append(item)
    return JsonResponse(data, safe=False, json_dumps_params={"ensure_ascii": False}, encoder=DjangoJSONEncoder)


@csrf_exempt
def api_crear_envio(request):
    """
    Endpoint para crear envíos desde Flutter/Externo (POST JSON)
    Ruta: /envios/api/envios/crear/
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            usuario = usuario_from_request(request, allow_legacy_params=False)
            if not usuario:
                return JsonResponse({"error": "No autenticado"}, status=401)
            if is_mensajero(usuario):
                return JsonResponse({"error": "Los mensajeros no pueden crear envíos."}, status=403)
            
            # Campos obligatorios mínimos
            required_fields = ['destinatario_nombre', 'origen_direccion', 'destino_direccion']
            for field in required_fields:
                if not data.get(field):
                    return JsonResponse({'error': f'Falta el campo obligatorio: {field}'}, status=400)

            cuenta = _datos_cuenta_envio(usuario)

            # Crear objeto Envio
            envio = Envio.objects.create(
                remitente=usuario,
                tipo=data.get('tipo') or 'Envío',
                remitente_nombre=data.get('remitente_nombre') or cuenta["nombre"] or usuario.nombre,
                remitente_telefono=data.get('remitente_telefono') or cuenta["telefono"] or '',
                destinatario_nombre=data.get('destinatario_nombre'),
                destinatario_telefono=data.get('destinatario_telefono', ''),
                origen_direccion=data.get('origen_direccion'),
                destino_direccion=data.get('destino_direccion'),
                peso=data.get('peso', 0),
                tipo_servicio=data.get('tipo_servicio', 'Estándar'),
                monto_pago=data.get('monto_pago', 0),
                tipo_pago=data.get('tipo_pago', 'Pendiente'),
                observaciones=data.get('observaciones', ''),
                # Si se envían coordenadas
                latitud_origen=data.get('latitud_origen'),
                longitud_origen=data.get('longitud_origen'),
                latitud_destino=data.get('latitud_destino'),
                longitud_destino=data.get('longitud_destino'),
            )
            HistorialEnvio.objects.create(
                envio=envio,
                tipo_evento="Creado",
                usuario=usuario,
                observaciones="Envío creado desde API.",
            )
            
            # Intentar geocodificar si no hay coordenadas (opcional, si tienes API Key activa)
            changed_coords = False
            if not envio.latitud_origen or not envio.longitud_origen:
                lat, lng = obtener_coordenadas(envio.origen_direccion)
                if lat and lng:
                    envio.latitud_origen = lat
                    envio.longitud_origen = lng
                    changed_coords = True
            if not envio.latitud_destino or not envio.longitud_destino:
                lat, lng = obtener_coordenadas(envio.destino_direccion)
                if lat and lng:
                    envio.latitud_destino = lat
                    envio.longitud_destino = lng
                    changed_coords = True
            if changed_coords:
                envio.save()

            return JsonResponse({
                "status": "success",
                "mensaje": "Envío creado correctamente",
                "envio_id": envio.id,
                "numero_seguimiento": envio.numero_seguimiento,
                "tracking_url": request.build_absolute_uri(
                    f"/envios/seguimiento/{envio.numero_seguimiento}/"
                ),
                "qr_url": f"/media/{envio.qr_code.name}" if envio.qr_code else None
            }, status=201)

        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON inválido"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Método no permitido"}, status=405)


from django.http import HttpResponse, Http404
from django.conf import settings
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user
import mimetypes, os
from utils.storage import PrivateEncryptedStorage
from .models import Entrega

# Si tu login es propio (session['usuario_id']), NO uses login_required de Django.
def require_panel_login(view_fn):
    def _wrapped(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            # respeta LOGIN_URL configurado en settings
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return view_fn(request, *args, **kwargs)
    return _wrapped

def ver_firma(request, entrega_id):
    try:
        entrega = Entrega.objects.get(pk=entrega_id)
        if not entrega.firma:
            raise Http404("No hay firma para esta entrega.")
    except Entrega.DoesNotExist:
        raise Http404("Entrega no encontrada.")

    storage = PrivateEncryptedStorage()
    path = entrega.firma.name  # ej: 'entregas/firma_20.png'

    if not storage.exists(path):
        raise Http404("Archivo no encontrado.")

    f = storage._open(path)  # descifrado
    f.seek(0)
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"

    resp = HttpResponse(f.read(), content_type=mime)
    resp["Content-Disposition"] = f'inline; filename="{os.path.basename(path)}"'
    return resp

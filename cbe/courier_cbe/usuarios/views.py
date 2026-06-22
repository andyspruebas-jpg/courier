from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q
from django.conf import settings

from .models import Empresa, Usuario
from .forms import EmpresaForm, PerfilMensajeroForm, UsuarioForm, LoginForm
from .security import is_admin, is_cliente, is_mensajero, usuario_from_request
from envios.models import Envio, Entrega
import json
from django.http import JsonResponse
from .models import PerfilMensajero, UbicacionMensajero
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken


def _empresa_payload(empresa):
    if not empresa:
        return None
    return {
        "id": empresa.id,
        "nombre": empresa.nombre,
        "nit": empresa.nit,
        "direccion": empresa.direccion,
        "contacto": empresa.contacto,
        "telefono": empresa.telefono,
        "email": empresa.email,
        "activa": empresa.activa,
    }


def _usuario_payload(usuario):
    return {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "telefono": usuario.telefono,
        "rol": usuario.rol.nombre,
        "is_active": usuario.is_active,
        "empresa": _empresa_payload(usuario.empresa),
    }


def _login_payload(usuario, refresh):
    return {
        **_usuario_payload(usuario),
        "status": "success",
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


@csrf_exempt
def api_token_refresh(request):
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
        refresh_raw = data.get("refresh")
        if not refresh_raw:
            return JsonResponse({"error": "Falta refresh"}, status=400)
        refresh = RefreshToken(refresh_raw)
        return JsonResponse({"access": str(refresh.access_token)}, status=200)
    except (TokenError, json.JSONDecodeError):
        return JsonResponse({"error": "Refresh inválido"}, status=401)


# ------------------------------------------------------------------------------
# 🔹 CRUD de usuarios
# ------------------------------------------------------------------------------

def lista_usuarios(request):
    # Obtener búsqueda
    search_query = request.GET.get('search', '')
    
    # Filtrar usuarios por búsqueda con select_related para optimizar
    usuarios = Usuario.objects.select_related('rol', 'empresa').all()
    if search_query:
        usuarios = usuarios.filter(
            nombre__icontains=search_query
        ) | usuarios.filter(
            email__icontains=search_query
        )
    
    # Ordenar por ID
    usuarios = usuarios.order_by('-id')
    
    # Paginación (10 por página)
    from django.core.paginator import Paginator
    paginator = Paginator(usuarios, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'usuarios/lista_usuarios.html', {
        'page_obj': page_obj,
        'search_query': search_query
    })


def crear_usuario(request):
    if request.method == 'POST':
        form = UsuarioForm(request.POST)
        perfil_form = PerfilMensajeroForm(request.POST, request.FILES)
        if form.is_valid():
            usuario = form.save()
            if usuario.rol and usuario.rol.nombre.lower() == "mensajero" and perfil_form.is_valid():
                perfil, _ = PerfilMensajero.objects.get_or_create(usuario=usuario)
                perfil.vehiculo = perfil_form.cleaned_data.get("vehiculo")
                perfil.zona_cobertura = perfil_form.cleaned_data.get("zona_cobertura")
                perfil.zona_cobertura_secundaria = perfil_form.cleaned_data.get("zona_cobertura_secundaria")
                perfil.disponible = perfil_form.cleaned_data.get("disponible")
                perfil.latitud = perfil_form.cleaned_data.get("latitud")
                perfil.longitud = perfil_form.cleaned_data.get("longitud")
                perfil.foto = perfil_form.cleaned_data.get("foto")
                perfil.save()
            return redirect('usuarios:lista_usuarios')
    else:
        form = UsuarioForm()
        perfil_form = PerfilMensajeroForm()
    return render(request, 'usuarios/crear_usuario.html', {'form': form, 'perfil_form': perfil_form})


def ver_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario.objects.select_related('rol'), id=usuario_id)
    return render(request, 'usuarios/ver_usuario.html', {'usuario': usuario})


def editar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario.objects.select_related('rol'), id=usuario_id)
    perfil, _ = PerfilMensajero.objects.get_or_create(usuario=usuario) if usuario.rol.nombre.lower() == "mensajero" else (None, False)
    if request.method == 'POST':
        form = UsuarioForm(request.POST, instance=usuario)
        perfil_form = PerfilMensajeroForm(request.POST, request.FILES, instance=perfil)
        if form.is_valid() and (perfil is None or perfil_form.is_valid()):
            usuario = form.save()
            if usuario.rol and usuario.rol.nombre.lower() == "mensajero":
                perfil, _ = PerfilMensajero.objects.get_or_create(usuario=usuario)
                perfil_form = PerfilMensajeroForm(request.POST, request.FILES, instance=perfil)
                if perfil_form.is_valid():
                    perfil_form.save()
            return redirect('usuarios:lista_usuarios')
    else:
        form = UsuarioForm(instance=usuario)
        perfil_form = PerfilMensajeroForm(instance=perfil)
    return render(request, 'usuarios/editar_usuario.html', {'form': form, 'perfil_form': perfil_form, 'usuario': usuario})


def eliminar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    if request.method == 'POST':
        usuario.delete()
        return redirect('usuarios:lista_usuarios')
    return render(request, 'usuarios/eliminar_usuario.html', {'usuario': usuario})


def lista_empresas(request):
    search_query = request.GET.get("search", "")
    empresas = Empresa.objects.annotate(
        usuarios_count=Count("usuarios", distinct=True),
        envios_count=Count("usuarios__remitente", distinct=True),
    ).order_by("nombre")
    if search_query:
        empresas = empresas.filter(
            Q(nombre__icontains=search_query)
            | Q(nit__icontains=search_query)
            | Q(contacto__icontains=search_query)
            | Q(direccion__icontains=search_query)
        )
    return render(request, "usuarios/lista_empresas.html", {
        "empresas": empresas,
        "search_query": search_query,
    })


def crear_empresa(request):
    form = EmpresaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("usuarios:lista_empresas")
    return render(request, "usuarios/empresa_form.html", {"form": form, "titulo": "Crear Empresa"})


def editar_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    form = EmpresaForm(request.POST or None, instance=empresa)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("usuarios:lista_empresas")
    return render(request, "usuarios/empresa_form.html", {"form": form, "titulo": "Editar Empresa", "empresa": empresa})


def eliminar_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    if request.method == "POST":
        empresa.delete()
        return redirect("usuarios:lista_empresas")
    return render(request, "usuarios/eliminar_empresa.html", {"empresa": empresa})


# ------------------------------------------------------------------------------
# 🔹 Cerrar sesión (para interfaz web)
# ------------------------------------------------------------------------------
def cerrar_sesion(request):
    logout(request)
    return redirect('usuarios:login')


# ------------------------------------------------------------------------------
# 🔹 Login general (web + API JSON)
# ------------------------------------------------------------------------------
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt  # 👈 Permite login desde Flutter (sin CSRF)
def login_view(request):
    """
    Maneja login tanto desde web (HTML) como desde API (JSON para Flutter)
    """
    if request.method == 'POST':
        # Detectar si la petición es JSON (Flutter) o form-data (web)
        is_json = request.content_type == 'application/json'

        if is_json:
            # ✅ Login desde Flutter (API)
            try:
                data = json.loads(request.body.decode('utf-8'))
                email = data.get('email')
                contrasena = data.get('contrasena')

                if not email or not contrasena:
                    return JsonResponse({'error': 'Faltan credenciales'}, status=400)

                usuario = Usuario.objects.select_related("rol", "empresa").filter(email=email).first()
                if usuario and usuario.check_password(contrasena):
                    # Generar token
                    refresh = RefreshToken.for_user(usuario)
                    
                    return JsonResponse(_login_payload(usuario, refresh), status=200)
                else:
                    return JsonResponse({'error': 'Credenciales inválidas'}, status=401)

            except json.JSONDecodeError:
                return JsonResponse({'error': 'JSON inválido'}, status=400)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

        else:
            # ✅ Login desde formulario HTML (web)
            form = LoginForm(request.POST)
            if form.is_valid():
                email = form.cleaned_data['email']
                contrasena = form.cleaned_data['contrasena']
                try:
                    usuario = Usuario.objects.get(email=email)
                    if usuario.check_password(contrasena):
                        request.session['usuario_id'] = usuario.id
                        return redirect('usuarios:home')
                    else:
                        messages.error(request, "Contraseña incorrecta")
                except Usuario.DoesNotExist:
                    messages.error(request, "El usuario con este correo no existe")
            return render(request, 'usuarios/login.html', {'form': form})

    else:
        form = LoginForm()
        return render(request, 'usuarios/login.html', {'form': form})


# ------------------------------------------------------------------------------
# 🔹 Página principal (Dashboard)
# ------------------------------------------------------------------------------
def home(request):
    from django.core.cache import cache

    usuario = usuario_from_request(request, allow_legacy_params=False)
    if usuario and is_cliente(usuario):
        envios = _envios_cliente_qs(usuario)
        return render(request, "usuarios/home_cliente.html", {
            "usuario": usuario,
            "envios": envios[:6],
            "total_envios": envios.count(),
            "pendientes": envios.filter(estado="Pendiente").count(),
            "en_ruta": envios.filter(estado="En Ruta").count(),
            "entregados": envios.filter(estado="Entregado").count(),
        })
    
    # Intentar obtener datos del caché
    cache_key = 'dashboard_data'
    context = cache.get(cache_key)
    
    if context is None:
        # Si no está en caché, calcular
        usuarios_count = Usuario.objects.count()
        envios_pendientes = Envio.objects.filter(estado="Pendiente").count()
        mensajeros_activos = Usuario.objects.filter(rol__nombre__iexact="mensajero").count()
        entregados = Entrega.objects.filter(estado="Entregado").count()
        total_envios = Envio.objects.count()
        porcentaje_entregados = (entregados / total_envios * 100) if total_envios > 0 else 0

        context = {
            "usuarios_count": usuarios_count,
            "envios_pendientes": envios_pendientes,
            "mensajeros_activos": mensajeros_activos,
            "porcentaje_entregados": round(porcentaje_entregados, 2),
        }
        
        # Guardar en caché por 5 minutos
        cache.set(cache_key, context, 300)
    
    return render(request, "usuarios/home.html", context)


def _envios_cliente_qs(usuario):
    qs = Envio.objects.select_related("remitente", "mensajero").filter(remitente=usuario)
    if usuario.empresa_id:
        qs = qs | Envio.objects.select_related("remitente", "mensajero").filter(
            remitente__empresa=usuario.empresa
        )
    return qs.distinct().order_by("-creado_en")


# ------------------------------------------------------------------------------
# 🔹 Vista de mensajeros (mapa / ubicación)
# ------------------------------------------------------------------------------
def mensajeros_view(request):
    from zonas.models import Zona

    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not is_admin(usuario):
        return JsonResponse({"error": "Solo administradores"}, status=403)

    mensajeros = (
        Usuario.objects.filter(rol__nombre__iexact="mensajero", is_active=True)
        .select_related(
            "rol",
            "perfil_mensajero",
            "perfil_mensajero__zona_cobertura",
            "perfil_mensajero__zona_cobertura_secundaria",
        )
    )
    mensajeros_data = _mensajeros_payload(mensajeros)

    zonas_qs = Zona.objects.order_by("nombre")
    zonas_geo = []
    for z in zonas_qs:
        try:
            area = z.get_area_as_list()
        except Exception:
            area = []
        zonas_geo.append({"id": z.id, "nombre": z.nombre, "area": area})

    return render(request, "usuarios/mensajeros.html", {
        "mensajeros_json": json.dumps(mensajeros_data),
        "zonas": zonas_qs,
        "zonas_geo_json": json.dumps(zonas_geo),
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
    })


# ------------------------------------------------------------------------------
# 🔹 API login separado (si quieres usar otra ruta /usuarios/api/login/)
# ------------------------------------------------------------------------------
@csrf_exempt
def api_login(request):
    """
    Endpoint alternativo solo para Flutter (POST JSON)
    Ruta: /usuarios/api/login/
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            email = data.get('email')
            contrasena = data.get('contrasena')

            usuario = Usuario.objects.select_related("rol", "empresa").filter(email=email).first()
            if usuario and usuario.check_password(contrasena):
                # Generar token
                refresh = RefreshToken.for_user(usuario)

                return JsonResponse(_login_payload(usuario, refresh), status=200)
            else:
                return JsonResponse({"error": "Credenciales inválidas"}, status=401)
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON inválido"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Método no permitido"}, status=405)


@csrf_exempt
def api_register(request):
    """
    Endpoint para registrar usuarios desde Flutter/Externo (POST JSON)
    Ruta: /usuarios/api/register/
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            nombre = data.get('nombre')
            email = data.get('email')
            contrasena = data.get('contrasena')
            rol_nombre = data.get('rol', 'Cliente')  # El registro público solo permite clientes.
            telefono = data.get('telefono', '')
            empresa_id = data.get('empresa_id')

            if not nombre or not email or not contrasena:
                return JsonResponse({'error': 'Faltan datos obligatorios (nombre, email, contrasena)'}, status=400)

            if (rol_nombre or "").strip().lower() != "cliente":
                return JsonResponse({'error': 'El registro público solo permite usuarios cliente'}, status=403)

            if Usuario.objects.filter(email=email).exists():
                return JsonResponse({'error': 'El email ya está registrado'}, status=400)

            empresa = None
            if empresa_id:
                empresa = Empresa.objects.filter(id=empresa_id, activa=True).first()
                if not empresa:
                    return JsonResponse({'error': 'La empresa indicada no existe o está inactiva'}, status=400)
            elif Empresa.objects.exists():
                return JsonResponse({'error': 'Debes indicar empresa_id para registrar el usuario'}, status=400)

            # Buscar o crear rol (ajusta según tu lógica de roles)
            from .models import Rol
            rol_obj, _ = Rol.objects.get_or_create(nombre=rol_nombre)

            usuario = Usuario.objects.create(
                nombre=nombre,
                email=email,
                telefono=telefono,
                rol=rol_obj,
                empresa=empresa,
            )
            usuario.set_password(contrasena)
            usuario.save()

            # Opcional: Devolver token directamente al registrarse
            refresh = RefreshToken.for_user(usuario)

            return JsonResponse(_login_payload(usuario, refresh), status=201)

        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON inválido"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Método no permitido"}, status=405)

from django.http import JsonResponse


@csrf_exempt
def perfil(request):
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not usuario:
        return JsonResponse({"error": "No autenticado"}, status=401)
    if request.method in ("PUT", "PATCH", "POST"):
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON inválido"}, status=400)

        nombre = (data.get("nombre") or "").strip()
        email = (data.get("email") or "").strip().lower()
        telefono = (data.get("telefono") or "").strip()

        changed_user_fields = []
        if nombre:
            usuario.nombre = nombre
            changed_user_fields.append("nombre")
        if telefono:
            usuario.telefono = telefono
            changed_user_fields.append("telefono")
        if email and email != usuario.email:
            if Usuario.objects.exclude(pk=usuario.pk).filter(email=email).exists():
                return JsonResponse({"error": "El correo ya está registrado"}, status=400)
            usuario.email = email
            changed_user_fields.append("email")
        if changed_user_fields:
            usuario.save(update_fields=changed_user_fields)

        empresa_data = data.get("empresa")
        if isinstance(empresa_data, dict) and usuario.empresa_id:
            empresa = usuario.empresa
            allowed_empresa_fields = ("nombre", "nit", "direccion", "contacto", "telefono", "email")
            changed_empresa_fields = []
            for field in allowed_empresa_fields:
                raw_value = empresa_data.get(field)
                if raw_value is None:
                    continue
                value = str(raw_value).strip()
                if field == "nit" and value:
                    if Empresa.objects.exclude(pk=empresa.pk).filter(nit=value).exists():
                        return JsonResponse({"error": "El NIT ya está registrado"}, status=400)
                if field == "email":
                    value = value.lower()
                setattr(empresa, field, value)
                changed_empresa_fields.append(field)
            if changed_empresa_fields:
                empresa.save(update_fields=changed_empresa_fields)

        usuario = Usuario.objects.select_related("rol", "empresa").get(pk=usuario.pk)
    return JsonResponse(_usuario_payload(usuario))


def home_data(request):
    from django.core.cache import cache
    
    # Intentar obtener datos del caché
    cache_key = 'dashboard_json_data'
    data = cache.get(cache_key)
    
    if data is None:
        usuarios_count = Usuario.objects.count()
        envios_pendientes = Envio.objects.filter(estado="Pendiente").count()
        mensajeros_activos = Usuario.objects.filter(rol__nombre__iexact="mensajero").count()
        entregados = Entrega.objects.filter(estado="Entregado").count()
        total_envios = Envio.objects.count()
        porcentaje_entregados = (entregados / total_envios * 100) if total_envios > 0 else 0

        data = {
            "usuarios_count": usuarios_count,
            "envios_pendientes": envios_pendientes,
            "mensajeros_activos": mensajeros_activos,
            "porcentaje_entregados": round(porcentaje_entregados, 2)
        }
        
        # Guardar en caché por 2 minutos (datos más dinámicos)
        cache.set(cache_key, data, 120)
    
    return JsonResponse(data)
def _mensajeros_payload(mensajeros):
    data = []
    for mensajero in mensajeros:
        perfil = getattr(mensajero, "perfil_mensajero", None)
        ultima = (
            UbicacionMensajero.objects
            .filter(mensajero=mensajero)
            .order_by("-fecha_hora")
            .only("fecha_hora")
            .first()
        )
        foto_url = None
        if perfil and perfil.foto:
            try:
                foto_url = perfil.foto.url
            except Exception:
                foto_url = None

        # Zonas que cubre el mensajero = su zona base + zonas de sus envíos activos
        zona_ids = set()
        if perfil and perfil.zona_cobertura_id:
            zona_ids.add(perfil.zona_cobertura_id)
        if perfil and perfil.zona_cobertura_secundaria_id:
            zona_ids.add(perfil.zona_cobertura_secundaria_id)

        zonas_nombres = []
        if perfil and perfil.zona_cobertura:
            zonas_nombres.append(perfil.zona_cobertura.nombre)
        if perfil and perfil.zona_cobertura_secundaria:
            zonas_nombres.append(perfil.zona_cobertura_secundaria.nombre)

        data.append({
            "id": mensajero.id,
            "nombre": mensajero.nombre,
            "email": mensajero.email,
            "telefono": mensajero.telefono,
            "foto_url": foto_url,
            "latitud": str(perfil.latitud) if perfil and perfil.latitud is not None else None,
            "longitud": str(perfil.longitud) if perfil and perfil.longitud is not None else None,
            "lat": float(perfil.latitud) if perfil and perfil.latitud is not None else None,
            "lng": float(perfil.longitud) if perfil and perfil.longitud is not None else None,
            "vehiculo": perfil.vehiculo if perfil else None,
            "disponible": not Envio.objects.filter(mensajero=mensajero, estado__in=['Pendiente', 'En Ruta']).exists(),
            "zona_id": perfil.zona_cobertura_id if perfil else None,
            "zona": " / ".join(zonas_nombres) if zonas_nombres else None,
            "zona_ids": list(zona_ids),
            "last_seen": ultima.fecha_hora.isoformat() if ultima else None,
        })
    return data


def mensajeros_json(request):
    """
    Devuelve mensajeros con envios asignados y coordenadas de perfil.
    """
    usuario = usuario_from_request(request, allow_legacy_params=False)
    if not is_admin(usuario):
        return JsonResponse({"error": "Solo administradores"}, status=403)

    # Filtrar mensajeros que tengan al menos un envío asignado
    mensajeros = Usuario.objects.select_related(
        "perfil_mensajero",
        "perfil_mensajero__zona_cobertura",
        "perfil_mensajero__zona_cobertura_secundaria",
    ).filter(
        rol__nombre__iexact="mensajero",
        is_active=True,
        id__in=Envio.objects.exclude(mensajero_id__isnull=True).values("mensajero_id"),
    ).distinct()

    zona_id = request.GET.get("zona_id")
    if zona_id:
        mensajeros = mensajeros.filter(
            Q(perfil_mensajero__zona_cobertura_id=zona_id)
            | Q(perfil_mensajero__zona_cobertura_secundaria_id=zona_id)
            | Q(mensajero__zona_id=zona_id)
        )

    ruta_id = request.GET.get("ruta_id")
    if ruta_id:
        from rutas.models import Ruta

        mensajero_ids = Ruta.objects.filter(id=ruta_id).values_list("mensajero_id", flat=True)
        mensajeros = mensajeros.filter(id__in=mensajero_ids)

    if request.GET.get("solo_disponibles") in ("1", "true", "True"):
        # Disponible = sin envíos Pendiente ni En Ruta
        mensajeros = mensajeros.exclude(
            id__in=Envio.objects.filter(estado__in=['Pendiente', 'En Ruta']).values_list('mensajero_id', flat=True)
        )

    return JsonResponse(_mensajeros_payload(mensajeros.order_by("nombre")), safe=False)

# views.py
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.http import JsonResponse
from .models import PerfilMensajero, UbicacionMensajero, Usuario
import json

@csrf_exempt
def actualizar_ubicacion(request):
    """
    Guarda la ubicación actual y registra histórico.
    POST JSON: { "latitud": -16.5, "longitud": -68.13 }
    Los administradores pueden enviar usuario_id; los mensajeros siempre usan el
    usuario resuelto desde sesión/JWT.
    """
    if request.method == 'POST':
        try:
            usuario_actual = usuario_from_request(request, allow_legacy_params=False)
            if not usuario_actual:
                return JsonResponse({'error': 'Token requerido'}, status=401)
            if not (is_admin(usuario_actual) or is_mensajero(usuario_actual)):
                return JsonResponse({'error': 'Solo mensajeros o administradores'}, status=403)

            data = json.loads(request.body.decode('utf-8'))
            latitud = data.get('latitud')
            longitud = data.get('longitud')

            if latitud in (None, "") or longitud in (None, ""):
                return JsonResponse({'error': 'Datos incompletos'}, status=400)

            usuario_id = data.get('usuario_id') if is_admin(usuario_actual) else usuario_actual.id
            if not usuario_id:
                usuario_id = usuario_actual.id

            usuario = Usuario.objects.filter(id=usuario_id, is_active=True).first()
            if not usuario:
                return JsonResponse({'error': 'Usuario no encontrado'}, status=404)
            if not is_mensajero(usuario):
                return JsonResponse({'error': 'El usuario destino no es mensajero'}, status=400)

            # 🔹 Actualiza ubicación actual
            perfil, _ = PerfilMensajero.objects.get_or_create(usuario=usuario)
            perfil.latitud = latitud
            perfil.longitud = longitud
            perfil.save()

            # 🔹 Guarda registro histórico
            UbicacionMensajero.objects.create(
                mensajero=usuario,
                latitud=latitud,
                longitud=longitud
            )

            return JsonResponse({'status': 'success', 'mensaje': 'Ubicación actualizada correctamente'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Método no permitido'}, status=405)
from django.shortcuts import render
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from .models import UbicacionMensajero, Usuario
from datetime import date
from django.db.models import Count, Max, Min
from django.db.models.functions import TruncDate


def mensajeros_con_ruta_en_fecha(fecha):
    if not fecha:
        return Usuario.objects.none()

    mensajero_ids = (
        UbicacionMensajero.objects.filter(fecha_hora__date=fecha)
        .values_list('mensajero_id', flat=True)
        .distinct()
    )

    return (
        Usuario.objects.filter(
            rol__nombre__iexact='mensajero',
            id__in=mensajero_ids,
        )
        .select_related('rol')
        .order_by('nombre')
    )


def disponibilidad_rutas_por_fecha():
    resumen = (
        UbicacionMensajero.objects.filter(mensajero__rol__nombre__iexact='mensajero')
        .annotate(fecha=TruncDate('fecha_hora'))
        .values('fecha')
        .annotate(total_mensajeros=Count('mensajero_id', distinct=True))
        .order_by('fecha')
    )

    return {
        item['fecha'].isoformat(): item['total_mensajeros']
        for item in resumen
        if item['fecha']
    }


def rutas_mensajeros_view(request):
    """
    Página principal del mapa de rutas de mensajeros
    """
    route_dates = UbicacionMensajero.objects.aggregate(
        min_fecha=Min('fecha_hora__date'),
        max_fecha=Max('fecha_hora__date'),
    )
    default_route_date = route_dates['max_fecha'] or date.today()
    mensajeros = mensajeros_con_ruta_en_fecha(default_route_date)
    route_availability = disponibilidad_rutas_por_fecha()

    return render(request, 'usuarios/rutas_mensajeros.html', {
        'mensajeros': mensajeros,
        'today': date.today(),
        'default_route_date': default_route_date,
        'min_route_date': route_dates['min_fecha'],
        'max_route_date': route_dates['max_fecha'],
        'route_availability': route_availability,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    })


def obtener_ruta_mensajero(request):
    """
    API que devuelve las coordenadas del mensajero en una fecha específica.
    Parámetros GET: ?mensajero_id=3&fecha=2025-10-19
    """
    mensajero_id = request.GET.get('mensajero_id')
    fecha_str = request.GET.get('fecha')
    if not mensajero_id or not fecha_str:
        return JsonResponse({'error': 'Faltan parámetros'}, status=400)

    try:
        fecha = parse_date(fecha_str)
        ubicaciones = UbicacionMensajero.objects.filter(
            mensajero_id=mensajero_id,
            fecha_hora__date=fecha
        ).only('latitud', 'longitud', 'fecha_hora').order_by('fecha_hora')

        data = [
            {
                'lat': float(u.latitud),
                'lng': float(u.longitud),
                'hora': u.fecha_hora.strftime('%H:%M:%S')
            }
            for u in ubicaciones
        ]
        return JsonResponse({'puntos': data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def obtener_mensajeros_con_ruta(request):
    fecha_str = request.GET.get('fecha')
    if not fecha_str:
        return JsonResponse({'error': 'Falta la fecha'}, status=400)

    fecha = parse_date(fecha_str)
    if not fecha:
        return JsonResponse({'error': 'Fecha inválida'}, status=400)

    mensajeros = mensajeros_con_ruta_en_fecha(fecha)
    data = [
        {
            'id': mensajero.id,
            'nombre': mensajero.nombre,
            'email': mensajero.email,
        }
        for mensajero in mensajeros
    ]
    return JsonResponse({'mensajeros': data})

from django.core.mail import send_mail
from django.conf import settings
from .models import PasswordResetToken
from .forms import PasswordResetRequestForm, PasswordResetForm

def password_reset_request(request):
    reset_url = None
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            usuario = Usuario.objects.filter(email=email).first()

            if usuario:
                PasswordResetToken.objects.filter(usuario=usuario).delete()
                token_obj = PasswordResetToken.objects.create(usuario=usuario)

                reset_url = f"{request.scheme}://{request.get_host()}/usuarios/restablecer/{token_obj.token}/"

                if settings.DEBUG:
                    messages.success(request, "Enlace generado correctamente para desarrollo local.")
                    return render(request, "usuarios/password_reset_request.html", {
                        "form": PasswordResetRequestForm(),
                        "reset_url": reset_url,
                        "email": email,
                    })

                send_mail(
                    subject="Recuperación de contraseña",
                    message=f"Hola {usuario.nombre}, usa este enlace para restablecer tu contraseña:\n\n{reset_url}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@courier.com"),
                    recipient_list=[email],
                    fail_silently=False,
                )

                messages.success(request, "Se envió un enlace a tu correo.")
                return redirect("usuarios:login")
            else:
                messages.error(request, "Este correo no está registrado.")
    else:
        form = PasswordResetRequestForm()

    return render(request, "usuarios/password_reset_request.html", {"form": form, "reset_url": reset_url})

def password_reset(request, token):
    token_obj = PasswordResetToken.objects.filter(token=token).first()

    if not token_obj or token_obj.expirado():
        messages.error(request, "El enlace es inválido o ha expirado.")
        return redirect("usuarios:password_reset_request")

    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            nueva = form.cleaned_data["nueva_contrasena"]
            usuario = token_obj.usuario

            usuario.set_password(nueva)
            usuario.save()

            token_obj.delete()  # invalidar token luego de usarlo

            messages.success(request, "Contraseña actualizada correctamente.")
            return redirect("usuarios:login")
    else:
        form = PasswordResetForm()

    return render(request, "usuarios/password_reset.html", {"form": form})

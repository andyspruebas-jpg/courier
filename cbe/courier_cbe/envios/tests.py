import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from usuarios.models import Empresa, Rol, Usuario
from .models import Envio, HistorialEnvio, NotificacionEnvio, ReasignacionEnvio


class SeguimientoEnvioTests(TestCase):
    def setUp(self):
        self.rol_admin = Rol.objects.create(nombre="Administrador")
        self.rol_mensajero = Rol.objects.create(nombre="Mensajero")
        self.admin = Usuario.objects.create(
            nombre="Admin",
            email="admin@test.com",
            contrasena="x",
            rol=self.rol_admin,
        )
        self.m1 = Usuario.objects.create(
            nombre="Mensajero Uno",
            email="m1@test.com",
            contrasena="x",
            rol=self.rol_mensajero,
        )
        self.m2 = Usuario.objects.create(
            nombre="Mensajero Dos",
            email="m2@test.com",
            contrasena="x",
            rol=self.rol_mensajero,
        )
        self.envio = Envio.objects.create(
            remitente_nombre="Ana",
            remitente_telefono="77777777",
            destinatario_nombre="Luis",
            destinatario_telefono="66666666",
            origen_direccion="Origen",
            destino_direccion="Destino",
            peso=1,
            tipo_servicio="Express",
            tipo_pago="Origen",
            monto_pago=10,
            mensajero=self.m1,
        )

    def test_api_crear_envio_devuelve_numero_de_seguimiento(self):
        token = RefreshToken.for_user(self.admin).access_token
        response = self.client.post(
            reverse("envios:api_crear_envio"),
            data=json.dumps({
                "remitente_nombre": "Juan",
                "destinatario_nombre": "Maria",
                "origen_direccion": "Av. Arce",
                "destino_direccion": "Calacoto",
                "peso": 2,
                "tipo_servicio": "Estándar",
                "tipo_pago": "Destino",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("numero_seguimiento", data)
        self.assertTrue(data["tracking_url"].endswith(f"/envios/seguimiento/{data['numero_seguimiento']}/"))

    def test_api_crear_envio_anonimo_devuelve_401(self):
        response = self.client.post(
            reverse("envios:api_crear_envio"),
            data=json.dumps({
                "remitente_nombre": "Juan",
                "destinatario_nombre": "Maria",
                "origen_direccion": "Av. Arce",
                "destino_direccion": "Calacoto",
                "peso": 2,
                "tipo_servicio": "Estándar",
                "tipo_pago": "Destino",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_api_crear_envio_mensajero_devuelve_403(self):
        token = RefreshToken.for_user(self.m1).access_token
        response = self.client.post(
            reverse("envios:api_crear_envio"),
            data=json.dumps({
                "remitente_nombre": "Juan",
                "destinatario_nombre": "Maria",
                "origen_direccion": "Av. Arce",
                "destino_direccion": "Calacoto",
                "peso": 2,
                "tipo_servicio": "Estándar",
                "tipo_pago": "Destino",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 403)

    def test_seguimiento_api_incluye_timeline_y_mensajero_en_curso(self):
        HistorialEnvio.objects.create(
            envio=self.envio,
            tipo_evento="Creado",
            observaciones="Alta inicial",
        )
        response = self.client.get(reverse("envios:seguimiento_api", args=[self.envio.numero_seguimiento]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["numero_seguimiento"], self.envio.numero_seguimiento)
        self.assertEqual(data["mensajero"]["nombre"], self.m1.nombre)
        self.assertEqual(data["timeline"][0]["tipo"], "Creado")

    def test_reasignar_envio_audita_y_notifica(self):
        session = self.client.session
        session["usuario_id"] = self.admin.id
        session.save()

        response = self.client.post(
            reverse("envios:reasignar_envio", args=[self.envio.id]),
            {"mensajero_id": self.m2.id, "motivo": "Sobrecarga"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.mensajero, self.m2)
        self.assertTrue(ReasignacionEnvio.objects.filter(envio=self.envio, mensajero_nuevo=self.m2).exists())
        self.assertTrue(HistorialEnvio.objects.filter(envio=self.envio, tipo_evento="Reasignado").exists())
        self.assertTrue(NotificacionEnvio.objects.filter(envio=self.envio, asunto="Envío reasignado").exists())


class RouteRecalculationSignalTests(TestCase):
    def setUp(self):
        self.rol_mensajero = Rol.objects.create(nombre="Mensajero")
        self.mensajero = Usuario.objects.create(
            nombre="Mensajero Ruta",
            email="ruta@test.com",
            contrasena="x",
            rol=self.rol_mensajero,
            is_active=True,
        )

    def _crear_envio(self):
        return Envio.objects.create(
            remitente_nombre="Ana",
            remitente_telefono="77777777",
            destinatario_nombre="Luis",
            destinatario_telefono="66666666",
            origen_direccion="Origen",
            destino_direccion="Destino",
            latitud_origen="-16.500000",
            longitud_origen="-68.150000",
            latitud_destino="-16.510000",
            longitud_destino="-68.140000",
            peso=1,
            tipo_servicio="Express",
            tipo_pago="Origen",
            monto_pago=10,
            mensajero=self.mensajero,
        )

    @patch("envios.signals.rebuild_route_for_messenger")
    def test_envio_asignado_recalcula_ruta_del_mensajero(self, rebuild):
        with self.captureOnCommitCallbacks(execute=True):
            self._crear_envio()

        rebuild.assert_called_once_with(self.mensajero)

    @patch("envios.signals.rebuild_route_for_messenger")
    def test_campos_internos_de_ruta_no_disparan_recalculo(self, rebuild):
        with self.captureOnCommitCallbacks(execute=True):
            envio = self._crear_envio()
        rebuild.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            envio.orden_ruta = 1
            envio.eta_min = 8.5
            envio.ruta_id = 99
            envio.save(update_fields=["orden_ruta", "eta_min", "ruta_id"])

        rebuild.assert_not_called()


class ClienteAccessTests(TestCase):
    def setUp(self):
        self.rol_cliente = Rol.objects.create(nombre="Cliente")
        self.empresa_cliente = Empresa.objects.create(
            nombre="Cliente Uno",
            nit="CLI-001",
            direccion="Av. Cliente 123",
            telefono="77777777",
        )
        self.empresa_otra = Empresa.objects.create(
            nombre="Cliente Dos",
            nit="CLI-002",
            direccion="Av. Otra 456",
            telefono="66666666",
        )
        self.cliente = Usuario.objects.create(
            nombre="Cliente Usuario",
            email="cliente@test.com",
            contrasena="x",
            rol=self.rol_cliente,
            empresa=self.empresa_cliente,
        )
        self.otro_cliente = Usuario.objects.create(
            nombre="Otro Cliente",
            email="otro@test.com",
            contrasena="x",
            rol=self.rol_cliente,
            empresa=self.empresa_otra,
        )
        self.envio_propio = Envio.objects.create(
            remitente=self.cliente,
            remitente_nombre="Cliente Usuario",
            remitente_telefono="77777777",
            destinatario_nombre="Destino Propio",
            destinatario_telefono="70000001",
            origen_direccion="Origen propio",
            destino_direccion="Destino propio",
            peso=1,
            tipo_servicio="Estándar",
            tipo_pago="Pendiente",
            monto_pago=0,
        )
        self.envio_ajeno = Envio.objects.create(
            remitente=self.otro_cliente,
            remitente_nombre="Otro Cliente",
            remitente_telefono="66666666",
            destinatario_nombre="Destino Ajeno",
            destinatario_telefono="70000002",
            origen_direccion="Origen ajeno",
            destino_direccion="Destino ajeno",
            peso=1,
            tipo_servicio="Estándar",
            tipo_pago="Pendiente",
            monto_pago=0,
        )
        session = self.client.session
        session["usuario_id"] = self.cliente.id
        session.save()

    def test_cliente_home_no_muestra_menu_administrativo(self):
        response = self.client.get(reverse("usuarios:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mis envíos")
        self.assertNotContains(response, "Usuarios</a>")
        self.assertNotContains(response, "Empresas</a>")
        self.assertNotContains(response, "Reportes</a>")

    def test_cliente_no_puede_abrir_empresas_por_url(self):
        response = self.client.get(reverse("usuarios:lista_empresas"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith(reverse("usuarios:home")))

    def test_cliente_lista_solo_sus_envios_y_sin_acciones_admin(self):
        response = self.client.get(reverse("envios:lista_envios"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.envio_propio.numero_seguimiento)
        self.assertNotContains(response, self.envio_ajeno.numero_seguimiento)
        self.assertNotContains(response, "Editar")
        self.assertNotContains(response, "Reasignar")
        self.assertNotContains(response, "Eliminar")

import json
from datetime import datetime
from decimal import Decimal

from django.test import SimpleTestCase
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from envios.models import Envio
from usuarios.models import Empresa, PerfilMensajero, Rol, UbicacionMensajero, Usuario
from usuarios.management.commands.import_legacy_dump import (
    coerce_sql_value,
    parse_insert_statement,
    preserve_explicit_auto_timestamps,
    split_sql_values,
)
from usuarios.views import disponibilidad_rutas_por_fecha, mensajeros_con_ruta_en_fecha


class LegacyDumpParserTests(SimpleTestCase):
    def test_split_sql_values_keeps_commas_inside_strings(self):
        values = "4, 'Sopocachi Alto', '[[-16.501, -68.132], [-16.504, -68.128]]'"

        tokens = split_sql_values(values)

        self.assertEqual(tokens, [
            "4",
            "'Sopocachi Alto'",
            "'[[-16.501, -68.132], [-16.504, -68.128]]'",
        ])

    def test_parse_insert_statement_converts_datetime_and_quotes(self):
        statement = (
            "INSERT INTO public.envios_historialenvio "
            "(id, tipo_evento, fecha_evento, ubicacion_latitud, ubicacion_longitud, envio_id) "
            "VALUES (1, 'Actualizado', '2025-11-04 14:43:23.22996+00', -16.000013, -68.000071, 20);"
        )

        table_name, row = parse_insert_statement(statement)

        self.assertEqual(table_name, "envios_historialenvio")
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["tipo_evento"], "Actualizado")
        self.assertEqual(row["envio_id"], 20)
        self.assertEqual(str(row["ubicacion_latitud"]), "-16.000013")
        self.assertIsNotNone(row["fecha_evento"].tzinfo)

    def test_coerce_sql_value_unescapes_single_quotes(self):
        self.assertEqual(coerce_sql_value("'O''Brien'"), "O'Brien")
        self.assertIsNone(coerce_sql_value("NULL"))

    def test_preserve_explicit_auto_timestamps_restores_model_flags(self):
        field = Envio._meta.get_field("creado_en")

        self.assertTrue(field.auto_now_add)

        with preserve_explicit_auto_timestamps(Envio):
            self.assertFalse(field.auto_now_add)
            self.assertFalse(field.auto_now)

        self.assertTrue(field.auto_now_add)


class PublicRegisterRoleTests(TestCase):
    def test_registro_publico_no_permite_crear_administrador(self):
        response = self.client.post(
            reverse("usuarios:api_register"),
            data=json.dumps({
                "nombre": "Admin falso",
                "email": "admin-falso@test.com",
                "contrasena": "Secreta123!",
                "rol": "Administrador",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Usuario.objects.filter(email="admin-falso@test.com").exists())


class PerfilApiTests(TestCase):
    def setUp(self):
        self.rol_cliente = Rol.objects.create(nombre="Cliente")
        self.empresa = Empresa.objects.create(
            nombre="Farmacia Inicial",
            nit="1000000001",
            direccion="Calle 1",
            contacto="Dra. Inicial",
            telefono="71000000",
            email="farmacia.inicial@cbe.com",
        )
        self.usuario = Usuario.objects.create(
            nombre="Cliente Inicial",
            email="cliente.inicial@cbe.com",
            telefono="72000000",
            contrasena="hash",
            rol=self.rol_cliente,
            empresa=self.empresa,
            is_active=True,
        )

    def test_perfil_permite_actualizar_usuario_y_empresa(self):
        token = RefreshToken.for_user(self.usuario).access_token
        response = self.client.put(
            reverse("usuarios:perfil"),
            data=json.dumps({
                "nombre": "Farmacia San Miguel",
                "email": "farmacia@cbe.com",
                "telefono": "72001010",
                "empresa": {
                    "nombre": "Farmacia San Miguel",
                    "nit": "1029384756",
                    "direccion": "Calle 21 de Calacoto #45, La Paz",
                    "contacto": "Dra. Valeria Rojas",
                    "telefono": "72001010",
                    "email": "farmacia@cbe.com",
                },
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], "farmacia@cbe.com")
        self.assertEqual(data["empresa"]["nit"], "1029384756")
        self.usuario.refresh_from_db()
        self.empresa.refresh_from_db()
        self.assertEqual(self.usuario.nombre, "Farmacia San Miguel")
        self.assertEqual(self.empresa.email, "farmacia@cbe.com")


class RutasMensajerosFiltersTests(TestCase):
    def setUp(self):
        self.rol_mensajero = Rol.objects.create(nombre="Mensajero")
        self.rol_admin = Rol.objects.create(nombre="Administrador")

        self.juan = Usuario.objects.create(
            nombre="Juan Perez",
            email="juan@test.com",
            telefono="70123456",
            contrasena="hash",
            rol=self.rol_mensajero,
            is_active=True,
        )
        self.carlos = Usuario.objects.create(
            nombre="Carlos Mamani",
            email="carlos@test.com",
            telefono="70234567",
            contrasena="hash",
            rol=self.rol_mensajero,
            is_active=True,
        )
        self.admin = Usuario.objects.create(
            nombre="Admin",
            email="admin@test.com",
            telefono="77777777",
            contrasena="hash",
            rol=self.rol_admin,
            is_active=True,
        )
        session = self.client.session
        session["usuario_id"] = self.admin.id
        session.save()

        self._crear_ubicacion(self.juan, timezone.make_aware(datetime(2025, 11, 7, 12, 0)))
        self._crear_ubicacion(self.carlos, timezone.make_aware(datetime(2025, 11, 8, 12, 0)))
        self._crear_ubicacion(self.admin, timezone.make_aware(datetime(2025, 11, 8, 13, 0)))

    def _crear_ubicacion(self, usuario, fecha_hora):
        ubicacion = UbicacionMensajero.objects.create(
            mensajero=usuario,
            latitud=Decimal("-16.500000"),
            longitud=Decimal("-68.150000"),
        )
        UbicacionMensajero.objects.filter(pk=ubicacion.pk).update(fecha_hora=fecha_hora)

    def test_helper_filters_messengers_for_specific_date(self):
        mensajeros = list(mensajeros_con_ruta_en_fecha(datetime(2025, 11, 8).date()))

        self.assertEqual([mensajero.id for mensajero in mensajeros], [self.carlos.id])

    def test_view_uses_default_date_and_filtered_messengers(self):
        response = self.client.get(reverse("usuarios:rutas_mensajeros"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_route_date"].isoformat(), "2025-11-08")
        self.assertEqual(
            list(response.context["mensajeros"].values_list("id", flat=True)),
            [self.carlos.id],
        )

    def test_available_messengers_endpoint_returns_only_matching_date(self):
        response = self.client.get(
            reverse("usuarios:obtener_mensajeros_con_ruta"),
            {"fecha": "2025-11-07"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["mensajeros"],
            [
                {
                    "id": self.juan.id,
                    "nombre": self.juan.nombre,
                    "email": self.juan.email,
                }
            ],
        )

    def test_route_availability_groups_dates_with_distinct_messengers(self):
        self._crear_ubicacion(self.carlos, timezone.make_aware(datetime(2025, 11, 8, 16, 30)))

        disponibilidad = disponibilidad_rutas_por_fecha()

        self.assertEqual(
            disponibilidad,
            {
                "2025-11-07": 1,
                "2025-11-08": 1,
            },
        )

    def test_view_exposes_route_availability_for_calendar(self):
        response = self.client.get(reverse("usuarios:rutas_mensajeros"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["route_availability"],
            {
                "2025-11-07": 1,
                "2025-11-08": 1,
            },
        )
        self.assertContains(
            response,
            json.dumps({"2025-11-07": 1, "2025-11-08": 1}),
        )


class ActualizarUbicacionApiTests(TestCase):
    def setUp(self):
        self.rol_mensajero = Rol.objects.create(nombre="Mensajero")
        self.m1 = Usuario.objects.create(
            nombre="Mensajero Uno",
            email="m1@test.com",
            contrasena="hash",
            rol=self.rol_mensajero,
            is_active=True,
        )
        self.m2 = Usuario.objects.create(
            nombre="Mensajero Dos",
            email="m2@test.com",
            contrasena="hash",
            rol=self.rol_mensajero,
            is_active=True,
        )

    def test_actualizar_ubicacion_sin_token_devuelve_401(self):
        response = self.client.post(
            reverse("usuarios:actualizar_ubicacion"),
            data=json.dumps({"latitud": -16.5, "longitud": -68.15}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_mensajero_ignora_usuario_id_ajeno(self):
        token = RefreshToken.for_user(self.m1).access_token
        response = self.client.post(
            reverse("usuarios:actualizar_ubicacion"),
            data=json.dumps({
                "usuario_id": self.m2.id,
                "latitud": -16.51,
                "longitud": -68.16,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(UbicacionMensajero.objects.filter(mensajero=self.m1).exists())
        self.assertFalse(UbicacionMensajero.objects.filter(mensajero=self.m2).exists())
        perfil = PerfilMensajero.objects.get(usuario=self.m1)
        self.assertAlmostEqual(float(perfil.latitud), -16.51)

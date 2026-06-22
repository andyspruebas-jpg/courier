from django.apps import apps
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
import numpy as np
from rest_framework_simplejwt.tokens import RefreshToken

from rutas.models import MLTrainingState
from rutas.routing import compute_algorithmic_route
from rutas.views import _ordenar_y_estimar_eta
from usuarios.models import Rol, Usuario


class MLTrainingStateRegistrationTests(TestCase):
    def test_ml_training_state_esta_registrado_en_django(self):
        model = apps.get_model("rutas", "MLTrainingState")
        self.assertIs(model, MLTrainingState)
        state = MLTrainingState.objects.create(processed_count=3)
        self.assertEqual(str(state).split()[0], "MLState")


class AlimentarMlAuthTests(TestCase):
    def setUp(self):
        self.rol_admin = Rol.objects.create(nombre="Administrador")
        self.rol_cliente = Rol.objects.create(nombre="Cliente")
        self.admin = Usuario.objects.create(
            nombre="Admin",
            email="admin@test.com",
            contrasena="hash",
            rol=self.rol_admin,
            is_active=True,
        )
        self.cliente = Usuario.objects.create(
            nombre="Cliente",
            email="cliente@test.com",
            contrasena="hash",
            rol=self.rol_cliente,
            is_active=True,
        )

    def test_alimentar_ml_sin_token_devuelve_401(self):
        response = self.client.post(reverse("rutas:alimentar_ml"))

        self.assertEqual(response.status_code, 401)

    def test_alimentar_ml_admin_autorizado(self):
        token = RefreshToken.for_user(self.admin).access_token
        response = self.client.post(
            reverse("rutas:alimentar_ml"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)

    def test_api_rutas_cliente_devuelve_403_json(self):
        token = RefreshToken.for_user(self.cliente).access_token
        response = self.client.get(
            reverse("rutas:mensajeros_con_rutas"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")


class OrdenarYEstimarEtaTests(SimpleTestCase):
    """Pruebas del ordenamiento por proximidad y la ETA acumulada.

    Usa SimpleTestCase porque la función es pura y no toca la base de datos.
    """

    def test_ordena_por_vecino_mas_cercano_y_asigna_orden(self):
        paradas = [
            {'id': 'lejos', 'lat': -16.40, 'lng': -68.05},
            {'id': 'cerca', 'lat': -16.501, 'lng': -68.151},
        ]
        out = _ordenar_y_estimar_eta(paradas, -16.50, -68.15)
        # La parada 'cerca' debe visitarse primero.
        self.assertEqual(out[0]['id'], 'cerca')
        self.assertEqual(out[0]['orden'], 1)
        self.assertEqual(out[1]['id'], 'lejos')
        self.assertEqual(out[1]['orden'], 2)

    def test_eta_es_acumulada_y_creciente(self):
        paradas = [
            {'id': 1, 'lat': -16.50, 'lng': -68.15},
            {'id': 2, 'lat': -16.49, 'lng': -68.13},
        ]
        out = _ordenar_y_estimar_eta(paradas, -16.51, -68.16)
        etas = [p['eta_min'] for p in out]
        self.assertTrue(all(e is not None for e in etas))
        self.assertLess(etas[0], etas[1])  # la ETA crece con cada parada

    def test_paradas_sin_coordenadas_van_al_final_sin_eta(self):
        paradas = [
            {'id': 'ok', 'lat': -16.50, 'lng': -68.15},
            {'id': 'sin', 'lat': None, 'lng': None},
        ]
        out = _ordenar_y_estimar_eta(paradas, -16.50, -68.15)
        self.assertEqual(out[-1]['id'], 'sin')
        self.assertIsNone(out[-1]['eta_min'])

    def test_sin_punto_de_inicio_no_falla(self):
        paradas = [{'id': 1, 'lat': -16.5, 'lng': -68.1}]
        out = _ordenar_y_estimar_eta(paradas, None, None)
        self.assertEqual(out[0]['orden'], 1)
        self.assertIsNone(out[0]['eta_min'])


class RoutingMlPriorityTests(SimpleTestCase):
    class FakeDelayTree:
        def predict_proba(self, X):
            return np.array([
                [0.95, 0.05],
                [0.05, 0.95],
            ])

    def test_probabilidad_de_retraso_prioriza_parada_en_la_ruta(self):
        stops = [
            {"id": "normal", "lat": -16.50, "lng": -68.15, "tipo_servicio": "Estándar"},
            {"id": "urgente", "lat": -16.49, "lng": -68.14, "tipo_servicio": "Express"},
        ]
        time_matrix = np.array([
            [0.0, 5.0, 6.0],
            [5.0, 0.0, 12.0],
            [6.0, 12.0, 0.0],
        ])

        result = compute_algorithmic_route(
            origin=(-16.51, -68.16),
            stops=stops,
            time_matrix=time_matrix,
            delay_model=self.FakeDelayTree(),
        )

        self.assertEqual(result["ordered_stops"][0]["id"], "urgente")
        self.assertEqual(result["delay_priorities"], [0.05, 0.95])
        self.assertTrue(result["ml_cost_applied"])

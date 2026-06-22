from django.test import TestCase, Client
from django.urls import reverse
from django.test import TestCase, Client
from django.urls import reverse
from usuarios.models import Usuario
import json

class LoginTokenTests(TestCase):
    def setUp(self):
        # Create a test user
        # Note: Adjust fields based on your Usuario model if necessary.
        # Based on views.py, it uses email and contrasena (password)
        # and has a 'rol' field.
        from usuarios.models import Rol
        self.rol = Rol.objects.create(nombre='Cliente')
        self.usuario = Usuario.objects.create(
            email='test@example.com',
            nombre='Test User',
            rol=self.rol
        )
        self.usuario.set_password('password123')
        self.usuario.save()

    def test_api_login_returns_token(self):
        """
        Test that the /usuarios/api/login/ endpoint returns access and refresh tokens.
        """
        client = Client()
        url = reverse('usuarios:api_login')
        data = {
            'email': 'test@example.com',
            'contrasena': 'password123'
        }
        response = client.post(url, json.dumps(data), content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertIn('access', response_data)
        self.assertIn('refresh', response_data)
        self.assertEqual(response_data['status'], 'success')
        print("\n[PASS] API Login Test Passed: Tokens received.")

    def test_login_view_json_returns_token(self):
        """
        Test that the /usuarios/login/ endpoint with JSON returns access and refresh tokens.
        """
        client = Client()
        url = reverse('usuarios:login')
        data = {
            'email': 'test@example.com',
            'contrasena': 'password123'
        }
        response = client.post(url, json.dumps(data), content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertIn('access', response_data)
        self.assertIn('refresh', response_data)
        self.assertEqual(response_data['status'], 'success')
        print("\n[PASS] Login View (JSON) Test Passed: Tokens received.")

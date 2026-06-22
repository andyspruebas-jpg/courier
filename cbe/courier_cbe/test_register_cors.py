import json

import requests


def main():
    # Configuración
    url = "http://127.0.0.1:8000/usuarios/api/register/"
    headers = {"Content-Type": "application/json"}

    # Datos del nuevo usuario
    payload = {
        "nombre": "Usuario Test CORS",
        "email": "test_cors@ejemplo.com",
        "contrasena": "passwordSegura123",
        "rol": "Cliente",
        "telefono": "12345678"
    }

    print(f"🔵 Enviando petición a {url}...")
    print(f"📦 Datos: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, headers=headers)

        print(f"\n🔹 Código de estado: {response.status_code}")

        if response.status_code == 201:
            print("✅ Usuario creado exitosamente!")
            print("📄 Respuesta JSON:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("❌ Error al crear usuario:")
            print(response.text)

    except Exception as e:
        print(f"❌ Error de conexión: {e}")


if __name__ == "__main__":
    main()

import json

import requests


def main():
    # Configuración
    url = "http://127.0.0.1:8000/envios/api/envios/crear/"
    headers = {"Content-Type": "application/json"}

    # Datos del nuevo envío
    payload = {
        "remitente_nombre": "Juan Pérez",
        "remitente_telefono": "77777777",
        "destinatario_nombre": "María López",
        "destinatario_telefono": "66666666",
        "origen_direccion": "Av. Arce, La Paz",
        "destino_direccion": "Calle 21 de Calacoto, La Paz",
        "peso": 2.5,
        "tipo_servicio": "Express",
        "monto_pago": 50.00,
        "tipo_pago": "Origen",
        "observaciones": "Paquete frágil"
    }

    print(f"[INFO] Enviando peticion a {url}...")
    print(f"[DATA] Datos: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, headers=headers)

        print(f"\n[STATUS] Codigo de estado: {response.status_code}")

        if response.status_code == 201:
            print("[OK] Envio creado exitosamente!")
            print("[JSON] Respuesta JSON:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("[ERROR] Error al crear envio:")
            print(response.text)

    except Exception as e:
        print(f"[ERROR] Error de conexion: {e}")


if __name__ == "__main__":
    main()

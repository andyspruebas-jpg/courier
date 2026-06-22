# Courier Bolivian Express

Sistema de gestión de mensajería (courier) para Bolivia. Consta de dos sub-proyectos:

| Sub-proyecto | Tecnología | Rol |
|---|---|---|
| [`cbe/courier_cbe/`](cbe/courier_cbe) | Django + Django REST Framework | Backend: panel web de administración + API REST |
| [`cbe/courier_cbe_movil/`](cbe/courier_cbe_movil) | Flutter | App móvil para el personal de reparto (mensajeros) |

---

## 🚀 Backend (Django) — `cbe/courier_cbe/`

### Requisitos
- Python 3.11+
- PostgreSQL
- Una API key de Google Maps (Directions, Distance Matrix, Geocoding)

### Configuración

```bash
cd cbe/courier_cbe
python -m venv venv
source venv/bin/activate          # En Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copia la plantilla de entorno y rellena tus valores reales
cp .env.example .env
```

#### Variables de entorno (`.env`)

| Variable | Propósito |
|---|---|
| `SECRET_KEY` | Clave secreta de Django |
| `DEBUG` | `True` o `False` |
| `NGROK_HOST` | Hostname del túnel de Ngrok (CORS/CSRF) |
| `ALLOWED_HOSTS` | Lista separada por comas |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexión a PostgreSQL |
| `GOOGLE_MAPS_API_KEY` | Requerida para las APIs de Google Maps |
| `MEDIA_SECRET_KEY` | Clave Fernet para cifrar la media (firmas/fotos). **Obligatoria o el servidor no arranca.** |

> Genera una clave Fernet:
> ```bash
> python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
> ```

### Base de datos y arranque

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Pruebas

```bash
python manage.py test            # todas
python manage.py test envios     # una app
```

---

## 📱 App móvil (Flutter) — `cbe/courier_cbe_movil/`

```bash
cd cbe/courier_cbe_movil
flutter pub get
flutter run
```

La URL base de la API está en [`lib/api/api.dart`](cbe/courier_cbe_movil/lib/api/api.dart). La app se conecta vía el túnel de Ngrok — actualiza `ngrokUrl` cuando el túnel cambie.

---

## 🏗️ Arquitectura

### Apps de Django

| App | Rol |
|---|---|
| `usuarios` | Modelo `Usuario` personalizado (sesión para web, JWT para Flutter). |
| `envios` | Modelo central de envío (`Envio`). Almacenamiento cifrado de firmas/fotos vía Fernet. |
| `rutas` | Motor de optimización de rutas + API REST para Flutter. |
| `zonas` | Zonas de reparto como polígonos GeoJSON. |
| `pagos` | Registros de pago ligados 1:1 a los envíos. |
| `ubicaciones_mensajeros` | Rastreo GPS de los mensajeros, ligado a `Ruta`. |

### Autenticación dual
- **Web admin:** autenticación por sesión de Django (`AutenticacionMiddleware`).
- **API Flutter:** JWT (`rest_framework_simplejwt`). Tokens en `/api/token/`, login en `/usuarios/api/login/`.

### Optimización de rutas (`rutas/routing.py`)
1. **Matriz de tiempos** — Google Distance Matrix (o Haversine a 30 km/h como respaldo).
2. **Clustering K-Means** — agrupa paradas en clústeres de ~8 paradas.
3. **Scoring de retrasos** — clasificador (árbol/SGD) que estima la probabilidad de retraso.
4. **Heurística TSP** — Nearest Neighbor + 2-Opt para ordenar las paradas.
5. **Polilínea** — ruta final enviada a Google Directions para visualización.

Tanto la ruta de Google como la algorítmica se persisten en el modelo `Ruta` para comparar.

---

## 🔒 Seguridad / datos sensibles

Este repositorio **no incluye** secretos ni datos de producción. El [`.gitignore`](.gitignore) excluye:

- `.env` (secretos) — usa [`.env.example`](cbe/courier_cbe/.env.example) como plantilla.
- `db.sqlite3` y volcados de base de datos.
- `media/` y `protected_media/` (fotos y firmas de clientes).
- `data/road_route_cache.json` (caché de coordenadas reales).
- `venv/`, builds, ejecutables y cachés.

---

## 📦 Estructura

```
courier/
└── cbe/
    ├── courier_cbe/        # Backend Django (web + API REST)
    └── courier_cbe_movil/  # App móvil Flutter (mensajeros)
```

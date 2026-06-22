# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Courier Bolivian Express** — a full-stack courier management system for Bolivia. It consists of two sub-projects:

- `cbe/courier_cbe/` — Django REST Framework backend (web admin + REST API)
- `cbe/courier_cbe_movil/` — Flutter mobile app (for delivery personnel)

---

## Backend (Django) — `cbe/courier_cbe/`

### Running the server

```bash
cd cbe/courier_cbe
# Activate virtualenv (Windows-style venv is committed at cbe/courier_cbe/venv/)
source venv/bin/activate  # or venv\Scripts\activate on Windows
python manage.py runserver
```

### Required environment variables (`.env` in `cbe/courier_cbe/`)

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` or `False` |
| `NGROK_HOST` | Ngrok tunnel hostname (used for CORS/CSRF) |
| `ALLOWED_HOSTS` | Comma-separated list |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection |
| `GOOGLE_MAPS_API_KEY` | Required for Directions, Distance Matrix, Geocoding APIs |
| `MEDIA_SECRET_KEY` | Fernet key for encrypted media files — **must be set or the server will refuse to start** |

Generate a Fernet key: `from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`

### Database & migrations

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Running tests

```bash
python manage.py test                      # all tests
python manage.py test envios               # single app
python manage.py test rutas.tests          # single module
```

---

## Mobile App (Flutter) — `cbe/courier_cbe_movil/`

### Running

```bash
cd cbe/courier_cbe_movil
flutter pub get
flutter run
```

### API base URL

Hardcoded in [cbe/courier_cbe_movil/lib/api/api.dart](cbe/courier_cbe_movil/lib/api/api.dart). The app always connects via the Ngrok tunnel URL — update `ngrokUrl` when the tunnel changes.

---

## Architecture

### Django apps and their roles

| App | Role |
|---|---|
| `usuarios` | Custom `Usuario` model (session-based for web, JWT for Flutter). Includes `AutenticacionMiddleware` for web session redirects. |
| `envios` | Core shipment model (`Envio`). Encrypted file storage for signatures/photos via Fernet. |
| `rutas` | Route optimization engine + REST API for Flutter. |
| `zonas` | Delivery zones as GeoJSON polygons stored as JSON text. |
| `pagos` | Payment records linked 1:1 to shipments. |
| `ubicaciones_mensajeros` | GPS breadcrumbs for delivery personnel, linked to `Ruta`. |

### Dual authentication pattern

- **Web admin** uses Django session authentication (`request.session['usuario_id']`) protected by `AutenticacionMiddleware`.
- **Flutter API** uses JWT (`rest_framework_simplejwt`). Tokens obtained at `/api/token/`, refreshed at `/api/token/refresh/`. Login via `/usuarios/api/login/`.

### Route optimization pipeline (`rutas/`)

The routing pipeline in [rutas/routing.py](cbe/courier_cbe/rutas/routing.py) works as follows:

1. **Time matrix** — built via Google Distance Matrix API (batched 10×10) or Haversine fallback at 30 km/h.
2. **K-Means clustering** — groups stops into ~8-stop clusters. Uses a persisted `MiniBatchKMeans` model if available.
3. **Delay scoring** — decision-tree/SGD classifier in `rutas/models_ai/delay_tree.joblib` scores each stop's delay probability by zone and service type.
4. **TSP heuristic** — Nearest Neighbor + 2-Opt improvement to order stops within each cluster.
5. **Polyline** — final ordered route sent to Google Directions API for a displayable polyline.

Both the Google route and the algorithmic route are persisted on the `Ruta` model for comparison (`polyline_google`, `polyline_algo`, `duracion_google_min`, `duracion_algo_min`, `retraso_estimado`).

### ML incremental training

`rutas/services/ml_trainer.py` → `feed_new_ubicaciones_and_train()`:
- Reads new `UbicacionMensajero` rows since the last run (tracked in `MLTrainingState`, single DB row).
- Updates `MiniBatchKMeans` incrementally; saved to `rutas/models_ai/kmeans.joblib`.
- Trains an `SGDClassifier` for delay prediction once ≥50 labeled `Ruta` records exist (labeled by comparing `duracion_real` vs `duracion_estimada + 10 min`); saved to `rutas/models_ai/delay_sgd.joblib`.
- Triggered via `POST /rutas/alimentar-ml/`.

### Flutter app structure (`lib/`)

- `api/api.dart` — base URL constants.
- `providers/auth_provider.dart` — `ChangeNotifier` wrapping `AuthService`; persists session.
- `models/` — typed models with tolerant `fromJson` (`Envio`, `RutaDetalle`/`EnvioParada`); `json_utils.dart` normalizes the backend's string-encoded Decimals.
- `services/` — `auth_service.dart` (login/session); `api_client.dart` (central HTTP client: Bearer token + 401 refresh + multipart); `entrega_service.dart` / `incidencia_service.dart` (delivery & incident POSTs); `ruta_service.dart` (route detail); `notificaciones_service.dart` (local notifications via polling, no Firebase); `cola_sync_service.dart` (offline delivery queue).
- `pages/` — one file per screen. Courier write-flows: `registrar_entrega_page.dart` (photo/signature/notes/payment), `registrar_incidencia_page.dart`, `mis_entregas_page.dart` (ordered itinerary with per-stop ETA).
- Dark theme is default; color scheme: Indigo `#6366F1` primary, Teal `#14B8A6` secondary.
- Offline: confirming a delivery without connection queues it (files persisted via `path_provider`, metadata in `shared_preferences`) and auto-syncs on reconnect (`connectivity_plus`). GPS pings are intentionally not queued.
- Notifications: local-only (no FCM). The app polls pending shipments (foreground timer + background isolate) and raises a local notification for newly assigned shipments.

### Key API endpoints (Flutter-facing)

| Endpoint | Description |
|---|---|
| `POST /usuarios/api/login/` | JWT login |
| `GET /usuarios/perfil/` | Current user profile |
| `GET /rutas/api/rutas-json/<mensajero_id>/` | Routes for a messenger |
| `GET /rutas/api/ruta-detalle/<mensajero_id>/` | Google vs algo route comparison |
| `GET /rutas/api/mensajeros-con-rutas/` | Messengers with active routes |
| `POST /rutas/alimentar-ml/` | Trigger incremental ML training |
| `POST /rutas/api/<ruta_id>/evento/` | Mark route start/finish with timestamp |
| `POST /usuarios/actualizar_ubicacion/` | GPS breadcrumb from mobile |
| `POST /envios/api/entregas/registrar/<envio_id>/` | Confirm delivery (multipart: estado, foto, firma, observaciones, modalidad_pago, monto, lat/lng). Creates `Entrega`, updates `Envio.estado`, creates `HistorialEnvio`, upserts `Pago`. |
| `POST /envios/api/incidentes/registrar/<envio_id>/` | Report an incident (multipart: tipo, descripcion, foto, lat/lng). Creates `Incidente` + `HistorialEnvio`. |
| `GET /envios/envios-pendientes-json/?usuario_id=&rol=Mensajero` | Pending shipments — also polled for local "new assignment" notifications. |

`ruta-detalle` paradas are enriched (contact, estado, payment) and ordered by nearest-neighbor with a cumulative `eta_min` per stop (`rutas/views.py::_ordenar_y_estimar_eta`, Haversine @30 km/h). `Entrega` has encrypted `firma`+`foto` and `observaciones`; `Incidente` has an encrypted `foto`. Both `/envios/...` paths are also reachable under `/api/...` (envios.urls is included twice). Endpoints are `@csrf_exempt` and currently unauthenticated; role filtering is done via query params.

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 🔹 Cargar variables de entorno (.env)
# ---------------------------------------------------------------------------
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]

# ---------------------------------------------------------------------------
# 🔹 Seguridad y configuración general
# ---------------------------------------------------------------------------
DEBUG = os.getenv('DEBUG', 'True') == 'True'
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-local-dev-key'
    else:
        raise RuntimeError("Falta SECRET_KEY en entorno no DEBUG.")

# Host externo (Ngrok / Railway)
NGROK_HOST = os.getenv('NGROK_HOST', 'ira-kitcheny-barbra.ngrok-free.dev')

# Leer ALLOWED_HOSTS desde .env (CSV → lista)
ALLOWED_HOSTS = env_list(
    'ALLOWED_HOSTS',
    'localhost,127.0.0.1,0.0.0.0,railway.app,ira-kitcheny-barbra.ngrok-free.dev'
)

# ---------------------------------------------------------------------------
# 🔹 Aplicaciones instaladas
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Apps internas
    'envios',
    'usuarios',
    'pagos',
    'rutas',
    'zonas',

    # Dependencias API / Auth / CORS
    'rest_framework',
    'corsheaders',
]

# ---------------------------------------------------------------------------
# 🔹 Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'usuarios.middleware.AutenticacionMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ---------------------------------------------------------------------------
# 🔹 CORS / CSRF - ajustes
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = DEBUG and not os.getenv("CORS_ALLOWED_ORIGINS")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ['*']

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS") or [
    f'https://{NGROK_HOST}',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://0.0.0.0:8000',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# ---------------------------------------------------------------------------
# 🔹 Configuración de plantillas
# ---------------------------------------------------------------------------
ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# ---------------------------------------------------------------------------
# 🔹 Base de datos
# ---------------------------------------------------------------------------
USE_POSTGRES = os.getenv('USE_POSTGRES', 'False') == 'True'
if USE_POSTGRES and all(os.getenv(key) for key in ("DB_NAME", "DB_USER", "DB_HOST")):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# 🔹 Validadores de contraseñas
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# 🔹 Internacionalización
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/La_Paz'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# 🔹 Archivos estáticos y media
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ---------------------------------------------------------------------------
# 🔒 Archivos protegidos (firmas, fotos cifradas)
# ---------------------------------------------------------------------------
PROTECTED_MEDIA_ROOT = os.path.join(BASE_DIR, 'protected_media')
PROTECTED_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Clave Fernet (desde .env)
MEDIA_SECRET_KEY = os.getenv('MEDIA_SECRET_KEY', None)
if not MEDIA_SECRET_KEY:
    raise RuntimeError(
        "⚠️ Falta MEDIA_SECRET_KEY en tu .env. "
        "Genera una con: from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    )

# ---------------------------------------------------------------------------
# 🔹 Django REST Framework + JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

# ---------------------------------------------------------------------------
# 🔹 Seguridad
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env_bool("USE_X_FORWARDED_PROTO", not DEBUG)
    else None
)

if DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# ---------------------------------------------------------------------------
# 🔹 Google Maps API Key
# ---------------------------------------------------------------------------
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')

# ---------------------------------------------------------------------------
# 🔹 Login personalizado
# ---------------------------------------------------------------------------
LOGIN_URL = '/usuarios/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/usuarios/login/'

# ---------------------------------------------------------------------------
# 🔹 Config final
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# 🔹 Configuraciones de Caché para mejor rendimiento
# ---------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}

# Tiempo de caché para sesiones (en segundos)
SESSION_CACHE_ALIAS = 'default'
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# ---------------------------------------------------------------------------
# 🔹 Optimizaciones de rendimiento
# ---------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# --- DEV TUNNELS: Cloudflare quick tunnel ---
ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'https://*.trycloudflare.com',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# --- END DEV TUNNELS ---

import os
import sys

# Asegúrate de que el directorio myproject esté en el path de Python
sys.path.append(os.path.join(os.path.dirname(__file__), 'myproject'))

from django.core.wsgi import get_wsgi_application

# Establecer la variable de entorno para el archivo de configuración de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

application = get_wsgi_application()

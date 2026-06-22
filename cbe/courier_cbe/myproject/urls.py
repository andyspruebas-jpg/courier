from django.contrib import admin
from django.urls import path, include, re_path
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

# Vista que sirve archivos cifrados
from envios.views_secure_files import serve_protected_file

# JWT para API (Flutter)
from rest_framework_simplejwt.views import TokenObtainPairView
from usuarios.views import api_token_refresh

urlpatterns = [
    # Panel admin
    path('admin/', admin.site.urls),

    # Raíz: login o home
    path(
        '',
        lambda request: redirect('usuarios:login')
        if 'usuario_id' not in request.session
        else redirect('usuarios:home'),
        name='root_redirect'
    ),

    # Módulos del sistema
    path('envios/', include(('envios.urls', 'envios'), namespace='envios')),
    path('usuarios/', include('usuarios.urls')),
    path('rutas/', include(('rutas.urls', 'rutas'), namespace='rutas')),
    path('zonas/', include(('zonas.urls', 'zonas'), namespace='zonas')),

    # Logout
    path('usuarios/logout/', auth_views.LogoutView.as_view(), name='cerrar_sesion'),

    # JWT API
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', api_token_refresh, name='token_refresh'),
    path('api/', include(('envios.urls', 'envios'), namespace='envios_api')),

    # Archivos protegidos
    re_path(r"^protected/(?P<path>.+)$", serve_protected_file, name="protected_file"),
]

# Archivos estáticos y media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static('/protected/', document_root=settings.PROTECTED_MEDIA_ROOT)

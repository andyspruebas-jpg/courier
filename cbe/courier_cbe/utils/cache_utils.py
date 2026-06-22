# Utilidad para invalidar caché cuando se hacen cambios
# Importar esto en signals o en las vistas donde se modifiquen datos

from django.core.cache import cache

def invalidar_cache_dashboard():
    """Invalida el caché del dashboard cuando hay cambios en los datos"""
    cache.delete('dashboard_data')
    cache.delete('dashboard_json_data')

def invalidar_cache_usuario(usuario_id=None):
    """Invalida el caché relacionado con usuarios"""
    if usuario_id:
        cache.delete(f'usuario_{usuario_id}')
    cache.delete('lista_usuarios')

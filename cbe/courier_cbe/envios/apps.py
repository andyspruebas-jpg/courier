from django.apps import AppConfig


class EnviosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'envios'

    def ready(self):
        from . import signals  # noqa: F401

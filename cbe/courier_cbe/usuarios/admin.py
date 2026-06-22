from django.contrib import admin

from .models import Empresa, PasswordResetToken, PerfilMensajero, Rol, UbicacionMensajero, Usuario


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nit", "telefono", "activa")
    search_fields = ("nombre", "nit", "contacto")
    list_filter = ("activa",)


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "email", "rol", "empresa", "is_active")
    search_fields = ("nombre", "email")
    list_filter = ("rol", "empresa", "is_active")


admin.site.register(Rol)
admin.site.register(PerfilMensajero)
admin.site.register(UbicacionMensajero)
admin.site.register(PasswordResetToken)

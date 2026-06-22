from django import forms
from .models import Empresa, Usuario, PerfilMensajero
from django.core.exceptions import ValidationError
from django.db.models import Q

import re

class UsuarioForm(forms.ModelForm):
    contrasena = forms.CharField(
        widget=forms.PasswordInput(attrs={'minlength': '8'}),
        required=False,
        label="Contraseña"
    )
    
    class Meta:
        model = Usuario
        fields = ['nombre', 'email', 'telefono', 'contrasena', 'rol', 'empresa', 'is_active']
        widgets = {
            'nombre': forms.TextInput(attrs={'maxlength': '150', 'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'maxlength': '20', 'pattern': '[0-9]{7,8}', 'class': 'form-control'}),
            'rol': forms.Select(attrs={'class': 'form-control'}),
            'empresa': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_empresa(self):
        empresa = self.cleaned_data.get("empresa")
        if Empresa.objects.exists() and empresa is None:
            raise ValidationError("Debes vincular el usuario a una empresa registrada.")
        return empresa

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if nombre and not nombre.replace(' ', '').isalpha():
            raise ValidationError('El nombre solo puede contener letras.')
        return nombre

    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono')
        if telefono and not telefono.isdigit():
            raise ValidationError('El teléfono solo puede contener números.')
        return telefono

    def clean_contrasena(self):
        contrasena = self.cleaned_data.get('contrasena')
        # Solo validar si se proporcionó una contraseña
        if contrasena:
            if len(contrasena) < 8:
                raise ValidationError('La contraseña debe tener al menos 8 caracteres.')
            if not re.search(r'[A-Z]', contrasena):
                raise ValidationError('La contraseña debe contener al menos una letra mayúscula.')
            if not re.search(r'[\W_]', contrasena):
                raise ValidationError('La contraseña debe contener al menos un carácter especial.')
        return contrasena

    def save(self, commit=True):
        usuario = super().save(commit=False)
        # Solo actualizar contraseña si se proporcionó una nueva
        if self.cleaned_data.get('contrasena'):
            usuario.set_password(self.cleaned_data['contrasena'])

        if commit:
            usuario.save()
            # Si el rol es Mensajero, crear perfil automáticamente
            if usuario.rol and usuario.rol.nombre.lower() == "mensajero":
                PerfilMensajero.objects.get_or_create(usuario=usuario)

        return usuario


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["nombre", "nit", "direccion", "contacto", "telefono", "email", "activa"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "nit": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.TextInput(attrs={"class": "form-control"}),
            "contacto": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PerfilMensajeroForm(forms.ModelForm):
    class Meta:
        model = PerfilMensajero
        fields = [
            "vehiculo",
            "foto",
            "zona_cobertura",
            "zona_cobertura_secundaria",
            "disponible",
            "latitud",
            "longitud",
        ]
        widgets = {
            "vehiculo": forms.TextInput(attrs={"class": "form-control"}),
            "foto": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "zona_cobertura": forms.Select(attrs={"class": "form-control"}),
            "zona_cobertura_secundaria": forms.Select(attrs={"class": "form-control"}),
            "disponible": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "latitud": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "longitud": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
        }

    def clean(self):
        cleaned = super().clean()
        principal = cleaned.get("zona_cobertura")
        secundaria = cleaned.get("zona_cobertura_secundaria")
        if principal and secundaria and principal.pk == secundaria.pk:
            self.add_error(
                "zona_cobertura_secundaria",
                "La segunda zona debe ser diferente de la principal.",
            )

        for field_name, zona in (
            ("zona_cobertura", principal),
            ("zona_cobertura_secundaria", secundaria),
        ):
            if not zona:
                continue
            ocupada = PerfilMensajero.objects.filter(
                usuario__is_active=True,
            ).filter(
                Q(zona_cobertura=zona)
                | Q(zona_cobertura_secundaria=zona)
            )
            if self.instance.pk:
                ocupada = ocupada.exclude(pk=self.instance.pk)
            if ocupada.exists():
                self.add_error(field_name, "Esta zona ya tiene un mensajero asignado.")
        return cleaned



class LoginForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={'placeholder': 'ejemplo@correo.com'})
    )
    contrasena = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'placeholder': '********'})
    )

from django import forms

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico")


class PasswordResetForm(forms.Form):
    nueva_contrasena = forms.CharField(widget=forms.PasswordInput, label="Nueva contraseña")
    confirmar_contrasena = forms.CharField(widget=forms.PasswordInput, label="Confirmar contraseña")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("nueva_contrasena") != cleaned.get("confirmar_contrasena"):
            raise forms.ValidationError("Las contraseñas no coinciden")
        return cleaned

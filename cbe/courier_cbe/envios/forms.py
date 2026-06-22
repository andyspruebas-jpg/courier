from django import forms
from .models import Envio, Incidente, Entrega, Usuario
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
import re
# ==============================
# Formulario para el modelo Envio
# ==============================
class EnvioForm(forms.ModelForm):
    class Meta:
        model = Envio
        fields = [
            'remitente_nombre',
            'remitente_telefono',
            'origen_direccion',
            'destino_direccion',
            'destinatario_nombre',
            'destinatario_telefono',
            'peso',
            'tipo_servicio',
            'estado',
            'observaciones',
            'monto_pago',
            'tipo',         
            'tipo_pago',
            'mensajero'
        ]
        widgets = {
            'remitente_nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del remitente'}),
            'remitente_telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono del remitente'}),
            'origen_direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dirección de origen'}),
            'destino_direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dirección de destino'}),
            'destinatario_nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del destinatario'}),
            'destinatario_telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de teléfono (7 u 8 dígitos)'}),
            'peso': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tipo_servicio': forms.Select(attrs={'class': 'form-control'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Observaciones adicionales'}),
            'monto_pago': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'tipo_pago': forms.Select(attrs={'class': 'form-control'}),
            'mensajero': forms.Select(attrs={'class': 'form-control'}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cambiar la forma en que mostramos el nombre del mensajero
        self.fields['mensajero'].label_from_instance = lambda obj: obj.__str__()

    # ... aquí van todas tus validaciones previas ...

    # Validación para el campo 'tipo' (solo 'Envío' o 'Recojo')
    def clean_tipo(self):
        tipo = self.cleaned_data.get('tipo')
        if tipo not in ['Envío', 'Recojo']:
            raise ValidationError("El tipo debe ser 'Envío' o 'Recojo'.")
        return tipo

    # Validación del número de teléfono del destinatario (solo números, 7 u 8 dígitos)
    def clean_destinatario_telefono(self):
        telefono = self.cleaned_data.get('destinatario_telefono')
        if not telefono.isdigit():
            raise ValidationError("El número de teléfono solo debe contener dígitos.")
        if len(telefono) not in [7, 8]:
            raise ValidationError("El número de teléfono debe tener 7 u 8 dígitos.")
        return telefono

    # Validación del número de teléfono del remitente (solo números, 7 u 8 dígitos)
    def clean_remitente_telefono(self):
        telefono = self.cleaned_data.get('remitente_telefono')
        if not telefono.isdigit():
            raise ValidationError("El número de teléfono solo debe contener dígitos.")
        if len(telefono) != 8:
            raise ValidationError("El número de teléfono debe tener 8 dígitos.")
        return telefono

    # Validación para el campo 'remitente_nombre' (solo letras, máximo 30 caracteres)
    def clean_remitente_nombre(self):
        nombre = self.cleaned_data.get('remitente_nombre')
        if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ ]+$', nombre):
            raise ValidationError("El nombre del remitente solo debe contener letras.")
        if len(nombre) > 30:
            raise ValidationError("El nombre del remitente no debe exceder los 30 caracteres.")
        return nombre

    # Validación para el campo 'destinatario_nombre' (solo letras, máximo 30 caracteres)
    def clean_destinatario_nombre(self):
        nombre = self.cleaned_data.get('destinatario_nombre')
        if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ ]+$', nombre):
            raise ValidationError("El nombre del destinatario solo debe contener letras.")
        if len(nombre) > 30:
            raise ValidationError("El nombre del destinatario no debe exceder los 30 caracteres.")
        return nombre

    # Validación para el campo 'origen_direccion' (letras y números, máximo 255 caracteres)
    def clean_origen_direccion(self):
        direccion = self.cleaned_data.get('origen_direccion')
        if len(direccion) > 255:
            raise ValidationError("La dirección de origen no debe exceder los 255 caracteres.")
        return direccion

    # Validación para el campo 'destino_direccion' (letras y números, máximo 255 caracteres)
    def clean_destino_direccion(self):
        direccion = self.cleaned_data.get('destino_direccion')
        if len(direccion) > 255:
            raise ValidationError("La dirección de destino no debe exceder los 255 caracteres.")
        return direccion

    # Validación para el campo 'peso' (números positivos, mayor a 0, máximo 100)
    def clean_peso(self):
        peso = self.cleaned_data.get('peso')
        if peso <= 0:
            raise ValidationError("El peso debe ser mayor a 0.")
        if peso > 100:
            raise ValidationError("El peso no puede superar los 100 kg.")
        return peso

    # Validación para el campo 'monto_pago' (números positivos, mayor a 0, máximo 1000)
    def clean_monto_pago(self):
        monto_pago = self.cleaned_data.get('monto_pago')
        if monto_pago <= 0:
            raise ValidationError("El monto de pago debe ser mayor a 0.")
        if monto_pago > 1000:
            raise ValidationError("El monto de pago no puede superar los 1000 Bs.")
        return monto_pago

    # Validación para el campo 'tipo_servicio'
    def clean_tipo_servicio(self):
        tipo_servicio = self.cleaned_data.get('tipo_servicio')
        if tipo_servicio not in ['Express', 'Estándar']:
            raise ValidationError("El tipo de servicio debe ser 'Express' o 'Estándar'.")
        return tipo_servicio


class SolicitudEnvioForm(forms.ModelForm):
    class Meta:
        model = Envio
        fields = [
            'remitente_nombre',
            'remitente_telefono',
            'origen_direccion',
            'destino_direccion',
            'destinatario_nombre',
            'destinatario_telefono',
            'peso',
            'tipo_servicio',
            'monto_pago',
            'tipo',
            'tipo_pago',
            'observaciones',
        ]
        labels = {
            'remitente_nombre': 'Quién entrega',
            'remitente_telefono': 'Teléfono de quien entrega',
            'origen_direccion': 'Dirección de recojo',
            'destino_direccion': 'Dirección de entrega',
            'destinatario_nombre': 'Quién recibe',
            'destinatario_telefono': 'Teléfono de quien recibe',
            'peso': 'Peso aproximado (kg)',
            'tipo_servicio': 'Servicio',
            'monto_pago': 'Monto a cobrar (Bs.)',
            'tipo': 'Operación',
            'tipo_pago': 'Pago',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'remitente_nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre o empresa'}),
            'remitente_telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono'}),
            'origen_direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Zona, calle, número y ciudad'}),
            'destino_direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Zona, calle, número y ciudad'}),
            'destinatario_nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre o empresa'}),
            'destinatario_telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono'}),
        }
        widgets.update({
            'peso': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'tipo_servicio': forms.Select(attrs={'class': 'form-control'}),
            'monto_pago': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'tipo_pago': forms.Select(attrs={'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Referencia, horario, instrucciones para el mensajero'}),
        })

# ==============================
# Formulario para el modelo Incidente
# ==============================
class IncidenteForm(forms.ModelForm):
    class Meta:
        model = Incidente
        fields = ['tipo', 'descripcion', 'estado']
        widgets = {
            'tipo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tipo de incidente'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Descripción del incidente'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_estado(self):
        estado = self.cleaned_data.get('estado')
        if estado not in ['Pendiente', 'Resuelto']:
            raise forms.ValidationError("El estado debe ser 'Pendiente' o 'Resuelto'.")
        return estado


# ==============================
# Formulario para el modelo Entrega
# ==============================
class EntregaForm(forms.ModelForm):
    modalidad_pago = forms.ChoiceField(
        choices=[('Origen', 'Origen'), ('Destino', 'Destino'), ('Pendiente', 'Pendiente')],
        required=True,
        label="Modalidad de pago",
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    monto = forms.DecimalField(
        required=False,
        label="Monto (Bs.)",
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
    )

    class Meta:
        model = Entrega
        # ✅ No incluimos 'mensajero' porque se asigna desde la vista
        fields = ['estado', 'firma', 'foto', 'observaciones']
        widgets = {
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'firma': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_estado(self):
        estado = self.cleaned_data.get('estado')
        if estado not in ['Entregado', 'Rechazado']:
            raise forms.ValidationError("El estado de la entrega debe ser 'Entregado' o 'Rechazado'.")
        return estado


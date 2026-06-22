from django import forms
from .models import Zona

class ZonaForm(forms.ModelForm):
    class Meta:
        model = Zona
        fields = ['nombre', 'descripcion', 'area']
        widgets = {
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'area': forms.Textarea(attrs={'placeholder': 'Introduce las coordenadas como un array JSON'}),
        }

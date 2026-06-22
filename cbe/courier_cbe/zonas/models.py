from django.db import models
import json

class Zona(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(null=True, blank=True)
    area = models.TextField()  # Almacena las coordenadas del polígono como JSON

    def __str__(self):
        return self.nombre

    def get_area_as_list(self):
        """Convierte las coordenadas del área de la zona a una lista."""
        return json.loads(self.area)

    def set_area_from_list(self, coordinates):
        """Convierte la lista de coordenadas a formato JSON para guardarla."""
        self.area = json.dumps(coordinates)

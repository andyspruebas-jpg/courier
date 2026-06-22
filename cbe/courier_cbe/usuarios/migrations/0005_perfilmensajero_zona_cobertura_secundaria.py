from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0004_perfilmensajero_foto"),
        ("zonas", "0002_zona_descripcion"),
    ]

    operations = [
        migrations.AddField(
            model_name="perfilmensajero",
            name="zona_cobertura_secundaria",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mensajeros_secundarios",
                to="zonas.zona",
            ),
        ),
    ]

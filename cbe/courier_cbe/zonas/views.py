from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from .models import Zona
from .forms import ZonaForm
import json

def lista_zonas(request):
    # Obtener búsqueda
    search_query = request.GET.get('search', '')
    
    # Filtrar zonas por búsqueda
    zonas = Zona.objects.all()
    if search_query:
        zonas = zonas.filter(nombre__icontains=search_query)
    
    # Ordenar
    zonas = zonas.order_by('nombre')
    
    # Paginación
    from django.core.paginator import Paginator
    paginator = Paginator(zonas, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'zonas/lista_zonas.html', {
        'page_obj': page_obj,
        'search_query': search_query
    })


def cobertura_zonas(request):
    zonas_payload = []
    for zona in Zona.objects.order_by("nombre"):
        try:
            area = zona.get_area_as_list()
        except Exception:
            area = []
        zonas_payload.append({
            "id": zona.id,
            "nombre": zona.nombre,
            "descripcion": zona.descripcion or "",
            "area": area,
        })
    return render(request, "zonas/cobertura.html", {
        "zonas_json": json.dumps(zonas_payload, ensure_ascii=False),
        "zonas": zonas_payload,
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
    })

def ver_zona(request, zona_id):
    zona = get_object_or_404(Zona, id=zona_id)
    return render(request, 'zonas/ver_zona.html', {
        'zona': zona,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    })

def crear_zona(request):
    if request.method == 'POST':
        form = ZonaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('zonas:lista_zonas')
    else:
        form = ZonaForm()
    return render(request, 'zonas/crear_zona.html', {
        'form': form,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    })

def editar_zona(request, zona_id):
    zona = get_object_or_404(Zona, id=zona_id)
    if request.method == 'POST':
        form = ZonaForm(request.POST, instance=zona)
        if form.is_valid():
            form.save()
            return redirect('zonas:lista_zonas')
    else:
        form = ZonaForm(instance=zona)
    return render(request, 'zonas/editar_zona.html', {
        'form': form,
        'zona': zona,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    })

def eliminar_zona(request, zona_id):
    zona = get_object_or_404(Zona, id=zona_id)
    if request.method == 'POST':
        zona.delete()
        return redirect('zonas:lista_zonas')
    return render(request, 'zonas/eliminar_zona.html', {'zona': zona})

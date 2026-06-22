import 'dart:convert';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:geolocator/geolocator.dart';
import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../widgets/role_drawer.dart';

class MensajerosPage extends StatefulWidget {
  const MensajerosPage({super.key});

  @override
  State<MensajerosPage> createState() => _MensajerosPageState();
}

class _MensajerosPageState extends State<MensajerosPage> {
  GoogleMapController? _mapController;
  List<dynamic> _mensajeros = [];
  bool _loading = true;
  final Set<Marker> _markers = {};
  LatLng _center = const LatLng(-16.5, -68.15); // La Paz por defecto

  @override
  void initState() {
    super.initState();
    _fetchMensajeros();
    _obtenerUbicacionActual();
  }

  @override
  void dispose() {
    _mapController?.dispose();
    super.dispose();
  }

  // 🎨 Ícono con nombre — versión compacta y estética
  Future<BitmapDescriptor> _crearIconoConNombre(String nombre) async {
    const double size = 72;

    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    final paint = Paint();

    paint.color = AppColors.primary;
    canvas.drawCircle(const Offset(size / 2, size / 2), 25, paint);
    canvas.drawShadow(
      Path()..addOval(
        Rect.fromCircle(center: const Offset(size / 2, size / 2), radius: 25),
      ),
      Colors.black54,
      4,
      false,
    );
    paint
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..color = Colors.white;
    canvas.drawCircle(const Offset(size / 2, size / 2), 25, paint);
    paint.style = PaintingStyle.fill;

    final initials =
        nombre
            .trim()
            .split(RegExp(r'\s+'))
            .where((p) => p.isNotEmpty)
            .take(2)
            .map((p) => p[0].toUpperCase())
            .join();

    final textPainter = TextPainter(
      text: TextSpan(
        text: initials.isEmpty ? 'M' : initials,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
      ),
      textAlign: TextAlign.center,
      textDirection: TextDirection.ltr,
    );

    textPainter.layout(maxWidth: size);
    textPainter.paint(
      canvas,
      Offset((size - textPainter.width) / 2, (size - textPainter.height) / 2),
    );

    final picture = recorder.endRecording();
    final image = await picture.toImage(size.toInt(), size.toInt());
    final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
    final bytes = byteData!.buffer.asUint8List();

    return BitmapDescriptor.bytes(bytes);
  }

  Future<void> _fetchMensajeros() async {
    try {
      final response = await ApiClient.instance.get(
        '/usuarios/mensajeros-json/',
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (!mounted) return;

        // Asegurar que sea lista
        final List<dynamic> lista =
            (data is List) ? data : (data is Map ? [data] : []);

        setState(() {
          _mensajeros = lista;
        });

        // Construir marcadores en buffer
        final Set<Marker> newMarkers = {};

        for (var m in _mensajeros) {
          try {
            // Diferentes nombres posibles según tu endpoint (usuario_nombre o nombre)
            final nombre =
                (m['usuario_nombre'] ?? m['nombre'] ?? 'Sin nombre').toString();

            // Intentar parsear lat/lng seguros
            final latRaw = m['latitud'] ?? m['lat'] ?? m['latitude'];
            final lonRaw = m['longitud'] ?? m['lng'] ?? m['longitude'];

            final double? lat =
                latRaw != null ? double.tryParse(latRaw.toString()) : null;
            final double? lon =
                lonRaw != null ? double.tryParse(lonRaw.toString()) : null;

            // Si no hay coordenadas válidas, saltar (no queremos marcadores en 0,0)
            if (lat == null || lon == null) continue;
            if (lat == 0.0 && lon == 0.0) continue;

            // Crear icono (puede tardar; capturamos errores individuales para no romper el loop)
            BitmapDescriptor icono;
            try {
              icono = await _crearIconoConNombre(nombre);
            } catch (e) {
              // fallback icono por si falla la creación personalizada
              icono = BitmapDescriptor.defaultMarkerWithHue(
                BitmapDescriptor.hueOrange,
              );
            }

            final id = 'mensajero_${m['id'] ?? nombre}';

            newMarkers.add(
              Marker(
                markerId: MarkerId(id),
                position: LatLng(lat, lon),
                icon: icono,
                infoWindow: InfoWindow(
                  title: nombre,
                  snippet:
                      '${m['vehiculo'] ?? 'Vehículo registrado'} · ${m['zona'] ?? 'Zona operativa'}',
                ),
              ),
            );
          } catch (e) {
            // Error con un mensajero -> lo ignoramos y seguimos
            debugPrint('Error procesando mensajero: $e');
            continue;
          }
        }

        if (!mounted) return;
        setState(() {
          _markers
            ..clear()
            ..addAll(newMarkers);
          _loading = false;
        });
        _fitMarkers();
      } else {
        debugPrint('❌ Error cargando mensajeros: ${response.statusCode}');
        if (mounted) setState(() => _loading = false);
      }
    } catch (e) {
      debugPrint('⚠️ Error de conexión: $e');
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _obtenerUbicacionActual() async {
    try {
      bool servicioHabilitado = await Geolocator.isLocationServiceEnabled();
      if (!servicioHabilitado) return;

      LocationPermission permiso = await Geolocator.checkPermission();
      if (permiso == LocationPermission.denied) {
        permiso = await Geolocator.requestPermission();
        if (permiso == LocationPermission.denied) return;
      }

      final posicion = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );

      if (!mounted) return;
      setState(() {
        _center = LatLng(posicion.latitude, posicion.longitude);
      });

      _mapController?.animateCamera(CameraUpdate.newLatLngZoom(_center, 14));
    } catch (e) {
      debugPrint('⚠️ Error obteniendo ubicación: $e');
    }
  }

  void _fitMarkers() {
    if (_mapController == null || _markers.isEmpty) return;
    final points = _markers.map((m) => m.position).toList();
    var minLat = points.first.latitude;
    var maxLat = points.first.latitude;
    var minLng = points.first.longitude;
    var maxLng = points.first.longitude;
    for (final p in points) {
      minLat = p.latitude < minLat ? p.latitude : minLat;
      maxLat = p.latitude > maxLat ? p.latitude : maxLat;
      minLng = p.longitude < minLng ? p.longitude : minLng;
      maxLng = p.longitude > maxLng ? p.longitude : maxLng;
    }
    _mapController!.animateCamera(
      CameraUpdate.newLatLngBounds(
        LatLngBounds(
          southwest: LatLng(minLat, minLng),
          northeast: LatLng(maxLat, maxLng),
        ),
        72,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: const Text('Mensajeros - Courier Bolivian Express'),
      ),
      drawer: const RoleDrawer(current: AppDestination.mensajeros),
      body:
          _loading
              ? const Center(
                child: CircularProgressIndicator(color: AppColors.primary),
              )
              : Stack(
                children: [
                  GoogleMap(
                    onMapCreated: (controller) {
                      _mapController = controller;
                      _fitMarkers();
                    },
                    initialCameraPosition: CameraPosition(
                      target: _center,
                      zoom: 12,
                    ),
                    markers: _markers,
                    myLocationEnabled: true,
                    myLocationButtonEnabled: false,
                    zoomControlsEnabled: false,
                    mapType: MapType.normal,
                  ),
                  Positioned(
                    right: 16,
                    bottom: 16,
                    child: FloatingActionButton(
                      backgroundColor: AppColors.surfaceDark,
                      onPressed: _obtenerUbicacionActual,
                      child: const Icon(Icons.my_location, color: Colors.white),
                    ),
                  ),
                  Positioned(
                    left: 16,
                    right: 96,
                    bottom: 16,
                    child: _summaryPanel(),
                  ),
                ],
              ),
    );
  }

  Widget _summaryPanel() {
    final ocupados =
        _mensajeros.where((m) => (m as Map)['disponible'] == false).length;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.22)),
      ),
      child: Row(
        children: [
          const Icon(Icons.person_pin_circle, color: AppColors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '${_mensajeros.length} mensajeros · $ocupados con ruta activa',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }
}

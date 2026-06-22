import 'dart:async';
import 'dart:convert';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:flutter_polyline_points/flutter_polyline_points.dart';
import '../theme/app_colors.dart';
import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../widgets/role_drawer.dart';

// Páginas adicionales
import 'guiar_mensajero.dart'; // ✅ NUEVO IMPORT

class RutasPage extends StatefulWidget {
  const RutasPage({super.key});

  @override
  State<RutasPage> createState() => _RutasPageState();
}

class _RutasPageState extends State<RutasPage> {
  final storage = const FlutterSecureStorage();
  bool _loading = true;
  Map<String, dynamic>? _usuario;
  String? _rol;
  Map<String, dynamic>? _ruta;
  final Set<Polyline> _polylines = {};
  final Set<Marker> _markers = {};
  LatLng? inicio, fin;
  GoogleMapController? _controller;
  Timer? _rutaTimer;
  BitmapDescriptor? _iconoUbicacion;

  // Para admin
  List<Map<String, dynamic>> _mensajeros = [];
  int? _selectedMensajeroId;
  String? _selectedMensajeroNombre;
  bool _rutaNoEncontrada = false;

  @override
  void initState() {
    super.initState();
    _cargarUsuarioYDatos();
  }

  @override
  void dispose() {
    _rutaTimer?.cancel();
    _controller?.dispose();
    super.dispose();
  }

  void _programarPollingRuta(int mensajeroId) {
    _rutaTimer?.cancel();
    _rutaTimer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _fetchRutaMensajero(mensajeroId),
    );
  }

  // =====================================================
  // Cargar usuario y su ruta asignada
  // =====================================================
  Future<void> _cargarUsuarioYDatos() async {
    final data = await storage.readAll();
    if (data.containsKey('id')) {
      _usuario = {
        'id': int.tryParse(data['id'] ?? '0') ?? 0,
        'nombre': data['nombre'],
        'email': data['email'],
        'rol': data['rol'],
      };
      _rol = _usuario?['rol']?.toString().toLowerCase();
      if (_rol == 'mensajero') {
        await _fetchRutaMensajero(_usuario!['id']);
        _programarPollingRuta(_usuario!['id']);
      } else if (_rol == 'administrador') {
        // Admin: cargar lista de mensajeros
        _rutaTimer?.cancel();
        await _fetchMensajeros();
      }
    }
    setState(() => _loading = false);
  }

  // =====================================================
  // Admin: Obtener TODOS los mensajeros con estado
  // =====================================================
  Future<void> _fetchMensajeros() async {
    try {
      // Usamos el endpoint de usuarios que devuelve todos los mensajeros
      // con disponibilidad, zona y última señal
      final res = await ApiClient.instance.get('/usuarios/mensajeros-json/');
      if (res.statusCode == 200) {
        final List<dynamic> data = jsonDecode(res.body);
        setState(() {
          _mensajeros = data.cast<Map<String, dynamic>>();
        });
        // Auto-seleccionar el primero si hay mensajeros y no hay uno activo
        if (_mensajeros.isNotEmpty && _selectedMensajeroId == null) {
          final primero = _mensajeros.first;
          setState(() {
            _selectedMensajeroId = primero['id'];
            _selectedMensajeroNombre = primero['nombre'];
          });
          await _fetchRutaMensajero(primero['id']);
          _programarPollingRuta(primero['id']);
        }
      }
    } catch (e) {
      debugPrint("⚠️ Error fetching mensajeros: $e");
    }
  }

  // =====================================================
  // Obtener la ruta detallada desde el backend
  // =====================================================
  Future<void> _fetchRutaMensajero(int mensajeroId) async {
    try {
      final res = await ApiClient.instance.get(
        '/rutas/api/ruta-detalle/$mensajeroId/',
      );

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        if (!mounted) return;
        setState(() {
          _ruta = data;
          _selectedMensajeroId = mensajeroId;
          _rutaNoEncontrada = false;
          inicio = null;
          fin = null;
          _polylines.clear();
          _markers.clear();
        });
        await _procesarRutaAlgoritmica(data);
      } else if (res.statusCode == 404) {
        if (!mounted) return;
        setState(() {
          _ruta = null;
          _rutaNoEncontrada = true;
        });
      } else {
        debugPrint("⚠️ Error HTTP ${res.statusCode}: ${res.body}");
      }
    } catch (e) {
      debugPrint("⚠️ Error al obtener ruta: $e");
    }
  }

  // =====================================================
  // Procesar y mostrar solo la ruta Algorítmica
  // =====================================================
  Future<BitmapDescriptor> _crearIconoUbicacion() async {
    if (_iconoUbicacion != null) return _iconoUbicacion!;

    const size = 64.0;
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    const center = ui.Offset(size / 2, size / 2);

    canvas.drawCircle(
      center,
      30,
      ui.Paint()..color = const ui.Color(0x66000000),
    );
    canvas.drawCircle(
      center,
      25,
      ui.Paint()..color = const ui.Color(0xFFFFFFFF),
    );
    canvas.drawCircle(
      center,
      20,
      ui.Paint()..color = const ui.Color(0xFF1976D2),
    );
    canvas.drawCircle(
      center,
      6,
      ui.Paint()..color = const ui.Color(0xFFFFFFFF),
    );

    final image = await recorder.endRecording().toImage(
      size.toInt(),
      size.toInt(),
    );
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    if (data == null) return BitmapDescriptor.defaultMarker;

    _iconoUbicacion = BitmapDescriptor.bytes(
      data.buffer.asUint8List(),
      width: 32,
      height: 32,
    );
    return _iconoUbicacion!;
  }

  Future<void> _procesarRutaAlgoritmica(Map<String, dynamic> data) async {
    final polyAlgoritmo = data['polyline_algoritmo'] ?? '';
    final envios = data['envios'] ?? [];

    debugPrint("🔍 PROCESANDO RUTA:");
    debugPrint("   Polyline length: ${polyAlgoritmo.length}");
    debugPrint("   Número de envíos: ${envios.length}");
    debugPrint("   Envíos data: $envios");

    if (polyAlgoritmo.isEmpty) {
      debugPrint("⚠️ No hay polyline de algoritmo disponible");
      if (mounted) {
        setState(() {
          inicio = null;
          fin = null;
          _polylines.clear();
          _markers.clear();
          _rutaNoEncontrada = true;
        });
      }
      return;
    }

    final decodedAlgoritmo = PolylinePoints.decodePolyline(polyAlgoritmo);
    final puntosAlgoritmo =
        decodedAlgoritmo.map((e) => LatLng(e.latitude, e.longitude)).toList();

    final poly = Polyline(
      polylineId: const PolylineId("algoritmo"),
      color: AppColors.warning,
      width: 6,
      points: puntosAlgoritmo,
    );

    // --- Marcadores de inicio y fin ---
    final markers = <Marker>{};
    if (puntosAlgoritmo.isNotEmpty) {
      inicio = puntosAlgoritmo.first;
      fin = puntosAlgoritmo.last;
      final iconoUbicacion = await _crearIconoUbicacion();

      markers.add(
        Marker(
          markerId: const MarkerId("inicio"),
          position: inicio!,
          icon: iconoUbicacion,
          anchor: const Offset(0.5, 0.5),
          zIndexInt: 100,
          infoWindow: InfoWindow(
            title: "Ubicación actual del mensajero",
            snippet: _selectedMensajeroNombre ?? "Inicio de la ruta",
          ),
        ),
      );

      markers.add(
        Marker(
          markerId: const MarkerId("fin"),
          position: fin!,
          icon: BitmapDescriptor.defaultMarkerWithHue(
            BitmapDescriptor.hueGreen,
          ),
          infoWindow: const InfoWindow(title: "Fin de ruta"),
        ),
      );
    }

    // --- Marcadores de envíos ---
    debugPrint("📍 Procesando ${envios.length} envíos para marcadores...");
    for (var e in envios) {
      final tipo = e['tipo'] ?? '';
      double? lat;
      double? lng;

      if (tipo.toLowerCase() == 'recojo') {
        lat = _toDouble(e['lat'] ?? e['latitud_origen']);
        lng = _toDouble(e['lng'] ?? e['longitud_origen']);
      } else if (tipo.toLowerCase() == 'envío' ||
          tipo.toLowerCase() == 'envio') {
        lat = _toDouble(e['lat'] ?? e['latitud_destino']);
        lng = _toDouble(e['lng'] ?? e['longitud_destino']);
      }

      if (lat != null && lng != null && lat != 0 && lng != 0) {
        debugPrint("✅ Agregando marcador $tipo #${e['id']} en ($lat, $lng)");
        markers.add(
          Marker(
            markerId: MarkerId("envio-${e['id']}"),
            position: LatLng(lat, lng),
            icon: BitmapDescriptor.defaultMarkerWithHue(
              BitmapDescriptor.hueOrange,
            ),
            infoWindow: InfoWindow(
              title: "${e['orden'] ?? ''} · ${e['tipo'] ?? 'Punto'}",
              snippet:
                  e['direccion'] ??
                  e['destino_direccion'] ??
                  e['origen_direccion'] ??
                  '',
            ),
          ),
        );
      } else {
        debugPrint(
          "⚠️ Coordenadas inválidas para envío #${e['id']}: lat=$lat, lng=$lng",
        );
      }
    }

    setState(() {
      _polylines.clear();
      _polylines.add(poly);
      _markers.clear();
      _markers.addAll(markers);
    });

    await Future.delayed(const Duration(milliseconds: 500));
    if (puntosAlgoritmo.isNotEmpty) {
      _fitToPolylines(puntosAlgoritmo);
    }
  }

  void _fitToPolylines(List<LatLng> puntos) {
    if (_controller == null || puntos.isEmpty) return;
    final bounds = _getLatLngBounds(puntos);
    _controller!.animateCamera(CameraUpdate.newLatLngBounds(bounds, 60));
  }

  LatLngBounds _getLatLngBounds(List<LatLng> points) {
    double x0 = points.first.latitude;
    double x1 = points.first.latitude;
    double y0 = points.first.longitude;
    double y1 = points.first.longitude;

    for (final p in points) {
      if (p.latitude > x1) x1 = p.latitude;
      if (p.latitude < x0) x0 = p.latitude;
      if (p.longitude > y1) y1 = p.longitude;
      if (p.longitude < y0) y0 = p.longitude;
    }

    return LatLngBounds(southwest: LatLng(x0, y0), northeast: LatLng(x1, y1));
  }

  // =====================================================
  // Drawer lateral
  // =====================================================
  Widget _buildDrawer(BuildContext context) {
    return const RoleDrawer(current: AppDestination.rutas);
  }

  // =====================================================
  // UI PRINCIPAL
  // =====================================================
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: Text(
          _rol == 'mensajero' ? 'Mi Ruta Asignada' : 'Rutas de Mensajeros',
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _cargarUsuarioYDatos,
          ),
        ],
      ),
      drawer: _buildDrawer(context),
      floatingActionButton:
          _rol == 'mensajero' && _ruta != null
              ? FloatingActionButton.extended(
                backgroundColor: AppColors.primary,
                icon: const Icon(Icons.navigation, color: Colors.white),
                label: const Text(
                  "Guiarme",
                  style: TextStyle(color: Colors.white, fontSize: 16),
                ),
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => GuiarMensajeroPage(ruta: _ruta),
                    ),
                  );
                },
              )
              : null, // ✅ solo aparece si es mensajero
      body:
          _loading
              ? const Center(
                child: CircularProgressIndicator(color: AppColors.primary),
              )
              : (_rol != 'mensajero' && _rol != 'administrador')
              ? const Center(
                child: Text(
                  'Esta sección está disponible para administradores y mensajeros.',
                  textAlign: TextAlign.center,
                ),
              )
              : Column(
                children: [
                  // Dropdown para seleccionar mensajero (solo admin)
                  if (_rol != 'mensajero' && _mensajeros.isNotEmpty)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceDark,
                        border: Border(
                          bottom: BorderSide(
                            color: AppColors.primary.withValues(alpha: 0.3),
                          ),
                        ),
                      ),
                      child: DropdownButtonFormField<int>(
                        initialValue: _selectedMensajeroId,
                        decoration: InputDecoration(
                          labelText: 'Seleccionar Mensajero',
                          labelStyle: const TextStyle(color: Colors.white70),
                          filled: true,
                          fillColor: AppColors.backgroundDark,
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: const BorderSide(
                              color: AppColors.primary,
                            ),
                          ),
                          enabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide(
                              color: AppColors.primary.withValues(alpha: 0.5),
                            ),
                          ),
                        ),
                        dropdownColor: AppColors.surfaceDark,
                        style: const TextStyle(color: Colors.white),
                        items:
                            _mensajeros.map((m) {
                              final disponible = m['disponible'] == true;
                              final zona = m['zona'] as String?;
                              return DropdownMenuItem<int>(
                                value: m['id'] as int,
                                child: Row(
                                  children: [
                                    Container(
                                      width: 8,
                                      height: 8,
                                      margin: const EdgeInsets.only(right: 8),
                                      decoration: BoxDecoration(
                                        shape: BoxShape.circle,
                                        color:
                                            disponible
                                                ? Colors.green
                                                : Colors.orange,
                                      ),
                                    ),
                                    Expanded(
                                      child: Text(
                                        m['nombre'] ?? 'Sin nombre',
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    if (zona != null)
                                      Text(
                                        ' · $zona',
                                        style: const TextStyle(
                                          fontSize: 11,
                                          color: Colors.white54,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                  ],
                                ),
                              );
                            }).toList(),
                        onChanged: (id) {
                          if (id == null) return;
                          final m = _mensajeros.firstWhere(
                            (x) => x['id'] == id,
                            orElse: () => {},
                          );
                          setState(() {
                            _selectedMensajeroId = id;
                            _selectedMensajeroNombre = m['nombre'] as String?;
                            _ruta = null;
                            _rutaNoEncontrada = false;
                          });
                          _fetchRutaMensajero(id);
                          _programarPollingRuta(id);
                        },
                      ),
                    ),
                  Expanded(child: _buildMapaComparativo()),
                ],
              ),
    );
  }

  // =====================================================
  // Mapa + Comparación (solo ruta Algoritmo)
  // =====================================================
  Widget _buildMapaComparativo() {
    if (_ruta == null || inicio == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              _rutaNoEncontrada ? Icons.route_outlined : Icons.map_outlined,
              size: 64,
              color: AppColors.primary.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 16),
            Text(
              _rutaNoEncontrada
                  ? "${_selectedMensajeroNombre ?? 'Este mensajero'} no tiene ruta generada aún."
                  : _rol == 'mensajero'
                  ? "No se encontró ninguna ruta asignada."
                  : "Selecciona un mensajero para ver su ruta.",
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white70, fontSize: 16),
            ),
            if (_rutaNoEncontrada) ...[
              const SizedBox(height: 8),
              const Text(
                "Genérala desde la sección Rutas del panel web.",
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white38, fontSize: 13),
              ),
            ],
          ],
        ),
      );
    }

    return Column(
      children: [
        SizedBox(
          height: 400,
          child: GoogleMap(
            style:
                '[{"elementType":"geometry","stylers":[{"color":"#212121"}]},{"elementType":"labels.icon","stylers":[{"visibility":"off"}]},{"elementType":"labels.text.fill","stylers":[{"color":"#757575"}]},{"elementType":"labels.text.stroke","stylers":[{"color":"#212121"}]},{"featureType":"administrative","elementType":"geometry","stylers":[{"color":"#757575"}]},{"featureType":"poi","elementType":"labels.text.fill","stylers":[{"color":"#757575"}]},{"featureType":"poi.park","elementType":"geometry","stylers":[{"color":"#181818"}]},{"featureType":"road","elementType":"geometry.fill","stylers":[{"color":"#2c2c2c"}]},{"featureType":"road","elementType":"labels.text.fill","stylers":[{"color":"#8a8a8a"}]},{"featureType":"road.highway","elementType":"geometry","stylers":[{"color":"#3c3c3c"}]},{"featureType":"water","elementType":"geometry","stylers":[{"color":"#000000"}]}]',
            initialCameraPosition: CameraPosition(target: inicio!, zoom: 13),
            onMapCreated: (controller) {
              _controller = controller;
            },
            polylines: _polylines,
            markers: _markers,
            myLocationButtonEnabled: true,
            zoomControlsEnabled: true,
          ),
        ),
        Expanded(
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.backgroundDark,
                  AppColors.surfaceDark.withValues(alpha: 0.8),
                ],
              ),
            ),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: AppColors.secondary.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.bar_chart,
                          color: AppColors.secondary,
                          size: 24,
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Text(
                        "Comparación de rutas",
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  _infoCard(
                    title: "Ruta asignada por el sistema",
                    color: AppColors.secondary,
                    icon: Icons.timeline,
                    duracion: _ruta?['duracion_algoritmo'],
                    distancia: _ruta?['distancia_algoritmo'],
                  ),
                  const SizedBox(height: 20),
                  _routeNarrativeCard(),
                  const SizedBox(height: 20),
                  _routeStopsCard(),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  // =====================================================
  // Tarjeta de información (duración / distancia)
  // =====================================================
  Widget _infoCard({
    required String title,
    required Color color,
    required IconData icon,
    dynamic duracion,
    dynamic distancia,
  }) {
    final distanciaStr = _formatDistance(distancia);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color, width: 2),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.3),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: color,
                    fontSize: 14,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.access_time, color: Colors.white70, size: 16),
              const SizedBox(width: 4),
              Text(
                "Duración:",
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.white.withValues(alpha: 0.7),
                ),
              ),
            ],
          ),
          Text(
            "${duracion ?? '-'} min",
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              const Icon(Icons.straighten, color: Colors.white70, size: 16),
              const SizedBox(width: 4),
              Text(
                "Distancia:",
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.white.withValues(alpha: 0.7),
                ),
              ),
            ],
          ),
          Text(
            distanciaStr,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: Colors.white,
            ),
          ),
        ],
      ),
    );
  }

  List<Map<String, dynamic>> _enviosRuta() {
    final raw = _ruta?['envios'];
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
      ..sort((a, b) {
        final ao = (a['orden'] as num?)?.toInt() ?? 9999;
        final bo = (b['orden'] as num?)?.toInt() ?? 9999;
        return ao.compareTo(bo);
      });
  }

  Widget _routeNarrativeCard() {
    final paradas = _enviosRuta();
    final siguiente = paradas.isNotEmpty ? paradas.first : null;
    final ultima = paradas.isNotEmpty ? paradas.last : null;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.22)),
      ),
      child: Column(
        children: [
          _narrativeRow(
            Icons.my_location,
            'Salida',
            _rol == 'mensajero'
                ? 'Tu ubicación actual registrada'
                : 'Ubicación registrada de ${_selectedMensajeroNombre ?? 'mensajero'}',
            AppColors.info,
          ),
          if (siguiente != null) ...[
            const Divider(height: 22),
            _narrativeRow(
              Icons.flag_outlined,
              'Siguiente parada',
              _stopTitle(siguiente),
              AppColors.warning,
            ),
          ],
          if (ultima != null && ultima != siguiente) ...[
            const Divider(height: 22),
            _narrativeRow(
              Icons.task_alt,
              'Última parada',
              _stopTitle(ultima),
              AppColors.success,
            ),
          ],
        ],
      ),
    );
  }

  Widget _routeStopsCard() {
    final paradas = _enviosRuta();
    if (paradas.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.secondary.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Orden de atención',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          for (final parada in paradas.take(6))
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: AppColors.primary,
                    child: Text(
                      '${parada['orden'] ?? ''}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _stopTitle(parada),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _narrativeRow(IconData icon, String label, String value, Color color) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.16),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, color: color, size: 18),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(color: AppColors.textTertiary),
              ),
              Text(
                value,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ),
      ],
    );
  }

  String _stopTitle(Map<String, dynamic> parada) {
    final tipo = parada['tipo']?.toString() ?? 'Parada';
    final nombre = parada['destinatario_nombre']?.toString();
    final direccion = parada['direccion']?.toString();
    final prefix = nombre?.isNotEmpty == true ? '$nombre · ' : '';
    return '$tipo · $prefix${direccion?.isNotEmpty == true ? direccion : 'Dirección pendiente'}';
  }

  String _formatDistance(dynamic distancia) {
    final value =
        distancia is num ? distancia.toDouble() : double.tryParse('$distancia');
    if (value == null) return '-';
    if (value >= 1000) return '${(value / 1000).toStringAsFixed(1)} km';
    return '${value.round()} m';
  }

  double? _toDouble(dynamic value) {
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }
}

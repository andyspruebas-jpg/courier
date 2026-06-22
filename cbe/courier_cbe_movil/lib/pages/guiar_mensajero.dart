import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_compass/flutter_compass.dart';
import 'package:flutter_polyline_points/flutter_polyline_points.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/envio.dart';
import '../services/api_client.dart';
import '../theme/app_colors.dart';
import 'registrar_entrega_page.dart';

class GuiarMensajeroPage extends StatefulWidget {
  final Map<String, dynamic>? ruta;
  final int? destinoEnvioId;

  const GuiarMensajeroPage({super.key, this.ruta, this.destinoEnvioId});

  @override
  State<GuiarMensajeroPage> createState() => _GuiarMensajeroPageState();
}

class _GuiarMensajeroPageState extends State<GuiarMensajeroPage> {
  final _storage = const FlutterSecureStorage();
  final _tts = FlutterTts();

  GoogleMapController? _controller;
  StreamSubscription<Position>? _posStream;
  StreamSubscription<CompassEvent>? _compassStream;
  Timer? _refreshTimer;

  Map<String, dynamic>? _ruta;
  List<Map<String, dynamic>> _paradas = [];
  List<LatLng> _puntosRuta = [];
  List<LatLng> _puntosTramo = [];
  final Set<Polyline> _polylines = {};
  final Set<Marker> _markers = {};

  int _mensajeroId = 0;
  int _paradaActiva = 0;
  LatLng? _posicionActual;
  LatLng? _inicio;
  bool _loading = true;
  bool _navegando = false;
  bool _centrar = true;
  bool _hablando = false;
  String? _error;
  DateTime? _lastOptimizeAt;
  DateTime? _lastLocationSentAt;
  DateTime? _lastInstructionAt;
  DateTime? _lastCameraMoveAt;
  String? _lastInstructionText;
  String? _indicacionActual;
  double? _headingCompass;
  double _lastCameraBearing = 0;
  double _distanciaRestante = 0;
  double _distanciaTramoM = 0;
  double _duracionTramoMin = 0;
  double _progreso = 0;
  int _indiceRutaCercano = 0;

  @override
  void initState() {
    super.initState();
    _configurarTts();
    _bootstrap();
  }

  @override
  void dispose() {
    _posStream?.cancel();
    _compassStream?.cancel();
    _refreshTimer?.cancel();
    _tts.stop();
    super.dispose();
  }

  Future<void> _configurarTts() async {
    await _tts.setLanguage('es-ES');
    await _tts.setSpeechRate(0.88);
    await _tts.setVolume(1);
  }

  Future<void> _bootstrap() async {
    final id = await _storage.read(key: 'id');
    _mensajeroId = int.tryParse(id ?? '') ?? 0;
    _iniciarBrujula();
    await _iniciarGps();
    await _cargarRuta(inicial: true, optimizar: _posicionActual != null);
  }

  void _iniciarBrujula() {
    _compassStream?.cancel();
    final events = FlutterCompass.events;
    if (events == null) return;
    _compassStream = events.listen((event) {
      final heading = event.heading;
      if (heading == null || !heading.isFinite) return;
      _headingCompass = (heading + 360) % 360;
      if (_navegando && _centrar) _actualizarCamaraNavegacion();
    });
  }

  Future<void> _cargarRuta({
    bool inicial = false,
    bool optimizar = false,
  }) async {
    if (_mensajeroId <= 0 && widget.ruta == null) {
      setState(() {
        _loading = false;
        _error = 'No se pudo identificar al mensajero.';
      });
      return;
    }

    try {
      if (inicial) setState(() => _loading = true);

      if (optimizar) {
        final tieneUbicacion = await _asegurarUbicacionActual(enviar: true);
        if (!tieneUbicacion) {
          optimizar = false;
        }
      }

      if (optimizar) {
        await _enviarUbicacionActual();
        await ApiClient.instance.post('/rutas/api/optimizar/$_mensajeroId/');
      }

      Map<String, dynamic>? data =
          inicial && widget.ruta != null
              ? Map<String, dynamic>.from(widget.ruta!)
              : null;

      if (data == null || optimizar) {
        final res = await ApiClient.instance.get(
          '/rutas/api/ruta-detalle/$_mensajeroId/',
        );
        if (res.statusCode != 200) {
          setState(() {
            _loading = false;
            _error = 'No hay ruta activa con paradas pendientes.';
          });
          return;
        }
        final decoded = jsonDecode(res.body);
        if (decoded is Map) data = Map<String, dynamic>.from(decoded);
      }

      if (data == null) {
        setState(() {
          _loading = false;
          _error = 'La ruta recibida no tiene un formato válido.';
        });
        return;
      }

      _aplicarRuta(data);
      if (_navegando) await _refrescarTramoActual();
      if (!mounted) return;
      setState(() {
        _ruta = data;
        _loading = false;
        _error = null;
      });
      if (_navegando) {
        _actualizarCamaraNavegacion(force: true);
      } else {
        _ajustarCamara(_puntosVisiblesMapa());
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'No se pudo cargar la guía: $e';
      });
    }
  }

  void _aplicarRuta(Map<String, dynamic> data) {
    final rawParadas =
        (data['envios'] as List? ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .where((e) => _latLngParada(e) != null && !_estaFinalizada(e))
            .toList()
          ..sort(
            (a, b) => (_toInt(a['orden']) ?? 9999).compareTo(
              _toInt(b['orden']) ?? 9999,
            ),
          );

    if (widget.destinoEnvioId != null) {
      final index = rawParadas.indexWhere(
        (p) => _toInt(p['id']) == widget.destinoEnvioId,
      );
      if (index > 0) {
        final selected = rawParadas.removeAt(index);
        rawParadas.insert(0, selected);
      }
    }

    final encoded =
        (data['polyline_algoritmo'] ?? data['polyline'] ?? '').toString();
    final decoded = _decodePolyline(encoded);

    _paradas = rawParadas;
    _paradaActiva = 0;
    _puntosRuta = decoded.length >= 2 ? decoded : [];
    if (!_navegando) _puntosTramo = [];
    _inicio =
        _posicionActual ??
        _latLngFrom(data['latitud_inicio'], data['longitud_inicio']) ??
        (_paradas.isNotEmpty ? _latLngParada(_paradas.first) : null);

    _rebuildMapObjects();
    _actualizarDistanciaYProgreso();
  }

  void _rebuildMapObjects() {
    _polylines
      ..clear()
      ..addAll([
        if (_puntosRuta.length >= 2)
          Polyline(
            polylineId: const PolylineId('ruta_restante'),
            color:
                _navegando
                    ? AppColors.secondary.withValues(alpha: 0.72)
                    : AppColors.secondary,
            width: _navegando ? 5 : 7,
            points: _puntosRuta,
          ),
        if (_navegando && _puntosTramo.length >= 2)
          Polyline(
            polylineId: const PolylineId('tramo_activo'),
            color: AppColors.primary,
            width: 7,
            points: _puntosTramo,
          ),
      ]);

    _markers
      ..clear()
      ..addAll([
        if (!_navegando && _inicio != null)
          Marker(
            markerId: const MarkerId('inicio'),
            position: _inicio!,
            icon: BitmapDescriptor.defaultMarkerWithHue(
              BitmapDescriptor.hueAzure,
            ),
            infoWindow: const InfoWindow(title: 'Punto actual del mensajero'),
          ),
        for (final parada in _paradas.where(
          (p) => !_navegando || _paradas.indexOf(p) == _paradaActiva,
        ))
          Marker(
            markerId: MarkerId('parada-${parada['id']}'),
            position: _latLngParada(parada)!,
            icon: BitmapDescriptor.defaultMarkerWithHue(
              _navegando || _paradas.indexOf(parada) == _paradaActiva
                  ? BitmapDescriptor.hueRed
                  : BitmapDescriptor.hueOrange,
            ),
            infoWindow: InfoWindow(
              title:
                  'Punto ${_paradas.indexOf(parada) + 1}: ${parada['tipo'] ?? 'Entrega'}',
              snippet: _labelParada(parada),
            ),
          ),
        if (_ubicacionVisible != null)
          Marker(
            markerId: const MarkerId('mensajero'),
            position: _ubicacionVisible!,
            anchor: const Offset(0.5, 0.5),
            icon: BitmapDescriptor.defaultMarkerWithHue(
              BitmapDescriptor.hueViolet,
            ),
            infoWindow: const InfoWindow(title: 'Estás aquí'),
          ),
      ]);
  }

  Future<void> _iniciarGps() async {
    final permitido = await _ubicacionPermitida();
    if (!permitido) return;

    await _asegurarUbicacionActual(enviar: true);

    _posStream = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.bestForNavigation,
        distanceFilter: 5,
      ),
    ).listen((pos) => _actualizarPosicion(pos, enviar: true));
  }

  Future<bool> _ubicacionPermitida() async {
    final servicioActivo = await Geolocator.isLocationServiceEnabled();
    if (!servicioActivo) {
      _snack('Activa la ubicación para iniciar la guía desde donde estás.');
      return false;
    }

    var permiso = await Geolocator.checkPermission();
    if (permiso == LocationPermission.denied) {
      permiso = await Geolocator.requestPermission();
    }
    if (permiso == LocationPermission.denied ||
        permiso == LocationPermission.deniedForever) {
      _snack('Permite el acceso a tu ubicación para calcular la ruta actual.');
      return false;
    }
    return true;
  }

  Future<bool> _asegurarUbicacionActual({bool enviar = false}) async {
    final permitido = await _ubicacionPermitida();
    if (!permitido) return false;
    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.best,
        ),
      ).timeout(const Duration(seconds: 8));
      _actualizarPosicion(pos, enviar: enviar);
      return true;
    } catch (_) {
      _snack('No pude obtener tu ubicación actual. Intenta de nuevo.');
      return _posicionActual != null;
    }
  }

  void _actualizarPosicion(Position pos, {bool enviar = false}) {
    _posicionActual = LatLng(pos.latitude, pos.longitude);
    _inicio = _posicionActual;
    _actualizarDistanciaYProgreso();
    _rebuildMapObjects();

    if (_controller != null && _centrar && _navegando) {
      _actualizarCamaraNavegacion(pos: pos);
    }

    if (enviar) _enviarUbicacionActual(throttle: true);
    if (_navegando) {
      _anunciarProximaAccion();
      _optimizarSiHaceFalta();
    }
    if (mounted) setState(() {});
  }

  Future<void> _enviarUbicacionActual({bool throttle = false}) async {
    final actual = _posicionActual;
    if (actual == null || _mensajeroId <= 0) return;
    final now = DateTime.now();
    if (throttle &&
        _lastLocationSentAt != null &&
        now.difference(_lastLocationSentAt!) < const Duration(seconds: 20)) {
      return;
    }
    _lastLocationSentAt = now;
    await ApiClient.instance.post(
      '/usuarios/actualizar_ubicacion/',
      body: {'latitud': actual.latitude, 'longitud': actual.longitude},
    );
  }

  Future<void> _refrescarTramoActual() async {
    final origen = _ubicacionVisible;
    final destino = _paradaActualLatLng;
    if (origen == null || destino == null) {
      _puntosTramo = [];
      _distanciaTramoM = 0;
      _duracionTramoMin = 0;
      return;
    }

    try {
      final res = await ApiClient.instance.post(
        '/rutas/api/tramo/',
        body: {
          'origin': {'lat': origen.latitude, 'lng': origen.longitude},
          'destination': {'lat': destino.latitude, 'lng': destino.longitude},
        },
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        if (data is Map) {
          final decoded = _decodePolyline(data['polyline']?.toString() ?? '');
          _puntosTramo =
              decoded.length >= 2 ? decoded : <LatLng>[origen, destino];
          _distanciaTramoM =
              _toDouble(data['distancia_m']) ?? _distancia(origen, destino);
          _duracionTramoMin =
              _toDouble(data['duracion_min']) ?? (_distanciaTramoM / 230);
          _indiceRutaCercano = 0;
          _actualizarDistanciaYProgreso();
          _rebuildMapObjects();
          return;
        }
      }
    } catch (e) {
      debugPrint('⚠️ Error cargando tramo activo: $e');
    }

    _puntosTramo = [origen, destino];
    _distanciaTramoM = _distancia(origen, destino);
    _duracionTramoMin = _distanciaTramoM / 230;
    _actualizarDistanciaYProgreso();
    _rebuildMapObjects();
  }

  Future<void> _optimizarSiHaceFalta() async {
    final now = DateTime.now();
    if (_lastOptimizeAt != null &&
        now.difference(_lastOptimizeAt!) < const Duration(seconds: 45)) {
      return;
    }
    _lastOptimizeAt = now;
    await _cargarRuta(optimizar: true);
    _actualizarCamaraNavegacion(force: true);
  }

  Future<void> _iniciarGuia() async {
    if (_paradas.isEmpty) {
      _snack('No hay paradas pendientes para guiar.');
      return;
    }
    final tieneUbicacion = await _asegurarUbicacionActual(enviar: true);
    if (!tieneUbicacion) {
      _snack('La guía necesita tu ubicación actual para ordenar la ruta.');
      return;
    }
    setState(() {
      _navegando = true;
      _indicacionActual = 'Calculando indicaciones desde tu ubicación...';
    });
    await _cargarRuta(optimizar: true);
    final rutaId = _toInt(_ruta?['id']);
    if (rutaId != null) {
      await ApiClient.instance.post(
        '/rutas/api/$rutaId/evento/',
        body: {
          'evento': 'start',
          'timestamp': DateTime.now().toIso8601String(),
        },
      );
    }
    if (mounted) {
      setState(() => _indicacionActual = _instruccionNavegacion());
    }
    _hablar('Guía iniciada. Primero ve a ${_labelParada(_paradaActual!)}.');
    _refreshTimer?.cancel();
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (_navegando) _cargarRuta();
    });
  }

  Future<void> _detenerGuia() async {
    setState(() {
      _navegando = false;
      _indicacionActual = null;
      _lastInstructionText = null;
      _lastInstructionAt = null;
      _puntosTramo = [];
    });
    _refreshTimer?.cancel();
    final rutaId = _toInt(_ruta?['id']);
    if (rutaId != null) {
      await ApiClient.instance.post(
        '/rutas/api/$rutaId/evento/',
        body: {
          'evento': 'finish',
          'timestamp': DateTime.now().toIso8601String(),
        },
      );
    }
  }

  Future<void> _registrarEntregaActual() async {
    final parada = _paradaActual;
    if (parada == null) return;
    final ok = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => RegistrarEntregaPage(envio: _paradaToEnvio(parada)),
      ),
    );
    if (ok == true) {
      await _cargarRuta(optimizar: true);
      if (_paradas.isNotEmpty) {
        _hablar(
          'Entrega registrada. Ahora ve al punto ${_paradaActiva + 1}: ${_labelParada(_paradaActual!)}.',
        );
      } else {
        _hablar('Ruta completada. No quedan sobres pendientes.');
        setState(() {
          _navegando = false;
          _indicacionActual = null;
          _puntosTramo = [];
        });
      }
    }
  }

  void _actualizarDistanciaYProgreso() {
    final actual = _posicionActual ?? _inicio;
    final destino = _paradaActualLatLng;
    if (actual == null || destino == null) {
      _distanciaRestante = 0;
      _progreso = 0;
      return;
    }
    _distanciaRestante = _distancia(actual, destino);
    final puntos = _puntosNavegacion;
    if (puntos.length >= 2) {
      final closestIndex = _indiceMasCercano(actual, puntos);
      _indiceRutaCercano = closestIndex;
      _progreso =
          _navegando ? (closestIndex / (puntos.length - 1)).clamp(0, 1) : 0;
    } else {
      _progreso = 0;
    }
  }

  void _anunciarProximaAccion() {
    final parada = _paradaActual;
    if (parada == null) return;
    if (_distanciaRestante < 35) {
      _hablar(
        'Llegaste al punto ${_paradaActiva + 1}. ${_labelParada(parada)}.',
      );
      return;
    }

    final instruccion = _instruccionNavegacion();
    if (instruccion == null) return;

    final now = DateTime.now();
    if (_lastInstructionAt != null) {
      final elapsed = now.difference(_lastInstructionAt!);
      final cooldown =
          _lastInstructionText == instruccion
              ? const Duration(seconds: 18)
              : const Duration(seconds: 10);
      if (elapsed < cooldown) return;
    }
    _lastInstructionAt = now;
    _lastInstructionText = instruccion;
    _indicacionActual = instruccion;
    _hablar(instruccion);
  }

  Future<void> _hablar(String texto) async {
    if (_hablando) return;
    _hablando = true;
    await _tts.speak(texto);
    Future.delayed(const Duration(seconds: 4), () => _hablando = false);
  }

  List<LatLng> _decodePolyline(String encoded) {
    if (encoded.isEmpty) return [];
    try {
      return PolylinePoints.decodePolyline(encoded)
          .map((p) => LatLng(p.latitude, p.longitude))
          .where(_validLatLng)
          .toList();
    } catch (_) {
      return [];
    }
  }

  LatLng? get _paradaActualLatLng =>
      _paradaActual == null ? null : _latLngParada(_paradaActual!);
  Map<String, dynamic>? get _paradaActual =>
      _paradaActiva >= 0 && _paradaActiva < _paradas.length
          ? _paradas[_paradaActiva]
          : null;
  LatLng? get _ubicacionVisible =>
      _posicionActual ??
      (_puntosTramo.isNotEmpty
          ? _puntosTramo.first
          : (_puntosRuta.isNotEmpty ? _puntosRuta.first : _inicio));
  List<LatLng> get _puntosNavegacion =>
      _puntosTramo.length >= 2 ? _puntosTramo : _puntosRuta;

  LatLng? _latLngParada(Map<String, dynamic> parada) => _latLngFrom(
    parada['lat'] ?? parada['latitud_destino'],
    parada['lng'] ?? parada['longitud_destino'],
  );

  LatLng? _latLngFrom(dynamic lat, dynamic lng) {
    final la = _toDouble(lat);
    final lo = _toDouble(lng);
    if (la == null || lo == null) return null;
    final p = LatLng(la, lo);
    return _validLatLng(p) ? p : null;
  }

  bool _validLatLng(LatLng p) =>
      p.latitude >= -90 &&
      p.latitude <= 90 &&
      p.longitude >= -180 &&
      p.longitude <= 180;

  bool _estaFinalizada(Map<String, dynamic> parada) {
    final estado = (parada['estado'] ?? '').toString().toLowerCase();
    return estado == 'entregado' ||
        estado == 'rechazado' ||
        estado == 'cancelado';
  }

  Envio _paradaToEnvio(Map<String, dynamic> p) => Envio(
    id: _toInt(p['id']),
    numeroSeguimiento: p['numero_seguimiento']?.toString(),
    tipo: p['tipo']?.toString(),
    estado: p['estado']?.toString(),
    destinoDireccion: p['direccion']?.toString(),
    latitudDestino: _toDouble(p['lat']),
    longitudDestino: _toDouble(p['lng']),
    destinatarioNombre: p['destinatario_nombre']?.toString(),
    destinatarioTelefono: p['destinatario_telefono']?.toString(),
    tipoPago: p['tipo_pago']?.toString(),
    montoPago: _toDouble(p['monto_pago']),
  );

  String _labelParada(Map<String, dynamic> p) {
    final tipo = p['tipo']?.toString() ?? 'Entrega';
    final nombre = p['destinatario_nombre']?.toString();
    final direccion = p['direccion']?.toString();
    final n = nombre != null && nombre.isNotEmpty ? '$nombre · ' : '';
    return '$tipo · $n${direccion != null && direccion.isNotEmpty ? direccion : 'Dirección pendiente'}';
  }

  int _indiceMasCercano(LatLng actual, List<LatLng> puntos) {
    var index = 0;
    var minDist = double.infinity;
    for (var i = 0; i < puntos.length; i++) {
      final d = _distancia(actual, puntos[i]);
      if (d < minDist) {
        minDist = d;
        index = i;
      }
    }
    return index;
  }

  String? _instruccionNavegacion() {
    final puntos = _puntosNavegacion;
    if (!_navegando || puntos.length < 3) {
      if (_distanciaRestante > 180) {
        return 'Sigue por ${_redondearDistancia(_distanciaRestante)}.';
      }
      return 'En ${_distanciaRestante.round()} metros llega al punto ${_paradaActiva + 1}.';
    }

    final giro = _proximoGiro();
    if (giro != null) {
      final distancia = _redondearDistancia(giro.distanciaMetros);
      final direccion = giro.angulo > 0 ? 'derecha' : 'izquierda';
      if (giro.distanciaMetros <= 35) return 'Gira a la $direccion.';
      return 'En $distancia gira a la $direccion.';
    }

    if (_distanciaRestante < 180) {
      return 'En ${_distanciaRestante.round()} metros llega al punto ${_paradaActiva + 1}.';
    }

    final tramo = math.min(_distanciaRestante, 160.0);
    return 'Sigue por ${_redondearDistancia(tramo)}.';
  }

  ({double distanciaMetros, double angulo})? _proximoGiro() {
    final puntos = _puntosNavegacion;
    if (puntos.length < 3) return null;
    var acumulado = 0.0;
    final start = _indiceRutaCercano.clamp(1, puntos.length - 3).toInt();

    for (var i = start; i < puntos.length - 2; i++) {
      final anterior = puntos[i - 1];
      final pivote = puntos[i];
      final siguiente = puntos[i + 1];
      acumulado += _distancia(anterior, pivote);
      if (acumulado < 25) continue;
      if (acumulado > 350) break;

      final entrada = _bearingEntre(anterior, pivote);
      final salida = _bearingEntre(pivote, siguiente);
      final angulo = _normalizarAngulo(salida - entrada);
      if (angulo.abs() >= 35) {
        return (distanciaMetros: acumulado, angulo: angulo);
      }
    }
    return null;
  }

  double _bearingParaCamara(Position pos) {
    if (_headingCompass != null) return _headingCompass!;

    final gpsHeading = pos.heading;
    if (gpsHeading.isFinite && gpsHeading >= 0 && pos.speed > 0.7) {
      return gpsHeading;
    }

    final actual = _posicionActual;
    final puntos = _puntosNavegacion;
    if (puntos.length >= 2) {
      final i = _indiceRutaCercano.clamp(0, puntos.length - 2).toInt();
      final desde = actual ?? puntos[i];
      final hasta = puntos[math.min(i + 3, puntos.length - 1)];
      return _bearingEntre(desde, hasta);
    }

    final destino = _paradaActualLatLng;
    if (actual != null && destino != null) {
      return _bearingEntre(actual, destino);
    }
    return 0;
  }

  void _actualizarCamaraNavegacion({Position? pos, bool force = false}) {
    final controller = _controller;
    final actual =
        _posicionActual ??
        (_puntosNavegacion.isNotEmpty
            ? _puntosNavegacion[_indiceRutaCercano
                .clamp(0, _puntosNavegacion.length - 1)
                .toInt()]
            : _inicio);
    if (controller == null || actual == null || !_navegando || !_centrar) {
      return;
    }

    final now = DateTime.now();
    final bearing =
        pos != null ? _bearingParaCamara(pos) : _bearingDesdeSensores();
    final deltaBearing = _normalizarAngulo(bearing - _lastCameraBearing).abs();
    if (!force &&
        _lastCameraMoveAt != null &&
        now.difference(_lastCameraMoveAt!) <
            const Duration(milliseconds: 280) &&
        deltaBearing < 2.5) {
      return;
    }

    _lastCameraMoveAt = now;
    _lastCameraBearing = bearing;
    controller.animateCamera(
      CameraUpdate.newCameraPosition(
        CameraPosition(
          target: _camaraTargetAdelantado(actual),
          zoom: 18.7,
          tilt: 67,
          bearing: bearing,
        ),
      ),
    );
  }

  double _bearingDesdeSensores() {
    if (_headingCompass != null) return _headingCompass!;
    final actual = _posicionActual;
    final puntos = _puntosNavegacion;
    if (puntos.length >= 2) {
      final i = _indiceRutaCercano.clamp(0, puntos.length - 2).toInt();
      final desde = actual ?? puntos[i];
      final hasta = puntos[math.min(i + 3, puntos.length - 1)];
      return _bearingEntre(desde, hasta);
    }
    final destino = _paradaActualLatLng;
    if (actual != null && destino != null) {
      return _bearingEntre(actual, destino);
    }
    return _lastCameraBearing;
  }

  LatLng _camaraTargetAdelantado(LatLng actual) {
    final puntos = _puntosNavegacion;
    if (puntos.length < 2) return actual;
    final nextIndex = math.min(_indiceRutaCercano + 4, puntos.length - 1);
    final adelante = puntos[nextIndex];
    return LatLng(
      actual.latitude + (adelante.latitude - actual.latitude) * 0.08,
      actual.longitude + (adelante.longitude - actual.longitude) * 0.08,
    );
  }

  double _bearingEntre(LatLng a, LatLng b) {
    final lat1 = _rad(a.latitude);
    final lat2 = _rad(b.latitude);
    final dLon = _rad(b.longitude - a.longitude);
    final y = math.sin(dLon) * math.cos(lat2);
    final x =
        math.cos(lat1) * math.sin(lat2) -
        math.sin(lat1) * math.cos(lat2) * math.cos(dLon);
    return (math.atan2(y, x) * 180 / math.pi + 360) % 360;
  }

  double _normalizarAngulo(double angle) {
    var a = angle;
    while (a > 180) {
      a -= 360;
    }
    while (a < -180) {
      a += 360;
    }
    return a;
  }

  String _redondearDistancia(double metros) {
    if (metros >= 1000) {
      return '${(metros / 1000).toStringAsFixed(1)} kilómetros';
    }
    if (metros >= 100) return '${(metros / 10).round() * 10} metros';
    return '${metros.round()} metros';
  }

  double _distancia(LatLng a, LatLng b) {
    const r = 6371000.0;
    final dLat = _rad(b.latitude - a.latitude);
    final dLon = _rad(b.longitude - a.longitude);
    final aa =
        math.sin(dLat / 2) * math.sin(dLat / 2) +
        math.cos(_rad(a.latitude)) *
            math.cos(_rad(b.latitude)) *
            math.sin(dLon / 2) *
            math.sin(dLon / 2);
    return r * 2 * math.atan2(math.sqrt(aa), math.sqrt(1 - aa));
  }

  double _rad(double deg) => deg * math.pi / 180;
  double? _toDouble(dynamic value) =>
      value is num
          ? value.toDouble()
          : double.tryParse(value?.toString() ?? '');
  int? _toInt(dynamic value) =>
      value is int ? value : int.tryParse(value?.toString() ?? '');

  void _ajustarCamara(List<LatLng> puntos) {
    if (_controller == null || puntos.isEmpty) return;
    if (puntos.length == 1) {
      _controller!.animateCamera(CameraUpdate.newLatLngZoom(puntos.first, 16));
      return;
    }
    var minLat = puntos.first.latitude;
    var maxLat = puntos.first.latitude;
    var minLng = puntos.first.longitude;
    var maxLng = puntos.first.longitude;
    for (final p in puntos) {
      minLat = math.min(minLat, p.latitude);
      maxLat = math.max(maxLat, p.latitude);
      minLng = math.min(minLng, p.longitude);
      maxLng = math.max(maxLng, p.longitude);
    }
    _controller!.animateCamera(
      CameraUpdate.newLatLngBounds(
        LatLngBounds(
          southwest: LatLng(minLat, minLng),
          northeast: LatLng(maxLat, maxLng),
        ),
        70,
      ),
    );
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  List<LatLng> _puntosVisiblesMapa() {
    if (_navegando && _puntosTramo.length >= 2) return _puntosTramo;
    return _markers.map((m) => m.position).toList();
  }

  @override
  Widget build(BuildContext context) {
    final mapTarget = _posicionActual ?? _inicio ?? const LatLng(-16.5, -68.12);
    return Scaffold(
      backgroundColor: AppColors.backgroundDark,
      extendBodyBehindAppBar: _navegando,
      appBar: _navegando ? null : _normalAppBar(),
      body: Stack(
        children: [
          GoogleMap(
            initialCameraPosition: CameraPosition(
              target: mapTarget,
              zoom: _navegando ? 18.5 : 14,
              tilt: _navegando ? 67 : 0,
              bearing: _navegando ? _bearingDesdeSensores() : 0,
            ),
            polylines: _polylines,
            markers: _markers,
            myLocationEnabled: true,
            myLocationButtonEnabled: false,
            compassEnabled: true,
            mapToolbarEnabled: false,
            zoomControlsEnabled: false,
            padding: EdgeInsets.only(
              top: _navegando ? 150 : 0,
              bottom: _navegando ? 170 : 0,
            ),
            onMapCreated: (controller) {
              _controller = controller;
              Future.delayed(
                const Duration(milliseconds: 250),
                () =>
                    _navegando
                        ? _actualizarCamaraNavegacion(force: true)
                        : _ajustarCamara(_puntosVisiblesMapa()),
              );
            },
          ),
          if (_loading) const Center(child: CircularProgressIndicator()),
          if (_error != null) _errorBox(_error!),
          if (_navegando) ...[
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: _navigationInstructionCard(),
            ),
            Positioned(right: 16, bottom: 160, child: _floatingMapControls()),
            Positioned(
              left: 16,
              right: 16,
              bottom: 16,
              child: _navigationBottomBar(),
            ),
          ] else
            Positioned(bottom: 18, left: 16, right: 16, child: _panel()),
        ],
      ),
    );
  }

  PreferredSizeWidget _normalAppBar() => AppBar(
    backgroundColor: AppColors.surfaceDark,
    title: const Text('Guía de ruta', style: TextStyle(color: Colors.white)),
    iconTheme: const IconThemeData(color: Colors.white),
    actions: [
      IconButton(
        tooltip: 'Recalcular desde mi ubicación',
        icon: const Icon(Icons.route, color: AppColors.secondary),
        onPressed: _loading ? null : () => _cargarRuta(optimizar: true),
      ),
      IconButton(
        tooltip: 'Centrar seguimiento',
        icon: Icon(
          _centrar ? Icons.my_location : Icons.location_searching,
          color: AppColors.primary,
        ),
        onPressed: () => setState(() => _centrar = !_centrar),
      ),
    ],
  );

  Widget _navigationInstructionCard() {
    final parada = _paradaActual;
    final instruction = _indicacionActual ?? _instruccionNavegacion();
    final next =
        _paradas.length > 1
            ? _labelParada(
              _paradas[math.min(_paradaActiva + 1, _paradas.length - 1)],
            )
            : 'Último punto de la ruta';

    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _roundMapButton(
                  icon: Icons.arrow_back,
                  onPressed: () => Navigator.maybePop(context),
                  background: Colors.black.withValues(alpha: 0.55),
                  foreground: Colors.white,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
                    decoration: BoxDecoration(
                      color: const Color(0xFF006D67),
                      borderRadius: BorderRadius.circular(18),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.24),
                          blurRadius: 18,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        Icon(
                          _instructionIcon(instruction),
                          size: 42,
                          color: Colors.white,
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                instruction ?? 'Sigue la ruta',
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w900,
                                  fontSize: 24,
                                  height: 1.05,
                                ),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                parada == null
                                    ? 'Sin parada activa'
                                    : _labelParada(parada),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: Colors.white70,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        const Icon(Icons.navigation, color: Colors.white),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            Container(
              margin: const EdgeInsets.only(left: 62),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: const BoxDecoration(
                color: Color(0xFF006D67),
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(12),
                  bottomRight: Radius.circular(12),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'Luego',
                    style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                      fontSize: 16,
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Icon(Icons.turn_right, color: Colors.white, size: 22),
                  const SizedBox(width: 8),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 240),
                    child: Text(
                      next,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.white70),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _floatingMapControls() => Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      _roundMapButton(
        icon: _centrar ? Icons.explore : Icons.my_location,
        onPressed: () {
          setState(() => _centrar = true);
          _actualizarCamaraNavegacion(force: true);
        },
      ),
      const SizedBox(height: 12),
      _roundMapButton(
        icon: Icons.add,
        onPressed: () => _controller?.animateCamera(CameraUpdate.zoomBy(1.0)),
      ),
      const SizedBox(height: 12),
      _roundMapButton(
        icon: Icons.remove,
        onPressed: () => _controller?.animateCamera(CameraUpdate.zoomBy(-1.0)),
      ),
      const SizedBox(height: 12),
      _roundMapButton(
        icon: Icons.volume_up,
        onPressed: () {
          final text = _indicacionActual ?? _instruccionNavegacion();
          if (text != null) _hablar(text);
        },
      ),
    ],
  );

  Widget _navigationBottomBar() {
    final parada = _paradaActual;
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(18, 14, 18, 16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.22),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _tiempoEstimadoTexto(),
                    style: const TextStyle(
                      color: Colors.black,
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${_redondearDistancia(_distanciaRestante)} · Punto ${_paradaActiva + 1} de ${_paradas.length}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.black54, fontSize: 15),
                  ),
                ],
              ),
            ),
            IconButton.filledTonal(
              tooltip: 'Entregar',
              icon: const Icon(Icons.assignment_turned_in),
              onPressed: parada == null ? null : _registrarEntregaActual,
            ),
            const SizedBox(width: 10),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.error,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(
                  horizontal: 22,
                  vertical: 18,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(18),
                ),
              ),
              onPressed: _detenerGuia,
              child: const Text(
                'Salir',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _roundMapButton({
    required IconData icon,
    required VoidCallback? onPressed,
    Color background = Colors.white,
    Color foreground = const Color(0xFF202124),
  }) => Material(
    color: background,
    shape: const CircleBorder(),
    elevation: 5,
    child: IconButton(
      icon: Icon(icon, color: foreground),
      onPressed: onPressed,
      iconSize: 28,
      padding: const EdgeInsets.all(14),
    ),
  );

  IconData _instructionIcon(String? instruction) {
    final text = instruction?.toLowerCase() ?? '';
    if (text.contains('izquierda')) return Icons.turn_left;
    if (text.contains('derecha')) return Icons.turn_right;
    if (text.contains('lleg')) return Icons.place;
    return Icons.straight;
  }

  String _tiempoEstimadoTexto() {
    if (_distanciaRestante <= 0) return '0 min';
    final estimate =
        _duracionTramoMin > 0 ? _duracionTramoMin : (_distanciaRestante / 230);
    final minutes = math.max(1, estimate.round());
    return '$minutes min';
  }

  Widget _errorBox(String text) => Align(
    alignment: Alignment.topCenter,
    child: Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.error.withValues(alpha: 0.5)),
      ),
      child: Text(text, textAlign: TextAlign.center),
    ),
  );

  Widget _panel() {
    final parada = _paradaActual;
    final porcentaje = (_progreso * 100).round();
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark.withValues(alpha: 0.96),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: AppColors.primary.withValues(alpha: 0.35),
          width: 1.3,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.35),
            blurRadius: 16,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            parada == null
                ? 'Ruta sin paradas pendientes'
                : '${_navegando ? 'En navegación' : 'Listo para iniciar'} · Punto ${_paradaActiva + 1} de ${_paradas.length}',
            textAlign: TextAlign.center,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
          ),
          const SizedBox(height: 8),
          if (_navegando && _indicacionActual != null) ...[
            Text(
              _indicacionActual!,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
                fontSize: 15,
              ),
            ),
            const SizedBox(height: 8),
          ],
          Text(
            parada == null
                ? 'No quedan sobres por entregar.'
                : _labelParada(parada),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 10),
          LinearProgressIndicator(
            value: _progreso,
            minHeight: 7,
            color: AppColors.secondary,
          ),
          const SizedBox(height: 8),
          Text(
            'Distancia al punto: ${_distanciaRestante.round()} m · Avance ruta: $porcentaje%',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white70, fontSize: 13),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  icon: Icon(_navegando ? Icons.stop : Icons.play_arrow),
                  label: Text(_navegando ? 'Detener' : 'Iniciar guía'),
                  onPressed:
                      parada == null
                          ? null
                          : (_navegando ? _detenerGuia : _iniciarGuia),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton.icon(
                  icon: const Icon(Icons.assignment_turned_in),
                  label: const Text('Entregar'),
                  onPressed: parada == null ? null : _registrarEntregaActual,
                ),
              ),
            ],
          ),
          if (_paradas.length > 1) ...[
            const SizedBox(height: 10),
            Text(
              'Luego: ${_labelParada(_paradas[math.min(_paradaActiva + 1, _paradas.length - 1)])}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white54, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

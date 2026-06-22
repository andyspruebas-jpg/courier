import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:geolocator/geolocator.dart' as geo;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:flutter/services.dart';
import '../models/envio.dart';
import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../services/auth_service.dart';
import '../theme/app_colors.dart';
import '../widgets/role_drawer.dart';

// 🔹 Páginas
import 'detalle_envio_page.dart';
import 'envios_page.dart';
import 'login_page.dart';
import '../services/notificaciones_service.dart';
import '../api/api.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final storage = const FlutterSecureStorage();
  Map<String, dynamic>? usuario;
  Map<String, dynamic>? dashboardData;
  List<Envio> _clienteEnvios = [];
  List<Envio> _mensajeroEnvios = [];
  Map<String, dynamic>? _mensajeroRuta;
  bool _loading = true;
  bool _compartiendoUbicacion = false;
  Timer? _notifTimer;
  Timer? _webTrackingTimer;

  @override
  void initState() {
    super.initState();
    _cargarUsuario();
  }

  @override
  void dispose() {
    _notifTimer?.cancel();
    _webTrackingTimer?.cancel();
    super.dispose();
  }

  /// Sondeo en primer plano (app abierta): revisa cada minuto si hay nuevas
  /// asignaciones para el mensajero y dispara una notificación local.
  void _iniciarNotificaciones(int mensajeroId) {
    if (mensajeroId <= 0) return;
    NotificacionesService.instance.init();
    // Primera revisión y luego periódica.
    NotificacionesService.instance.revisarNuevasAsignaciones(mensajeroId);
    _notifTimer?.cancel();
    _notifTimer = Timer.periodic(
      const Duration(seconds: 60),
      (_) =>
          NotificacionesService.instance.revisarNuevasAsignaciones(mensajeroId),
    );
  }

  // Cargar los datos del usuario desde almacenamiento seguro
  Future<void> _cargarUsuario() async {
    final usuarioValidado = await AuthService().getUsuario();
    if (usuarioValidado == null) {
      if (!mounted) return;
      setState(() => _loading = false);
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const LoginPage()),
      );
      return;
    }

    usuario = usuarioValidado;
    final rol = usuario?['rol']?.toString();
    if (RoleNames.isAdmin(rol)) {
      await _fetchDashboardData();
    } else if (RoleNames.isMensajero(rol)) {
      // Si es mensajero: restablecer el servicio si estaba activo previamente
      final compartir = await storage.read(key: 'compartir_ubicacion');
      if (compartir == 'true') {
        if (kIsWeb) {
          await _iniciarTrackingWeb(silent: true);
        } else {
          // intenta iniciar el servicio sin pedir permisos otra vez (permisos ya deben estar concedidos)
          await _iniciarServicio(); // esto mostrará la notificación persistente
          if (mounted) setState(() => _compartiendoUbicacion = true);
        }
      }
      // Notificaciones locales de nuevas asignaciones (sondeo en primer plano)
      _iniciarNotificaciones(usuario?['id'] is int ? usuario!['id'] as int : 0);
      await _fetchMensajeroPanel();
      setState(() => _loading = false);
    } else if (RoleNames.isCliente(rol)) {
      await _fetchClienteEnvios();
    } else {
      setState(() => _loading = false);
    }
  }

  // Obtener los datos del dashboard desde el backend
  Future<void> _fetchDashboardData() async {
    setState(() => _loading = true);

    try {
      final response = await ApiClient.instance.get('/usuarios/home_data/');

      debugPrint('home_data status: ${response.statusCode}');
      debugPrint('home_data headers: ${response.headers}');

      if (response.statusCode == 200) {
        final contentType = response.headers['content-type'] ?? '';
        debugPrint('home_data content-type: $contentType');

        if (contentType.contains('application/json')) {
          try {
            final parsed = jsonDecode(response.body);
            if (parsed is Map<String, dynamic>) {
              setState(() {
                dashboardData = parsed;
                _loading = false;
              });
            } else {
              debugPrint(
                'home_data: JSON recibido no es Map: ${parsed.runtimeType}',
              );
              setState(() => _loading = false);
            }
          } catch (e) {
            debugPrint('Error parseando JSON de home_data: $e');
            debugPrint(
              'Respuesta (truncada): ${response.body.length > 300 ? response.body.substring(0, 300) : response.body}',
            );
            setState(() => _loading = false);
          }
        } else {
          debugPrint(
            'home_data: respuesta inesperada (no JSON). Body trunca: ${response.body.substring(0, response.body.length > 300 ? 300 : response.body.length)}',
          );
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text(
                  'Respuesta inesperada del servidor (esperaba JSON). Revisa sesión o endpoint.',
                ),
              ),
            );
          }
          setState(() => _loading = false);
        }
      } else if (response.statusCode == 401 || response.statusCode == 302) {
        debugPrint(
          'home_data: no autorizado o redirect (status ${response.statusCode})',
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('No autorizado. Inicia sesión de nuevo.'),
            ),
          );
        }
        setState(() => _loading = false);
      } else {
        debugPrint(
          'home_data: HTTP ${response.statusCode} - body: ${response.body}',
        );
        setState(() => _loading = false);
      }
    } on TimeoutException catch (e) {
      debugPrint('Timeout al solicitar home_data: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Timeout: no se pudo cargar el dashboard'),
          ),
        );
      }
      setState(() => _loading = false);
    } catch (e) {
      debugPrint('Error al cargar home_data: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Error al cargar el dashboard')),
        );
      }
      setState(() => _loading = false);
    }
  }

  Future<void> _fetchClienteEnvios() async {
    setState(() => _loading = true);
    try {
      final response = await ApiClient.instance.get('/envios/envios-json/');
      if (response.statusCode == 200) {
        final parsed = jsonDecode(response.body);
        final envios =
            parsed is List
                ? parsed
                    .map(
                      (item) => Envio.fromJson(
                        Map<String, dynamic>.from(item as Map),
                      ),
                    )
                    .toList()
                : <Envio>[];
        if (!mounted) return;
        setState(() {
          _clienteEnvios = envios;
          _loading = false;
        });
      } else {
        debugPrint(
          'envios cliente: HTTP ${response.statusCode} - ${response.body}',
        );
        if (mounted) setState(() => _loading = false);
      }
    } catch (e) {
      debugPrint('Error cargando envíos del cliente: $e');
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _fetchMensajeroPanel() async {
    try {
      final enviosResponse = await ApiClient.instance.get(
        '/envios/envios-json/',
      );
      final rutaResponse = await ApiClient.instance.get(
        '/rutas/api/ruta-detalle/${usuario?['id']}/',
      );
      final envios =
          enviosResponse.statusCode == 200
              ? (jsonDecode(enviosResponse.body) as List)
                  .map(
                    (item) =>
                        Envio.fromJson(Map<String, dynamic>.from(item as Map)),
                  )
                  .where((envio) => envio.estado != EstadoEnvio.entregado)
                  .toList()
              : <Envio>[];
      final ruta =
          rutaResponse.statusCode == 200
              ? Map<String, dynamic>.from(jsonDecode(rutaResponse.body) as Map)
              : null;
      if (!mounted) return;
      setState(() {
        _mensajeroEnvios = envios;
        _mensajeroRuta = ruta;
      });
    } catch (e) {
      debugPrint('Error cargando panel de mensajero: $e');
    }
  }

  // =====================================================
  // 📍 SERVICIO DE UBICACIÓN EN SEGUNDO PLANO
  // =====================================================

  // Iniciar el seguimiento de ubicación
  Future<void> _iniciarTracking() async {
    if (kIsWeb) {
      await _iniciarTrackingWeb();
      return;
    }

    bool serviceEnabled = await geo.Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Activa la ubicación en tu dispositivo.')),
      );
      return;
    }

    geo.LocationPermission permission =
        await geo.Geolocator.requestPermission();
    if (permission == geo.LocationPermission.denied ||
        permission == geo.LocationPermission.deniedForever) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Permiso de ubicación denegado')),
      );
      return;
    }

    // Solicitar permiso en segundo plano explícitamente (Android)
    if (await Permission.locationAlways.isDenied) {
      final status = await Permission.locationAlways.request();
      if (status != PermissionStatus.granted) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Concede "Permitir siempre" para ubicación en segundo plano',
            ),
          ),
        );
        return;
      }
    }

    // Solicitar permiso de notificaciones (Android 13+)
    if (Platform.isAndroid) {
      if (await Permission.notification.isDenied) {
        final nstatus = await Permission.notification.request();
        if (nstatus != PermissionStatus.granted) {
          if (!mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'Concede permiso de notificaciones para ver la notificación persistente',
              ),
            ),
          );
          return;
        }
      }
    }

    // PEDIR al usuario que ignore optimización de batería (abrirá settings)
    try {
      const channel = MethodChannel('cbe/battery');
      await channel.invokeMethod('requestIgnoreBatteryOptimizations');
    } catch (e) {
      debugPrint('⚠️ Error pidiendo ignorar optimización batería: $e');
    }

    await _iniciarServicio();

    // Guardar preferencia para reactivar la notificación si el usuario vuelve a la pantalla inicio
    await storage.write(key: 'compartir_ubicacion', value: 'true');

    setState(() => _compartiendoUbicacion = true);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('🟢 Compartiendo ubicación en segundo plano'),
      ),
    );
  }

  Future<void> _iniciarTrackingWeb({bool silent = false}) async {
    try {
      final serviceEnabled = await geo.Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        if (!silent && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Activa la ubicación en tu navegador.'),
            ),
          );
        }
        return;
      }

      var permission = await geo.Geolocator.checkPermission();
      if (permission == geo.LocationPermission.denied && !silent) {
        permission = await geo.Geolocator.requestPermission();
      }
      if (permission == geo.LocationPermission.denied ||
          permission == geo.LocationPermission.deniedForever) {
        if (!silent && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Permiso de ubicación denegado')),
          );
        }
        return;
      }

      final sent = await _enviarUbicacionWeb();
      _webTrackingTimer?.cancel();
      _webTrackingTimer = Timer.periodic(
        const Duration(seconds: 30),
        (_) => _enviarUbicacionWeb(),
      );
      await storage.write(key: 'compartir_ubicacion', value: 'true');
      if (!mounted) return;
      setState(() => _compartiendoUbicacion = true);
      if (!silent) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              sent
                  ? '🟢 Compartiendo ubicación mientras la app está abierta'
                  : 'Seguimiento activo; esperando primera ubicación válida.',
            ),
          ),
        );
      }
    } catch (e) {
      debugPrint('⚠️ Error iniciando tracking web: $e');
      if (!silent && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo iniciar la ubicación.')),
        );
      }
    }
  }

  Future<bool> _enviarUbicacionWeb() async {
    try {
      final position = await geo.Geolocator.getCurrentPosition(
        locationSettings: const geo.LocationSettings(
          accuracy: geo.LocationAccuracy.high,
        ),
      );
      final response = await ApiClient.instance.post(
        '/usuarios/actualizar_ubicacion/',
        body: {'latitud': position.latitude, 'longitud': position.longitude},
      );
      return response.statusCode >= 200 && response.statusCode < 300;
    } catch (e) {
      debugPrint('⚠️ Error enviando ubicación web: $e');
      return false;
    }
  }

  // Configurar el servicio para ejecutar en segundo plano
  Future<void> _iniciarServicio() async {
    final service = FlutterBackgroundService();

    await service.configure(
      androidConfiguration: AndroidConfiguration(
        onStart: onStart, // Función que maneja el servicio en segundo plano
        autoStart: true, // El servicio se inicia automáticamente
        isForegroundMode: true, // Mantén el servicio en primer plano
        notificationChannelId:
            'ubicacion_courier_channel', // Canal de notificación
        initialNotificationTitle: 'Courier Bolivian Express',
        initialNotificationContent: 'Compartiendo ubicación...',
        foregroundServiceNotificationId:
            999, // ID de la notificación para primer plano
      ),
      iosConfiguration: IosConfiguration(),
    );

    await service.startService(); // Inicia el servicio en primer plano

    // Establece el ID del usuario en el isolate del servicio
    // Asegúrate de que usuario ya esté cargado; si no, envía 0 por defecto.
    service.invoke('setUserId', {'id': usuario?['id'] ?? 0});
  }

  // Detener el seguimiento de ubicación
  Future<void> _detenerTracking() async {
    if (kIsWeb) {
      _webTrackingTimer?.cancel();
      await storage.delete(key: 'compartir_ubicacion');
      setState(() => _compartiendoUbicacion = false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('🔴 Se detuvo el envío de ubicación')),
      );
      return;
    }

    final service = FlutterBackgroundService();
    service.invoke('stopService');
    // quitar preferencia para que no se vuelva a iniciar al volver a Home
    await storage.delete(key: 'compartir_ubicacion');
    setState(() => _compartiendoUbicacion = false);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('🔴 Se detuvo el envío de ubicación')),
    );
  }

  // Cambiar entre iniciar y detener el seguimiento
  void _toggleTracking() {
    if (_compartiendoUbicacion) {
      _detenerTracking();
    } else {
      _iniciarTracking();
    }
  }

  // =====================================================
  // 🔹 INTERFAZ (UI)
  // =====================================================

  @override
  Widget build(BuildContext context) {
    final rol = usuario?['rol'] ?? '';
    final isAdmin = RoleNames.isAdmin(rol.toString());
    final isMensajero = RoleNames.isMensajero(rol.toString());
    final title =
        isAdmin
            ? 'Dashboard - Courier Bolivian Express'
            : isMensajero
            ? 'Panel del Mensajero'
            : 'Panel Cliente / Empresa';

    return Scaffold(
      backgroundColor: AppColors.backgroundDark,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await storage.deleteAll();
              if (_compartiendoUbicacion) await _detenerTracking();
              if (!context.mounted) return;
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (_) => const LoginPage()),
              );
            },
          ),
        ],
      ),
      drawer: RoleDrawer(
        current: AppDestination.dashboard,
        trackingEnabled: _compartiendoUbicacion,
        onToggleTracking: isMensajero ? _toggleTracking : null,
      ),
      body:
          _loading
              ? const Center(
                child: CircularProgressIndicator(color: AppColors.primary),
              )
              : isAdmin
              ? _buildDashboard()
              : isMensajero
              ? _buildMensajero()
              : _buildClienteDashboard(),
    );
  }

  Widget _buildClienteDashboard() {
    final empresa = usuario?['empresa'];
    final empresaNombre = empresa is Map ? empresa['nombre']?.toString() : null;
    final nombre =
        (empresaNombre?.isNotEmpty ?? false)
            ? empresaNombre!
            : usuario?['nombre']?.toString() ?? 'Cliente';
    final recientes = _clienteEnvios.take(5).toList();

    return RefreshIndicator(
      onRefresh: _fetchClienteEnvios,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              gradient: AppColors.primaryGradient,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 30,
                  backgroundColor: Colors.white,
                  child: Icon(
                    Icons.business_outlined,
                    color: AppColors.primary,
                    size: 34,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Cuenta cliente',
                        style: TextStyle(color: Colors.white70, fontSize: 13),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        nombre,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 21,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          GridView.count(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisCount: 2,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 1.1,
            children: [
              _buildCard(
                'Total',
                _clienteEnvios.length.toString(),
                Icons.inventory_2,
                AppColors.primary,
                onTap: () => _abrirClienteEnvios('Todos'),
              ),
              _buildCard(
                'En recepción',
                _countEstado('Pendiente').toString(),
                Icons.pending_actions,
                AppColors.warning,
                onTap: () => _abrirClienteEnvios('Pendiente'),
              ),
              _buildCard(
                'En tránsito',
                _countEstado('En Ruta').toString(),
                Icons.route,
                AppColors.info,
                onTap: () => _abrirClienteEnvios('En Ruta'),
              ),
              _buildCard(
                'Entregados',
                _countEstado('Entregado').toString(),
                Icons.check_circle,
                AppColors.success,
                onTap: () => _abrirClienteEnvios('Entregado'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed:
                      () => Navigator.pushNamed(
                        context,
                        AppRoutes.solicitarEnvio,
                      ),
                  icon: const Icon(Icons.add_box_outlined),
                  label: const Text('Solicitar'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed:
                      () => Navigator.pushNamed(context, AppRoutes.seguimiento),
                  icon: const Icon(Icons.manage_search),
                  label: const Text('Seguimiento'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 22),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Últimos envíos',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              TextButton(
                onPressed: () => Navigator.pushNamed(context, AppRoutes.envios),
                child: const Text('Ver todos'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (recientes.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 28),
              child: Center(child: Text('No hay envíos registrados.')),
            )
          else
            for (final envio in recientes)
              Card(
                child: ListTile(
                  leading: const Icon(
                    Icons.local_shipping_outlined,
                    color: AppColors.primary,
                  ),
                  title: Text(
                    envio.destinatarioNombre ?? 'Sin destinatario',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(
                    '${envio.estadoPublico ?? _estadoPublicoCliente(envio.estado)}\n${envio.destinoDireccion ?? 'Sin destino'}',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap:
                      () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => DetalleEnvioPage(envio: envio),
                        ),
                      ),
                ),
              ),
        ],
      ),
    );
  }

  void _abrirClienteEnvios(String estado) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => EnviosPage(initialEstado: estado)),
    );
  }

  int _countEstado(String estado) {
    return _clienteEnvios
        .where((envio) => envio.estado?.toLowerCase() == estado.toLowerCase())
        .length;
  }

  String _estadoPublicoCliente(String? estado) {
    switch ((estado ?? '').toLowerCase()) {
      case 'pendiente':
        return 'En recepción';
      case 'en ruta':
      case 'reintentado':
        return 'En tránsito';
      case 'entregado':
        return 'Entregado';
      case 'rechazado':
      case 'fallido':
      case 'cancelado':
        return estado ?? 'Sin estado';
      default:
        return estado?.isNotEmpty == true ? estado! : 'Registrado';
    }
  }

  // Construir la interfaz del mensajero
  Widget _buildMensajero() {
    final pendientes =
        _mensajeroEnvios
            .where((e) => e.estado?.toLowerCase() == 'pendiente')
            .length;
    final enRuta =
        _mensajeroEnvios
            .where((e) => e.estado?.toLowerCase() == 'en ruta')
            .length;
    final paradas = (_mensajeroRuta?['envios'] as List?) ?? const [];
    return RefreshIndicator(
      onRefresh: () async {
        await _fetchMensajeroPanel();
      },
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0.96, end: 1),
            duration: const Duration(milliseconds: 450),
            curve: Curves.easeOutBack,
            builder:
                (_, scale, child) =>
                    Transform.scale(scale: scale, child: child),
            child: Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                gradient: AppColors.primaryGradient,
                borderRadius: BorderRadius.circular(22),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primary.withValues(alpha: 0.25),
                    blurRadius: 24,
                    offset: const Offset(0, 12),
                  ),
                ],
              ),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 34,
                    backgroundColor: Colors.white,
                    child: Icon(
                      _compartiendoUbicacion
                          ? Icons.satellite_alt
                          : Icons.location_searching,
                      color:
                          _compartiendoUbicacion
                              ? AppColors.success
                              : AppColors.primary,
                      size: 34,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _compartiendoUbicacion
                              ? 'Ubicación activa'
                              : 'Ubicación pausada',
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 13,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          usuario?['nombre']?.toString() ?? 'Mensajero',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '${paradas.length} parada(s) asignadas · actualización cada 10 s',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _buildCard(
                  'Pendientes',
                  pendientes.toString(),
                  Icons.inventory_2_outlined,
                  AppColors.warning,
                  onTap:
                      () => Navigator.pushNamed(context, AppRoutes.misEntregas),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildCard(
                  'En ruta',
                  enRuta.toString(),
                  Icons.route,
                  AppColors.info,
                  onTap: () => Navigator.pushNamed(context, AppRoutes.rutas),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _trackingControlCard(),
          const SizedBox(height: 16),
          _quickActionsMensajero(),
          const SizedBox(height: 16),
          _nextStopsMensajero(paradas),
        ],
      ),
    );
  }

  Widget _trackingControlCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: (_compartiendoUbicacion
                        ? AppColors.success
                        : AppColors.warning)
                    .withValues(alpha: 0.16),
                shape: BoxShape.circle,
              ),
              child: Icon(
                _compartiendoUbicacion ? Icons.gps_fixed : Icons.gps_not_fixed,
                color:
                    _compartiendoUbicacion
                        ? AppColors.success
                        : AppColors.warning,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Seguimiento en vivo',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  Text(
                    _compartiendoUbicacion
                        ? 'Tu posición se está enviando al centro operativo.'
                        : 'Actívalo al iniciar tu turno o una ruta.',
                    style: const TextStyle(color: AppColors.textTertiary),
                  ),
                ],
              ),
            ),
            Switch(
              value: _compartiendoUbicacion,
              onChanged: (_) => _toggleTracking(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _quickActionsMensajero() {
    return Row(
      children: [
        Expanded(
          child: FilledButton.icon(
            onPressed: () => Navigator.pushNamed(context, AppRoutes.guia),
            icon: const Icon(Icons.assistant_direction),
            label: const Text('Guía'),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: OutlinedButton.icon(
            onPressed:
                () => Navigator.pushNamed(context, AppRoutes.misEntregas),
            icon: const Icon(Icons.checklist),
            label: const Text('Mis entregas'),
          ),
        ),
      ],
    );
  }

  Widget _nextStopsMensajero(List<dynamic> paradas) {
    if (paradas.isEmpty) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(18),
          child: Text('No hay paradas asignadas para tu turno actual.'),
        ),
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Próximas paradas',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10),
            for (final parada in paradas.take(3))
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: CircleAvatar(
                  backgroundColor: AppColors.primary,
                  child: Text('${(parada as Map)['orden'] ?? ''}'),
                ),
                title: Text(
                  parada['destinatario_nombre']?.toString() ?? 'Parada',
                ),
                subtitle: Text(
                  parada['direccion']?.toString() ?? 'Dirección pendiente',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
        ),
      ),
    );
  }

  // Construir el dashboard para el administrador
  Widget _buildDashboard() {
    return RefreshIndicator(
      onRefresh: _fetchDashboardData,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Resumen general',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 2,
              crossAxisSpacing: 16,
              mainAxisSpacing: 16,
              children: [
                _buildCard(
                  'Usuarios',
                  dashboardData?['usuarios_count']?.toString() ?? '0',
                  Icons.people,
                  AppColors.info,
                  onTap:
                      () => Navigator.pushNamed(context, AppRoutes.mensajeros),
                ),
                _buildCard(
                  'Envíos Pendientes',
                  dashboardData?['envios_pendientes']?.toString() ?? '0',
                  Icons.local_shipping,
                  AppColors.warning,
                  onTap:
                      () => Navigator.pushNamed(context, AppRoutes.pendientes),
                ),
                _buildCard(
                  'Mensajeros Activos',
                  dashboardData?['mensajeros_activos']?.toString() ?? '0',
                  Icons.delivery_dining,
                  AppColors.success,
                  onTap:
                      () => Navigator.pushNamed(context, AppRoutes.mensajeros),
                ),
                _buildCard(
                  '% Entregados',
                  '${dashboardData?['porcentaje_entregados'] ?? 0}%',
                  Icons.check_circle,
                  AppColors.secondary,
                  onTap:
                      () => Navigator.pushNamed(context, AppRoutes.entregados),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // Crear tarjeta para el dashboard
  Widget _buildCard(
    String title,
    String value,
    IconData icon,
    Color color, {
    VoidCallback? onTap,
  }) {
    return MouseRegion(
      cursor: onTap != null ? SystemMouseCursors.click : MouseCursor.defer,
      child: Card(
        elevation: 4,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, color: color, size: 40),
                const SizedBox(height: 10),
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.grey, fontSize: 14),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// =====================================================
// 🛰️ FUNCIÓN GLOBAL DE SERVICIO EN SEGUNDO PLANO
// =====================================================
@pragma('vm:entry-point')
Future<void> onStart(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();

  StreamSubscription<geo.Position>? positionSubscription;
  int userId = 0;
  String? token;

  // El isolate del servicio no comparte memoria con la UI: leemos el id y el
  // token directamente del almacenamiento seguro para no depender solo del
  // evento `setUserId` (que puede perderse por una carrera al arrancar).
  const isolateStorage = FlutterSecureStorage();
  try {
    userId = int.tryParse(await isolateStorage.read(key: 'id') ?? '') ?? 0;
    token = await isolateStorage.read(key: 'token');
  } catch (e) {
    debugPrint('⚠️ No se pudieron leer credenciales en el isolate: $e');
  }

  if (service is AndroidServiceInstance) {
    await service.setForegroundNotificationInfo(
      title: "Courier Bolivian Express",
      content: "Compartiendo ubicación en segundo plano",
    );
  }

  service.on('setUserId').listen((event) {
    userId =
        (event?['id'] is int)
            ? event!['id'] as int
            : int.tryParse('${event?['id']}') ?? 0;
    debugPrint('🔢 userId seteado en isolate: $userId');
  });

  service.on('stopService').listen((event) async {
    debugPrint('🔴 stopService recibido en isolate');
    await positionSubscription?.cancel();
    service.stopSelf();
  });

  try {
    bool enabled = await geo.Geolocator.isLocationServiceEnabled();
    if (!enabled) {
      debugPrint('⚠️ Servicio de ubicación no habilitado');
      return;
    }
    geo.LocationPermission perm = await geo.Geolocator.checkPermission();
    if (perm == geo.LocationPermission.denied ||
        perm == geo.LocationPermission.deniedForever) {
      perm = await geo.Geolocator.requestPermission();
      if (perm == geo.LocationPermission.denied ||
          perm == geo.LocationPermission.deniedForever) {
        debugPrint('⚠️ Permiso de ubicación denegado en isolate: $perm');
        return;
      }
    }
  } catch (e) {
    debugPrint('⚠️ Error comprobando permisos en isolate: $e');
  }

  final androidSettings = geo.AndroidSettings(
    accuracy: geo.LocationAccuracy.high,
    intervalDuration: const Duration(seconds: 10),
    distanceFilter: 0,
    foregroundNotificationConfig: const geo.ForegroundNotificationConfig(
      notificationTitle: "Courier Bolivian Express",
      notificationText: "Compartiendo ubicación en segundo plano",
      notificationIcon: geo.AndroidResource(
        name: 'ic_launcher',
        defType: 'mipmap',
      ),
    ),
  );

  // 🔔 Sondeo de nuevas asignaciones también con la app minimizada: mientras el
  // servicio de ubicación corre, revisamos cada minuto y notificamos localmente.
  Timer.periodic(const Duration(seconds: 60), (_) async {
    if (userId > 0) {
      await NotificacionesService.instance.revisarNuevasAsignaciones(userId);
    }
  });

  positionSubscription = geo.Geolocator.getPositionStream(
    locationSettings: androidSettings,
  ).listen(
    (position) async {
      // No atribuir la ubicación a un usuario desconocido: antes se enviaba al
      // usuario 1 por defecto, corrompiendo los datos de seguimiento.
      if (userId <= 0) {
        debugPrint('⚠️ userId no disponible; se omite el envío de ubicación');
        return;
      }
      try {
        // Cabeceras mínimas para el isolate (ngrok skip header incluido)
        final headers = <String, String>{
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': '1',
          'Accept': 'application/json',
        };
        if (token != null && token.isNotEmpty) {
          headers['Authorization'] = 'Bearer $token';
        }

        final resp = await http
            .post(
              Uri.parse("$apiUrl/usuarios/actualizar_ubicacion/"),
              headers: headers,
              body: jsonEncode({
                'latitud': position.latitude,
                'longitud': position.longitude,
              }),
            )
            .timeout(const Duration(seconds: 10));

        debugPrint(
          "✅ Ubicación enviada (stream): (${position.latitude}, ${position.longitude}) status:${resp.statusCode}",
        );
      } on TimeoutException catch (e) {
        debugPrint("⚠️ Timeout enviando ubicación (stream): $e");
      } catch (e) {
        debugPrint("⚠️ Error enviando ubicación (stream): $e");
      }
    },
    onError: (e) {
      debugPrint("⚠️ Error en stream de ubicación: $e");
    },
  );

  debugPrint('🟢 background onStart (stream) inicializado');
}

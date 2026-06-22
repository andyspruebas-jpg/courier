import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'api_client.dart';

/// Notificaciones **locales** (sin Firebase): la propia app revisa por sondeo
/// si hay nuevos envíos asignados al mensajero y dispara una notificación del
/// sistema. Funciona tanto en primer plano (Timer en la UI) como en el isolate
/// del servicio en segundo plano.
class NotificacionesService {
  NotificacionesService._();
  static final NotificacionesService instance = NotificacionesService._();

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  static const String _canalId = 'asignaciones_channel';
  static const String _canalNombre = 'Asignaciones';
  static const String _claveVistos = 'notif_envios_vistos';

  bool _inicializado = false;

  /// Inicializa el plugin y el canal de Android. Idempotente.
  Future<void> init() async {
    if (_inicializado) return;
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const ios = DarwinInitializationSettings();
    await _plugin.initialize(
      const InitializationSettings(android: android, iOS: ios),
    );

    // Crear el canal (Android 8+). Idempotente: recrearlo no causa problemas.
    final androidImpl =
        _plugin
            .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin
            >();
    await androidImpl?.createNotificationChannel(
      const AndroidNotificationChannel(
        _canalId,
        _canalNombre,
        description: 'Avisos de nuevas entregas asignadas',
        importance: Importance.high,
      ),
    );
    await androidImpl?.requestNotificationsPermission();
    _inicializado = true;
  }

  Future<void> mostrar(int id, String titulo, String cuerpo) async {
    await init();
    await _plugin.show(
      id,
      titulo,
      cuerpo,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          _canalId,
          _canalNombre,
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      ),
    );
  }

  /// Consulta los envíos pendientes del mensajero y notifica los que no se
  /// habían visto antes. En la primera ejecución solo registra el estado actual
  /// (no notifica) para evitar avisar de envíos antiguos.
  ///
  /// Devuelve la cantidad de envíos nuevos detectados.
  Future<int> revisarNuevasAsignaciones(int mensajeroId) async {
    if (mensajeroId <= 0) return 0;
    try {
      final resp = await ApiClient.instance.get(
        '/envios/envios-pendientes-json/',
      );
      if (resp.statusCode != 200) return 0;

      final data = jsonDecode(resp.body);
      if (data is! List) return 0;

      final actuales = <String>{};
      final porId = <String, Map<String, dynamic>>{};
      for (final e in data) {
        if (e is Map && e['id'] != null) {
          final key = e['id'].toString();
          actuales.add(key);
          porId[key] = Map<String, dynamic>.from(e);
        }
      }

      final vistosRaw = await _storage.read(key: _claveVistos);

      // Primera ejecución: registrar sin notificar.
      if (vistosRaw == null) {
        await _storage.write(key: _claveVistos, value: actuales.join(','));
        return 0;
      }

      final vistos = vistosRaw.split(',').where((s) => s.isNotEmpty).toSet();
      final nuevos = actuales.difference(vistos);

      for (final id in nuevos) {
        final envio = porId[id];
        final dest = envio?['destinatario_nombre'] ?? 'destinatario';
        final dir = envio?['destino_direccion'] ?? '';
        await mostrar(
          int.tryParse(id) ?? id.hashCode,
          '📦 Nuevo envío asignado',
          'Para $dest${dir.toString().isNotEmpty ? ' · $dir' : ''}',
        );
      }

      // Persistir el estado actual (ids ya entregados desaparecen del set).
      await _storage.write(key: _claveVistos, value: actuales.join(','));
      return nuevos.length;
    } catch (e) {
      debugPrint('⚠️ Error revisando nuevas asignaciones: $e');
      return 0;
    }
  }
}

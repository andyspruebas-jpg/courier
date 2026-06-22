import 'dart:convert';
import 'dart:io';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'entrega_service.dart';

/// Cola de sincronización **offline** para confirmaciones de entrega.
///
/// Si el mensajero confirma una entrega sin conexión, se guarda localmente
/// (incluida la foto y la firma copiadas a un directorio persistente) y se
/// reenvía automáticamente al recuperar la conexión.
///
/// Nota: los pings GPS NO se encolan a propósito — una ubicación vieja no
/// aporta valor; solo interesa la confirmación de entrega.
class ColaSyncService {
  ColaSyncService._();
  static final ColaSyncService instance = ColaSyncService._();

  static const String _clave = 'cola_entregas';
  final EntregaService _entregaService = EntregaService();
  bool _sincronizando = false;

  Future<bool> hayConexion() async {
    final r = await Connectivity().checkConnectivity();
    return r.any((c) => c != ConnectivityResult.none);
  }

  /// Escucha cambios de conectividad: al recuperar conexión, sincroniza.
  /// Llamar una vez al arrancar la app.
  void iniciar() {
    Connectivity().onConnectivityChanged.listen((r) {
      if (r.any((c) => c != ConnectivityResult.none)) {
        sincronizar();
      }
    });
    sincronizar();
  }

  Future<int> pendientes() async => (await _leerCola()).length;

  Future<List<Map<String, dynamic>>> _leerCola() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_clave);
    if (raw == null) return [];
    try {
      final list = jsonDecode(raw) as List;
      return list.map((e) => Map<String, dynamic>.from(e)).toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> _guardarCola(List<Map<String, dynamic>> cola) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_clave, jsonEncode(cola));
  }

  /// Copia un archivo a un directorio persistente y devuelve la nueva ruta.
  Future<String?> _persistir(File? archivo, String nombre) async {
    if (archivo == null) return null;
    final dir = await getApplicationDocumentsDirectory();
    final colaDir = Directory('${dir.path}/cola_entregas');
    if (!await colaDir.exists()) await colaDir.create(recursive: true);
    final destino = File('${colaDir.path}/$nombre');
    await archivo.copy(destino.path);
    return destino.path;
  }

  /// Encola una entrega para enviarla cuando haya conexión.
  Future<void> encolarEntrega({
    required int envioId,
    required int mensajeroId,
    required String estado,
    String? observaciones,
    String? modalidadPago,
    double? monto,
    File? foto,
    File? firma,
    double? latitud,
    double? longitud,
  }) async {
    final stamp = DateTime.now().millisecondsSinceEpoch;
    final fotoPath = await _persistir(foto, 'foto_${envioId}_$stamp.jpg');
    final firmaPath = await _persistir(firma, 'firma_${envioId}_$stamp.png');
    final cola = await _leerCola();
    cola.add({
      'envioId': envioId,
      'mensajeroId': mensajeroId,
      'estado': estado,
      'observaciones': observaciones,
      'modalidadPago': modalidadPago,
      'monto': monto,
      'fotoPath': fotoPath,
      'firmaPath': firmaPath,
      'latitud': latitud,
      'longitud': longitud,
      'creadoEn': stamp,
    });
    await _guardarCola(cola);
  }

  /// Intenta reenviar todas las entregas en cola; quita las enviadas con éxito.
  /// Devuelve cuántas se sincronizaron.
  Future<int> sincronizar() async {
    if (_sincronizando) return 0;
    _sincronizando = true;
    int enviadas = 0;
    try {
      if (!await hayConexion()) return 0;
      final cola = await _leerCola();
      if (cola.isEmpty) return 0;

      final restantes = <Map<String, dynamic>>[];
      for (final item in cola) {
        final fotoPath = item['fotoPath'] as String?;
        final firmaPath = item['firmaPath'] as String?;
        final result = await _entregaService.registrarEntrega(
          envioId: item['envioId'] as int,
          mensajeroId: item['mensajeroId'] as int,
          estado: item['estado'] as String,
          observaciones: item['observaciones'] as String?,
          modalidadPago: item['modalidadPago'] as String?,
          monto: (item['monto'] as num?)?.toDouble(),
          foto: fotoPath != null ? File(fotoPath) : null,
          firma: firmaPath != null ? File(firmaPath) : null,
          latitud: (item['latitud'] as num?)?.toDouble(),
          longitud: (item['longitud'] as num?)?.toDouble(),
        );
        if (result.ok) {
          enviadas++;
          for (final p in [fotoPath, firmaPath]) {
            if (p == null) continue;
            try {
              final f = File(p);
              if (await f.exists()) await f.delete();
            } catch (_) {}
          }
        } else {
          restantes.add(item); // se reintentará en la próxima sincronización
        }
      }
      await _guardarCola(restantes);
    } catch (e) {
      debugPrint('⚠️ Error sincronizando cola de entregas: $e');
    } finally {
      _sincronizando = false;
    }
    return enviadas;
  }
}

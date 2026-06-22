import 'dart:io';
import 'package:flutter/foundation.dart';
import 'api_client.dart';

/// Tipos de incidencia válidos (coinciden con `Incidente.tipo` del backend).
class TipoIncidencia {
  static const retraso = 'Retraso';
  static const dano = 'Daño';
  static const perdida = 'Pérdida';
  static const otro = 'Otro';

  static const todos = [retraso, dano, perdida, otro];
}

class RegistroIncidenciaResult {
  final bool ok;
  final String? mensaje;
  const RegistroIncidenciaResult(this.ok, [this.mensaje]);
}

/// Servicio que registra una incidencia de un envío desde la app del mensajero.
/// POST multipart a `/envios/api/incidentes/registrar/<envioId>/`.
class IncidenciaService {
  Future<RegistroIncidenciaResult> registrarIncidencia({
    required int envioId,
    required String tipo,
    String? descripcion,
    File? foto,
    double? latitud,
    double? longitud,
  }) async {
    try {
      final fields = <String, String>{
        'tipo': tipo,
        if (descripcion != null && descripcion.trim().isNotEmpty)
          'descripcion': descripcion.trim(),
        if (latitud != null) 'latitud': latitud.toString(),
        if (longitud != null) 'longitud': longitud.toString(),
      };
      final files = <String, String>{
        if (foto != null) 'foto': foto.path,
      };

      final resp = await ApiClient.instance.postMultipart(
        '/envios/api/incidentes/registrar/$envioId/',
        fields: fields,
        files: files,
      );

      if (resp.statusCode == 200 || resp.statusCode == 201) {
        return const RegistroIncidenciaResult(true);
      }
      debugPrint('❌ registrarIncidencia ${resp.statusCode}: ${resp.body}');
      return RegistroIncidenciaResult(
          false, 'El servidor respondió ${resp.statusCode}.');
    } catch (e) {
      debugPrint('⚠️ Error registrando incidencia: $e');
      return const RegistroIncidenciaResult(
          false, 'No se pudo conectar con el servidor.');
    }
  }
}

import 'dart:convert';
import 'package:flutter/foundation.dart';
import '../models/ruta_detalle.dart';
import 'api_client.dart';

/// Servicio para consultar la ruta optimizada del mensajero.
class RutaService {
  /// Obtiene el detalle de la última ruta del mensajero, con las paradas ya
  /// ordenadas por proximidad y con ETA por parada (las calcula el backend).
  /// Devuelve `null` si el mensajero no tiene ruta asignada.
  Future<RutaDetalle?> getRutaDetalle(int mensajeroId) async {
    try {
      final resp =
          await ApiClient.instance.get('/rutas/api/ruta-detalle/$mensajeroId/');
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        if (data is Map<String, dynamic> && data['error'] == null) {
          return RutaDetalle.fromJson(data);
        }
        return null; // {"error": "No se encontró ruta"}
      }
      debugPrint('❌ getRutaDetalle ${resp.statusCode}: ${resp.body}');
      return null;
    } catch (e) {
      debugPrint('⚠️ Error obteniendo ruta-detalle: $e');
      return null;
    }
  }
}

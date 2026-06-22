import 'dart:io';
import 'package:flutter/foundation.dart';
import 'api_client.dart';

/// Resultado de registrar una entrega.
class RegistroEntregaResult {
  final bool ok;
  final String? mensaje;
  const RegistroEntregaResult(this.ok, [this.mensaje]);
}

/// Servicio que confirma la entrega de un envío desde la app del mensajero.
///
/// Envía un POST multipart a `/envios/api/entregas/registrar/<envioId>/`
/// con el estado, observaciones, modalidad de pago y los archivos de
/// evidencia (foto y/o firma). El backend crea la `Entrega`, actualiza el
/// estado del `Envio` y registra el evento en el historial.
class EntregaService {
  Future<RegistroEntregaResult> registrarEntrega({
    required int envioId,
    required int mensajeroId,
    required String estado, // 'Entregado' | 'Rechazado'
    String? observaciones,
    String? modalidadPago, // 'Origen' | 'Destino' | 'Pendiente'
    double? monto,
    File? foto,
    File? firma,
    Uint8List? firmaBytes,
    String? firmaFileName,
    double? latitud,
    double? longitud,
  }) async {
    try {
      final fields = <String, String>{
        'estado': estado,
        'mensajero_id': mensajeroId.toString(),
        if (modalidadPago != null) 'modalidad_pago': modalidadPago,
        if (monto != null) 'monto': monto.toString(),
        if (observaciones != null && observaciones.trim().isNotEmpty)
          'observaciones': observaciones.trim(),
        if (latitud != null) 'latitud': latitud.toString(),
        if (longitud != null) 'longitud': longitud.toString(),
      };
      final files = <String, String>{
        if (foto != null) 'foto': foto.path,
        if (firma != null) 'firma': firma.path,
      };

      final resp = await ApiClient.instance.postMultipart(
        '/envios/api/entregas/registrar/$envioId/',
        fields: fields,
        files: files,
        byteFiles: {if (firmaBytes != null) 'firma': firmaBytes},
        byteFileNames: {
          if (firmaBytes != null)
            'firma': firmaFileName ?? 'firma_envio_$envioId.png',
        },
      );

      if (resp.statusCode == 200 || resp.statusCode == 201) {
        return const RegistroEntregaResult(true);
      }
      debugPrint('❌ registrarEntrega ${resp.statusCode}: ${resp.body}');
      return RegistroEntregaResult(
        false,
        'El servidor respondió ${resp.statusCode}.',
      );
    } catch (e) {
      debugPrint('⚠️ Error registrando entrega: $e');
      return const RegistroEntregaResult(
        false,
        'No se pudo conectar con el servidor.',
      );
    }
  }
}

import 'json_utils.dart';
import 'envio.dart';

/// Una parada (envío) dentro de una ruta, tal como la devuelve
/// `/rutas/api/ruta-detalle/<mensajero_id>/` en el arreglo `envios`.
class EnvioParada {
  final int? id;
  final String? numeroSeguimiento;
  final String? tipo;
  final double? lat;
  final double? lng;
  final String? direccion;
  final String? destinatarioNombre;
  final String? destinatarioTelefono;
  final String? estado;
  final String? tipoPago;
  final double? montoPago;
  final int? orden; // posición de visita (1-based)
  final double? etaMin; // minutos acumulados estimados desde el inicio

  const EnvioParada({
    this.id,
    this.numeroSeguimiento,
    this.tipo,
    this.lat,
    this.lng,
    this.direccion,
    this.destinatarioNombre,
    this.destinatarioTelefono,
    this.estado,
    this.tipoPago,
    this.montoPago,
    this.orden,
    this.etaMin,
  });

  factory EnvioParada.fromJson(Map<String, dynamic> j) => EnvioParada(
        id: toIntOrNull(j['id']),
        numeroSeguimiento: toStringOrNull(j['numero_seguimiento']),
        tipo: toStringOrNull(j['tipo']),
        lat: toDoubleOrNull(j['lat']),
        lng: toDoubleOrNull(j['lng']),
        direccion: toStringOrNull(j['direccion']),
        destinatarioNombre: toStringOrNull(j['destinatario_nombre']),
        destinatarioTelefono: toStringOrNull(j['destinatario_telefono']),
        estado: toStringOrNull(j['estado']),
        tipoPago: toStringOrNull(j['tipo_pago']),
        montoPago: toDoubleOrNull(j['monto_pago']),
        orden: toIntOrNull(j['orden']),
        etaMin: toDoubleOrNull(j['eta_min']),
      );

  bool get tieneCoordenadas => lat != null && lng != null;

  /// Convierte la parada en un [Envio] mínimo para abrir la pantalla de
  /// confirmación de entrega.
  Envio toEnvio() => Envio(
        id: id,
        numeroSeguimiento: numeroSeguimiento,
        tipo: tipo,
        estado: estado,
        destinoDireccion: direccion,
        latitudDestino: lat,
        longitudDestino: lng,
        destinatarioNombre: destinatarioNombre,
        destinatarioTelefono: destinatarioTelefono,
        tipoPago: tipoPago,
        montoPago: montoPago,
      );
}

/// Detalle de ruta optimizada para un mensajero
/// (`/rutas/api/ruta-detalle/<mensajero_id>/`), incluye la comparación
/// Google vs. algoritmo y las polilíneas.
class RutaDetalle {
  final int? id;
  final String? fecha;
  final double? latitudInicio;
  final double? longitudInicio;
  final double? latitudFin;
  final double? longitudFin;
  final double? distanciaGoogle;
  final double? duracionGoogle;
  final double? distanciaAlgoritmo;
  final double? duracionAlgoritmo;
  final String? polylineGoogle;
  final String? polylineAlgoritmo;
  final List<EnvioParada> envios;

  const RutaDetalle({
    this.id,
    this.fecha,
    this.latitudInicio,
    this.longitudInicio,
    this.latitudFin,
    this.longitudFin,
    this.distanciaGoogle,
    this.duracionGoogle,
    this.distanciaAlgoritmo,
    this.duracionAlgoritmo,
    this.polylineGoogle,
    this.polylineAlgoritmo,
    this.envios = const [],
  });

  factory RutaDetalle.fromJson(Map<String, dynamic> j) {
    final lista = (j['envios'] as List?) ?? const [];
    return RutaDetalle(
      id: toIntOrNull(j['id']),
      fecha: toStringOrNull(j['fecha']),
      latitudInicio: toDoubleOrNull(j['latitud_inicio']),
      longitudInicio: toDoubleOrNull(j['longitud_inicio']),
      latitudFin: toDoubleOrNull(j['latitud_fin']),
      longitudFin: toDoubleOrNull(j['longitud_fin']),
      distanciaGoogle: toDoubleOrNull(j['distancia_google']),
      duracionGoogle: toDoubleOrNull(j['duracion_google']),
      distanciaAlgoritmo: toDoubleOrNull(j['distancia_algoritmo']),
      duracionAlgoritmo: toDoubleOrNull(j['duracion_algoritmo']),
      polylineGoogle: toStringOrNull(j['polyline_google']),
      polylineAlgoritmo: toStringOrNull(j['polyline_algoritmo']),
      envios: lista
          .whereType<Map>()
          .map((e) => EnvioParada.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }
}

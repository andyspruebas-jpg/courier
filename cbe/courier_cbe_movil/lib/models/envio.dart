import 'json_utils.dart';

/// Estados posibles de un [Envio] (coinciden exactamente con el backend Django,
/// `envios/models.py` → `Envio.estado`).
class EstadoEnvio {
  static const pendiente = 'Pendiente';
  static const enRuta = 'En Ruta';
  static const entregado = 'Entregado';
  static const rechazado = 'Rechazado';
  static const fallido = 'Fallido';
  static const reintentado = 'Reintentado';
  static const cancelado = 'Cancelado';
}

/// Modelo tipado de un envío.
///
/// `fromJson` tolera las dos formas que devuelve el backend:
///  - `/envios/envios-json/` (usa `creado_en`, `mensajero_id`, `remitente_id`)
///  - `/envios/envios-pendientes-json/` (usa `fecha_creado`, `mensajero` por nombre,
///    e incluye `remitente_nombre`/`remitente_telefono`).
class Envio {
  final int? id;
  final String? numeroSeguimiento;
  final String? tipo;
  final String? tipoServicio;
  final String? estado;
  final String? estadoPublico;

  final String? remitenteNombre;
  final String? remitenteTelefono;
  final int? remitenteId;
  final String? destinatarioNombre;
  final String? destinatarioTelefono;

  final String? origenDireccion;
  final String? destinoDireccion;
  final double? latitudOrigen;
  final double? longitudOrigen;
  final double? latitudDestino;
  final double? longitudDestino;

  final double? peso;
  final String? observaciones;
  final double? montoPago;
  final String? tipoPago; // 'Origen' | 'Destino'

  final int? rutaId;
  final int? mensajeroId;
  final String? mensajeroNombre;
  final String? creadoEn;

  const Envio({
    this.id,
    this.numeroSeguimiento,
    this.tipo,
    this.tipoServicio,
    this.estado,
    this.estadoPublico,
    this.remitenteNombre,
    this.remitenteTelefono,
    this.remitenteId,
    this.destinatarioNombre,
    this.destinatarioTelefono,
    this.origenDireccion,
    this.destinoDireccion,
    this.latitudOrigen,
    this.longitudOrigen,
    this.latitudDestino,
    this.longitudDestino,
    this.peso,
    this.observaciones,
    this.montoPago,
    this.tipoPago,
    this.rutaId,
    this.mensajeroId,
    this.mensajeroNombre,
    this.creadoEn,
  });

  factory Envio.fromJson(Map<String, dynamic> j) {
    return Envio(
      id: toIntOrNull(j['id']),
      numeroSeguimiento: toStringOrNull(j['numero_seguimiento']),
      tipo: toStringOrNull(j['tipo']),
      tipoServicio: toStringOrNull(j['tipo_servicio']),
      estado: toStringOrNull(j['estado']),
      estadoPublico: toStringOrNull(j['estado_publico']),
      remitenteNombre: toStringOrNull(j['remitente_nombre']),
      remitenteTelefono: toStringOrNull(j['remitente_telefono']),
      remitenteId: toIntOrNull(j['remitente_id']),
      destinatarioNombre: toStringOrNull(j['destinatario_nombre']),
      destinatarioTelefono: toStringOrNull(j['destinatario_telefono']),
      origenDireccion: toStringOrNull(j['origen_direccion']),
      destinoDireccion: toStringOrNull(j['destino_direccion']),
      latitudOrigen: toDoubleOrNull(j['latitud_origen']),
      longitudOrigen: toDoubleOrNull(j['longitud_origen']),
      latitudDestino: toDoubleOrNull(j['latitud_destino']),
      longitudDestino: toDoubleOrNull(j['longitud_destino']),
      peso: toDoubleOrNull(j['peso']),
      observaciones: toStringOrNull(j['observaciones']),
      montoPago: toDoubleOrNull(j['monto_pago']),
      tipoPago: toStringOrNull(j['tipo_pago']),
      rutaId: toIntOrNull(j['ruta_id']),
      mensajeroId: toIntOrNull(j['mensajero_id']),
      // En envios-json `mensajero` no viene; en pendientes llega como nombre.
      mensajeroNombre:
          toStringOrNull(j['mensajero']) ??
          toStringOrNull(j['mensajero__nombre']),
      // envios-json usa `creado_en`; pendientes usa `fecha_creado`.
      creadoEn:
          toStringOrNull(j['creado_en']) ?? toStringOrNull(j['fecha_creado']),
    );
  }

  bool get tieneCoordenadasDestino =>
      latitudDestino != null && longitudDestino != null;
}

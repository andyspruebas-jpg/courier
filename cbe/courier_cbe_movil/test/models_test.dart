import 'package:flutter_test/flutter_test.dart';
import 'package:courier_cbe_movil/models/json_utils.dart';
import 'package:courier_cbe_movil/models/envio.dart';
import 'package:courier_cbe_movil/models/ruta_detalle.dart';

void main() {
  group('json_utils', () {
    test('toDoubleOrNull acepta num, String y null', () {
      expect(toDoubleOrNull(3), 3.0);
      expect(toDoubleOrNull('3.5'), 3.5);
      expect(toDoubleOrNull('-16.5'), -16.5); // Decimal serializado como String
      expect(toDoubleOrNull(null), isNull);
      expect(toDoubleOrNull('abc'), isNull);
    });

    test('toIntOrNull acepta int, String y null', () {
      expect(toIntOrNull(5), 5);
      expect(toIntOrNull('7'), 7);
      expect(toIntOrNull(null), isNull);
      expect(toIntOrNull('x'), isNull);
    });

    test('toStringOrNull convierte vacío a null', () {
      expect(toStringOrNull('hola'), 'hola');
      expect(toStringOrNull(''), isNull);
      expect(toStringOrNull(null), isNull);
    });
  });

  group('Envio.fromJson', () {
    test('parsea la forma de envios-json (creado_en, mensajero_id)', () {
      final e = Envio.fromJson({
        'id': 12,
        'tipo': 'Envío',
        'estado': 'Pendiente',
        'destinatario_nombre': 'Ana',
        'destino_direccion': 'Calle 1',
        'latitud_destino': '-16.5',
        'longitud_destino': '-68.15',
        'monto_pago': 50.0,
        'tipo_pago': 'Destino',
        'mensajero_id': 3,
        'creado_en': '2026-06-06T10:00:00',
      });
      expect(e.id, 12);
      expect(e.estado, EstadoEnvio.pendiente);
      expect(e.destinatarioNombre, 'Ana');
      expect(e.latitudDestino, -16.5);
      expect(e.montoPago, 50.0);
      expect(e.tipoPago, 'Destino');
      expect(e.mensajeroId, 3);
      expect(e.creadoEn, '2026-06-06T10:00:00');
      expect(e.tieneCoordenadasDestino, isTrue);
    });

    test('parsea la forma de pendientes (fecha_creado, mensajero por nombre)', () {
      final e = Envio.fromJson({
        'id': 9,
        'tipo': 'Recojo',
        'mensajero': 'Carlos',
        'fecha_creado': '2026-06-01 09:00:00',
      });
      expect(e.id, 9);
      expect(e.mensajeroNombre, 'Carlos');
      expect(e.creadoEn, '2026-06-01 09:00:00');
      expect(e.tieneCoordenadasDestino, isFalse);
    });
  });

  group('EnvioParada', () {
    test('fromJson parsea orden, eta y datos de contacto', () {
      final p = EnvioParada.fromJson({
        'id': 1,
        'tipo': 'Envío',
        'lat': -16.5,
        'lng': -68.1,
        'direccion': 'Av. Siempre Viva',
        'destinatario_nombre': 'Beto',
        'destinatario_telefono': '777',
        'tipo_pago': 'Origen',
        'monto_pago': 20,
        'orden': 2,
        'eta_min': 7.9,
      });
      expect(p.orden, 2);
      expect(p.etaMin, 7.9);
      expect(p.destinatarioTelefono, '777');
      expect(p.tieneCoordenadas, isTrue);
    });

    test('toEnvio mapea los campos para la pantalla de entrega', () {
      final p = EnvioParada.fromJson({
        'id': 4,
        'direccion': 'Calle X',
        'destinatario_nombre': 'Lia',
        'tipo_pago': 'Destino',
        'monto_pago': 30,
      });
      final e = p.toEnvio();
      expect(e.id, 4);
      expect(e.destinoDireccion, 'Calle X');
      expect(e.destinatarioNombre, 'Lia');
      expect(e.tipoPago, 'Destino');
      expect(e.montoPago, 30);
    });
  });

  group('RutaDetalle.fromJson', () {
    test('parsea la cabecera y la lista de paradas', () {
      final r = RutaDetalle.fromJson({
        'id': 100,
        'fecha': '2026-06-06T08:00:00',
        'polyline_algoritmo': 'abc',
        'envios': [
          {'id': 1, 'lat': -16.5, 'lng': -68.1, 'orden': 1, 'eta_min': 3.1},
          {'id': 2, 'lat': -16.49, 'lng': -68.13, 'orden': 2, 'eta_min': 7.9},
        ],
      });
      expect(r.id, 100);
      expect(r.polylineAlgoritmo, 'abc');
      expect(r.envios.length, 2);
      expect(r.envios.first.orden, 1);
      expect(r.envios.last.etaMin, 7.9);
    });

    test('tolera ausencia de la lista de envíos', () {
      final r = RutaDetalle.fromJson({'id': 1});
      expect(r.envios, isEmpty);
    });
  });
}

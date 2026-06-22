import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:courier_cbe_movil/models/envio.dart';
import 'package:courier_cbe_movil/pages/detalle_envio_page.dart';

void main() {
  // DetalleEnvioPage es un StatelessWidget que solo renderiza datos del Envio,
  // sin depender de plugins nativos, así que es testeable de forma fiable.
  testWidgets('DetalleEnvioPage muestra los datos del envío', (
    WidgetTester tester,
  ) async {
    const envio = Envio(
      id: 42,
      estado: EstadoEnvio.pendiente,
      destinatarioNombre: 'Ana Pérez',
      destinoDireccion: 'Av. Siempre Viva 123',
      montoPago: 50,
      tipoPago: 'Destino',
    );

    FlutterSecureStorage.setMockInitialValues({'rol': 'Mensajero'});
    await tester.pumpWidget(
      const MaterialApp(home: DetalleEnvioPage(envio: envio)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Envío #42'), findsOneWidget);
    expect(find.text('Ana Pérez'), findsOneWidget);
    expect(find.text('Av. Siempre Viva 123'), findsWidgets);
    // El FAB de registrar entrega aparece porque el envío no está entregado.
    expect(find.text('Registrar entrega'), findsOneWidget);
  });

  testWidgets('DetalleEnvioPage oculta el FAB si ya está entregado', (
    WidgetTester tester,
  ) async {
    FlutterSecureStorage.setMockInitialValues({'rol': 'Mensajero'});
    const envio = Envio(id: 7, estado: EstadoEnvio.entregado);
    await tester.pumpWidget(
      const MaterialApp(home: DetalleEnvioPage(envio: envio)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Registrar entrega'), findsNothing);
  });
}

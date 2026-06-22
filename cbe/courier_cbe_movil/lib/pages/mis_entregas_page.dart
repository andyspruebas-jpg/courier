import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/ruta_detalle.dart';
import '../navigation/role_navigation.dart';
import '../services/ruta_service.dart';
import '../services/cola_sync_service.dart';
import '../theme/app_colors.dart';
import '../widgets/role_drawer.dart';
import 'guiar_mensajero.dart';
import 'registrar_entrega_page.dart';

/// Itinerario del mensajero: lista las paradas de su ruta en orden de visita,
/// con dirección, contacto, ETA estimada y método de pago, y permite navegar
/// a cada parada o registrar la entrega directamente.
class MisEntregasPage extends StatefulWidget {
  const MisEntregasPage({super.key});

  @override
  State<MisEntregasPage> createState() => _MisEntregasPageState();
}

class _MisEntregasPageState extends State<MisEntregasPage> {
  final _storage = const FlutterSecureStorage();
  final _service = RutaService();

  bool _loading = true;
  RutaDetalle? _ruta;
  int _mensajeroId = 0;
  int _pendientesSync = 0;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _loading = true);
    final id = await _storage.read(key: 'id');
    _mensajeroId = int.tryParse(id ?? '') ?? 0;
    final ruta =
        _mensajeroId > 0 ? await _service.getRutaDetalle(_mensajeroId) : null;
    final pendientes = await ColaSyncService.instance.pendientes();
    if (!mounted) return;
    setState(() {
      _ruta = ruta;
      _pendientesSync = pendientes;
      _loading = false;
    });
  }

  Future<void> _sincronizar() async {
    final enviadas = await ColaSyncService.instance.sincronizar();
    if (!mounted) return;
    _snack(
      enviadas > 0
          ? '✅ $enviadas entrega(s) sincronizada(s).'
          : 'No se pudo sincronizar (¿sigue sin conexión?).',
    );
    _cargar();
  }

  Future<void> _navegar(EnvioParada p) async {
    if (!p.tieneCoordenadas) {
      _snack('La parada no tiene coordenadas para navegar.');
      return;
    }
    final ruta = _ruta;
    if (ruta == null) {
      _snack('No hay ruta asignada para iniciar navegación.');
      return;
    }
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder:
            (_) => GuiarMensajeroPage(
              ruta: _rutaToMap(ruta),
              destinoEnvioId: p.id,
            ),
      ),
    );
  }

  Map<String, dynamic> _rutaToMap(RutaDetalle ruta) => {
    'id': ruta.id,
    'fecha': ruta.fecha,
    'latitud_inicio': ruta.latitudInicio,
    'longitud_inicio': ruta.longitudInicio,
    'latitud_fin': ruta.latitudFin,
    'longitud_fin': ruta.longitudFin,
    'distancia_algoritmo': ruta.distanciaAlgoritmo,
    'duracion_algoritmo': ruta.duracionAlgoritmo,
    'polyline_algoritmo': ruta.polylineAlgoritmo,
    'envios':
        ruta.envios
            .map(
              (p) => {
                'id': p.id,
                'numero_seguimiento': p.numeroSeguimiento,
                'tipo': p.tipo,
                'lat': p.lat,
                'lng': p.lng,
                'direccion': p.direccion,
                'destinatario_nombre': p.destinatarioNombre,
                'destinatario_telefono': p.destinatarioTelefono,
                'estado': p.estado,
                'tipo_pago': p.tipoPago,
                'monto_pago': p.montoPago,
                'orden': p.orden,
                'eta_min': p.etaMin,
              },
            )
            .toList(),
  };

  Future<void> _registrarEntrega(EnvioParada p) async {
    final ok = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => RegistrarEntregaPage(envio: p.toEnvio()),
      ),
    );
    // Tras registrar, recargamos para que la parada entregada desaparezca.
    if (ok == true) _cargar();
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    final paradas = _ruta?.envios ?? const [];
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: const Text('Mis entregas'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _cargar,
          ),
        ],
      ),
      drawer: const RoleDrawer(current: AppDestination.misEntregas),
      body:
          _loading
              ? const Center(child: CircularProgressIndicator())
              : Column(
                children: [
                  if (_pendientesSync > 0) _bannerPendientes(),
                  Expanded(
                    child:
                        paradas.isEmpty
                            ? _vacio()
                            : RefreshIndicator(
                              onRefresh: _cargar,
                              child: ListView.separated(
                                padding: const EdgeInsets.all(12),
                                itemCount: paradas.length,
                                separatorBuilder:
                                    (_, __) => const SizedBox(height: 8),
                                itemBuilder:
                                    (_, i) => _tarjetaParada(paradas[i]),
                              ),
                            ),
                  ),
                ],
              ),
    );
  }

  Widget _bannerPendientes() => Container(
    width: double.infinity,
    color: AppColors.warning.withValues(alpha: 0.15),
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
    child: Row(
      children: [
        const Icon(Icons.cloud_off, color: AppColors.warning, size: 20),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            '$_pendientesSync entrega(s) sin sincronizar',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
        TextButton(onPressed: _sincronizar, child: const Text('Sincronizar')),
      ],
    ),
  );

  Widget _vacio() => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.inbox_outlined, size: 64, color: Colors.grey),
          const SizedBox(height: 12),
          const Text(
            'No tienes entregas pendientes en tu ruta.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _cargar,
            icon: const Icon(Icons.refresh),
            label: const Text('Recargar'),
          ),
        ],
      ),
    ),
  );

  Widget _tarjetaParada(EnvioParada p) {
    final esRecojo = p.tipo == 'Recojo';
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: AppColors.primary,
                  child: Text(
                    '${p.orden ?? '?'}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        p.destinatarioNombre ?? 'Sin destinatario',
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                        ),
                      ),
                      if (p.direccion != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            p.direccion!,
                            style: const TextStyle(color: Colors.grey),
                          ),
                        ),
                    ],
                  ),
                ),
                Chip(
                  visualDensity: VisualDensity.compact,
                  label: Text(esRecojo ? 'Recojo' : 'Envío'),
                  backgroundColor: (esRecojo
                          ? AppColors.info
                          : AppColors.primary)
                      .withValues(alpha: 0.15),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 16,
              runSpacing: 4,
              children: [
                if (p.etaMin != null)
                  _meta(Icons.schedule, '≈ ${p.etaMin!.round()} min'),
                if (p.destinatarioTelefono != null)
                  _meta(Icons.phone, p.destinatarioTelefono!),
                if (p.tipoPago != null || p.montoPago != null)
                  _meta(
                    Icons.payments,
                    '${p.tipoPago ?? 'Pago'}'
                    '${p.montoPago != null ? ' · Bs. ${p.montoPago}' : ''}',
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _navegar(p),
                    icon: const Icon(Icons.navigation_outlined, size: 18),
                    label: const Text('Navegar'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: () => _registrarEntrega(p),
                    icon: const Icon(Icons.assignment_turned_in, size: 18),
                    label: const Text('Entregar'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _meta(IconData icon, String text) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 16, color: Colors.grey),
      const SizedBox(width: 4),
      Text(text, style: const TextStyle(fontSize: 13)),
    ],
  );
}

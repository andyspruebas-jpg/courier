import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../models/envio.dart';
import '../navigation/role_navigation.dart';
import '../theme/app_colors.dart';
import 'registrar_entrega_page.dart';
import 'registrar_incidencia_page.dart';

class DetalleEnvioPage extends StatefulWidget {
  final Envio envio;

  const DetalleEnvioPage({super.key, required this.envio});

  @override
  State<DetalleEnvioPage> createState() => _DetalleEnvioPageState();
}

class _DetalleEnvioPageState extends State<DetalleEnvioPage> {
  bool _isMensajero = false;

  @override
  void initState() {
    super.initState();
    _loadRol();
  }

  Future<void> _loadRol() async {
    const storage = FlutterSecureStorage();
    final rol = await storage.read(key: 'rol');
    if (!mounted) return;
    setState(() => _isMensajero = RoleNames.isMensajero(rol));
  }

  @override
  Widget build(BuildContext context) {
    final envio = widget.envio;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: Text('Envío #${envio.id ?? ''}'),
        actions:
            _isMensajero
                ? [
                  IconButton(
                    tooltip: 'Reportar incidencia',
                    icon: const Icon(Icons.report_problem_outlined),
                    onPressed:
                        () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder:
                                (_) => RegistrarIncidenciaPage(envio: envio),
                          ),
                        ),
                  ),
                ]
                : null,
      ),
      floatingActionButton:
          _isMensajero && envio.estado != EstadoEnvio.entregado
              ? FloatingActionButton.extended(
                onPressed: () async {
                  final ok = await Navigator.push<bool>(
                    context,
                    MaterialPageRoute(
                      builder: (_) => RegistrarEntregaPage(envio: envio),
                    ),
                  );
                  // Si se registró la entrega, volvemos a la lista para refrescar.
                  if (ok == true && context.mounted) Navigator.pop(context);
                },
                backgroundColor: AppColors.primary,
                icon: const Icon(Icons.assignment_turned_in),
                label: const Text('Registrar entrega'),
              )
              : null,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Estado del envío
            _buildStatusCard(),
            const SizedBox(height: 16),

            // Información del destinatario
            _buildSection(
              title: 'Destinatario',
              children: [
                _buildInfoRow('Nombre', envio.destinatarioNombre),
                _buildInfoRow('Teléfono', envio.destinatarioTelefono),
                _buildInfoRow('Dirección', envio.destinoDireccion),
              ],
            ),
            const SizedBox(height: 16),

            // Información del remitente
            _buildSection(
              title: 'Remitente',
              children: [
                _buildInfoRow(
                  'Remitente',
                  envio.remitenteNombre ??
                      (envio.remitenteId != null
                          ? 'ID ${envio.remitenteId}'
                          : null),
                ),
                _buildInfoRow('Teléfono', envio.remitenteTelefono),
              ],
            ),
            const SizedBox(height: 16),

            // Detalles del envío
            _buildSection(
              title: 'Detalles del envío',
              children: [
                _buildInfoRow('Tipo', envio.tipo),
                _buildInfoRow('Peso', '${envio.peso ?? 0} kg'),
                _buildInfoRow('Tipo de Servicio', envio.tipoServicio),
                _buildInfoRow('Estado', envio.estado),
                _buildInfoRow(
                  'Observaciones',
                  _observacionVisible(envio.observaciones),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Información de pago
            _buildSection(
              title: 'Información de pago',
              children: [
                _buildInfoRow('Monto', 'Bs. ${envio.montoPago ?? 0}'),
                _buildInfoRow('Tipo de Pago', envio.tipoPago),
              ],
            ),
            const SizedBox(height: 16),

            // Direcciones
            _buildSection(
              title: 'Ubicaciones',
              children: [
                if (_tieneMapa(envio)) ...[
                  _buildMapaUbicaciones(envio),
                  const SizedBox(height: 14),
                ],
                _buildInfoRow('Origen', envio.origenDireccion),
                const Divider(),
                _buildInfoRow('Destino', envio.destinoDireccion),
              ],
            ),
            const SizedBox(height: 16),

            // Información adicional
            _buildSection(
              title: 'Información adicional',
              children: [
                _buildInfoRow(
                  'Ruta ID',
                  envio.rutaId?.toString() ?? 'Sin asignar',
                ),
                _buildInfoRow(
                  'Mensajero',
                  envio.mensajeroNombre ??
                      envio.mensajeroId?.toString() ??
                      'Sin asignar',
                ),
                _buildInfoRow(
                  'Fecha de Creación',
                  envio.creadoEn?.split('T').first ?? 'N/A',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  bool _tieneMapa(Envio envio) =>
      (envio.latitudOrigen != null && envio.longitudOrigen != null) ||
      (envio.latitudDestino != null && envio.longitudDestino != null);

  String _observacionVisible(String? value) {
    final text = (value ?? '').trim();
    if (text.isEmpty) return 'Sin observaciones';
    final sinPrefijo = text.contains('|') ? text.split('|').last.trim() : text;
    return sinPrefijo
        .replaceAll(RegExp(r'[dD][eE][mM][oO][_ -]?'), '')
        .replaceAll(RegExp(r'operacion:[^|:]*:?\s*', caseSensitive: false), '')
        .trim();
  }

  Widget _buildMapaUbicaciones(Envio envio) {
    final markers = <Marker>{};
    LatLng? target;
    if (envio.latitudOrigen != null && envio.longitudOrigen != null) {
      target = LatLng(envio.latitudOrigen!, envio.longitudOrigen!);
      markers.add(
        Marker(
          markerId: const MarkerId('origen'),
          position: target,
          icon: BitmapDescriptor.defaultMarkerWithHue(
            BitmapDescriptor.hueAzure,
          ),
          infoWindow: InfoWindow(
            title: 'Origen',
            snippet: envio.origenDireccion ?? '',
          ),
        ),
      );
    }
    if (envio.latitudDestino != null && envio.longitudDestino != null) {
      target ??= LatLng(envio.latitudDestino!, envio.longitudDestino!);
      markers.add(
        Marker(
          markerId: const MarkerId('destino'),
          position: LatLng(envio.latitudDestino!, envio.longitudDestino!),
          icon: BitmapDescriptor.defaultMarkerWithHue(
            BitmapDescriptor.hueGreen,
          ),
          infoWindow: InfoWindow(
            title: 'Destino',
            snippet: envio.destinoDireccion ?? '',
          ),
        ),
      );
    }
    final polylines = <Polyline>{};
    if (envio.latitudOrigen != null &&
        envio.longitudOrigen != null &&
        envio.latitudDestino != null &&
        envio.longitudDestino != null) {
      polylines.add(
        Polyline(
          polylineId: const PolylineId('envio'),
          color: AppColors.primary,
          width: 5,
          points: [
            LatLng(envio.latitudOrigen!, envio.longitudOrigen!),
            LatLng(envio.latitudDestino!, envio.longitudDestino!),
          ],
        ),
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: SizedBox(
        height: 220,
        child: GoogleMap(
          initialCameraPosition: CameraPosition(
            target: target ?? const LatLng(-16.5, -68.15),
            zoom: 13,
          ),
          markers: markers,
          polylines: polylines,
          zoomControlsEnabled: false,
          myLocationButtonEnabled: false,
          mapToolbarEnabled: false,
        ),
      ),
    );
  }

  Widget _buildStatusCard() {
    final estado = widget.envio.estado ?? 'N/A';
    Color statusColor;
    IconData statusIcon;

    switch (estado.toLowerCase()) {
      case 'pendiente':
        statusColor = AppColors.warning;
        statusIcon = Icons.pending_actions;
        break;
      case 'en ruta':
        statusColor = AppColors.info;
        statusIcon = Icons.local_shipping;
        break;
      case 'entregado':
        statusColor = AppColors.success;
        statusIcon = Icons.check_circle;
        break;
      case 'rechazado':
      case 'cancelado':
        statusColor = AppColors.error;
        statusIcon = Icons.cancel;
        break;
      default:
        statusColor = Colors.grey;
        statusIcon = Icons.help_outline;
    }

    return Card(
      elevation: 4,
      color: statusColor.withValues(alpha: 0.1),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(statusIcon, size: 48, color: statusColor),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Estado del Envío',
                    style: TextStyle(fontSize: 14, color: Colors.grey),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    estado.toUpperCase(),
                    style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      color: statusColor,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSection({
    required String title,
    required List<Widget> children,
  }) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: AppColors.primary,
              ),
            ),
            const SizedBox(height: 12),
            ...children,
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String? value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                color: Colors.grey,
              ),
            ),
          ),
          Expanded(
            child: Text(value ?? 'N/A', style: const TextStyle(fontSize: 15)),
          ),
        ],
      ),
    );
  }
}

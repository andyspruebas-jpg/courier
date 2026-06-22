import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/envio.dart';
import '../navigation/role_navigation.dart';
import '../api/api.dart';
import '../services/api_client.dart';
import '../theme/app_colors.dart';
import '../widgets/role_drawer.dart';

class SeguimientoPage extends StatefulWidget {
  const SeguimientoPage({super.key});

  @override
  State<SeguimientoPage> createState() => _SeguimientoPageState();
}

class _SeguimientoPageState extends State<SeguimientoPage> {
  final _numeroCtrl = TextEditingController();
  bool _loading = false;
  bool _loadingEnvios = true;
  List<Envio> _envios = [];
  Map<String, dynamic>? _tracking;
  Timer? _trackingTimer;
  String? _trackingNumero;

  @override
  void initState() {
    super.initState();
    _loadEnvios();
  }

  @override
  void dispose() {
    _trackingTimer?.cancel();
    _numeroCtrl.dispose();
    super.dispose();
  }

  int _pollSeconds(Map<String, dynamic>? data) {
    final value = data?['poll_interval_seconds'];
    if (value is int && value > 0) return value;
    if (value is String) return int.tryParse(value) ?? 10;
    return 10;
  }

  void _programarPolling(Map<String, dynamic> data) {
    _trackingTimer?.cancel();
    _trackingTimer = Timer.periodic(
      Duration(seconds: _pollSeconds(data)),
      (_) => _refrescarTracking(),
    );
  }

  Future<void> _refrescarTracking() async {
    final numero = _trackingNumero;
    if (numero == null || numero.isEmpty) return;
    try {
      final response = await ApiClient.instance.get(
        '/envios/api/seguimiento/${Uri.encodeComponent(numero)}/',
      );
      if (!mounted || response.statusCode != 200) return;
      final data = Map<String, dynamic>.from(jsonDecode(response.body) as Map);
      setState(() => _tracking = data);
    } catch (e) {
      debugPrint('Error refrescando seguimiento: $e');
    }
  }

  Future<void> _loadEnvios() async {
    setState(() => _loadingEnvios = true);
    try {
      final response = await ApiClient.instance.get('/envios/envios-json/');
      if (response.statusCode == 200) {
        final parsed = jsonDecode(response.body);
        final envios =
            parsed is List
                ? parsed
                    .map(
                      (item) => Envio.fromJson(
                        Map<String, dynamic>.from(item as Map),
                      ),
                    )
                    .toList()
                : <Envio>[];
        if (!mounted) return;
        setState(() => _envios = envios);
      }
    } catch (e) {
      debugPrint('Error cargando guías del cliente: $e');
    } finally {
      if (mounted) setState(() => _loadingEnvios = false);
    }
  }

  Future<void> _buscar([String? selectedNumero]) async {
    final numero = (selectedNumero ?? _numeroCtrl.text).trim();
    if (numero.isEmpty) return;
    _numeroCtrl.text = numero;
    _trackingTimer?.cancel();
    setState(() => _loading = true);
    try {
      final response = await ApiClient.instance.get(
        '/envios/api/seguimiento/${Uri.encodeComponent(numero)}/',
      );
      if (!mounted) return;
      if (response.statusCode == 200) {
        final data = Map<String, dynamic>.from(
          jsonDecode(response.body) as Map,
        );
        setState(() {
          _tracking = data;
          _trackingNumero = numero;
        });
        _programarPolling(data);
      } else {
        setState(() {
          _tracking = null;
          _trackingNumero = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('No se encontró el envío.'),
            backgroundColor: AppColors.error,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error de conexión: $e'),
          backgroundColor: AppColors.error,
        ),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: const Text('Seguimiento'),
      ),
      drawer: const RoleDrawer(current: AppDestination.seguimiento),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _numeroCtrl,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _buscar(),
            decoration: InputDecoration(
              labelText: 'Número de seguimiento',
              prefixIcon: const Icon(Icons.manage_search),
              suffixIcon: IconButton(
                tooltip: 'Buscar',
                icon:
                    _loading
                        ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                        : const Icon(Icons.search),
                onPressed: _loading ? null : _buscar,
              ),
            ),
          ),
          const SizedBox(height: 18),
          _MisGuiasSection(
            loading: _loadingEnvios,
            envios: _envios,
            selectedNumero: _tracking?['numero_seguimiento']?.toString(),
            onSelected: _buscar,
            onRefresh: _loadEnvios,
          ),
          const SizedBox(height: 18),
          if (_tracking == null)
            const _EmptyState()
          else
            _TrackingResult(data: _tracking!),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark,
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Column(
        children: [
          Icon(Icons.search_outlined, size: 56, color: AppColors.primary),
          SizedBox(height: 12),
          Text(
            'Ingresa un número de seguimiento para consultar el estado del envío.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary),
          ),
        ],
      ),
    );
  }
}

class _MisGuiasSection extends StatelessWidget {
  final bool loading;
  final List<Envio> envios;
  final String? selectedNumero;
  final ValueChanged<String> onSelected;
  final Future<void> Function() onRefresh;

  const _MisGuiasSection({
    required this.loading,
    required this.envios,
    required this.selectedNumero,
    required this.onSelected,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.inventory_2_outlined,
                  color: AppColors.primary,
                ),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'Mis envíos y recojos',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  tooltip: 'Actualizar',
                  icon: const Icon(Icons.refresh),
                  onPressed: loading ? null : onRefresh,
                ),
              ],
            ),
            const SizedBox(height: 10),
            if (loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Center(
                  child: CircularProgressIndicator(color: AppColors.primary),
                ),
              )
            else if (envios.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('Todavía no tienes envíos registrados.'),
              )
            else
              for (final envio in envios)
                _GuiaTile(
                  envio: envio,
                  selected: envio.numeroSeguimiento == selectedNumero,
                  onTap: () {
                    final numero = envio.numeroSeguimiento;
                    if (numero != null && numero.isNotEmpty) onSelected(numero);
                  },
                ),
          ],
        ),
      ),
    );
  }
}

class _GuiaTile extends StatelessWidget {
  final Envio envio;
  final bool selected;
  final VoidCallback onTap;

  const _GuiaTile({
    required this.envio,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final estado = envio.estadoPublico ?? _estadoPublico(envio.estado);
    final color = _estadoColor(estado);

    return Container(
      margin: const EdgeInsets.only(top: 8),
      decoration: BoxDecoration(
        color:
            selected
                ? AppColors.primary.withValues(alpha: 0.18)
                : AppColors.backgroundDark.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color:
              selected
                  ? AppColors.primary
                  : AppColors.primary.withValues(alpha: 0.18),
        ),
      ),
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.18),
          child: Icon(
            envio.tipo == 'Recojo'
                ? Icons.assignment_return_outlined
                : Icons.local_shipping_outlined,
            color: color,
          ),
        ),
        title: Text(
          envio.numeroSeguimiento ?? 'Sin número',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        subtitle: Text(
          '${envio.tipo ?? 'Envío'} • ${envio.destinatarioNombre ?? 'Sin destinatario'}\n'
          '${envio.destinoDireccion ?? 'Sin destino'}',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              estado,
              style: TextStyle(color: color, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            const Icon(Icons.chevron_right, size: 18),
          ],
        ),
      ),
    );
  }
}

class _TrackingResult extends StatelessWidget {
  final Map<String, dynamic> data;

  const _TrackingResult({required this.data});

  @override
  Widget build(BuildContext context) {
    final estado =
        data['estado_publico']?.toString() ??
        _estadoPublico(data['estado']?.toString());
    final descripcion = data['estado_descripcion']?.toString();
    final timeline = data['timeline'];
    final mensajero = data['mensajero'];
    final pago = data['pago'];
    final etapas = data['etapas'];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatusCard(
          estado: estado,
          description: descripcion,
          numero: data['numero_seguimiento']?.toString() ?? '',
        ),
        if (etapas is List && etapas.isNotEmpty) ...[
          const SizedBox(height: 14),
          _StepsCard(etapas: etapas),
        ],
        const SizedBox(height: 14),
        _InfoCard(
          title: 'Datos del envío',
          icon: Icons.inventory_2_outlined,
          rows: [
            ('Destinatario', data['destinatario_nombre']),
            ('Origen', data['origen_direccion']),
            ('Destino', data['destino_direccion']),
            ('Servicio', data['tipo_servicio']),
            ('Pago', data['tipo_pago']),
          ],
        ),
        if (mensajero is Map) ...[
          const SizedBox(height: 14),
          _MensajeroCard(mensajero: Map<String, dynamic>.from(mensajero)),
        ],
        if (pago is Map) ...[
          const SizedBox(height: 14),
          _InfoCard(
            title: 'Pago',
            icon: Icons.payments_outlined,
            rows: [
              ('Estado', pago['estado']),
              ('Monto', pago['monto'] == null ? null : 'Bs. ${pago['monto']}'),
              ('Método', pago['metodo']),
              ('Fecha', pago['fecha_pago']),
            ],
          ),
        ],
        const SizedBox(height: 18),
        const Text(
          'Historial',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        if (timeline is List && timeline.isNotEmpty)
          for (final item in timeline.cast<dynamic>())
            _TimelineTile(item: Map<String, dynamic>.from(item as Map))
        else
          const Text('Sin historial disponible.'),
      ],
    );
  }
}

class _StatusCard extends StatelessWidget {
  final String estado;
  final String? description;
  final String numero;

  const _StatusCard({
    required this.estado,
    required this.numero,
    this.description,
  });

  @override
  Widget build(BuildContext context) {
    final color = _estadoColor(estado);

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Icon(Icons.local_shipping_outlined, color: color, size: 36),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  numero,
                  style: const TextStyle(color: AppColors.textTertiary),
                ),
                const SizedBox(height: 4),
                Text(
                  estado,
                  style: TextStyle(
                    color: color,
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                if (description != null && description!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    description!,
                    style: const TextStyle(color: AppColors.textSecondary),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StepsCard extends StatelessWidget {
  final List<dynamic> etapas;

  const _StepsCard({required this.etapas});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Estado del servicio',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            for (final raw in etapas)
              _StepRow(etapa: Map<String, dynamic>.from(raw as Map)),
          ],
        ),
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  final Map<String, dynamic> etapa;

  const _StepRow({required this.etapa});

  @override
  Widget build(BuildContext context) {
    final completed = etapa['completed'] == true;
    final current = etapa['current'] == true;
    final color =
        completed || current ? AppColors.primary : AppColors.textTertiary;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            completed ? Icons.check_circle : Icons.radio_button_unchecked,
            color: color,
            size: 22,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  etapa['label']?.toString() ?? '',
                  style: TextStyle(
                    color: color,
                    fontWeight: current ? FontWeight.bold : FontWeight.w600,
                  ),
                ),
                Text(
                  etapa['description']?.toString() ?? '',
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MensajeroCard extends StatelessWidget {
  final Map<String, dynamic> mensajero;

  const _MensajeroCard({required this.mensajero});

  @override
  Widget build(BuildContext context) {
    final visible = mensajero['ubicacion_visible'] == true;
    final distancia = mensajero['distancia_destino_m'];
    final latitud = mensajero['latitud'];
    final longitud = mensajero['longitud'];
    final fotoUrl = _absoluteMediaUrl(mensajero['foto_url']?.toString());

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: AppColors.primary.withValues(alpha: 0.18),
                  backgroundImage:
                      fotoUrl != null && fotoUrl.isNotEmpty
                          ? NetworkImage(fotoUrl)
                          : null,
                  child:
                      fotoUrl == null || fotoUrl.isEmpty
                          ? const Icon(
                            Icons.delivery_dining,
                            color: AppColors.primary,
                          )
                          : null,
                ),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'Mensajero asignado',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 17),
                  ),
                ),
                Icon(
                  visible ? Icons.location_on : Icons.lock_outline,
                  color: visible ? AppColors.success : AppColors.textTertiary,
                ),
              ],
            ),
            const SizedBox(height: 12),
            _miniRow('Nombre', mensajero['nombre']),
            _miniRow('Teléfono', mensajero['telefono']),
            _miniRow('Vehículo', mensajero['vehiculo']),
            if (visible && latitud != null && longitud != null)
              _miniRow('Ubicación', '$latitud, $longitud'),
            const Divider(height: 22),
            Text(
              visible
                  ? 'Ubicación habilitada: el mensajero está cerca del destino'
                      '${distancia == null ? '' : ' (≈ $distancia m)'}.'
                  : mensajero['mensaje_ubicacion']?.toString() ??
                      'La ubicación exacta se mostrará cuando esté cerca.',
              style: TextStyle(
                color: visible ? AppColors.success : AppColors.textSecondary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _miniRow(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 82,
            child: Text(
              label,
              style: const TextStyle(color: AppColors.textTertiary),
            ),
          ),
          Expanded(
            child: Text(
              value?.toString().isNotEmpty == true
                  ? value.toString()
                  : 'Sin dato',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

String? _absoluteMediaUrl(String? url) {
  if (url == null || url.isEmpty) return null;
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (url.startsWith('/')) return '$apiUrl$url';
  return '$apiUrl/$url';
}

class _InfoCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<(String, dynamic)> rows;

  const _InfoCard({
    required this.title,
    required this.icon,
    required this.rows,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: AppColors.primary),
                const SizedBox(width: 10),
                Text(
                  title,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 17,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (final row in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 92,
                      child: Text(
                        row.$1,
                        style: const TextStyle(color: AppColors.textTertiary),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        row.$2?.toString().isNotEmpty == true
                            ? row.$2.toString()
                            : 'Sin dato',
                        style: const TextStyle(fontWeight: FontWeight.w600),
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
}

class _TimelineTile extends StatelessWidget {
  final Map<String, dynamic> item;

  const _TimelineTile({required this.item});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const CircleAvatar(
        backgroundColor: AppColors.surfaceDark,
        child: Icon(Icons.history, color: AppColors.primary),
      ),
      title: Text(item['tipo']?.toString() ?? 'Actualización'),
      subtitle: Text(
        [
          item['fecha']?.toString(),
          item['usuario']?.toString(),
          item['observaciones']?.toString(),
        ].where((value) => value != null && value.isNotEmpty).join('\n'),
      ),
    );
  }
}

String _estadoPublico(String? estado) {
  switch ((estado ?? '').toLowerCase()) {
    case 'pendiente':
      return 'En recepción';
    case 'en ruta':
    case 'reintentado':
      return 'En tránsito';
    case 'entregado':
      return 'Entregado';
    case 'rechazado':
    case 'fallido':
    case 'cancelado':
      return estado ?? 'Revisión';
    default:
      return 'Registrado';
  }
}

Color _estadoColor(String estado) {
  switch (estado.toLowerCase()) {
    case 'entregado':
      return AppColors.success;
    case 'en tránsito':
    case 'en ruta':
      return AppColors.info;
    case 'en recepción':
    case 'registrado':
    case 'pendiente':
      return AppColors.warning;
    case 'rechazado':
    case 'fallido':
    case 'cancelado':
      return AppColors.error;
    default:
      return AppColors.textTertiary;
  }
}

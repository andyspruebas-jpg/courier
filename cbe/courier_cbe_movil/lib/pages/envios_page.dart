import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/envio.dart';
import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../theme/app_colors.dart';
import '../widgets/role_drawer.dart';
import 'detalle_envio_page.dart';

class EnviosPage extends StatefulWidget {
  final String initialEstado;

  const EnviosPage({super.key, this.initialEstado = 'Todos'});

  @override
  State<EnviosPage> createState() => _EnviosPageState();
}

class _EnviosPageState extends State<EnviosPage> {
  bool _loading = true;
  List<Envio> _envios = [];
  List<Map<String, dynamic>> _mensajeros = [];
  String? _selectedMensajeroId = 'todos';
  String? _userRol;
  late String _estadoFiltro;

  bool get _isAdmin => RoleNames.isAdmin(_userRol);
  bool get _isCliente => RoleNames.isCliente(_userRol);

  @override
  void initState() {
    super.initState();
    _estadoFiltro = widget.initialEstado;
    _init();
  }

  Future<void> _init() async {
    const storage = FlutterSecureStorage();
    _userRol = await storage.read(key: 'rol');
    if (_isAdmin) await _loadMensajeros();
    await _loadEnvios();
  }

  Future<void> _loadMensajeros() async {
    try {
      final res = await ApiClient.instance.get('/usuarios/mensajeros-json/');
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        if (data is List && mounted) {
          setState(() {
            _mensajeros =
                data
                    .map((item) => Map<String, dynamic>.from(item as Map))
                    .toList();
          });
        }
      }
    } catch (e) {
      debugPrint('Error al cargar mensajeros: $e');
    }
  }

  Future<void> _loadEnvios() async {
    setState(() => _loading = true);

    final query = <String, String>{};
    if (_isAdmin &&
        _selectedMensajeroId != null &&
        _selectedMensajeroId != 'todos') {
      query['usuario_id'] = _selectedMensajeroId!;
      query['rol'] = 'Mensajero';
    }

    try {
      final res = await ApiClient.instance.get(
        '/envios/envios-json/',
        query: query.isEmpty ? null : query,
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        final envios =
            data is List
                ? data
                    .map(
                      (item) => Envio.fromJson(
                        Map<String, dynamic>.from(item as Map),
                      ),
                    )
                    .toList()
                : <Envio>[];
        if (!mounted) return;
        setState(() => _envios = envios);
      } else {
        debugPrint('Error al cargar envíos: ${res.statusCode} ${res.body}');
      }
    } catch (e) {
      debugPrint('Error al obtener envíos: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<Envio> get _enviosFiltrados {
    if (_estadoFiltro == 'Todos') return _envios;
    return _envios
        .where(
          (envio) => envio.estado?.toLowerCase() == _estadoFiltro.toLowerCase(),
        )
        .toList();
  }

  Widget _buildMensajeroFilter() {
    if (!_isAdmin || _mensajeros.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: DropdownButtonFormField<String>(
        initialValue: _selectedMensajeroId,
        decoration: const InputDecoration(
          labelText: 'Filtrar por mensajero',
          prefixIcon: Icon(Icons.filter_list),
        ),
        items: [
          const DropdownMenuItem(
            value: 'todos',
            child: Text('Todos los mensajeros'),
          ),
          ..._mensajeros.map(
            (m) => DropdownMenuItem(
              value: m['id'].toString(),
              child: Text(m['nombre']?.toString() ?? 'Sin nombre'),
            ),
          ),
        ],
        onChanged: (value) {
          setState(() => _selectedMensajeroId = value);
          _loadEnvios();
        },
      ),
    );
  }

  Widget _buildEstadoFilter() {
    const estados = [
      ('Todos', 'Todos'),
      ('Pendiente', 'En recepción'),
      ('En Ruta', 'En tránsito'),
      ('Entregado', 'Entregado'),
      ('Rechazado', 'Rechazado'),
      ('Fallido', 'Fallido'),
    ];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Row(
        children: [
          for (final estado in estados)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: FilterChip(
                selected: _estadoFiltro == estado.$1,
                label: Text(estado.$2),
                onSelected: (_) => setState(() => _estadoFiltro = estado.$1),
              ),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final title = _isCliente ? 'Mis envíos' : 'Gestión de envíos';

    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: Text(title),
        actions: [
          IconButton(
            tooltip: 'Actualizar',
            icon: const Icon(Icons.refresh),
            onPressed: _loadEnvios,
          ),
        ],
      ),
      drawer: const RoleDrawer(current: AppDestination.envios),
      body: Column(
        children: [
          _buildMensajeroFilter(),
          _buildEstadoFilter(),
          Expanded(
            child:
                _loading
                    ? const Center(
                      child: CircularProgressIndicator(
                        color: AppColors.primary,
                      ),
                    )
                    : _buildEnviosList(),
          ),
        ],
      ),
      floatingActionButton:
          _isCliente
              ? FloatingActionButton.extended(
                onPressed:
                    () =>
                        Navigator.pushNamed(context, AppRoutes.solicitarEnvio),
                backgroundColor: AppColors.primary,
                icon: const Icon(Icons.add),
                label: const Text('Solicitar'),
              )
              : null,
    );
  }

  Widget _buildEnviosList() {
    final envios = _enviosFiltrados;
    if (envios.isEmpty) {
      return const Center(child: Text('No hay envíos para mostrar.'));
    }

    return RefreshIndicator(
      onRefresh: _loadEnvios,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: envios.length,
        itemBuilder: (context, i) {
          final envio = envios[i];
          return Card(
            margin: const EdgeInsets.symmetric(vertical: 6),
            child: ListTile(
              leading: const Icon(
                Icons.local_shipping,
                color: AppColors.primary,
              ),
              title: Text(
                envio.destinatarioNombre ?? 'Sin destinatario',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              subtitle: Text(
                '${envio.destinoDireccion ?? 'Sin dirección'}\n'
                '${envio.tipoServicio ?? ''} • ${envio.peso ?? 0} kg',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  _StatusPill(
                    estado: envio.estadoPublico ?? _estadoPublico(envio.estado),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    envio.creadoEn?.split('T').first ?? '',
                    style: const TextStyle(color: Colors.grey, fontSize: 12),
                  ),
                ],
              ),
              onTap:
                  () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => DetalleEnvioPage(envio: envio),
                    ),
                  ),
            ),
          );
        },
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String? estado;

  const _StatusPill({required this.estado});

  @override
  Widget build(BuildContext context) {
    final value = estado ?? 'N/A';
    final color = switch (value.toLowerCase()) {
      'entregado' => AppColors.success,
      'en tránsito' || 'en ruta' => AppColors.info,
      'en recepción' || 'pendiente' => AppColors.warning,
      'rechazado' || 'fallido' || 'cancelado' => AppColors.error,
      _ => AppColors.textTertiary,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        value,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.bold,
        ),
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
      return estado ?? 'Sin estado';
    default:
      return estado?.isNotEmpty == true ? estado! : 'Registrado';
  }
}

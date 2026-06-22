import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../theme/app_colors.dart';
import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../widgets/role_drawer.dart';

class EnviosPendientesPage extends StatefulWidget {
  const EnviosPendientesPage({super.key});

  @override
  State<EnviosPendientesPage> createState() => _EnviosPendientesPageState();
}

class _EnviosPendientesPageState extends State<EnviosPendientesPage> {
  List<dynamic> _envios = [];
  List<dynamic> _mensajeros = [];
  bool _loading = true;
  String? _selectedMensajeroId = 'todos';
  String? _userRol;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    const storage = FlutterSecureStorage();
    _userRol = await storage.read(key: 'rol');

    // Si es admin, cargar lista de mensajeros
    if (_userRol == 'Administrador') {
      await _loadMensajeros();
    }

    await _fetchEnviosPendientes();
  }

  // Cargar lista de mensajeros (solo para admin)
  Future<void> _loadMensajeros() async {
    try {
      final res = await ApiClient.instance.get('/usuarios/mensajeros-json/');
      if (res.statusCode == 200 &&
          res.headers['content-type']!.contains('application/json')) {
        final data = jsonDecode(res.body);
        if (data is List) {
          setState(() => _mensajeros = data);
        }
      }
    } catch (e) {
      debugPrint('🚨 Error al cargar mensajeros: $e');
    }
  }

  Future<void> _fetchEnviosPendientes() async {
    setState(() => _loading = true);

    // Construir parámetros de filtrado
    final queryParams = <String, String>{};

    // Si es admin y hay un mensajero seleccionado, filtrar por ese mensajero
    if (_userRol == 'Administrador' &&
        _selectedMensajeroId != null &&
        _selectedMensajeroId != 'todos') {
      queryParams['usuario_id'] = _selectedMensajeroId!;
      queryParams['rol'] = 'Mensajero';
    }

    try {
      final response = await ApiClient.instance.get(
        '/envios/envios-pendientes-json/',
        query: queryParams.isEmpty ? null : queryParams,
      );

      if (response.statusCode == 200) {
        final body = response.body;
        try {
          final parsed = jsonDecode(body);
          if (!mounted) return;
          setState(() {
            _envios = (parsed is List) ? parsed : [];
            _loading = false;
          });
        } catch (e) {
          debugPrint(
            'Error parseando JSON de envios pendientes: $e\nBody: $body',
          );
          if (mounted) setState(() => _loading = false);
        }
      } else {
        debugPrint(
          'Error HTTP al cargar envíos pendientes: ${response.statusCode} ${response.body}',
        );
        if (mounted) setState(() => _loading = false);
      }
    } catch (e) {
      debugPrint('⚠️ Error de conexión al cargar envíos pendientes: $e');
      if (mounted) setState(() => _loading = false);
    }
  }

  // Dropdown para seleccionar mensajero (solo admin)
  Widget _buildMensajeroFilter() {
    if (_userRol != 'Administrador' || _mensajeros.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: AppColors.surfaceDark.withValues(alpha: 0.3),
      child: Row(
        children: [
          const Icon(Icons.filter_list, color: AppColors.primary, size: 20),
          const SizedBox(width: 8),
          const Text(
            'Filtrar por mensajero:',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButton<String>(
              value: _selectedMensajeroId,
              isExpanded: true,
              hint: const Text('Todos los mensajeros'),
              items: [
                const DropdownMenuItem(
                  value: 'todos',
                  child: Text(
                    'Todos los mensajeros',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                ..._mensajeros.map(
                  (m) => DropdownMenuItem(
                    value: m['id'].toString(),
                    child: Text(m['nombre'] ?? 'Sin nombre'),
                  ),
                ),
              ],
              onChanged: (value) {
                setState(() => _selectedMensajeroId = value);
                _fetchEnviosPendientes();
              },
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: const Text('Envíos Pendientes - Courier Bolivian Express'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _fetchEnviosPendientes,
          ),
        ],
      ),
      drawer: const RoleDrawer(current: AppDestination.pendientes),
      body: Column(
        children: [
          _buildMensajeroFilter(),
          Expanded(
            child:
                _loading
                    ? const Center(
                      child: CircularProgressIndicator(
                        color: AppColors.primary,
                      ),
                    )
                    : _envios.isEmpty
                    ? const Center(
                      child: Text(
                        'No hay envíos pendientes.',
                        style: TextStyle(fontSize: 16, color: Colors.black54),
                      ),
                    )
                    : RefreshIndicator(
                      onRefresh: _fetchEnviosPendientes,
                      child: ListView.builder(
                        itemCount: _envios.length,
                        padding: const EdgeInsets.symmetric(
                          vertical: 8,
                          horizontal: 10,
                        ),
                        itemBuilder: (context, index) {
                          final envio = _envios[index];
                          return Card(
                            elevation: 3,
                            margin: const EdgeInsets.symmetric(
                              vertical: 8,
                              horizontal: 6,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 10,
                              ),
                              leading: CircleAvatar(
                                radius: 24,
                                backgroundColor: AppColors.primary.withValues(
                                  alpha: 0.3,
                                ),
                                child: const Icon(
                                  Icons.local_shipping,
                                  color: Colors.white,
                                  size: 26,
                                ),
                              ),
                              title: Text(
                                envio['destinatario_nombre'] ?? 'Sin nombre',
                                style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 16,
                                ),
                              ),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const SizedBox(height: 4),
                                  Text(
                                    'Origen: ${envio['origen_direccion'] ?? '—'}',
                                    style: const TextStyle(fontSize: 13),
                                  ),
                                  Text(
                                    'Destino: ${envio['destino_direccion'] ?? '—'}',
                                    style: const TextStyle(fontSize: 13),
                                  ),
                                  Text(
                                    'Teléfono: ${envio['destinatario_telefono'] ?? '—'}',
                                    style: const TextStyle(fontSize: 13),
                                  ),
                                  Text(
                                    'Tipo servicio: ${envio['tipo_servicio'] ?? '—'}',
                                    style: const TextStyle(fontSize: 13),
                                  ),
                                  Text(
                                    'Pago: ${envio['tipo_pago'] ?? '—'}',
                                    style: const TextStyle(fontSize: 13),
                                  ),
                                ],
                              ),
                              trailing: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Chip(
                                    label: Text(
                                      envio['estado'] ?? 'Pendiente',
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 12,
                                      ),
                                    ),
                                    backgroundColor: AppColors.primary,
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
          ),
        ],
      ),
    );
  }
}

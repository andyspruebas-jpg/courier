import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../theme/app_colors.dart';
import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../widgets/role_drawer.dart';

class EntregadosPage extends StatefulWidget {
  const EntregadosPage({super.key});

  @override
  State<EntregadosPage> createState() => _EntregadosPageState();
}

class _EntregadosPageState extends State<EntregadosPage> {
  List<dynamic> _entregas = [];
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

    await _fetchEntregas();
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

  Future<void> _fetchEntregas() async {
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
        '/envios/entregas-json/',
        query: queryParams.isEmpty ? null : queryParams,
      );

      if (response.statusCode == 200) {
        try {
          final parsed = jsonDecode(response.body);
          if (!mounted) return;
          setState(() {
            _entregas = (parsed is List) ? parsed : [];
            _loading = false;
          });
        } catch (e) {
          debugPrint('Error parseando JSON: $e\nBody: ${response.body}');
          if (mounted) setState(() => _loading = false);
        }
      } else {
        debugPrint('Error HTTP al cargar entregas: ${response.statusCode}');
        if (mounted) setState(() => _loading = false);
      }
    } catch (e) {
      debugPrint('⚠️ Error de conexión al cargar entregas: $e');
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
                _fetchEntregas();
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
        title: const Text('Entregas - Courier Bolivian Express'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _fetchEntregas,
          ),
        ],
      ),
      drawer: const RoleDrawer(current: AppDestination.entregados),
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
                    : _entregas.isEmpty
                    ? const Center(child: Text('No hay entregas registradas.'))
                    : RefreshIndicator(
                      onRefresh: _fetchEntregas,
                      child: ListView.builder(
                        itemCount: _entregas.length,
                        itemBuilder: (context, index) {
                          final entrega = _entregas[index];
                          return Card(
                            margin: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 6,
                            ),
                            child: ListTile(
                              title: Text('Entrega #${entrega['id']}'),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('Envío ID: ${entrega['envio']}'),
                                  Text('Mensajero: ${entrega['mensajero']}'),
                                  Text(
                                    'Fecha: ${entrega['fecha_entrega'] ?? "Sin fecha"}',
                                  ),
                                ],
                              ),
                              trailing: Chip(
                                label: Text(
                                  entrega['estado'] ?? '—',
                                  style: const TextStyle(color: Colors.white),
                                ),
                                backgroundColor:
                                    entrega['estado'] == 'Entregado'
                                        ? Colors.green
                                        : Colors.grey,
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

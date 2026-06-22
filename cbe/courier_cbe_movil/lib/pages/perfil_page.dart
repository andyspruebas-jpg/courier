import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../theme/app_colors.dart';
import '../widgets/role_drawer.dart';

class PerfilPage extends StatefulWidget {
  const PerfilPage({super.key});

  @override
  State<PerfilPage> createState() => _PerfilPageState();
}

class _PerfilPageState extends State<PerfilPage> {
  final _storage = const FlutterSecureStorage();
  bool _loading = true;
  Map<String, dynamic>? _perfil;

  @override
  void initState() {
    super.initState();
    _loadPerfil();
  }

  Future<void> _loadPerfil() async {
    setState(() => _loading = true);
    try {
      final response = await ApiClient.instance.get('/usuarios/perfil/');
      if (response.statusCode == 200) {
        final data = Map<String, dynamic>.from(
          jsonDecode(response.body) as Map,
        );
        await _storage.write(
          key: 'nombre',
          value: data['nombre']?.toString() ?? '',
        );
        await _storage.write(
          key: 'email',
          value: data['email']?.toString() ?? '',
        );
        await _storage.write(
          key: 'telefono',
          value: data['telefono']?.toString() ?? '',
        );
        await _storage.write(key: 'rol', value: data['rol']?.toString() ?? '');
        await _storage.write(
          key: 'empresa',
          value: jsonEncode(data['empresa']),
        );
        if (!mounted) return;
        setState(() => _perfil = data);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editarPerfil() async {
    final perfil = _perfil;
    if (perfil == null) return;
    final empresa = perfil['empresa'];
    final nombreCtrl = TextEditingController(
      text: perfil['nombre']?.toString() ?? '',
    );
    final emailCtrl = TextEditingController(
      text: perfil['email']?.toString() ?? '',
    );
    final telefonoCtrl = TextEditingController(
      text: perfil['telefono']?.toString() ?? '',
    );
    final empresaNombreCtrl = TextEditingController(
      text: empresa is Map ? empresa['nombre']?.toString() ?? '' : '',
    );
    final nitCtrl = TextEditingController(
      text: empresa is Map ? empresa['nit']?.toString() ?? '' : '',
    );
    final direccionCtrl = TextEditingController(
      text: empresa is Map ? empresa['direccion']?.toString() ?? '' : '',
    );
    final contactoCtrl = TextEditingController(
      text: empresa is Map ? empresa['contacto']?.toString() ?? '' : '',
    );
    final empresaTelefonoCtrl = TextEditingController(
      text: empresa is Map ? empresa['telefono']?.toString() ?? '' : '',
    );
    final empresaEmailCtrl = TextEditingController(
      text: empresa is Map ? empresa['email']?.toString() ?? '' : '',
    );

    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surfaceDark,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return Padding(
          padding: EdgeInsets.only(
            left: 16,
            right: 16,
            top: 16,
            bottom: MediaQuery.of(context).viewInsets.bottom + 16,
          ),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Editar perfil',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 14),
                _editField(nombreCtrl, 'Nombre', Icons.person_outline),
                _editField(emailCtrl, 'Correo', Icons.mail_outline),
                _editField(telefonoCtrl, 'Teléfono', Icons.phone_outlined),
                if (empresa is Map) ...[
                  const SizedBox(height: 12),
                  const Text(
                    'Empresa',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  _editField(
                    empresaNombreCtrl,
                    'Empresa',
                    Icons.business_outlined,
                  ),
                  _editField(
                    nitCtrl,
                    'NIT',
                    Icons.confirmation_number_outlined,
                  ),
                  _editField(
                    direccionCtrl,
                    'Dirección',
                    Icons.location_on_outlined,
                  ),
                  _editField(contactoCtrl, 'Contacto', Icons.badge_outlined),
                  _editField(
                    empresaTelefonoCtrl,
                    'Teléfono empresa',
                    Icons.phone_outlined,
                  ),
                  _editField(
                    empresaEmailCtrl,
                    'Correo empresa',
                    Icons.alternate_email,
                  ),
                ],
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('Cancelar'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: () => Navigator.pop(context, true),
                        icon: const Icon(Icons.save_outlined),
                        label: const Text('Guardar'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );

    if (ok != true) return;
    final body = {
      'nombre': nombreCtrl.text.trim(),
      'email': emailCtrl.text.trim(),
      'telefono': telefonoCtrl.text.trim(),
      if (empresa is Map)
        'empresa': {
          'nombre': empresaNombreCtrl.text.trim(),
          'nit': nitCtrl.text.trim(),
          'direccion': direccionCtrl.text.trim(),
          'contacto': contactoCtrl.text.trim(),
          'telefono': empresaTelefonoCtrl.text.trim(),
          'email': empresaEmailCtrl.text.trim(),
        },
    };
    final response = await ApiClient.instance.put(
      '/usuarios/perfil/',
      body: body,
    );
    if (!mounted) return;
    if (response.statusCode == 200) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Perfil actualizado.')));
      await _loadPerfil();
    } else {
      final msg =
          response.body.isNotEmpty
              ? response.body
              : 'No se pudo guardar el perfil.';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  Widget _editField(
    TextEditingController controller,
    String label,
    IconData icon,
  ) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(labelText: label, prefixIcon: Icon(icon)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final rol = _perfil?['rol']?.toString();
    final empresa = _perfil?['empresa'];

    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: const Text('Perfil'),
        actions: [
          IconButton(
            tooltip: 'Editar perfil',
            icon: const Icon(Icons.edit_outlined),
            onPressed: _loading ? null : _editarPerfil,
          ),
          IconButton(
            tooltip: 'Actualizar',
            icon: const Icon(Icons.refresh),
            onPressed: _loadPerfil,
          ),
        ],
      ),
      drawer: const RoleDrawer(current: AppDestination.perfil),
      body:
          _loading
              ? const Center(
                child: CircularProgressIndicator(color: AppColors.primary),
              )
              : RefreshIndicator(
                onRefresh: _loadPerfil,
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    _HeaderCard(perfil: _perfil),
                    if (empresa is Map) ...[
                      const SizedBox(height: 14),
                      _CompanySummary(
                        empresa: Map<String, dynamic>.from(empresa),
                      ),
                    ],
                    const SizedBox(height: 16),
                    _InfoSection(
                      title: 'Datos de usuario',
                      icon: Icons.person_outline,
                      rows: [
                        ('Nombre', _perfil?['nombre']),
                        ('Correo', _perfil?['email']),
                        ('Teléfono', _perfil?['telefono']),
                        ('Rol', rol),
                        (
                          'Estado',
                          _perfil?['is_active'] == true ? 'Activo' : 'Inactivo',
                        ),
                      ],
                    ),
                    if (empresa is Map) ...[
                      const SizedBox(height: 16),
                      _InfoSection(
                        title: 'Datos de empresa',
                        icon: Icons.business_outlined,
                        rows: [
                          ('Empresa', empresa['nombre']),
                          ('NIT', empresa['nit']),
                          ('Dirección', empresa['direccion']),
                          ('Contacto', empresa['contacto']),
                          ('Teléfono', empresa['telefono']),
                          ('Correo', empresa['email']),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
    );
  }
}

class _HeaderCard extends StatelessWidget {
  final Map<String, dynamic>? perfil;

  const _HeaderCard({required this.perfil});

  @override
  Widget build(BuildContext context) {
    final empresa = perfil?['empresa'];
    final empresaNombre = empresa is Map ? empresa['nombre']?.toString() : null;
    final title =
        (empresaNombre?.isNotEmpty ?? false)
            ? empresaNombre!
            : perfil?['nombre']?.toString() ?? 'Usuario';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: AppColors.primaryGradient,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withValues(alpha: 0.25),
            blurRadius: 26,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const CircleAvatar(
                radius: 34,
                backgroundColor: Colors.white,
                child: Icon(
                  Icons.business_center_outlined,
                  color: AppColors.primary,
                  size: 36,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Perfil de cuenta',
                      style: TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _HeaderChip(
                icon: Icons.verified_user_outlined,
                label:
                    perfil?['is_active'] == true
                        ? 'Cuenta activa'
                        : 'Cuenta inactiva',
              ),
              _HeaderChip(
                icon: Icons.mail_outline,
                label: perfil?['email']?.toString() ?? 'Sin correo',
              ),
              _HeaderChip(
                icon: Icons.badge_outlined,
                label: perfil?['rol']?.toString() ?? 'Usuario',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeaderChip extends StatelessWidget {
  final IconData icon;
  final String label;

  const _HeaderChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.22)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Colors.white, size: 15),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w600,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

class _CompanySummary extends StatelessWidget {
  final Map<String, dynamic> empresa;

  const _CompanySummary({required this.empresa});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _SummaryCard(
            icon: Icons.confirmation_number_outlined,
            label: 'NIT',
            value: empresa['nit']?.toString() ?? 'Sin dato',
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _SummaryCard(
            icon: Icons.phone_outlined,
            label: 'Contacto',
            value: empresa['telefono']?.toString() ?? 'Sin dato',
          ),
        ),
      ],
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _SummaryCard({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.22)),
      ),
      child: Row(
        children: [
          Icon(icon, color: AppColors.secondary),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                ),
                Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.bold,
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

class _InfoSection extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<(String, dynamic)> rows;

  const _InfoSection({
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
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (final row in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
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

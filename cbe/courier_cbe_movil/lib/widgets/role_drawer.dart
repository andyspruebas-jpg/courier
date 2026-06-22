import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../navigation/role_navigation.dart';
import '../pages/login_page.dart';
import '../theme/app_colors.dart';

class RoleDrawer extends StatefulWidget {
  final AppDestination current;
  final bool trackingEnabled;
  final VoidCallback? onToggleTracking;

  const RoleDrawer({
    super.key,
    required this.current,
    this.trackingEnabled = false,
    this.onToggleTracking,
  });

  @override
  State<RoleDrawer> createState() => _RoleDrawerState();
}

class _RoleDrawerState extends State<RoleDrawer> {
  final _storage = const FlutterSecureStorage();
  Map<String, dynamic> _usuario = const {};

  @override
  void initState() {
    super.initState();
    _loadUsuario();
  }

  Future<void> _loadUsuario() async {
    final data = await _storage.readAll();
    Map<String, dynamic>? empresa;
    final rawEmpresa = data['empresa'];
    if (rawEmpresa != null && rawEmpresa.isNotEmpty) {
      try {
        empresa = Map<String, dynamic>.from(jsonDecode(rawEmpresa) as Map);
      } catch (_) {
        empresa = null;
      }
    }
    if (!mounted) return;
    setState(() {
      _usuario = {
        'nombre': data['nombre'] ?? 'Usuario',
        'email': data['email'] ?? '',
        'rol': data['rol'] ?? '',
        'empresa': empresa,
      };
    });
  }

  @override
  Widget build(BuildContext context) {
    final rol = _usuario['rol']?.toString();
    final empresa = _usuario['empresa'];
    final empresaNombre = empresa is Map ? empresa['nombre']?.toString() : null;
    final nombre =
        (empresaNombre?.isNotEmpty ?? false)
            ? empresaNombre!
            : (_usuario['nombre']?.toString().isNotEmpty ?? false)
            ? _usuario['nombre'].toString()
            : 'Usuario';

    return Drawer(
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          DrawerHeader(
            decoration: const BoxDecoration(
              gradient: AppColors.primaryGradient,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const CircleAvatar(
                  backgroundColor: Colors.white,
                  radius: 28,
                  child: Icon(Icons.person, color: AppColors.primary, size: 38),
                ),
                const SizedBox(height: 12),
                Text(
                  nombre,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  _usuario['email']?.toString() ?? '',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          ),
          for (final item in destinationsForRole(rol))
            ListTile(
              leading: Icon(item.icon, color: AppColors.primary),
              title: Text(item.label),
              selected: item.destination == widget.current,
              selectedTileColor: AppColors.primary.withValues(alpha: 0.12),
              onTap: () {
                if (item.destination == widget.current) {
                  Navigator.pop(context);
                  return;
                }
                Navigator.pushReplacementNamed(context, item.route);
              },
            ),
          if (RoleNames.isMensajero(rol) &&
              widget.onToggleTracking != null) ...[
            const Divider(),
            ListTile(
              leading: Icon(
                widget.trackingEnabled
                    ? Icons.stop_circle
                    : Icons.play_circle_fill,
                color: AppColors.primary,
              ),
              title: Text(
                widget.trackingEnabled
                    ? 'Dejar de compartir ubicación'
                    : 'Compartir ubicación',
              ),
              onTap: widget.onToggleTracking,
            ),
          ],
          const Divider(),
          ListTile(
            leading: const Icon(Icons.logout, color: AppColors.error),
            title: const Text('Cerrar sesión'),
            onTap: () async {
              await _storage.deleteAll();
              if (!context.mounted) return;
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const LoginPage()),
                (_) => false,
              );
            },
          ),
        ],
      ),
    );
  }
}

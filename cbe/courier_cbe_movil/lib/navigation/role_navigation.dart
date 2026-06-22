import 'package:flutter/material.dart';

enum AppDestination {
  dashboard,
  rutas,
  guia,
  misEntregas,
  mensajeros,
  envios,
  entregados,
  pendientes,
  solicitarEnvio,
  seguimiento,
  perfil,
}

class AppRoutes {
  static const dashboard = '/dashboard';
  static const rutas = '/rutas';
  static const guia = '/guia';
  static const misEntregas = '/mis-entregas';
  static const mensajeros = '/mensajeros';
  static const envios = '/envios';
  static const entregados = '/entregados';
  static const pendientes = '/envios-pendientes';
  static const solicitarEnvio = '/solicitar-envio';
  static const seguimiento = '/seguimiento';
  static const perfil = '/perfil';
}

class RoleNames {
  static bool isAdmin(String? rol) => _norm(rol) == 'administrador';
  static bool isMensajero(String? rol) => _norm(rol) == 'mensajero';
  static bool isCliente(String? rol) => _norm(rol) == 'cliente';

  static String _norm(String? value) =>
      (value ?? '').trim().toLowerCase().replaceAll('á', 'a');
}

class DrawerDestination {
  final AppDestination destination;
  final String label;
  final IconData icon;
  final String route;

  const DrawerDestination({
    required this.destination,
    required this.label,
    required this.icon,
    required this.route,
  });
}

const _dashboard = DrawerDestination(
  destination: AppDestination.dashboard,
  label: 'Dashboard',
  icon: Icons.dashboard,
  route: AppRoutes.dashboard,
);

List<DrawerDestination> destinationsForRole(String? rol) {
  if (RoleNames.isAdmin(rol)) {
    return const [
      _dashboard,
      DrawerDestination(
        destination: AppDestination.rutas,
        label: 'Rutas',
        icon: Icons.route,
        route: AppRoutes.rutas,
      ),
      DrawerDestination(
        destination: AppDestination.mensajeros,
        label: 'Mensajeros',
        icon: Icons.person_pin_circle,
        route: AppRoutes.mensajeros,
      ),
      DrawerDestination(
        destination: AppDestination.envios,
        label: 'Envíos',
        icon: Icons.local_shipping,
        route: AppRoutes.envios,
      ),
      DrawerDestination(
        destination: AppDestination.entregados,
        label: 'Entregados',
        icon: Icons.check_circle_outline,
        route: AppRoutes.entregados,
      ),
      DrawerDestination(
        destination: AppDestination.pendientes,
        label: 'Pendientes',
        icon: Icons.pending_actions,
        route: AppRoutes.pendientes,
      ),
      DrawerDestination(
        destination: AppDestination.perfil,
        label: 'Perfil',
        icon: Icons.badge_outlined,
        route: AppRoutes.perfil,
      ),
    ];
  }

  if (RoleNames.isCliente(rol)) {
    return const [
      _dashboard,
      DrawerDestination(
        destination: AppDestination.envios,
        label: 'Mis envíos',
        icon: Icons.inventory_2_outlined,
        route: AppRoutes.envios,
      ),
      DrawerDestination(
        destination: AppDestination.solicitarEnvio,
        label: 'Solicitar envío',
        icon: Icons.add_box_outlined,
        route: AppRoutes.solicitarEnvio,
      ),
      DrawerDestination(
        destination: AppDestination.seguimiento,
        label: 'Seguimiento',
        icon: Icons.manage_search,
        route: AppRoutes.seguimiento,
      ),
      DrawerDestination(
        destination: AppDestination.perfil,
        label: 'Perfil',
        icon: Icons.badge_outlined,
        route: AppRoutes.perfil,
      ),
    ];
  }

  return const [
    _dashboard,
    DrawerDestination(
      destination: AppDestination.rutas,
      label: 'Rutas',
      icon: Icons.route,
      route: AppRoutes.rutas,
    ),
    DrawerDestination(
      destination: AppDestination.misEntregas,
      label: 'Mis entregas',
      icon: Icons.checklist,
      route: AppRoutes.misEntregas,
    ),
    DrawerDestination(
      destination: AppDestination.guia,
      label: 'Guía',
      icon: Icons.assistant_direction,
      route: AppRoutes.guia,
    ),
    DrawerDestination(
      destination: AppDestination.envios,
      label: 'Envíos',
      icon: Icons.local_shipping,
      route: AppRoutes.envios,
    ),
    DrawerDestination(
      destination: AppDestination.entregados,
      label: 'Entregados',
      icon: Icons.check_circle_outline,
      route: AppRoutes.entregados,
    ),
    DrawerDestination(
      destination: AppDestination.pendientes,
      label: 'Pendientes',
      icon: Icons.pending_actions,
      route: AppRoutes.pendientes,
    ),
    DrawerDestination(
      destination: AppDestination.perfil,
      label: 'Perfil',
      icon: Icons.badge_outlined,
      route: AppRoutes.perfil,
    ),
  ];
}

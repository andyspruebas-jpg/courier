import 'package:flutter/material.dart';

/// Colores consistentes con la página web
class AppColors {
  // Colores primarios (igual que la web)
  static const Color primary = Color(0xFF6366F1); // Indigo
  static const Color primaryLight = Color(0xFF818CF8); // Indigo claro
  static const Color secondary = Color(0xFF14B8A6); // Teal
  static const Color secondaryLight = Color(0xFF2DD4BF); // Teal claro

  // Fondos oscuros
  static const Color backgroundDark = Color(0xFF0A0E1A);
  static const Color surfaceDark = Color(0xFF1A1F35);
  static const Color cardDark = Color(0xFF27272A);

  // Estados
  static const Color success = Color(0xFF10B981); // Verde
  static const Color warning = Color(0xFFFBBF24); // Amarillo
  static const Color error = Color(0xFFEF4444); // Rojo
  static const Color info = Color(0xFF3B82F6); // Azul

  // Texto
  static const Color textPrimary = Color(0xFFFAFAFA);
  static const Color textSecondary = Color(0xFFE4E4E7);
  static const Color textTertiary = Color(0xFFA1A1AA);

  // Degradados
  static const LinearGradient primaryGradient = LinearGradient(
    colors: [Color(0xFF6366F1), Color(0xFF818CF8)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient secondaryGradient = LinearGradient(
    colors: [Color(0xFF14B8A6), Color(0xFF2DD4BF)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient backgroundGradient = LinearGradient(
    colors: [
      Color(0xFF0A0E1A),
      Color(0xFF1A1F35),
      Color(0xFF0A0E1A),
    ],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}

/// Estilos de texto consistentes
class AppTextStyles {
  static const TextStyle heading1 = TextStyle(
    fontSize: 32,
    fontWeight: FontWeight.w800,
    color: AppColors.textPrimary,
  );

  static const TextStyle heading2 = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w700,
    color: AppColors.textPrimary,
  );

  static const TextStyle heading3 = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w600,
    color: AppColors.textPrimary,
  );

  static const TextStyle body = TextStyle(
    fontSize: 16,
    color: AppColors.textSecondary,
  );

  static const TextStyle caption = TextStyle(
    fontSize: 14,
    color: AppColors.textTertiary,
  );
}

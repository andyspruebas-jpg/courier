import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/auth_provider.dart';
import 'services/cola_sync_service.dart';
import 'navigation/role_navigation.dart';
import 'pages/entregados_page.dart';
import 'pages/envios_page.dart';
import 'pages/envios_pendientes_page.dart';
import 'pages/login_page.dart';
import 'pages/home_page.dart';
import 'pages/guiar_mensajero.dart';
import 'pages/mensajeros_page.dart';
import 'pages/mis_entregas_page.dart';
import 'pages/perfil_page.dart';
import 'pages/rutas_page.dart';
import 'pages/seguimiento_page.dart';
import 'pages/solicitar_envio_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Arranca el reenvío de entregas guardadas offline cuando vuelva la conexión.
  ColaSyncService.instance.iniciar();
  runApp(const CourierApp());
}

class CourierApp extends StatelessWidget {
  const CourierApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [ChangeNotifierProvider(create: (_) => AuthProvider())],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        title: 'Courier Bolivian Express',
        theme: _buildModernTheme(),
        darkTheme: _buildDarkTheme(),
        themeMode: ThemeMode.dark, // Modo oscuro por defecto
        home: const SplashScreen(),
        routes: {
          AppRoutes.dashboard: (_) => const HomePage(),
          AppRoutes.rutas: (_) => const RutasPage(),
          AppRoutes.guia: (_) => const GuiarMensajeroPage(),
          AppRoutes.misEntregas: (_) => const MisEntregasPage(),
          AppRoutes.mensajeros: (_) => const MensajerosPage(),
          AppRoutes.envios: (_) => const EnviosPage(),
          AppRoutes.entregados: (_) => const EntregadosPage(),
          AppRoutes.pendientes: (_) => const EnviosPendientesPage(),
          AppRoutes.solicitarEnvio: (_) => const SolicitarEnvioPage(),
          AppRoutes.seguimiento: (_) => const SeguimientoPage(),
          AppRoutes.perfil: (_) => const PerfilPage(),
        },
      ),
    );
  }

  // Tema Oscuro Premium
  ThemeData _buildDarkTheme() {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      primaryColor: const Color(0xFF6366F1), // Indigo
      scaffoldBackgroundColor: const Color(0xFF0A0E1A),

      // Color Scheme
      colorScheme: const ColorScheme.dark(
        primary: Color(0xFF6366F1), // Indigo
        secondary: Color(0xFF14B8A6), // Teal
        surface: Color(0xFF1A1F35),
        error: Color(0xFFEF4444),
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: Color(0xFFFAFAFA),
        onError: Colors.white,
      ),

      // AppBar
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFF1A1F35),
        elevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          color: Color(0xFFFAFAFA),
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
      ),

      // Card
      cardTheme: CardThemeData(
        color: const Color(0xFF1A1F35).withValues(alpha: 0.85),
        elevation: 8,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(24),
          side: BorderSide(
            color: const Color(0xFF6366F1).withValues(alpha: 0.3),
            width: 2,
          ),
        ),
      ),

      // Input
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF27272A).withValues(alpha: 0.6),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(
            color: const Color(0xFF6366F1).withValues(alpha: 0.3),
            width: 2,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(
            color: const Color(0xFF6366F1).withValues(alpha: 0.3),
            width: 2,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF6366F1), width: 2),
        ),
        labelStyle: const TextStyle(color: Color(0xFFA1A1AA)),
        hintStyle: const TextStyle(color: Color(0xFF71717A)),
      ),

      // ElevatedButton
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF6366F1),
          foregroundColor: Colors.white,
          elevation: 4,
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 32),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
      ),

      // Text
      textTheme: const TextTheme(
        headlineLarge: TextStyle(
          fontSize: 32,
          fontWeight: FontWeight.w800,
          color: Color(0xFFFAFAFA),
        ),
        headlineMedium: TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w700,
          color: Color(0xFFFAFAFA),
        ),
        bodyLarge: TextStyle(fontSize: 16, color: Color(0xFFE4E4E7)),
        bodyMedium: TextStyle(fontSize: 14, color: Color(0xFFA1A1AA)),
      ),
    );
  }

  // Tema Claro (por si lo necesitas)
  ThemeData _buildModernTheme() {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      primaryColor: const Color(0xFF6366F1),
      scaffoldBackgroundColor: const Color(0xFFF5F5F5),
      colorScheme: const ColorScheme.light(
        primary: Color(0xFF6366F1),
        secondary: Color(0xFF14B8A6),
        surface: Colors.white,
      ),
    );
  }
}

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      duration: const Duration(milliseconds: 450),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeIn));

    _controller.forward();
    _checkSession();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _checkSession() async {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    await authProvider.cargarUsuario();

    if (!mounted) return;

    if (authProvider.isAuthenticated) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const HomePage()),
      );
    } else {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const LoginPage()),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0E1A),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF0A0E1A), Color(0xFF1A1F35), Color(0xFF0A0E1A)],
          ),
        ),
        child: Center(
          child: FadeTransition(
            opacity: _fadeAnimation,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    color: const Color(0xFF6366F1),
                    borderRadius: BorderRadius.circular(24),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF6366F1).withValues(alpha: 0.5),
                        blurRadius: 32,
                        spreadRadius: 8,
                      ),
                    ],
                  ),
                  child: const Icon(
                    Icons.local_shipping,
                    size: 50,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 32),
                ShaderMask(
                  shaderCallback:
                      (bounds) => const LinearGradient(
                        colors: [Color(0xFF818CF8), Color(0xFF14B8A6)],
                      ).createShader(bounds),
                  child: const Text(
                    'Courier Bolivian Express',
                    style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(height: 48),
                const CircularProgressIndicator(
                  color: Color(0xFF6366F1),
                  strokeWidth: 3,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

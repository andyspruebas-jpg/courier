import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import 'home_page.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> with SingleTickerProviderStateMixin {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;
  bool _obscurePassword = true;
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeIn),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutCubic,
    ));

    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final authProvider = Provider.of<AuthProvider>(context);

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF0A0E1A),
              Color(0xFF1A1F35),
              Color(0xFF0A0E1A),
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24.0),
              child: FadeTransition(
                opacity: _fadeAnimation,
                child: SlideTransition(
                  position: _slideAnimation,
                  child: Card(
                    elevation: 20,
                    shadowColor: const Color(0xFF6366F1).withValues(alpha: 0.3),
                    child: Container(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(24),
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            const Color(0xFF1A1F35).withValues(alpha: 0.9),
                            const Color(0xFF27272A).withValues(alpha: 0.8),
                          ],
                        ),
                        border: Border.all(
                          color: const Color(0xFF6366F1).withValues(alpha: 0.3),
                          width: 2,
                        ),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(32.0),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            // Logo/Icon
                            Container(
                              width: 80,
                              height: 80,
                              decoration: BoxDecoration(
                                gradient: const LinearGradient(
                                  colors: [Color(0xFF6366F1), Color(0xFF818CF8)],
                                ),
                                borderRadius: BorderRadius.circular(20),
                                boxShadow: [
                                  BoxShadow(
                                    color: const Color(0xFF6366F1).withValues(alpha: 0.5),
                                    blurRadius: 24,
                                    spreadRadius: 4,
                                  ),
                                ],
                              ),
                              child: const Icon(
                                Icons.local_shipping,
                                size: 40,
                                color: Colors.white,
                              ),
                            ),
                            const SizedBox(height: 24),

                            // Título
                            ShaderMask(
                              shaderCallback: (bounds) => const LinearGradient(
                                colors: [Color(0xFF818CF8), Color(0xFF14B8A6)],
                              ).createShader(bounds),
                              child: const Text(
                                "Courier Bolivian Express",
                                style: TextStyle(
                                  fontSize: 22,
                                  fontWeight: FontWeight.w800,
                                  color: Colors.white,
                                ),
                                textAlign: TextAlign.center,
                              ),
                            ),
                            const SizedBox(height: 8),
                            const Text(
                              "Inicia sesión para continuar",
                              style: TextStyle(
                                fontSize: 14,
                                color: Color(0xFFA1A1AA),
                              ),
                            ),
                            const SizedBox(height: 32),

                            // Email Input
                            TextField(
                              controller: _emailController,
                              keyboardType: TextInputType.emailAddress,
                              decoration: InputDecoration(
                                labelText: "Correo electrónico",
                                prefixIcon: const Icon(
                                  Icons.email_outlined,
                                  color: Color(0xFF6366F1),
                                ),
                                suffixIcon: _emailController.text.isNotEmpty
                                    ? IconButton(
                                        icon: const Icon(Icons.clear, size: 20),
                                        onPressed: () => _emailController.clear(),
                                      )
                                    : null,
                              ),
                              onChanged: (_) => setState(() {}),
                            ),
                            const SizedBox(height: 20),

                            // Password Input
                            TextField(
                              controller: _passwordController,
                              obscureText: _obscurePassword,
                              decoration: InputDecoration(
                                labelText: "Contraseña",
                                prefixIcon: const Icon(
                                  Icons.lock_outline,
                                  color: Color(0xFF6366F1),
                                ),
                                suffixIcon: IconButton(
                                  icon: Icon(
                                    _obscurePassword
                                        ? Icons.visibility_off
                                        : Icons.visibility,
                                    color: const Color(0xFFA1A1AA),
                                  ),
                                  onPressed: () {
                                    setState(() {
                                      _obscurePassword = !_obscurePassword;
                                    });
                                  },
                                ),
                              ),
                            ),
                            const SizedBox(height: 32),

                            // Login Button
                            SizedBox(
                              width: double.infinity,
                              height: 56,
                              child: ElevatedButton(
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: const Color(0xFF6366F1),
                                  foregroundColor: Colors.white,
                                  elevation: 8,
                                  shadowColor: const Color(0xFF6366F1).withValues(alpha: 0.5),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                ),
                                onPressed: _loading
                                    ? null
                                    : () async {
                                        if (_emailController.text.isEmpty ||
                                            _passwordController.text.isEmpty) {
                                          ScaffoldMessenger.of(context).showSnackBar(
                                            SnackBar(
                                              content: const Text("Por favor completa todos los campos"),
                                              backgroundColor: const Color(0xFFEF4444),
                                              behavior: SnackBarBehavior.floating,
                                              shape: RoundedRectangleBorder(
                                                borderRadius: BorderRadius.circular(12),
                                              ),
                                            ),
                                          );
                                          return;
                                        }

                                        setState(() => _loading = true);
                                        
                                        final success = await authProvider.login(
                                          _emailController.text.trim(),
                                          _passwordController.text.trim(),
                                        );
                                        
                                        setState(() => _loading = false);

                                        if (!context.mounted) return;

                                        if (success) {
                                          Navigator.pushReplacement(
                                            context,
                                            PageRouteBuilder(
                                              pageBuilder: (context, animation, secondaryAnimation) =>
                                                  const HomePage(),
                                              transitionsBuilder:
                                                  (context, animation, secondaryAnimation, child) {
                                                return FadeTransition(
                                                  opacity: animation,
                                                  child: child,
                                                );
                                              },
                                            ),
                                          );
                                        } else {
                                          ScaffoldMessenger.of(context).showSnackBar(
                                            SnackBar(
                                              content: const Row(
                                                children: [
                                                  Icon(Icons.error_outline, color: Colors.white),
                                                  SizedBox(width: 12),
                                                  Expanded(
                                                    child: Text(
                                                      "Credenciales inválidas o servidor no disponible",
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              backgroundColor: const Color(0xFFEF4444),
                                              behavior: SnackBarBehavior.floating,
                                              shape: RoundedRectangleBorder(
                                                borderRadius: BorderRadius.circular(12),
                                              ),
                                            ),
                                          );
                                        }
                                      },
                                child: _loading
                                    ? const SizedBox(
                                        width: 24,
                                        height: 24,
                                        child: CircularProgressIndicator(
                                          color: Colors.white,
                                          strokeWidth: 2.5,
                                        ),
                                      )
                                    : const Row(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        children: [
                                          Icon(Icons.login, size: 20),
                                          SizedBox(width: 8),
                                          Text("Iniciar Sesión"),
                                        ],
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

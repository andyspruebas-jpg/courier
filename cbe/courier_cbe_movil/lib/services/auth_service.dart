import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api.dart'; // ✅ Importa tu archivo con LOGIN_URL y demás

/// Servicio de autenticación para login, sesión y logout
class AuthService {
  final storage = const FlutterSecureStorage();

  // ============================================================
  // 🔐 LOGIN
  // ============================================================
  Future<Map<String, dynamic>?> login(String email, String password) async {
    try {
      final url = Uri.parse(loginUrl);
      debugPrint("🌍 Intentando login en: $url");
      debugPrint("📧 Email: $email");

      // 🔹 Usa los nombres exactos que Django espera: "email" y "contrasena"
      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: jsonEncode({
          'email': email.trim(),
          'contrasena': password.trim(), // 👈 CAMBIO CLAVE
        }),
      );

      debugPrint('📡 Código de respuesta: ${response.statusCode}');
      debugPrint('🧾 Cuerpo recibido: ${response.body}');

      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = jsonDecode(response.body);

        // Si la respuesta incluye un campo "usuario", úsalo
        final user = data.containsKey('usuario') ? data['usuario'] : data;

        // ✅ Guarda los datos en almacenamiento seguro
        await storage.write(key: 'id', value: user['id'].toString());
        await storage.write(key: 'nombre', value: user['nombre'] ?? '');
        await storage.write(key: 'email', value: user['email'] ?? '');
        await storage.write(key: 'telefono', value: user['telefono'] ?? '');
        await storage.write(key: 'rol', value: user['rol'] ?? '');
        await storage.write(
          key: 'is_active',
          value: (user['is_active'] ?? true).toString(),
        );
        await storage.write(key: 'empresa', value: jsonEncode(user['empresa']));
        if (data['access'] != null) {
          await storage.write(key: 'token', value: data['access'].toString());
        }
        if (data['refresh'] != null) {
          await storage.write(
            key: 'refresh_token',
            value: data['refresh'].toString(),
          );
        }

        debugPrint(
          '✅ Login exitoso. Usuario guardado en almacenamiento seguro.',
        );
        return data;
      } else {
        debugPrint('❌ Error en login: ${response.body}');
        return null;
      }
    } catch (e) {
      debugPrint('⚠️ Error en login: $e');
      return null;
    }
  }

  // ============================================================
  // 👤 OBTENER USUARIO LOCAL
  // ============================================================
  Future<Map<String, dynamic>?> getUsuario() async {
    try {
      final idStr = await storage.read(key: 'id');
      if (idStr == null) {
        debugPrint('⚠️ No hay usuario guardado localmente.');
        return null;
      }
      final token = await storage.read(key: 'token');
      final refreshToken = await storage.read(key: 'refresh_token');
      if ((token == null || token.isEmpty) &&
          (refreshToken == null || refreshToken.isEmpty)) {
        debugPrint('⚠️ Sesión local sin token. Se requiere iniciar sesión.');
        await storage.deleteAll();
        return null;
      }

      final perfil = await _perfilValido(token, refreshToken);
      if (perfil == null) {
        debugPrint('⚠️ Sesión local inválida o vencida. Limpiando datos.');
        await storage.deleteAll();
        return null;
      }

      await _guardarUsuarioLocal(perfil);
      return perfil;
    } catch (e) {
      debugPrint('⚠️ Error obteniendo usuario: $e');
      await storage.deleteAll();
      return null;
    }
  }

  Future<Map<String, dynamic>?> _perfilValido(
    String? token,
    String? refreshToken,
  ) async {
    final currentToken = token;
    if (currentToken != null && currentToken.isNotEmpty) {
      final perfil = await _consultarPerfil(currentToken);
      if (perfil != null) return perfil;
    }

    if (refreshToken == null || refreshToken.isEmpty) return null;
    final refreshed = await _refrescarToken(refreshToken);
    if (refreshed == null || refreshed.isEmpty) return null;

    await storage.write(key: 'token', value: refreshed);
    return _consultarPerfil(refreshed);
  }

  Future<Map<String, dynamic>?> _consultarPerfil(String token) async {
    try {
      final response = await http.get(
        Uri.parse(perfilUrl),
        headers: {
          'Accept': 'application/json',
          'Authorization': 'Bearer $token',
          'ngrok-skip-browser-warning': '1',
        },
      );
      final contentType = response.headers['content-type'] ?? '';
      if (response.statusCode != 200 ||
          !contentType.contains('application/json')) {
        return null;
      }
      final data = jsonDecode(response.body);
      if (data is Map<String, dynamic> && data['id'] != null) return data;
    } catch (e) {
      debugPrint('⚠️ Error validando perfil: $e');
    }
    return null;
  }

  Future<String?> _refrescarToken(String refreshToken) async {
    try {
      final response = await http.post(
        Uri.parse('$apiUrl/api/token/refresh/'),
        headers: const {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: jsonEncode({'refresh': refreshToken}),
      );
      if (response.statusCode != 200) return null;
      final data = jsonDecode(response.body);
      if (data is Map<String, dynamic>) return data['access']?.toString();
    } catch (e) {
      debugPrint('⚠️ Error refrescando sesión: $e');
    }
    return null;
  }

  Future<void> _guardarUsuarioLocal(Map<String, dynamic> user) async {
    await storage.write(key: 'id', value: user['id'].toString());
    await storage.write(key: 'nombre', value: user['nombre'] ?? '');
    await storage.write(key: 'email', value: user['email'] ?? '');
    await storage.write(key: 'telefono', value: user['telefono'] ?? '');
    await storage.write(key: 'rol', value: user['rol'] ?? '');
    await storage.write(
      key: 'is_active',
      value: (user['is_active'] ?? true).toString(),
    );
    await storage.write(key: 'empresa', value: jsonEncode(user['empresa']));
  }

  @Deprecated('La sesión local ahora se valida contra /usuarios/perfil/.')
  Future<Map<String, dynamic>?> getUsuarioLocalSinValidar() async {
    try {
      final idStr = await storage.read(key: 'id');
      if (idStr == null) return null;

      final id = int.tryParse(idStr) ?? 0;
      final nombre = await storage.read(key: 'nombre');
      final email = await storage.read(key: 'email');
      final telefono = await storage.read(key: 'telefono');
      final rol = await storage.read(key: 'rol');
      final isActiveStr = await storage.read(key: 'is_active');
      final isActive = isActiveStr == 'true' || isActiveStr == '1';
      final empresaRaw = await storage.read(key: 'empresa');
      Map<String, dynamic>? empresa;
      if (empresaRaw != null && empresaRaw.isNotEmpty && empresaRaw != 'null') {
        empresa = Map<String, dynamic>.from(jsonDecode(empresaRaw) as Map);
      }

      final user = {
        'id': id,
        'nombre': nombre,
        'email': email,
        'telefono': telefono,
        'rol': rol,
        'is_active': isActive,
        'empresa': empresa,
      };

      debugPrint('👤 Usuario cargado desde almacenamiento: $user');
      return user;
    } catch (e) {
      debugPrint('⚠️ Error obteniendo usuario: $e');
      return null;
    }
  }

  // ============================================================
  // 🚪 LOGOUT
  // ============================================================
  Future<void> logout() async {
    await storage.deleteAll();
    debugPrint('👋 Sesión cerrada y datos locales eliminados.');
  }
}

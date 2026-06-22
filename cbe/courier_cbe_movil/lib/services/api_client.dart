import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../api/api.dart';

/// Cliente HTTP central de la app.
///
/// Centraliza lo que antes estaba repetido en cada página:
///  - cabeceras por defecto (`Accept`, salto del aviso de ngrok),
///  - token JWT (`Authorization: Bearer …`) leído del almacenamiento seguro,
///  - refresco automático del token ante un `401` (vía `/api/token/refresh/`),
///  - timeouts y subida multipart (foto/firma) para la confirmación de entregas.
///
/// Uso: `ApiClient.instance.get('/envios/envios-json/', query: {...})`.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  static const Duration _timeout = Duration(seconds: 15);

  Future<Map<String, String>> _headers({bool json = true}) async {
    final token = await _storage.read(key: 'token');
    final headers = <String, String>{
      'Accept': 'application/json',
      'ngrok-skip-browser-warning': '1',
    };
    if (json) headers['Content-Type'] = 'application/json';
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Uri _uri(String path, Map<String, String>? query) {
    final base = path.startsWith('http') ? path : '$apiUrl$path';
    final uri = Uri.parse(base);
    if (query == null || query.isEmpty) return uri;
    return uri.replace(queryParameters: {...uri.queryParameters, ...query});
  }

  Future<http.Response> get(String path, {Map<String, String>? query}) {
    final uri = _uri(path, query);
    return _send(() async => http.get(uri, headers: await _headers()));
  }

  Future<http.Response> post(String path, {Object? body}) {
    final uri = _uri(path, null);
    return _send(
      () async => http.post(
        uri,
        headers: await _headers(),
        body: body == null ? null : jsonEncode(body),
      ),
    );
  }

  Future<http.Response> put(String path, {Object? body}) {
    final uri = _uri(path, null);
    return _send(
      () async => http.put(
        uri,
        headers: await _headers(),
        body: body == null ? null : jsonEncode(body),
      ),
    );
  }

  /// POST multipart para subir archivos (foto/firma de entrega).
  /// [fields] son campos de texto; [files] mapea nombre-de-campo → ruta-en-disco.
  /// Devuelve la respuesta completa ya leída.
  Future<http.Response> postMultipart(
    String path, {
    Map<String, String> fields = const {},
    Map<String, String> files = const {},
    Map<String, Uint8List> byteFiles = const {},
    Map<String, String> byteFileNames = const {},
  }) async {
    final uri = _uri(path, null);
    final token = await _storage.read(key: 'token');
    final req = http.MultipartRequest('POST', uri);
    req.headers['Accept'] = 'application/json';
    req.headers['ngrok-skip-browser-warning'] = '1';
    if (token != null && token.isNotEmpty) {
      req.headers['Authorization'] = 'Bearer $token';
    }
    req.fields.addAll(fields);
    for (final entry in files.entries) {
      req.files.add(await http.MultipartFile.fromPath(entry.key, entry.value));
    }
    for (final entry in byteFiles.entries) {
      req.files.add(
        http.MultipartFile.fromBytes(
          entry.key,
          entry.value,
          filename: byteFileNames[entry.key] ?? '${entry.key}.bin',
        ),
      );
    }
    final streamed = await req.send().timeout(const Duration(seconds: 30));
    return http.Response.fromStream(streamed);
  }

  /// Ejecuta la petición; ante un `401` intenta refrescar el token una vez y reintenta.
  Future<http.Response> _send(Future<http.Response> Function() request) async {
    http.Response resp = await request().timeout(_timeout);
    if (resp.statusCode == 401 && await _refreshToken()) {
      resp = await request().timeout(_timeout);
    }
    return resp;
  }

  Future<bool> _refreshToken() async {
    try {
      final refresh = await _storage.read(key: 'refresh_token');
      if (refresh == null || refresh.isEmpty) return false;
      final resp = await http
          .post(
            Uri.parse('$apiUrl/api/token/refresh/'),
            headers: const {
              'Content-Type': 'application/json',
              'Accept': 'application/json',
            },
            body: jsonEncode({'refresh': refresh}),
          )
          .timeout(_timeout);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        final access = data['access']?.toString();
        if (access != null && access.isNotEmpty) {
          await _storage.write(key: 'token', value: access);
          return true;
        }
      }
    } catch (e) {
      debugPrint('⚠️ Error refrescando token: $e');
    }
    return false;
  }
}

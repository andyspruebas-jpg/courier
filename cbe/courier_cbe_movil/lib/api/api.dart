import 'package:flutter/foundation.dart';

String getBaseUrl() {
  const overrideUrl = String.fromEnvironment('API_BASE_URL');
  if (overrideUrl.isNotEmpty) return overrideUrl;
  return 'https://investigated-sociology-protein-ray.trycloudflare.com';
}

final String apiUrl = getBaseUrl();
final String loginUrl = "$apiUrl/usuarios/login/";
final String perfilUrl = "$apiUrl/usuarios/perfil/";

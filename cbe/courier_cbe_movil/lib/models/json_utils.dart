/// Utilidades de parseo tolerante para los JSON del backend Django.
///
/// El backend serializa los `DecimalField` como **cadenas** (p. ej. la latitud
/// llega como `"-16.5"`) y algunos campos numéricos pueden venir como `int`,
/// `double`, `String` o `null`. Estos helpers normalizan esas variantes.
library;

double? toDoubleOrNull(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString());
}

int? toIntOrNull(dynamic v) {
  if (v == null) return null;
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString());
}

String? toStringOrNull(dynamic v) {
  if (v == null) return null;
  final s = v.toString();
  return s.isEmpty ? null : s;
}

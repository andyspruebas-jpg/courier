import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:geolocator/geolocator.dart' as geo;
import 'package:permission_handler/permission_handler.dart';

import '../models/envio.dart';
import '../services/incidencia_service.dart';
import '../theme/app_colors.dart';

/// Pantalla del mensajero para reportar una incidencia sobre un envío
/// (retraso, daño, pérdida, otro) con descripción y foto opcional.
class RegistrarIncidenciaPage extends StatefulWidget {
  final Envio envio;

  const RegistrarIncidenciaPage({super.key, required this.envio});

  @override
  State<RegistrarIncidenciaPage> createState() =>
      _RegistrarIncidenciaPageState();
}

class _RegistrarIncidenciaPageState extends State<RegistrarIncidenciaPage> {
  final _picker = ImagePicker();
  final _service = IncidenciaService();
  final _descController = TextEditingController();

  String _tipo = TipoIncidencia.retraso;
  File? _foto;
  bool _enviando = false;

  @override
  void dispose() {
    _descController.dispose();
    super.dispose();
  }

  Future<void> _tomarFoto() async {
    try {
      final status = await Permission.camera.request();
      if (!status.isGranted) {
        _snack('Se necesita permiso de cámara para tomar la foto.');
        return;
      }
      final XFile? x = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 70,
        maxWidth: 1280,
      );
      if (x != null) setState(() => _foto = File(x.path));
    } catch (e) {
      _snack('No se pudo abrir la cámara: $e');
    }
  }

  Future<({double? lat, double? lng})> _ubicacionActual() async {
    try {
      final pos = await geo.Geolocator.getCurrentPosition(
        locationSettings:
            const geo.LocationSettings(accuracy: geo.LocationAccuracy.high),
      ).timeout(const Duration(seconds: 8));
      return (lat: pos.latitude, lng: pos.longitude);
    } catch (_) {
      return (lat: null, lng: null);
    }
  }

  Future<void> _confirmar() async {
    final envioId = widget.envio.id;
    if (envioId == null) {
      _snack('Envío inválido.');
      return;
    }
    if (_descController.text.trim().isEmpty) {
      _snack('Describe brevemente la incidencia.');
      return;
    }

    setState(() => _enviando = true);
    final ubic = await _ubicacionActual();

    final result = await _service.registrarIncidencia(
      envioId: envioId,
      tipo: _tipo,
      descripcion: _descController.text,
      foto: _foto,
      latitud: ubic.lat,
      longitud: ubic.lng,
    );

    if (!mounted) return;
    setState(() => _enviando = false);

    if (result.ok) {
      _snack('✅ Incidencia registrada.');
      Navigator.pop(context, true);
    } else {
      _snack('❌ ${result.mensaje ?? 'No se pudo registrar la incidencia.'}');
    }
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    final envio = widget.envio;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: Text('Incidencia · Envío #${envio.id ?? ''}'),
      ),
      body: AbsorbPointer(
        absorbing: _enviando,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (envio.destinatarioNombre != null)
                Text(
                  envio.destinatarioNombre!,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.bold),
                ),
              const SizedBox(height: 20),

              _label('Tipo de incidencia'),
              DropdownButtonFormField<String>(
                initialValue: _tipo,
                decoration: const InputDecoration(border: OutlineInputBorder()),
                items: [
                  for (final t in TipoIncidencia.todos)
                    DropdownMenuItem(value: t, child: Text(t)),
                ],
                onChanged: (v) => setState(() => _tipo = v ?? _tipo),
              ),
              const SizedBox(height: 20),

              _label('Descripción'),
              TextField(
                controller: _descController,
                maxLines: 4,
                decoration: const InputDecoration(
                  hintText: 'Describe qué ocurrió',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 20),

              _label('Fotografía (opcional)'),
              if (_foto != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Image.file(_foto!,
                      height: 180, width: double.infinity, fit: BoxFit.cover),
                ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _tomarFoto,
                icon: const Icon(Icons.camera_alt),
                label: Text(_foto == null ? 'Tomar foto' : 'Volver a tomar'),
              ),
              const SizedBox(height: 24),

              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _enviando ? null : _confirmar,
                  icon: _enviando
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.report_problem),
                  label: Text(_enviando ? 'Enviando…' : 'Reportar incidencia'),
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.warning,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          text,
          style: const TextStyle(
              fontWeight: FontWeight.bold, color: AppColors.primary),
        ),
      );
}

import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';
import 'package:signature/signature.dart';
import 'package:geolocator/geolocator.dart' as geo;
import 'package:permission_handler/permission_handler.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/envio.dart';
import '../services/entrega_service.dart';
import '../services/cola_sync_service.dart';
import '../theme/app_colors.dart';

/// Pantalla del mensajero para confirmar (o rechazar) una entrega adjuntando
/// fotografía, firma digital y observaciones. Cierra con `Navigator.pop(true)`
/// cuando la entrega se registra correctamente.
class RegistrarEntregaPage extends StatefulWidget {
  final Envio envio;

  const RegistrarEntregaPage({super.key, required this.envio});

  @override
  State<RegistrarEntregaPage> createState() => _RegistrarEntregaPageState();
}

class _RegistrarEntregaPageState extends State<RegistrarEntregaPage> {
  final _storage = const FlutterSecureStorage();
  final _picker = ImagePicker();
  final _entregaService = EntregaService();
  final _obsController = TextEditingController();
  final _montoController = TextEditingController();
  final _firmaController = SignatureController(
    penStrokeWidth: 3,
    penColor: Colors.black,
    exportBackgroundColor: Colors.white,
  );

  String _estado = EstadoEnvio.entregado; // 'Entregado' | 'Rechazado'
  String _modalidadPago = 'Pendiente'; // 'Origen' | 'Destino' | 'Pendiente'
  File? _foto;
  int _mensajeroId = 0;
  bool _enviando = false;

  @override
  void initState() {
    super.initState();
    _cargarMensajero();
    // Prefijar el monto y la modalidad con los datos del envío, si existen.
    if (widget.envio.montoPago != null) {
      _montoController.text = widget.envio.montoPago!.toStringAsFixed(2);
    }
    final tp = widget.envio.tipoPago;
    if (tp == 'Origen' || tp == 'Destino') _modalidadPago = tp!;
  }

  @override
  void dispose() {
    _obsController.dispose();
    _montoController.dispose();
    _firmaController.dispose();
    super.dispose();
  }

  Future<void> _cargarMensajero() async {
    final id = await _storage.read(key: 'id');
    if (!mounted) return;
    setState(() => _mensajeroId = int.tryParse(id ?? '') ?? 0);
  }

  Future<void> _tomarFoto() async {
    try {
      if (kIsWeb) {
        _snack(
          'En web usa la firma como evidencia; la foto se adjunta desde Android.',
        );
        return;
      }
      // El permiso CAMERA está declarado en el manifest, así que Android lo
      // exige en runtime: lo solicitamos antes de abrir la cámara.
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
      if (x != null) {
        setState(() => _foto = File(x.path));
      }
    } catch (e) {
      _snack('No se pudo abrir la cámara: $e');
    }
  }

  Future<Uint8List?> _exportarFirmaBytes() async {
    if (_firmaController.isEmpty) return null;
    final bytes = await _firmaController.toPngBytes();
    if (bytes == null) return null;
    return Uint8List.fromList(bytes);
  }

  /// Exporta la firma a un archivo PNG temporal para subirla como multipart.
  Future<File?> _exportarFirma(Uint8List bytes) async {
    if (kIsWeb) return null;
    final ruta =
        '${Directory.systemTemp.path}/firma_envio_${widget.envio.id ?? 0}.png';
    final file = File(ruta);
    await file.writeAsBytes(bytes);
    return file;
  }

  Future<({double? lat, double? lng})> _ubicacionActual() async {
    try {
      final pos = await geo.Geolocator.getCurrentPosition(
        locationSettings: const geo.LocationSettings(
          accuracy: geo.LocationAccuracy.high,
        ),
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
    if (_mensajeroId <= 0) {
      _snack('No se pudo identificar al mensajero. Inicia sesión de nuevo.');
      return;
    }

    final firmaBytes = await _exportarFirmaBytes();
    final firma = firmaBytes == null ? null : await _exportarFirma(firmaBytes);

    // Para una entrega exitosa se exige al menos una evidencia (foto o firma).
    if (_estado == EstadoEnvio.entregado &&
        _foto == null &&
        firma == null &&
        firmaBytes == null) {
      _snack('Adjunta una foto o una firma como comprobante de entrega.');
      return;
    }

    setState(() => _enviando = true);
    final ubic = await _ubicacionActual();
    final monto = double.tryParse(_montoController.text.replaceAll(',', '.'));
    // La modalidad solo aplica a una entrega exitosa.
    final modalidad = _estado == EstadoEnvio.entregado ? _modalidadPago : null;

    // 🔌 Sin conexión: encolar la entrega para sincronizarla al reconectar.
    if (!await ColaSyncService.instance.hayConexion()) {
      if (kIsWeb) {
        if (!mounted) return;
        setState(() => _enviando = false);
        _snack(
          'Sin conexión: la cola offline con evidencias está disponible en Android.',
        );
        return;
      }
      await ColaSyncService.instance.encolarEntrega(
        envioId: envioId,
        mensajeroId: _mensajeroId,
        estado: _estado,
        observaciones: _obsController.text,
        modalidadPago: modalidad,
        monto: monto,
        foto: _foto,
        firma: firma,
        latitud: ubic.lat,
        longitud: ubic.lng,
      );
      if (!mounted) return;
      setState(() => _enviando = false);
      _snack(
        '📴 Sin conexión: la entrega se guardó y se enviará al reconectar.',
      );
      Navigator.pop(context, true);
      return;
    }

    final result = await _entregaService.registrarEntrega(
      envioId: envioId,
      mensajeroId: _mensajeroId,
      estado: _estado,
      observaciones: _obsController.text,
      modalidadPago: modalidad,
      monto: monto,
      foto: _foto,
      firma: firma,
      firmaBytes: kIsWeb ? firmaBytes : null,
      firmaFileName: 'firma_envio_$envioId.png',
      latitud: ubic.lat,
      longitud: ubic.lng,
    );

    if (!mounted) return;
    setState(() => _enviando = false);

    if (result.ok) {
      _snack('✅ Entrega registrada correctamente.');
      Navigator.pop(context, true);
    } else {
      _snack('❌ ${result.mensaje ?? 'No se pudo registrar la entrega.'}');
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
        title: Text('Registrar entrega #${envio.id ?? ''}'),
      ),
      body: AbsorbPointer(
        absorbing: _enviando,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                envio.destinatarioNombre ?? 'Destinatario',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              if (envio.destinoDireccion != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    envio.destinoDireccion!,
                    style: const TextStyle(color: Colors.grey),
                  ),
                ),
              const SizedBox(height: 20),

              // Estado de la entrega
              _label('Resultado'),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(
                    value: EstadoEnvio.entregado,
                    label: Text('Entregado'),
                    icon: Icon(Icons.check_circle),
                  ),
                  ButtonSegment(
                    value: EstadoEnvio.rechazado,
                    label: Text('Rechazado'),
                    icon: Icon(Icons.cancel),
                  ),
                ],
                selected: {_estado},
                onSelectionChanged: (s) => setState(() => _estado = s.first),
              ),
              const SizedBox(height: 20),

              // Fotografía
              _label('Fotografía de evidencia'),
              if (_foto != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Image.file(
                    _foto!,
                    height: 180,
                    width: double.infinity,
                    fit: BoxFit.cover,
                  ),
                ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _tomarFoto,
                icon: const Icon(Icons.camera_alt),
                label: Text(_foto == null ? 'Tomar foto' : 'Volver a tomar'),
              ),
              const SizedBox(height: 20),

              // Firma digital
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _label('Firma del receptor'),
                  TextButton.icon(
                    onPressed: () => _firmaController.clear(),
                    icon: const Icon(Icons.refresh, size: 18),
                    label: const Text('Limpiar'),
                  ),
                ],
              ),
              Container(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.grey.shade400),
                ),
                clipBehavior: Clip.antiAlias,
                child: Signature(
                  controller: _firmaController,
                  height: 180,
                  backgroundColor: Colors.white,
                ),
              ),
              const SizedBox(height: 20),

              // Observaciones
              _label('Observaciones'),
              TextField(
                controller: _obsController,
                maxLines: 3,
                decoration: const InputDecoration(
                  hintText: 'Notas sobre la entrega (opcional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),

              // Pago — solo relevante en una entrega exitosa
              if (_estado == EstadoEnvio.entregado) ...[
                _label('Modalidad de pago'),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'Origen', label: Text('Origen')),
                    ButtonSegment(value: 'Destino', label: Text('Destino')),
                    ButtonSegment(value: 'Pendiente', label: Text('Pendiente')),
                  ],
                  selected: {_modalidadPago},
                  onSelectionChanged:
                      (s) => setState(() => _modalidadPago = s.first),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _montoController,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'Monto (Bs.)',
                    prefixIcon: Icon(Icons.attach_money),
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
              ],

              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _enviando ? null : _confirmar,
                  icon:
                      _enviando
                          ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                          : const Icon(Icons.send),
                  label: Text(_enviando ? 'Enviando…' : 'Confirmar entrega'),
                  style: FilledButton.styleFrom(
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
        fontWeight: FontWeight.bold,
        color: AppColors.primary,
      ),
    ),
  );
}

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../navigation/role_navigation.dart';
import '../services/api_client.dart';
import '../theme/app_colors.dart';
import '../widgets/role_drawer.dart';

class SolicitarEnvioPage extends StatefulWidget {
  const SolicitarEnvioPage({super.key});

  @override
  State<SolicitarEnvioPage> createState() => _SolicitarEnvioPageState();
}

class _SolicitarEnvioPageState extends State<SolicitarEnvioPage> {
  final _formKey = GlobalKey<FormState>();
  final _contactoCtrl = TextEditingController();
  final _telefonoCtrl = TextEditingController();
  final _origenCtrl = TextEditingController();
  final _destinoCtrl = TextEditingController();
  final _pesoCtrl = TextEditingController(text: '1');
  final _montoCtrl = TextEditingController(text: '0');
  final _observacionesCtrl = TextEditingController();

  bool _saving = false;
  String _servicio = 'Estándar';
  String _tipoPago = 'Pendiente';
  String _tipoSolicitud = 'Envío';
  String _accountName = '';
  String _accountPhone = '';
  String _accountAddress = '';

  bool get _esRecojo => _tipoSolicitud == 'Recojo';

  @override
  void initState() {
    super.initState();
    _prefillCuenta();
  }

  @override
  void dispose() {
    _contactoCtrl.dispose();
    _telefonoCtrl.dispose();
    _origenCtrl.dispose();
    _destinoCtrl.dispose();
    _pesoCtrl.dispose();
    _montoCtrl.dispose();
    _observacionesCtrl.dispose();
    super.dispose();
  }

  Future<void> _prefillCuenta() async {
    const storage = FlutterSecureStorage();
    final data = await storage.readAll();
    Map<String, dynamic>? empresa;
    final rawEmpresa = data['empresa'];
    if (rawEmpresa != null && rawEmpresa.isNotEmpty && rawEmpresa != 'null') {
      try {
        empresa = Map<String, dynamic>.from(jsonDecode(rawEmpresa) as Map);
      } catch (_) {
        empresa = null;
      }
    }

    final name =
        _stringValue(empresa?['nombre']) ??
        _stringValue(data['nombre']) ??
        'Mi cuenta';
    final phone =
        _stringValue(empresa?['telefono']) ??
        _stringValue(data['telefono']) ??
        '';
    final address = _stringValue(empresa?['direccion']) ?? '';

    if (!mounted) return;
    setState(() {
      _accountName = name;
      _accountPhone = phone;
      _accountAddress = address;
      _applyAccountDefaults(force: true);
    });
  }

  void _selectTipoSolicitud(String tipo) {
    if (_tipoSolicitud == tipo) return;
    setState(() {
      final previous = _tipoSolicitud;
      _tipoSolicitud = tipo;
      if (_accountAddress.isEmpty) return;

      if (_tipoSolicitud == 'Envío') {
        if (_origenCtrl.text.trim().isEmpty ||
            _origenCtrl.text.trim() == _accountAddress) {
          _origenCtrl.text = _accountAddress;
        }
        if (previous == 'Recojo' &&
            _destinoCtrl.text.trim() == _accountAddress) {
          _destinoCtrl.clear();
        }
      } else {
        if (_destinoCtrl.text.trim().isEmpty ||
            _destinoCtrl.text.trim() == _accountAddress) {
          _destinoCtrl.text = _accountAddress;
        }
        if (previous == 'Envío' && _origenCtrl.text.trim() == _accountAddress) {
          _origenCtrl.clear();
        }
      }
    });
  }

  void _applyAccountDefaults({bool force = false}) {
    if (_accountAddress.isEmpty) return;
    if (_esRecojo) {
      if (force || _destinoCtrl.text.trim().isEmpty) {
        _destinoCtrl.text = _accountAddress;
      }
    } else if (force || _origenCtrl.text.trim().isEmpty) {
      _origenCtrl.text = _accountAddress;
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final contacto = _contactoCtrl.text.trim();
      final telefono = _telefonoCtrl.text.trim();
      final accountName =
          _accountName.trim().isNotEmpty ? _accountName.trim() : contacto;

      final body =
          _esRecojo
              ? {
                'tipo': 'Recojo',
                'remitente_nombre': contacto,
                'remitente_telefono': telefono,
                'destinatario_nombre': accountName,
                'destinatario_telefono': _accountPhone,
                'origen_direccion': _origenCtrl.text.trim(),
                'destino_direccion': _destinoCtrl.text.trim(),
              }
              : {
                'tipo': 'Envío',
                'remitente_nombre': accountName,
                'remitente_telefono': _accountPhone,
                'destinatario_nombre': contacto,
                'destinatario_telefono': telefono,
                'origen_direccion': _origenCtrl.text.trim(),
                'destino_direccion': _destinoCtrl.text.trim(),
              };

      final response = await ApiClient.instance.post(
        '/envios/api/envios/crear/',
        body: {
          ...body,
          'peso': _pesoCtrl.text.trim().replaceAll(',', '.'),
          'tipo_servicio': _servicio,
          'monto_pago': _montoCtrl.text.trim().replaceAll(',', '.'),
          'tipo_pago': _tipoPago,
          'observaciones': _observacionesCtrl.text.trim(),
        },
      );
      final data =
          response.body.isNotEmpty
              ? Map<String, dynamic>.from(jsonDecode(response.body) as Map)
              : <String, dynamic>{};
      if (!mounted) return;
      if (response.statusCode == 201) {
        await showDialog<void>(
          context: context,
          builder:
              (_) => AlertDialog(
                title: const Text('Solicitud registrada'),
                content: Text(
                  'Número de seguimiento: ${data['numero_seguimiento'] ?? 'sin número'}',
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Aceptar'),
                  ),
                ],
              ),
        );
        if (!mounted) return;
        Navigator.pushReplacementNamed(context, AppRoutes.envios);
      } else {
        _showError(data['error']?.toString() ?? 'No se pudo crear el envío.');
      }
    } catch (e) {
      if (mounted) _showError('Error de conexión: $e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: AppColors.error),
    );
  }

  @override
  Widget build(BuildContext context) {
    final contactLabel = _esRecojo ? 'Contacto de recojo' : 'Destinatario';
    final phoneLabel =
        _esRecojo ? 'Teléfono de recojo' : 'Teléfono destinatario';
    final originLabel =
        _esRecojo ? 'Dirección donde se recoge' : 'Dirección de origen';
    final destinationLabel =
        _esRecojo ? 'Dirección de entrega' : 'Dirección de destino';

    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.surfaceDark,
        title: const Text('Solicitar envío'),
      ),
      drawer: const RoleDrawer(current: AppDestination.solicitarEnvio),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _SolicitudHero(
                accountName: _accountName,
                accountAddress: _accountAddress,
              ),
              const SizedBox(height: 14),
              _ModeSelector(
                selected: _tipoSolicitud,
                onSelected: _selectTipoSolicitud,
              ),
              const SizedBox(height: 14),
              _AccountStrip(
                name: _accountName,
                phone: _accountPhone,
                address: _accountAddress,
                mode: _tipoSolicitud,
              ),
              const SizedBox(height: 14),
              _FormPanel(
                title: _esRecojo ? 'Datos del recojo' : 'Datos del envío',
                icon:
                    _esRecojo
                        ? Icons.assignment_return_outlined
                        : Icons.local_shipping_outlined,
                children: [
                  _field(
                    controller: _contactoCtrl,
                    label: contactLabel,
                    icon: Icons.person_outline,
                    isRequired: true,
                  ),
                  _field(
                    controller: _telefonoCtrl,
                    label: phoneLabel,
                    icon: Icons.phone_outlined,
                    keyboardType: TextInputType.phone,
                  ),
                  _field(
                    controller: _origenCtrl,
                    label: originLabel,
                    icon: Icons.my_location_outlined,
                    isRequired: true,
                    maxLines: 2,
                  ),
                  _field(
                    controller: _destinoCtrl,
                    label: destinationLabel,
                    icon: Icons.location_on_outlined,
                    isRequired: true,
                    maxLines: 2,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _FormPanel(
                title: 'Servicio y pago',
                icon: Icons.receipt_long_outlined,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: _field(
                          controller: _pesoCtrl,
                          label: 'Peso kg',
                          icon: Icons.scale_outlined,
                          keyboardType: TextInputType.number,
                          isRequired: true,
                          validator: _positiveNumber,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _field(
                          controller: _montoCtrl,
                          label: 'Monto Bs.',
                          icon: Icons.payments_outlined,
                          keyboardType: TextInputType.number,
                          validator: _zeroOrPositive,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _servicio,
                    decoration: const InputDecoration(
                      labelText: 'Tipo de servicio',
                      prefixIcon: Icon(Icons.flash_on_outlined),
                    ),
                    items: const [
                      DropdownMenuItem(
                        value: 'Estándar',
                        child: Text('Estándar'),
                      ),
                      DropdownMenuItem(
                        value: 'Express',
                        child: Text('Express'),
                      ),
                    ],
                    onChanged:
                        (value) =>
                            setState(() => _servicio = value ?? 'Estándar'),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _tipoPago,
                    decoration: const InputDecoration(
                      labelText: 'Modalidad de pago',
                      prefixIcon: Icon(Icons.receipt_long_outlined),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'Origen', child: Text('Origen')),
                      DropdownMenuItem(
                        value: 'Destino',
                        child: Text('Destino'),
                      ),
                      DropdownMenuItem(
                        value: 'Pendiente',
                        child: Text('Pendiente'),
                      ),
                    ],
                    onChanged:
                        (value) =>
                            setState(() => _tipoPago = value ?? 'Pendiente'),
                  ),
                  const SizedBox(height: 12),
                  _field(
                    controller: _observacionesCtrl,
                    label: 'Observaciones',
                    icon: Icons.notes_outlined,
                    maxLines: 3,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: _saving ? null : _submit,
                icon:
                    _saving
                        ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                        : const Icon(Icons.send_outlined),
                label: Text(_saving ? 'Registrando...' : 'Registrar solicitud'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _field({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    bool isRequired = false,
    int maxLines = 1,
    TextInputType? keyboardType,
    String? Function(String?)? validator,
  }) {
    return TextFormField(
      controller: controller,
      maxLines: maxLines,
      keyboardType: keyboardType,
      decoration: InputDecoration(labelText: label, prefixIcon: Icon(icon)),
      validator:
          validator ??
          (value) {
            if (isRequired && (value == null || value.trim().isEmpty)) {
              return 'Campo obligatorio';
            }
            return null;
          },
    );
  }

  String? _positiveNumber(String? value) {
    if (value == null || value.trim().isEmpty) return 'Campo obligatorio';
    final number = double.tryParse(value.replaceAll(',', '.'));
    if (number == null || number <= 0) return 'Debe ser mayor a 0';
    return null;
  }

  String? _zeroOrPositive(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    final number = double.tryParse(value.replaceAll(',', '.'));
    if (number == null || number < 0) return 'Debe ser 0 o mayor';
    return null;
  }

  String? _stringValue(dynamic value) {
    final text = value?.toString().trim();
    return text == null || text.isEmpty ? null : text;
  }
}

class _SolicitudHero extends StatelessWidget {
  final String accountName;
  final String accountAddress;

  const _SolicitudHero({
    required this.accountName,
    required this.accountAddress,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: AppColors.primaryGradient,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withValues(alpha: 0.24),
            blurRadius: 24,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Row(
        children: [
          const CircleAvatar(
            radius: 31,
            backgroundColor: Colors.white,
            child: Icon(
              Icons.add_location_alt_outlined,
              color: AppColors.primary,
              size: 34,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Nueva solicitud',
                  style: TextStyle(color: Colors.white70, fontSize: 13),
                ),
                const SizedBox(height: 4),
                Text(
                  accountName.isNotEmpty ? accountName : 'Cliente',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                if (accountAddress.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    accountAddress,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ModeSelector extends StatelessWidget {
  final String selected;
  final ValueChanged<String> onSelected;

  const _ModeSelector({required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _ModeOption(
            value: 'Envío',
            selected: selected == 'Envío',
            icon: Icons.local_shipping_outlined,
            title: 'Envío',
            subtitle: 'Sale desde tu cuenta',
            onTap: onSelected,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _ModeOption(
            value: 'Recojo',
            selected: selected == 'Recojo',
            icon: Icons.assignment_return_outlined,
            title: 'Recojo',
            subtitle: 'Vuelve a tu cuenta',
            onTap: onSelected,
          ),
        ),
      ],
    );
  }
}

class _ModeOption extends StatelessWidget {
  final String value;
  final bool selected;
  final IconData icon;
  final String title;
  final String subtitle;
  final ValueChanged<String> onTap;

  const _ModeOption({
    required this.value,
    required this.selected,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.primary : AppColors.textTertiary;
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => onTap(value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color:
              selected
                  ? AppColors.primary.withValues(alpha: 0.18)
                  : AppColors.surfaceDark,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color:
                selected
                    ? AppColors.primary
                    : AppColors.primary.withValues(alpha: 0.16),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color),
            const SizedBox(height: 10),
            Text(
              title,
              style: TextStyle(
                color:
                    selected ? AppColors.textPrimary : AppColors.textSecondary,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              subtitle,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: AppColors.textTertiary,
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AccountStrip extends StatelessWidget {
  final String name;
  final String phone;
  final String address;
  final String mode;

  const _AccountStrip({
    required this.name,
    required this.phone,
    required this.address,
    required this.mode,
  });

  @override
  Widget build(BuildContext context) {
    final anchor = mode == 'Recojo' ? 'destino guardado' : 'origen guardado';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.secondary.withValues(alpha: 0.11),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.secondary.withValues(alpha: 0.28)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.verified_outlined, color: AppColors.secondary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name.isNotEmpty ? name : 'Datos de la cuenta',
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 5),
                Text(
                  [
                    if (phone.isNotEmpty) phone,
                    if (address.isNotEmpty) address,
                  ].join(' • '),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  'Se usa como $anchor de esta solicitud.',
                  style: const TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FormPanel extends StatelessWidget {
  final String title;
  final IconData icon;
  final List<Widget> children;

  const _FormPanel({
    required this.title,
    required this.icon,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceDark,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.14)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: AppColors.primary),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          for (var index = 0; index < children.length; index++) ...[
            children[index],
            if (index != children.length - 1) const SizedBox(height: 12),
          ],
        ],
      ),
    );
  }
}

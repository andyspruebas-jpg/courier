from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.utils import timezone

from envios.models import (
    Entrega,
    Envio,
    HistorialEnvio,
    Incidente,
    NotificacionEnvio,
    ReasignacionEnvio,
)
from pagos.models import MetodoPago, Pago
from rutas.models import Ruta, RutaParada
from rutas.ml_models import MLTrainingState
from rutas.services.google_maps import fallback_distance
from usuarios.models import Empresa, PerfilMensajero, Rol, UbicacionMensajero, Usuario
from zonas.models import Zona


ADMIN_PASSWORD = "CbeAdmin2026!"
COURIER_PASSWORD = "CbeRuta2026!"
CLIENT_PASSWORD = "CbeCliente2026!"
SEED_PREFIX = "OPERACION"


def encode_polyline(points: Iterable[tuple[float, float]]) -> str:
    result: list[str] = []
    prev_lat = 0
    prev_lng = 0

    def encode_value(value: int) -> None:
        value = ~(value << 1) if value < 0 else value << 1
        while value >= 0x20:
            result.append(chr((0x20 | (value & 0x1F)) + 63))
            value >>= 5
        result.append(chr(value + 63))

    for lat, lng in points:
        lat_i = int(round(lat * 1e5))
        lng_i = int(round(lng * 1e5))
        encode_value(lat_i - prev_lat)
        encode_value(lng_i - prev_lng)
        prev_lat = lat_i
        prev_lng = lng_i

    return "".join(result)


def route_totals(points: list[tuple[float, float]]) -> tuple[float, float]:
    distance = 0.0
    duration = 0.0
    for start, end in zip(points, points[1:]):
        dur, dist = fallback_distance(start[0], start[1], end[0], end[1])
        duration += float(dur or 0)
        distance += float(dist or 0)
    return round(distance, 2), round(duration, 2)


class Command(BaseCommand):
    help = "Carga datos locales de prueba para Courier Bolivian Express."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Elimina primero los datos creados por este comando.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.reset_seeded_data()

        companies = self.create_companies()
        admin_role, _ = Rol.objects.get_or_create(nombre="Administrador")
        courier_role, _ = Rol.objects.get_or_create(nombre="Mensajero")
        client_role, _ = Rol.objects.get_or_create(nombre="Cliente")

        admin = self.upsert_usuario(
            email="admin@cbe.com",
            nombre="Administrador CBE",
            telefono="77777777",
            rol=admin_role,
            password=ADMIN_PASSWORD,
            empresa=companies["cbe"],
        )

        couriers = [
            self.upsert_usuario(
                email="juan@cbe.com",
                nombre="Juan Perez",
                telefono="70123456",
                rol=courier_role,
                password=COURIER_PASSWORD,
                empresa=companies["cbe"],
                lat="-16.498700000000000",
                lng="-68.105000000000000",
                vehiculo="Moto Honda XR 150 - placa 4821CBE",
                zona=companies["zones"]["Local - Centro La Paz"],
                disponible=True,
            ),
            self.upsert_usuario(
                email="carlos@cbe.com",
                nombre="Carlos Mamani",
                telefono="70234567",
                rol=courier_role,
                password=COURIER_PASSWORD,
                empresa=companies["cbe"],
                lat="-16.503500000000000",
                lng="-68.119800000000000",
                vehiculo="Vagoneta Suzuki APV - placa 7312CBE",
                zona=companies["zones"]["Local - Zona Sur"],
                disponible=True,
            ),
            self.upsert_usuario(
                email="luis@cbe.com",
                nombre="Luis Gutierrez",
                telefono="70345678",
                rol=courier_role,
                password=COURIER_PASSWORD,
                empresa=companies["cbe"],
                lat="-16.485100000000000",
                lng="-68.092400000000000",
                vehiculo="Moto Yamaha FZ - placa 9054CBE",
                zona=companies["zones"]["Local - El Alto"],
                disponible=False,
            ),
        ]

        clients = [
            self.upsert_usuario(
                email="farmacia@cbe.com",
                nombre="Farmacia San Miguel",
                telefono="72001010",
                rol=client_role,
                password=CLIENT_PASSWORD,
                empresa=companies["farmacia"],
            ),
            self.upsert_usuario(
                email="textiles@cbe.com",
                nombre="Textiles Andinos",
                telefono="72002020",
                rol=client_role,
                password=CLIENT_PASSWORD,
                empresa=companies["textiles"],
            ),
        ]

        self.ensure_django_admin()
        methods = self.create_payment_methods()

        shipments = self.create_shipments(admin, couriers, clients, companies["zones"])
        self.ensure_existing_records_complete(admin, couriers, methods, companies["zones"])
        self.create_payments(shipments, methods, admin)
        self.create_deliveries_and_history(shipments, admin)
        self.create_reassignments(shipments, couriers, admin)
        self.create_locations(couriers)
        self.create_route_summaries(couriers)
        MLTrainingState.objects.get_or_create(id=1)
        cache.clear()

        self.stdout.write(self.style.SUCCESS("Datos locales cargados correctamente."))
        self.stdout.write(f"Panel web: admin@cbe.com / {ADMIN_PASSWORD}")
        self.stdout.write(f"Mensajeros: juan@cbe.com, carlos@cbe.com, luis@cbe.com / {COURIER_PASSWORD}")
        self.stdout.write(
            "Resumen: "
            f"{Usuario.objects.count()} usuarios, "
            f"{Envio.objects.count()} envios, "
            f"{Entrega.objects.count()} entregas, "
            f"{Ruta.objects.count()} rutas."
        )

    def reset_seeded_data(self):
        seeded_envios = Envio.objects.filter(observaciones__startswith=f"{SEED_PREFIX}:")
        RutaParada.objects.filter(envio__in=seeded_envios).delete()
        ReasignacionEnvio.objects.filter(envio__in=seeded_envios).delete()
        NotificacionEnvio.objects.filter(envio__in=seeded_envios).delete()
        Entrega.objects.filter(envio__in=seeded_envios).delete()
        Pago.objects.filter(envio__in=seeded_envios).delete()
        HistorialEnvio.objects.filter(envio__in=seeded_envios).delete()
        Incidente.objects.filter(envio__in=seeded_envios).delete()
        Ruta.objects.filter(mensajero__email__endswith="@cbe.com").delete()
        seeded_envios.delete()
        UbicacionMensajero.objects.filter(mensajero__email__endswith="@cbe.com").delete()
        PerfilMensajero.objects.filter(usuario__email__endswith="@cbe.com").delete()
        Usuario.objects.filter(email__endswith="@cbe.com").delete()
        Zona.objects.filter(nombre__startswith="Local - ").delete()
        MetodoPago.objects.filter(nombre__in=["Efectivo", "QR", "Transferencia bancaria"]).delete()
        Empresa.objects.filter(nit__in=["1004493029", "1029384756", "1092837465"]).delete()

    def upsert_usuario(
        self,
        *,
        email: str,
        nombre: str,
        telefono: str,
        rol: Rol,
        password: str,
        empresa: Empresa | None = None,
        lat: str | None = None,
        lng: str | None = None,
        vehiculo: str | None = None,
        zona: Zona | None = None,
        disponible: bool = True,
    ) -> Usuario:
        usuario, _ = Usuario.objects.update_or_create(
            email=email,
            defaults={
                "nombre": nombre,
                "telefono": telefono,
                "rol": rol,
                "empresa": empresa,
                "is_active": True,
            },
        )
        usuario.set_password(password)
        usuario.save(update_fields=["contrasena"])

        if lat is not None and lng is not None:
            PerfilMensajero.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "latitud": Decimal(lat),
                    "longitud": Decimal(lng),
                    "vehiculo": vehiculo,
                    "zona_cobertura": zona,
                    "disponible": disponible,
                },
            )
        return usuario

    def ensure_django_admin(self):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@cbe.com", "is_staff": True, "is_superuser": True},
        )
        user.email = "admin@cbe.com"
        user.is_staff = True
        user.is_superuser = True
        user.set_password(ADMIN_PASSWORD)
        user.save()

    def create_companies(self) -> dict[str, Empresa | dict[str, Zona]]:
        zones = self.create_zones()
        companies = {
            "cbe": Empresa.objects.update_or_create(
                nit="1004493029",
                defaults={
                    "nombre": "Courier Bolivian Express",
                    "direccion": "Av. Arce #1200, La Paz",
                    "contacto": "Gabriel Boyan",
                    "telefono": "77777777",
                    "email": "admin@cbe.com",
                    "activa": True,
                },
            )[0],
            "farmacia": Empresa.objects.update_or_create(
                nit="1029384756",
                defaults={
                    "nombre": "Farmacia San Miguel",
                    "direccion": "Calle 21 de Calacoto #45",
                    "contacto": "Dra. Valeria Rojas",
                    "telefono": "72001010",
                    "email": "farmacia@cbe.com",
                    "activa": True,
                },
            )[0],
            "textiles": Empresa.objects.update_or_create(
                nit="1092837465",
                defaults={
                    "nombre": "Textiles Andinos SRL",
                    "direccion": "Av. Buenos Aires #880",
                    "contacto": "Marcelo Flores",
                    "telefono": "72002020",
                    "email": "textiles@cbe.com",
                    "activa": True,
                },
            )[0],
        }
        companies["zones"] = zones
        return companies

    def create_zones(self) -> dict[str, Zona]:
        zones = {
            "Local - Centro La Paz": [
                [-16.5012, -68.1432],
                [-16.4889, -68.1398],
                [-16.4899, -68.1237],
                [-16.5059, -68.1248],
                [-16.5012, -68.1432],
            ],
            "Local - Zona Sur": [
                [-16.5362, -68.1014],
                [-16.5057, -68.0919],
                [-16.5024, -68.1315],
                [-16.5351, -68.1297],
                [-16.5362, -68.1014],
            ],
            "Local - El Alto": [
                [-16.5295, -68.2051],
                [-16.4872, -68.1987],
                [-16.4868, -68.1642],
                [-16.5352, -68.1704],
                [-16.5295, -68.2051],
            ],
        }
        created: dict[str, Zona] = {}
        for name, area in zones.items():
            zone, _ = Zona.objects.get_or_create(nombre=name, defaults={"area": "[]"})
            zone.set_area_from_list(area)
            zone.save(update_fields=["area"])
            created[name] = zone
        return created

    def create_payment_methods(self) -> dict[str, MetodoPago]:
        return {
            name: MetodoPago.objects.get_or_create(nombre=name)[0]
            for name in ["Efectivo", "QR", "Transferencia bancaria"]
        }

    def create_shipments(
        self,
        admin: Usuario,
        couriers: list[Usuario],
        clients: list[Usuario],
        zones: dict[str, Zona],
    ) -> list[Envio]:
        shipment_rows = [
            ("LP-001", "Envío", couriers[0], clients[0], "Local - Centro La Paz", "Av. 6 de Agosto #123", "Av. Tejada Sorzano #25", "Maria Lopez", "72668368", "1.90", "Express", "En Ruta", "22.26", "Origen", "-16.518319", "-68.132073", "-16.490863", "-68.177538"),
            ("LP-002", "Envío", couriers[0], clients[1], "Local - El Alto", "Calle Comercio #45", "Calle Colombia #47", "Jose Quispe", "72564345", "0.92", "Estándar", "Pendiente", "95.31", "Origen", "-16.524068", "-68.198927", "-16.495807", "-68.187244"),
            ("LP-003", "Recojo", couriers[0], clients[0], "Local - El Alto", "Av. Arce #501", "Av. Buenos Aires #600", "Ana Gutierrez", "72818624", "0.99", "Express", "Entregado", "51.18", "Destino", "-16.525536", "-68.133080", "-16.524533", "-68.164838"),
            ("LP-004", "Envío", couriers[1], clients[0], "Local - Zona Sur", "Zona Sur #25", "Calle 16 de Obrajes #70", "Mario Choque", "72167347", "0.61", "Estándar", "Pendiente", "38.66", "Destino", "-16.524028", "-68.174206", "-16.514180", "-68.104374"),
            ("LP-005", "Envío", couriers[1], clients[1], "Local - Zona Sur", "Av. Montes #789", "Av. Kollasuyo #210", "Rosa Fernandez", "72637161", "1.16", "Express", "Reintentado", "57.59", "Origen", "-16.509726", "-68.191988", "-16.499176", "-68.110777"),
            ("LP-006", "Recojo", couriers[1], clients[1], "Local - Centro La Paz", "Calle Loayza #56", "Calle Linares #40", "Pedro Perez", "72490576", "0.83", "Estándar", "Rechazado", "84.65", "Origen", "-16.506908", "-68.191497", "-16.529446", "-68.145198"),
            ("LP-007", "Envío", couriers[2], clients[0], "Local - El Alto", "Av. Busch #789", "Av. del Policia #25", "Lucia Rojas", "72462735", "1.05", "Express", "Pendiente", "77.56", "Origen", "-16.506495", "-68.196453", "-16.501145", "-68.161645"),
            ("LP-008", "Envío", couriers[2], clients[1], "Local - El Alto", "Calle 21 de Calacoto #11", "Calle 8 de Calacoto #10", "Diego Vargas", "72115877", "1.89", "Estándar", "Fallido", "70.79", "Destino", "-16.528930", "-68.196451", "-16.507424", "-68.169584"),
            ("LP-009", "Recojo", couriers[2], clients[0], "Local - Zona Sur", "Av. Camacho #88", "Av. Costanera #100", "Carmen Flores", "72623862", "3.21", "Estándar", "Entregado", "52.90", "Destino", "-16.490272", "-68.103991", "-16.529736", "-68.102864"),
            ("LP-010", "Envío", couriers[0], clients[1], "Local - Centro La Paz", "Sucursal Miraflores #12", "Hospital Obrero, bloque B", "Dr. Pablo Vargas", "72009988", "0.35", "Express", "Pendiente", "34.50", "Pendiente", "-16.497800", "-68.124510", "-16.497060", "-68.119930"),
        ]

        shipments: list[Envio] = []
        for row in shipment_rows:
            (
                key,
                tipo,
                courier,
                sender,
                zone_name,
                origin,
                destination,
                recipient,
                phone,
                weight,
                service,
                status,
                amount,
                payment_type,
                lat_origin,
                lng_origin,
                lat_destination,
                lng_destination,
            ) = row
            envio = self.upsert_envio(
                key,
                {
                    "numero_seguimiento": f"CBE-{key.replace('-', '')}",
                    "tipo": tipo,
                    "remitente": sender,
                    "remitente_nombre": sender.nombre,
                    "remitente_telefono": sender.telefono or "",
                    "destinatario_nombre": recipient,
                    "destinatario_telefono": phone,
                    "origen_direccion": origin,
                    "destino_direccion": destination,
                    "peso": Decimal(weight),
                    "tipo_servicio": service,
                    "estado": status,
                    "observaciones": f"{SEED_PREFIX}:{key}|Envío histórico operativo",
                    "latitud_origen": Decimal(lat_origin),
                    "longitud_origen": Decimal(lng_origin),
                    "latitud_destino": Decimal(lat_destination),
                    "longitud_destino": Decimal(lng_destination),
                    "monto_pago": Decimal(amount),
                    "tipo_pago": payment_type,
                    "mensajero": courier,
                    "zona": zones.get(zone_name),
                },
            )
            shipments.append(envio)
        return shipments

    def upsert_envio(self, key: str, defaults: dict) -> Envio:
        envio = Envio.objects.filter(observaciones__startswith=f"{SEED_PREFIX}:{key}|").first()
        if envio:
            for field, value in defaults.items():
                setattr(envio, field, value)
            envio.save()
            return envio
        return Envio.objects.create(**defaults)

    def create_payments(
        self,
        shipments: list[Envio],
        methods: dict[str, MetodoPago],
        admin: Usuario | None = None,
    ):
        method_names = list(methods)
        for idx, envio in enumerate(shipments):
            Pago.objects.update_or_create(
                envio=envio,
                defaults={
                    "metodo_pago": methods[method_names[idx % len(method_names)]],
                    "monto": envio.monto_pago or Decimal("0.00"),
                    "estado": "Pagado" if envio.estado == "Entregado" else "Pendiente",
                    "registrado_por": admin,
                },
            )

    def create_deliveries_and_history(self, shipments: list[Envio], admin: Usuario | None = None):
        for envio in shipments:
            HistorialEnvio.objects.get_or_create(
                envio=envio,
                tipo_evento="Creado",
                defaults={
                    "ubicacion_latitud": envio.latitud_origen,
                    "ubicacion_longitud": envio.longitud_origen,
                    "usuario": envio.remitente or admin,
                    "observaciones": "Solicitud registrada desde empresa cliente.",
                },
            )
            HistorialEnvio.objects.get_or_create(
                envio=envio,
                tipo_evento="Asignado",
                defaults={
                    "ubicacion_latitud": envio.latitud_origen,
                    "ubicacion_longitud": envio.longitud_origen,
                    "usuario": admin,
                    "observaciones": f"Asignado a {envio.mensajero.nombre if envio.mensajero else 'sin mensajero'}.",
                },
            )
            if envio.estado in {"En Ruta", "Entregado", "Rechazado", "Fallido", "Reintentado"}:
                HistorialEnvio.objects.get_or_create(
                    envio=envio,
                    tipo_evento="Recogido",
                    defaults={
                        "ubicacion_latitud": envio.latitud_origen,
                        "ubicacion_longitud": envio.longitud_origen,
                        "usuario": envio.mensajero or admin,
                        "observaciones": "Paquete recogido para ruta asignada.",
                    },
                )
            if envio.estado == "Entregado":
                Entrega.objects.update_or_create(
                    envio=envio,
                    defaults={
                        "mensajero": envio.mensajero,
                        "estado": "Entregado",
                        "pagado": True,
                        "observaciones": "Entrega completada con conformidad del receptor.",
                    },
                )
                HistorialEnvio.objects.get_or_create(
                    envio=envio,
                    tipo_evento="Entregado",
                    defaults={
                        "ubicacion_latitud": envio.latitud_destino,
                        "ubicacion_longitud": envio.longitud_destino,
                        "usuario": envio.mensajero or admin,
                        "observaciones": "Entrega registrada en destino.",
                    },
                )
            elif envio.estado in {"Rechazado", "Fallido"}:
                Entrega.objects.update_or_create(
                    envio=envio,
                    defaults={
                        "mensajero": envio.mensajero,
                        "estado": "Rechazado",
                        "pagado": False,
                        "observaciones": "Entrega rechazada o fallida por incidencia operativa.",
                    },
                )
                Incidente.objects.get_or_create(
                    envio=envio,
                    defaults={
                        "tipo": "Otro",
                        "descripcion": "Cliente no disponible durante la visita de prueba.",
                    },
                )
                HistorialEnvio.objects.get_or_create(
                    envio=envio,
                    tipo_evento="Incidente",
                    defaults={
                        "ubicacion_latitud": envio.latitud_destino,
                        "ubicacion_longitud": envio.longitud_destino,
                        "usuario": envio.mensajero or admin,
                        "observaciones": "Visita fallida: cliente no disponible.",
                    },
                )
            elif envio.estado == "Reintentado":
                Incidente.objects.get_or_create(
                    envio=envio,
                    defaults={
                        "tipo": "Retraso",
                        "descripcion": "Reintento programado por tráfico y ventana de entrega vencida.",
                    },
                )
                HistorialEnvio.objects.get_or_create(
                    envio=envio,
                    tipo_evento="Incidente",
                    defaults={
                        "ubicacion_latitud": envio.latitud_destino,
                        "ubicacion_longitud": envio.longitud_destino,
                        "usuario": envio.mensajero or admin,
                        "observaciones": "Reintento programado para la siguiente ruta.",
                    },
                )

            NotificacionEnvio.objects.get_or_create(
                envio=envio,
                asunto="Actualización de envío",
                defaults={
                    "destinatario": envio.destinatario_telefono or envio.destinatario_nombre,
                    "canal": "sistema",
                    "mensaje": f"El envío {envio.numero_seguimiento} está en estado {envio.estado}.",
                    "estado": "enviada" if envio.estado in {"Entregado", "En Ruta"} else "pendiente",
                    "enviado_en": timezone.now() if envio.estado in {"Entregado", "En Ruta"} else None,
                },
            )

    def create_reassignments(self, shipments: list[Envio], couriers: list[Usuario], admin: Usuario):
        target = next((envio for envio in shipments if "LP-005" in envio.observaciones), None)
        if not target:
            return
        motivo = f"{SEED_PREFIX}: ajuste por saturación de zona"
        if ReasignacionEnvio.objects.filter(envio=target, motivo__startswith=SEED_PREFIX).exists():
            return
        ReasignacionEnvio.objects.create(
            envio=target,
            mensajero_anterior=couriers[0],
            mensajero_nuevo=target.mensajero,
            responsable=admin,
            motivo=motivo,
        )
        HistorialEnvio.objects.get_or_create(
            envio=target,
            tipo_evento="Reasignado",
            defaults={
                "usuario": admin,
                "observaciones": f"Reasignado a {target.mensajero.nombre} por carga de trabajo.",
            },
        )

    def ensure_existing_records_complete(
        self,
        admin: Usuario,
        couriers: list[Usuario],
        methods: dict[str, MetodoPago],
        zones: dict[str, Zona],
    ):
        method = methods["Efectivo"]
        zone_cycle = list(zones.values())
        for idx, envio in enumerate(Envio.objects.all().order_by("id")):
            changed_fields: list[str] = []
            if envio.mensajero_id is None and couriers:
                envio.mensajero = couriers[idx % len(couriers)]
                changed_fields.append("mensajero")
            if envio.zona_id is None and zone_cycle:
                envio.zona = zone_cycle[idx % len(zone_cycle)]
                changed_fields.append("zona")
            if envio.tipo_pago in {None, ""}:
                envio.tipo_pago = "Pendiente"
                changed_fields.append("tipo_pago")
            if envio.monto_pago is None:
                envio.monto_pago = Decimal("25.00")
                changed_fields.append("monto_pago")
            if changed_fields:
                envio.save(update_fields=changed_fields)

            Pago.objects.get_or_create(
                envio=envio,
                defaults={
                    "metodo_pago": method,
                    "monto": envio.monto_pago or Decimal("0.00"),
                    "estado": "Pagado" if envio.estado == "Entregado" else "Pendiente",
                    "registrado_por": admin,
                },
            )
            HistorialEnvio.objects.get_or_create(
                envio=envio,
                tipo_evento="Creado",
                defaults={
                    "ubicacion_latitud": envio.latitud_origen,
                    "ubicacion_longitud": envio.longitud_origen,
                    "usuario": envio.remitente or admin,
                    "observaciones": "Evento inicial agregado al historial operativo.",
                },
            )
            if envio.mensajero_id:
                HistorialEnvio.objects.get_or_create(
                    envio=envio,
                    tipo_evento="Asignado",
                    defaults={
                        "ubicacion_latitud": envio.latitud_origen,
                        "ubicacion_longitud": envio.longitud_origen,
                        "usuario": admin,
                        "observaciones": f"Asignado a {envio.mensajero.nombre}.",
                    },
                )
            if envio.estado == "Entregado" and not Entrega.objects.filter(envio=envio).exists():
                Entrega.objects.create(
                    envio=envio,
                    mensajero=envio.mensajero or couriers[0],
                    estado="Entregado",
                    pagado=True,
                    observaciones="Entrega histórica completada.",
                )
            if not NotificacionEnvio.objects.filter(envio=envio).exists():
                NotificacionEnvio.objects.create(
                    envio=envio,
                    destinatario=envio.destinatario_telefono or envio.destinatario_nombre,
                    canal="sistema",
                    asunto="Estado de envío",
                    mensaje=f"El envío {envio.numero_seguimiento} se encuentra en estado {envio.estado}.",
                    estado="pendiente",
                )

    def create_locations(self, couriers: list[Usuario]):
        for courier in couriers:
            profile = courier.perfil_mensajero
            if not UbicacionMensajero.objects.filter(mensajero=courier).exists():
                UbicacionMensajero.objects.create(
                    mensajero=courier,
                    latitud=profile.latitud,
                    longitud=profile.longitud,
                )

    def create_route_summaries(self, couriers: list[Usuario]):
        try:
            from rutas.signals import rutas_infer_delay, rutas_set_coords_and_google_estimate

            pre_save.disconnect(rutas_set_coords_and_google_estimate, sender=Ruta)
            post_save.disconnect(rutas_infer_delay, sender=Ruta)
        except Exception:
            pass

        for courier in couriers:
            profile = courier.perfil_mensajero
            points = [(float(profile.latitud), float(profile.longitud))]
            stops: list[Envio] = []
            for envio in Envio.objects.filter(
                mensajero=courier,
                estado__in=["Pendiente", "En Ruta", "Reintentado"],
            ).order_by("id"):
                if envio.tipo == "Recojo":
                    if envio.latitud_origen is None or envio.longitud_origen is None:
                        continue
                    points.append((float(envio.latitud_origen), float(envio.longitud_origen)))
                else:
                    if envio.latitud_destino is None or envio.longitud_destino is None:
                        continue
                    points.append((float(envio.latitud_destino), float(envio.longitud_destino)))
                stops.append(envio)

            if len(points) < 2:
                continue

            distance, duration = route_totals(points)
            now = timezone.now()
            polyline = encode_polyline(points)
            defaults = {
                "latitud_inicio": Decimal(str(points[0][0])),
                "longitud_inicio": Decimal(str(points[0][1])),
                "latitud_fin": Decimal(str(points[-1][0])),
                "longitud_fin": Decimal(str(points[-1][1])),
                "polyline_google": polyline,
                "polyline_algo": polyline,
                "distancia_google_m": distance,
                "duracion_google_min": duration,
                "distancia_algo_m": round(distance * 0.96, 2),
                "duracion_algo_min": round(duration * 0.92, 2),
                "retraso_estimado": round((duration * 0.92) - duration, 2),
                "duracion_estimada": duration,
                "duracion_real": round(duration * 1.08, 2),
                "started_at": now - timedelta(minutes=round(duration * 1.08)),
                "finished_at": now,
            }
            ruta = Ruta.objects.filter(mensajero=courier, envio__isnull=True).first()
            if ruta:
                for field, value in defaults.items():
                    setattr(ruta, field, value)
                ruta.save()
            else:
                ruta = Ruta.objects.create(mensajero=courier, envio=None, **defaults)

            RutaParada.objects.filter(ruta=ruta).delete()
            elapsed = 0.0
            previous = points[0]
            for order, envio in enumerate(stops, start=1):
                current = points[order]
                leg_duration, leg_distance = fallback_distance(
                    previous[0],
                    previous[1],
                    current[0],
                    current[1],
                )
                elapsed += float(leg_duration or 0)
                RutaParada.objects.create(
                    ruta=ruta,
                    envio=envio,
                    orden=order,
                    eta_min=round(elapsed, 2),
                    distancia_desde_anterior_m=round(float(leg_distance or 0), 2),
                )
                envio.orden_ruta = order
                envio.eta_min = round(elapsed, 2)
                envio.ruta_id = ruta.id
                envio.save(update_fields=["orden_ruta", "eta_min", "ruta_id"])
                previous = current

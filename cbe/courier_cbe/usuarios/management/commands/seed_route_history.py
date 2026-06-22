from __future__ import annotations

import math
import random
import re
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from rutas.models import Ruta
from usuarios.management.commands.import_legacy_dump import (
    parse_datetime_literal,
    preserve_explicit_auto_timestamps,
)
from usuarios.models import PerfilMensajero, UbicacionMensajero, Usuario
from zonas.models import Zona


DEFAULT_DUMP_PATH = Path("/Users/gabrielboyan/Downloads/solo_datos (1).sql")
LEGACY_LOCATION_RE = re.compile(
    r"^INSERT INTO public\.usuarios_ubicacionmensajero "
    r"\(id, latitud, longitud, fecha_hora, mensajero_id\) VALUES "
    r"\((?P<id>\d+), (?P<lat>[^,]+), (?P<lng>[^,]+), "
    r"'(?P<dt>[^']+)', (?P<mensajero_id>\d+)\);$"
)

ROAD_CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "road_route_cache.json"
DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

# These coordinates are only control stops. The command asks Google Directions
# for the real road geometry between them, then stores the decoded street path.
ZONE_ROUTE_SPECS: dict[str, list[list[tuple[float, float]]]] = {
    "Sopocachi Alto": [
        [(-16.50755, -68.12815), (-16.50505, -68.13035), (-16.50305, -68.13285), (-16.50035, -68.13415), (-16.49795, -68.13220)],
        [(-16.50485, -68.12690), (-16.50290, -68.12975), (-16.50085, -68.13165), (-16.49925, -68.13390), (-16.50195, -68.13535)],
        [(-16.50620, -68.12485), (-16.50415, -68.12755), (-16.50235, -68.13005), (-16.50065, -68.13275), (-16.49880, -68.13520)],
    ],
    "Sopocachi Bajo": [
        [(-16.51225, -68.12285), (-16.50925, -68.12415), (-16.50655, -68.12595), (-16.50415, -68.12735), (-16.50185, -68.12940)],
        [(-16.51095, -68.12060), (-16.50805, -68.12280), (-16.50505, -68.12485), (-16.50230, -68.12705), (-16.50035, -68.12925)],
    ],
    "Miraflores Alto": [
        [(-16.49795, -68.11315), (-16.49595, -68.11135), (-16.49365, -68.10945), (-16.49155, -68.10715), (-16.48945, -68.10475)],
        [(-16.50105, -68.11625), (-16.49855, -68.11410), (-16.49605, -68.11180), (-16.49335, -68.10910), (-16.49070, -68.10655)],
        [(-16.49915, -68.11805), (-16.49665, -68.11580), (-16.49420, -68.11335), (-16.49175, -68.11110), (-16.48930, -68.10875)],
    ],
    "Miraflores Bajo": [
        [(-16.50325, -68.11995), (-16.50065, -68.11845), (-16.49780, -68.11695), (-16.49515, -68.11515), (-16.49275, -68.11350)],
        [(-16.50195, -68.12175), (-16.49945, -68.11985), (-16.49665, -68.11810), (-16.49410, -68.11630), (-16.49185, -68.11425)],
    ],
    "San Pedro": [
        [(-16.49965, -68.13695), (-16.49815, -68.13425), (-16.49705, -68.13170), (-16.49595, -68.12880), (-16.49485, -68.12620)],
        [(-16.50125, -68.13880), (-16.49965, -68.13605), (-16.49775, -68.13310), (-16.49620, -68.13020), (-16.49465, -68.12725)],
        [(-16.49715, -68.13935), (-16.49615, -68.13650), (-16.49535, -68.13365), (-16.49435, -68.13090), (-16.49325, -68.12830)],
    ],
    "Zona Sur - Obrajes": [
        [(-16.51525, -68.11605), (-16.51895, -68.11325), (-16.52225, -68.11025), (-16.52585, -68.10805), (-16.52935, -68.10570)],
        [(-16.51645, -68.11925), (-16.51995, -68.11610), (-16.52315, -68.11275), (-16.52620, -68.10950), (-16.52990, -68.10695)],
        [(-16.52055, -68.11840), (-16.52265, -68.11505), (-16.52530, -68.11180), (-16.52805, -68.10910), (-16.53110, -68.10645)],
    ],
    "Zona Sur - Calacoto": [
        [(-16.53475, -68.10095), (-16.53815, -68.09730), (-16.54155, -68.09395), (-16.54435, -68.09020), (-16.54510, -68.08625)],
        [(-16.53820, -68.10215), (-16.54130, -68.09840), (-16.54390, -68.09475), (-16.54640, -68.09120), (-16.54810, -68.08765)],
        [(-16.53655, -68.09615), (-16.53970, -68.09325), (-16.54280, -68.09055), (-16.54545, -68.08780), (-16.54815, -68.08500)],
    ],
    "El Alto - Centro": [
        [(-16.50065, -68.17175), (-16.50105, -68.16625), (-16.50175, -68.16065), (-16.50235, -68.15515), (-16.50320, -68.14960)],
        [(-16.49695, -68.16895), (-16.49915, -68.16535), (-16.50125, -68.16140), (-16.50325, -68.15755), (-16.50525, -68.15375)],
        [(-16.50445, -68.17015), (-16.50315, -68.16500), (-16.50220, -68.15990), (-16.50165, -68.15475), (-16.50125, -68.14945)],
    ],
    "Local - Centro La Paz": [
        [(-16.49720, -68.13710), (-16.49635, -68.13325), (-16.49555, -68.12935), (-16.49520, -68.12545), (-16.49505, -68.12160)],
        [(-16.50055, -68.13585), (-16.49860, -68.13270), (-16.49680, -68.12945), (-16.49560, -68.12615), (-16.49470, -68.12285)],
    ],
    "Local - Zona Sur": [
        [(-16.52420, -68.11140), (-16.52865, -68.10780), (-16.53310, -68.10405), (-16.53735, -68.10015), (-16.54165, -68.09615)],
        [(-16.53855, -68.09775), (-16.54180, -68.09415), (-16.54485, -68.09055), (-16.54760, -68.08710), (-16.55035, -68.08385)],
    ],
    "Local - El Alto": [
        [(-16.49825, -68.16940), (-16.50005, -68.16425), (-16.50170, -68.15900), (-16.50330, -68.15395), (-16.50505, -68.14870)],
        [(-16.50530, -68.16905), (-16.50385, -68.16420), (-16.50275, -68.15925), (-16.50195, -68.15415), (-16.50120, -68.14905)],
    ],
}

DEFAULT_ZONE_SEQUENCE = [
    "Sopocachi Alto",
    "Miraflores Alto",
    "Zona Sur - Obrajes",
    "El Alto - Centro",
    "San Pedro",
    "Zona Sur - Calacoto",
    "Miraflores Bajo",
    "Sopocachi Bajo",
]


def aware_at(day: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    naive = datetime.combine(day, time(hour, minute, second))
    return timezone.make_aware(naive, timezone.get_current_timezone())


def quant(value: float) -> Decimal:
    return Decimal(f"{value:.6f}")


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6371000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def decode_polyline(polyline: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0

    while index < len(polyline):
        shift = 0
        result = 0
        while True:
            byte = ord(polyline[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1

        shift = 0
        result = 0
        while True:
            byte = ord(polyline[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        points.append((lat / 1e5, lng / 1e5))

    return points


def sample_every_10_seconds(
    road_points: list[tuple[float, float]],
    *,
    speed_kmh: float,
    reverse: bool = False,
) -> list[tuple[float, float]]:
    points = list(reversed(road_points)) if reverse else road_points[:]
    if len(points) < 2:
        return points

    step_m = max(8.0, speed_kmh * 1000.0 / 3600.0 * 10.0)
    sampled = [points[0]]
    carry = 0.0

    for start, end in zip(points, points[1:]):
        segment_m = haversine_m(start, end)
        if segment_m <= 0:
            continue
        travelled = step_m - carry
        while travelled <= segment_m:
            t = travelled / segment_m
            sampled.append((
                start[0] + (end[0] - start[0]) * t,
                start[1] + (end[1] - start[1]) * t,
            ))
            travelled += step_m
        carry = segment_m - (travelled - step_m)
        if carry >= step_m:
            carry = 0.0

    if haversine_m(sampled[-1], points[-1]) > 5:
        sampled.append(points[-1])
    return sampled


def route_distance(points: list[tuple[float, float]]) -> float:
    return sum(haversine_m(a, b) for a, b in zip(points, points[1:]))


def fetch_google_route_points(waypoints: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], int, int]:
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise CommandError("Falta GOOGLE_MAPS_API_KEY para generar rutas calle por calle.")

    params = {
        "origin": f"{waypoints[0][0]},{waypoints[0][1]}",
        "destination": f"{waypoints[-1][0]},{waypoints[-1][1]}",
        "mode": "driving",
        "key": api_key,
    }
    if len(waypoints) > 2:
        params["waypoints"] = "|".join(f"{lat},{lng}" for lat, lng in waypoints[1:-1])

    response = requests.get(DIRECTIONS_URL, params=params, timeout=20)
    data = response.json()
    if data.get("status") != "OK":
        message = data.get("error_message") or data.get("status") or "respuesta desconocida"
        raise CommandError(f"Google Directions fallo: {message}")

    route = data["routes"][0]
    points: list[tuple[float, float]] = []
    for leg in route["legs"]:
        for step in leg["steps"]:
            decoded = decode_polyline(step["polyline"]["points"])
            if points and decoded and points[-1] == decoded[0]:
                points.extend(decoded[1:])
            else:
                points.extend(decoded)

    distance_m = sum(leg["distance"]["value"] for leg in route["legs"])
    duration_s = sum(leg["duration"]["value"] for leg in route["legs"])
    return points, distance_m, duration_s


def build_road_route_cache(refresh: bool = False) -> dict[str, list[dict[str, object]]]:
    if ROAD_CACHE_PATH.exists() and not refresh:
        return json.loads(ROAD_CACHE_PATH.read_text(encoding="utf-8"))

    ROAD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, list[dict[str, object]]] = {}
    for zone_name, specs in ZONE_ROUTE_SPECS.items():
        cache[zone_name] = []
        for index, waypoints in enumerate(specs, start=1):
            points, distance_m, duration_s = fetch_google_route_points(waypoints)
            cache[zone_name].append(
                {
                    "name": f"{zone_name} #{index}",
                    "points": points,
                    "distance_m": distance_m,
                    "duration_s": duration_s,
                }
            )
    ROAD_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache


class Command(BaseCommand):
    help = "Restaura y genera historial denso de rutas de mensajeros para ML y mapa."

    def add_arguments(self, parser):
        parser.add_argument("--dump", default=str(DEFAULT_DUMP_PATH))
        parser.add_argument("--start-date", default="2025-11-09")
        parser.add_argument("--end-date", default="2026-06-16")
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--skip-legacy", action="store_true")
        parser.add_argument("--couriers-per-day", type=int, default=12)
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument(
            "--refresh-road-cache",
            action="store_true",
            help="Vuelve a consultar Google Directions para regenerar las plantillas de calle.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dump_path = Path(options["dump"]).expanduser()
        if not options["skip_legacy"] and not dump_path.exists():
            raise CommandError(f"No existe el dump: {dump_path}")

        start_date = date.fromisoformat(options["start_date"])
        end_date = date.fromisoformat(options["end_date"])
        if end_date < start_date:
            raise CommandError("--end-date no puede ser anterior a --start-date")

        if options["reset"]:
            self.stdout.write("Limpiando historial local de ubicaciones y rutas resumen...")
            UbicacionMensajero.objects.all().delete()
            Ruta.objects.filter(envio__isnull=True).delete()

        self.ensure_courier_zones()

        couriers = list(
            Usuario.objects.filter(rol__nombre__iexact="mensajero", is_active=True)
            .select_related("rol", "perfil_mensajero__zona_cobertura")
            .order_by("id")
        )
        if not couriers:
            raise CommandError("No hay mensajeros activos para asignar rutas.")

        road_cache = build_road_route_cache(refresh=options["refresh_road_cache"])

        legacy_count = 0
        if not options["skip_legacy"]:
            legacy_count = self.import_legacy_locations(dump_path, options["batch_size"])

        generated_locations, generated_routes = self.generate_daily_routes(
            couriers=couriers,
            road_cache=road_cache,
            start_date=start_date,
            end_date=end_date,
            couriers_per_day=max(1, options["couriers_per_day"]),
            batch_size=options["batch_size"],
        )

        self.update_courier_profiles()
        cache.clear()

        total = UbicacionMensajero.objects.count()
        self.stdout.write(self.style.SUCCESS("Historial de rutas cargado."))
        self.stdout.write(f"Puntos restaurados del SQL: {legacy_count}")
        self.stdout.write(f"Puntos generados: {generated_locations}")
        self.stdout.write(f"Rutas resumen generadas: {generated_routes}")
        self.stdout.write(f"Total puntos en usuarios_ubicacionmensajero: {total}")

    def ensure_courier_zones(self) -> None:
        zones = {
            zone.nombre: zone
            for zone in Zona.objects.filter(nombre__in=set(DEFAULT_ZONE_SEQUENCE) | set(ZONE_ROUTE_SPECS))
        }
        if not zones:
            return

        couriers = list(
            Usuario.objects.filter(rol__nombre__iexact="mensajero", is_active=True)
            .select_related("perfil_mensajero__zona_cobertura")
            .order_by("id")
        )
        for index, courier in enumerate(couriers):
            profile, _ = PerfilMensajero.objects.get_or_create(usuario=courier)
            current = profile.zona_cobertura.nombre if profile.zona_cobertura else None
            if current in ZONE_ROUTE_SPECS:
                continue
            zone_name = DEFAULT_ZONE_SEQUENCE[index % len(DEFAULT_ZONE_SEQUENCE)]
            zone = zones.get(zone_name)
            if zone:
                profile.zona_cobertura = zone
                profile.disponible = True
                profile.save(update_fields=["zona_cobertura", "disponible"])

    def import_legacy_locations(self, dump_path: Path, batch_size: int) -> int:
        valid_courier_ids = set(
            Usuario.objects.filter(rol__nombre__iexact="mensajero").values_list("id", flat=True)
        )
        pending: list[UbicacionMensajero] = []
        inserted = 0

        def flush() -> None:
            nonlocal pending, inserted
            if not pending:
                return
            with preserve_explicit_auto_timestamps(UbicacionMensajero):
                UbicacionMensajero.objects.bulk_create(pending, batch_size=batch_size)
            inserted += len(pending)
            pending = []

        with dump_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                match = LEGACY_LOCATION_RE.match(raw_line.strip())
                if not match:
                    continue
                mensajero_id = int(match.group("mensajero_id"))
                if mensajero_id not in valid_courier_ids:
                    continue
                pending.append(
                    UbicacionMensajero(
                        latitud=quant(float(match.group("lat"))),
                        longitud=quant(float(match.group("lng"))),
                        fecha_hora=parse_datetime_literal(match.group("dt")),
                        mensajero_id=mensajero_id,
                    )
                )
                if len(pending) >= batch_size:
                    flush()
        flush()
        return inserted

    def generate_daily_routes(
        self,
        *,
        couriers: list[Usuario],
        road_cache: dict[str, list[dict[str, object]]],
        start_date: date,
        end_date: date,
        couriers_per_day: int,
        batch_size: int,
    ) -> tuple[int, int]:
        rng = random.Random(20260616)
        current = start_date
        location_batch: list[UbicacionMensajero] = []
        route_batch: list[Ruta] = []
        generated_locations = 0
        generated_routes = 0
        day_index = 0

        def flush_locations() -> None:
            nonlocal location_batch, generated_locations
            if not location_batch:
                return
            with preserve_explicit_auto_timestamps(UbicacionMensajero):
                UbicacionMensajero.objects.bulk_create(location_batch, batch_size=batch_size)
            generated_locations += len(location_batch)
            location_batch = []

        def flush_routes() -> None:
            nonlocal route_batch, generated_routes
            if not route_batch:
                return
            with preserve_explicit_auto_timestamps(Ruta):
                Ruta.objects.bulk_create(route_batch, batch_size=batch_size)
            generated_routes += len(route_batch)
            route_batch = []

        while current <= end_date:
            shuffled = couriers[:]
            rng.shuffle(shuffled)
            active_couriers = shuffled[: min(couriers_per_day, len(shuffled))]
            weekday_offset = 1 if current.weekday() >= 5 else 0

            for courier_index, courier in enumerate(active_couriers):
                zone_name = self.zone_name_for_courier(courier)
                templates = road_cache.get(zone_name) or road_cache.get("Local - Centro La Paz") or []
                if not templates:
                    raise CommandError(f"No hay plantilla de calles para la zona {zone_name}.")
                template = templates[(day_index + courier_index) % len(templates)]
                road_points = [tuple(point) for point in template["points"]]  # type: ignore[assignment]
                reverse = (day_index + courier.id) % 4 == 0
                points = sample_every_10_seconds(
                    road_points, speed_kmh=9.0 + ((courier.id + day_index) % 5), reverse=reverse
                )

                start_hour = 7 + ((courier_index + day_index) % 9)
                start_dt = aware_at(
                    current,
                    min(start_hour + weekday_offset, 18),
                    minute=(courier_index * 7 + day_index * 3) % 60,
                    second=(courier.id * 11) % 60,
                )
                for point_index, (lat, lng) in enumerate(points):
                    location_batch.append(
                        UbicacionMensajero(
                            mensajero=courier,
                            latitud=quant(lat),
                            longitud=quant(lng),
                            fecha_hora=start_dt + timedelta(seconds=point_index * 10),
                        )
                    )
                    if len(location_batch) >= batch_size:
                        flush_locations()

                distance_m = route_distance(points)
                estimated_min = max(8.0, distance_m / 1000.0 / 22.0 * 60.0)
                real_min = estimated_min + rng.uniform(-4.0, 13.0)
                route_batch.append(
                    Ruta(
                        mensajero=courier,
                        latitud_inicio=Decimal(f"{points[0][0]:.15f}"),
                        longitud_inicio=Decimal(f"{points[0][1]:.15f}"),
                        latitud_fin=Decimal(f"{points[-1][0]:.15f}"),
                        longitud_fin=Decimal(f"{points[-1][1]:.15f}"),
                        fecha=start_dt,
                        distancia_algo_m=round(distance_m, 2),
                        distancia_google_m=round(distance_m * rng.uniform(0.94, 1.08), 2),
                        duracion_estimada=round(estimated_min, 2),
                        duracion_real=round(real_min, 2),
                        duracion_algo_min=round(real_min, 2),
                        duracion_google_min=round(estimated_min * rng.uniform(0.90, 1.05), 2),
                        retraso_estimado=round(real_min - estimated_min, 2),
                        zona_asignada=courier.perfil_mensajero.zona_cobertura_id,
                        started_at=start_dt,
                        finished_at=start_dt + timedelta(minutes=max(real_min, 1)),
                    )
                )
                if len(route_batch) >= batch_size:
                    flush_routes()

            current += timedelta(days=1)
            day_index += 1

        flush_locations()
        flush_routes()
        return generated_locations, generated_routes

    def zone_name_for_courier(self, courier: Usuario) -> str:
        try:
            zone_name = courier.perfil_mensajero.zona_cobertura.nombre
        except PerfilMensajero.DoesNotExist:
            zone_name = None
        if zone_name in ZONE_ROUTE_SPECS:
            return zone_name
        return "Local - Centro La Paz"

    def update_courier_profiles(self) -> None:
        latest_by_courier = (
            UbicacionMensajero.objects.order_by("mensajero_id", "-fecha_hora")
            .distinct("mensajero_id")
            if not connection_is_sqlite()
            else []
        )
        if latest_by_courier:
            for ubicacion in latest_by_courier:
                PerfilMensajero.objects.update_or_create(
                    usuario=ubicacion.mensajero,
                    defaults={
                        "latitud": Decimal(f"{float(ubicacion.latitud):.15f}"),
                        "longitud": Decimal(f"{float(ubicacion.longitud):.15f}"),
                        "disponible": True,
                    },
                )
            return

        for courier in Usuario.objects.filter(rol__nombre__iexact="mensajero"):
            ubicacion = (
                UbicacionMensajero.objects.filter(mensajero=courier)
                .order_by("-fecha_hora")
                .first()
            )
            if not ubicacion:
                continue
            PerfilMensajero.objects.update_or_create(
                usuario=courier,
                defaults={
                    "latitud": Decimal(f"{float(ubicacion.latitud):.15f}"),
                    "longitud": Decimal(f"{float(ubicacion.longitud):.15f}"),
                    "disponible": True,
                },
            )


def connection_is_sqlite() -> bool:
    from django.db import connection

    return connection.vendor == "sqlite"

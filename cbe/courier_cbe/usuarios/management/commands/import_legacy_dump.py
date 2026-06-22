from __future__ import annotations

from contextlib import contextmanager
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from django.utils import timezone

from envios.models import Entrega, Envio, HistorialEnvio, Incidente
from pagos.models import MetodoPago, Pago
from rutas.ml_models import MLTrainingState
from rutas.models import Ruta
from usuarios.models import PerfilMensajero, Rol, UbicacionMensajero, Usuario
from zonas.models import Zona


DEFAULT_DUMP_PATH = Path("/Users/gabrielboyan/Downloads/solo_datos.sql")
INSERT_RE = re.compile(
    r"^INSERT INTO public\.([a-z0-9_]+)\s*\((.*?)\)\s*VALUES\s*\((.*)\)$",
    re.IGNORECASE,
)
DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}(?::\d{2})?)?$"
)
NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

MODEL_MAP = {
    "usuarios_rol": Rol,
    "usuarios_usuario": Usuario,
    "usuarios_perfilmensajero": PerfilMensajero,
    "usuarios_ubicacionmensajero": UbicacionMensajero,
    "envios_envio": Envio,
    "envios_entrega": Entrega,
    "envios_historialenvio": HistorialEnvio,
    "envios_incidente": Incidente,
    "rutas_ruta": Ruta,
    "zonas_zona": Zona,
    "pagos_metodopago": MetodoPago,
    "pagos_pago": Pago,
    "rutas_mltrainingstate": MLTrainingState,
}

RESET_ORDER = [
    UbicacionMensajero,
    Entrega,
    HistorialEnvio,
    Incidente,
    Ruta,
    Pago,
    Envio,
    PerfilMensajero,
    Usuario,
    Rol,
    MetodoPago,
    Zona,
    MLTrainingState,
]


def split_sql_values(values_text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    i = 0

    while i < len(values_text):
        char = values_text[i]
        if in_quotes:
            if char == "'" and i + 1 < len(values_text) and values_text[i + 1] == "'":
                current.append("''")
                i += 2
                continue
            if char == "'":
                in_quotes = False
            current.append(char)
        else:
            if char == "'":
                in_quotes = True
                current.append(char)
            elif char == ",":
                tokens.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        i += 1

    if current:
        tokens.append("".join(current).strip())

    return tokens


def parse_datetime_literal(value: str) -> datetime:
    normalized = value.replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    if re.search(r"[+-]\d{2}$", normalized):
        normalized = f"{normalized}:00"

    parsed = datetime.fromisoformat(normalized)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def coerce_sql_value(token: str) -> Any:
    token = token.strip()
    if token.upper() == "NULL":
        return None
    if token.lower() == "true":
        return True
    if token.lower() == "false":
        return False

    if token.startswith("'") and token.endswith("'"):
        value = token[1:-1].replace("''", "'")
        if DATETIME_RE.match(value):
            try:
                return parse_datetime_literal(value)
            except ValueError:
                return value
        return value

    if NUMBER_RE.match(token):
        return Decimal(token) if "." in token else int(token)

    return token


def parse_insert_statement(statement: str) -> tuple[str, dict[str, Any]]:
    statement = statement.strip()
    if statement.endswith(";"):
        statement = statement[:-1]

    match = INSERT_RE.match(statement)
    if not match:
        raise ValueError(f"No se pudo leer el INSERT: {statement[:120]}")

    table_name, columns_text, values_text = match.groups()
    columns = [column.strip() for column in columns_text.split(",")]
    values = split_sql_values(values_text)
    if len(columns) != len(values):
        raise ValueError(
            f"Columnas y valores no coinciden en {table_name}: {len(columns)} != {len(values)}"
        )

    row = {column: coerce_sql_value(token) for column, token in zip(columns, values)}
    return table_name, row


def iter_insert_statements(path: Path):
    buffer: list[str] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if not buffer:
                if stripped.startswith("INSERT INTO public."):
                    buffer.append(stripped)
                    if stripped.endswith(";"):
                        yield " ".join(buffer)
                        buffer = []
                continue

            buffer.append(stripped)
            if stripped.endswith(";"):
                yield " ".join(buffer)
                buffer = []


@contextmanager
def preserve_explicit_auto_timestamps(model):
    timestamp_fields = [
        field
        for field in model._meta.concrete_fields
        if getattr(field, "auto_now_add", False) or getattr(field, "auto_now", False)
    ]
    original_flags = [
        (field, field.auto_now_add, field.auto_now)
        for field in timestamp_fields
    ]

    for field, _, _ in original_flags:
        field.auto_now_add = False
        field.auto_now = False

    try:
        yield
    finally:
        for field, auto_now_add, auto_now in original_flags:
            field.auto_now_add = auto_now_add
            field.auto_now = auto_now


class Command(BaseCommand):
    help = "Importa el dump PostgreSQL de datos de negocio a la base local."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=str(DEFAULT_DUMP_PATH),
            help="Ruta del archivo .sql exportado desde PostgreSQL.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Limpia primero las tablas del proyecto antes de importar.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Cantidad de filas por lote para bulk_create.",
        )
        parser.add_argument(
            "--set-demo-passwords",
            action="store_true",
            help="Asigna claves locales conocidas: administradores/admin123 y mensajeros/courier123.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dump_path = Path(options["path"]).expanduser()
        if not dump_path.exists():
            raise CommandError(f"No existe el archivo: {dump_path}")

        batch_size = max(1, int(options["batch_size"]))

        if options["reset"]:
            self.stdout.write("Limpiando tablas locales...")
            self.reset_tables()

        counts: dict[str, int] = {}
        pending_model = None
        pending_objects = []

        def flush_pending():
            nonlocal pending_model, pending_objects
            if not pending_model or not pending_objects:
                return
            with preserve_explicit_auto_timestamps(pending_model):
                pending_model.objects.bulk_create(pending_objects, batch_size=batch_size)
            counts[pending_model._meta.db_table] = counts.get(pending_model._meta.db_table, 0) + len(pending_objects)
            pending_objects = []

        for statement in iter_insert_statements(dump_path):
            table_name, row = parse_insert_statement(statement)
            model = MODEL_MAP.get(table_name)
            if model is None:
                continue

            if pending_model is not model:
                flush_pending()
                pending_model = model

            obj = model()
            for field_name, value in row.items():
                setattr(obj, field_name, value)

            for field in model._meta.concrete_fields:
                if field.name in row:
                    continue
                if getattr(field, "auto_now_add", False) or getattr(field, "auto_now", False):
                    setattr(obj, field.attname, timezone.now())

            pending_objects.append(obj)
            if len(pending_objects) >= batch_size:
                flush_pending()

        flush_pending()

        if options["set_demo_passwords"]:
            self.set_demo_passwords()

        self.reset_sequences(list(dict.fromkeys(MODEL_MAP.values())))
        cache.clear()

        self.stdout.write(self.style.SUCCESS("Importación completada."))
        for table_name in sorted(counts):
            self.stdout.write(f"  {table_name}: {counts[table_name]}")

        self.stdout.write(
            self.style.WARNING(
                "Nota: el dump no trae datos para pagos o ML state en este archivo, "
                "así que esas tablas quedan vacías salvo que las cargues por separado."
            )
        )

    def reset_tables(self):
        for model in RESET_ORDER:
            model.objects.all().delete()

    def reset_sequences(self, models: list[type]):
        sql_statements = connection.ops.sequence_reset_sql(no_style(), models)
        if not sql_statements:
            return

        with connection.cursor() as cursor:
            for sql in sql_statements:
                cursor.execute(sql)

    def set_demo_passwords(self):
        admin_count = 0
        courier_count = 0

        for usuario in Usuario.objects.select_related("rol"):
            role_name = usuario.rol.nombre.lower()
            if role_name == "administrador":
                usuario.set_password("admin123")
                admin_count += 1
            elif role_name == "mensajero":
                usuario.set_password("courier123")
                courier_count += 1
            else:
                continue
            usuario.save(update_fields=["contrasena"])

        User = get_user_model()
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@cbe.com", "is_staff": True, "is_superuser": True},
        )
        admin_user.email = "admin@cbe.com"
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.set_password("admin123")
        admin_user.save()

        self.stdout.write(
            f"Claves locales asignadas: {admin_count} administradores y {courier_count} mensajeros."
        )

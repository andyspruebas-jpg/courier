#!/bin/bash
set -e

PROJECT="/Users/gabrielboyan/Projects/courier/cbe"
BACKEND="$PROJECT/courier_cbe"
MOBILE="$PROJECT/courier_cbe_movil"

echo ""
echo "================================================"
echo "  COURIER BOLIVIAN EXPRESS — Iniciando sistemas"
echo "================================================"
echo ""

# ── 1. Matar procesos viejos ──────────────────────
echo "[1/6] Limpiando procesos anteriores..."
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
pkill -f "caffeinate" 2>/dev/null || true
sleep 1

# ── 2. Evitar que el Mac duerma ──────────────────
echo "[2/6] Evitando sleep del sistema..."
nohup caffeinate -s > /tmp/caffeinate.log 2>&1 &

# ── 3. Levantar Django ───────────────────────────
echo "[3/6] Iniciando servidor Django..."
cd "$BACKEND"
nohup venv/bin/python manage.py runserver 0.0.0.0:8000 > /tmp/django.log 2>&1 &
DJANGO_PID=$!
sleep 4

# Verificar Django
if ! /usr/bin/curl -s http://localhost:8000/ -o /dev/null; then
  echo "ERROR: Django no respondió. Revisá /tmp/django.log"
  exit 1
fi

# ── 4. Tunnel cloudflared para backend ───────────
echo "[4/6] Creando tunnel para el backend..."
nohup cloudflared tunnel --url http://localhost:8000 > /tmp/cf_backend.log 2>&1 &
sleep 8

BACKEND_URL=$(grep -o "https://[a-zA-Z0-9\-]*\.trycloudflare\.com" /tmp/cf_backend.log | head -1)
if [ -z "$BACKEND_URL" ]; then
  echo "ERROR: No se pudo obtener URL del tunnel. Revisá /tmp/cf_backend.log"
  exit 1
fi

BACKEND_HOST=$(echo "$BACKEND_URL" | sed 's|https://||')

# Actualizar .env
sed -i '' "s|NGROK_HOST=.*|NGROK_HOST=$BACKEND_HOST|" "$BACKEND/.env"
sed -i '' "s|ALLOWED_HOSTS=.*|ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,railway.app,$BACKEND_HOST|" "$BACKEND/.env"

# Reiniciar Django con nuevo .env
kill $DJANGO_PID 2>/dev/null || true
sleep 2
cd "$BACKEND"
nohup venv/bin/python manage.py runserver 0.0.0.0:8000 > /tmp/django.log 2>&1 &
sleep 3

# ── 5. Compilar y levantar app web Flutter ───────
echo "[5/6] Compilando app móvil para web (puede tardar 2-3 min)..."

# Actualizar URL en api.dart
cat > "$MOBILE/lib/api/api.dart" << DART
import 'package:flutter/foundation.dart';

String getBaseUrl() {
  const overrideUrl = String.fromEnvironment('API_BASE_URL');
  if (overrideUrl.isNotEmpty) return overrideUrl;
  return '$BACKEND_URL';
}

final String apiUrl = getBaseUrl();
final String loginUrl = "\$apiUrl/usuarios/login/";
final String perfilUrl = "\$apiUrl/usuarios/perfil/";
DART

cd "$MOBILE"
flutter build web --release > /tmp/flutter_build.log 2>&1
echo "   App web compilada OK"

# Levantar servidor de la app web
nohup python3 -m http.server 8080 --directory "$MOBILE/build/web" > /tmp/flutter_web.log 2>&1 &
sleep 2

# ── 6. Tunnel cloudflared para app web ───────────
echo "[6/6] Creando tunnel para la app web..."
nohup cloudflared tunnel --url http://localhost:8080 > /tmp/cf_web.log 2>&1 &
sleep 8

WEB_URL=$(grep -o "https://[a-zA-Z0-9\-]*\.trycloudflare\.com" /tmp/cf_web.log | head -1)

# ── Resultado ────────────────────────────────────
echo ""
echo "================================================"
echo "  SISTEMAS ACTIVOS"
echo "================================================"
echo ""
echo "  PANEL WEB ADMIN"
echo "  $BACKEND_URL/usuarios/login/"
echo "  Usuario: admin@cbe.com"
echo "  Clave:   CbeAdmin2026!"
echo ""
echo "  APP MOVIL (web)"
echo "  $WEB_URL"
echo ""
echo "  MENSAJEROS (app movil)"
echo "  Clave para todos: CbeRuta2026!"
echo "  - cristian@cbe.com"
echo "  - marcoticona@cbe.com"
echo "  - jhonatantula@cbe.com"
echo "  - andreaarancibia@cbe.com"
echo "  - juan.operativo@cbe.com"
echo "  - carlos.operativo@cbe.com"
echo "  - luis.operativo@cbe.com"
echo ""
echo "================================================"
echo ""

#!/usr/bin/env bash
set -euo pipefail

BASE="${BFF_BASE_URL:-http://127.0.0.1:3000}"
EMAIL="smoke-$(date +%s)@example.com"
PASSWORD="password12"

echo "== health =="
curl -fsS "$BASE/api/health"

echo
echo "== register =="
REGISTER=$(curl -fsS -D /tmp/bff-register.hdr -X POST "$BASE/api/auth/register" \
  -H 'Content-Type: application/json' \
  -H 'Origin: http://127.0.0.1:3000' \
  -H 'x-csrf: 1' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
echo "$REGISTER"
grep -i set-cookie /tmp/bff-register.hdr || true
if echo "$REGISTER" | grep -qiE 'access|refresh='; then
  echo "tokens leaked to browser JSON" >&2
  exit 1
fi

COOKIE=$(python3 - <<'PY'
from pathlib import Path
for line in Path("/tmp/bff-register.hdr").read_text().splitlines():
    if line.lower().startswith("set-cookie:") and "session=" in line.lower():
        value = line.split(":", 1)[1].strip().split(";", 1)[0]
        print(value)
        break
PY
)

echo "== companions =="
curl -fsS "$BASE/api/companions" -H "Cookie: $COOKIE" -H 'x-request-id: smoke-companions'
echo

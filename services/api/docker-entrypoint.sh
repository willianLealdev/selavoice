#!/bin/sh
# Inicialização da API no contêiner.
# 1) Garante que o disco persistente /data pertence ao usuário "app" (volumes novos vêm como root e o banco não gravaria).
# 2) Abaixa os privilégios para o usuário "app" (sem root) e sobe: migrações -> seed (super admin/planos) -> API.
# UM único processo: os canais de tradução ao vivo ficam em memória.
set -e
mkdir -p /data/storage
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /data 2>/dev/null || echo "aviso: não consegui ajustar a permissão de /data"
  RUN="runuser -u app --"
else
  RUN=""
fi
exec $RUN sh -c "python -m alembic upgrade head && python -m app.seed && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"

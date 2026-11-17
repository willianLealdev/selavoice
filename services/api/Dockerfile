FROM python:3.12-slim
# Bibliotecas do SDK de voz do Azure (só carregadas se o Azure for usado) + certificados HTTPS
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 libasound2 \
    && rm -rf /var/lib/apt/lists/*
# Usuário sem privilégios (princípio do menor privilégio)
RUN useradd -m -u 10001 app
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# /data = disco PERSISTENTE (volume no Easypanel): banco SQLite (teste) e PDFs. Sem volume, tudo some a cada deploy.
RUN mkdir -p /data /srv/storage && chown -R app:app /srv /data
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u;u.urlopen('http://localhost:8000/health')" || exit 1
# Sobe: aplica migrações do banco, cria super admin/planos (se faltarem) e inicia a API (UM único processo: os canais ao vivo são em memória).
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]

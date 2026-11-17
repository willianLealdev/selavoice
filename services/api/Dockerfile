FROM python:3.12-slim
# Bibliotecas do SDK de voz do Azure (só carregadas se o Azure for usado) + certificados HTTPS
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 libasound2 \
    && rm -rf /var/lib/apt/lists/*
# Usuário sem privilégios (princípio do menor privilégio): o entrypoint ajusta o disco como root e depois ABAIXA para "app".
RUN useradd -m -u 10001 app
WORKDIR /srv
# Garante que `import app` funciona também quando o alembic roda como programa (e não como `python -m`).
ENV PYTHONPATH=/srv PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# /data = disco PERSISTENTE (volume no Easypanel): banco SQLite (teste) e PDFs. Sem volume, tudo some a cada deploy.
RUN mkdir -p /data /srv/storage && chown -R app:app /srv /data
EXPOSE 8000
HEALTHCHECK --start-period=40s CMD python -c "import urllib.request as u;u.urlopen('http://localhost:8000/health')" || exit 1
ENTRYPOINT ["sh", "/srv/docker-entrypoint.sh"]

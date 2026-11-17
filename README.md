# SelaVoice — Real-time Translation

Plataforma SaaS multitenant de tradução simultânea para igrejas, congressos e feiras.
**Comece por:** [`docs/PROJECT_MEMORY.md`](docs/PROJECT_MEMORY.md) · Estado real: [`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md) · Dev: [`docs/MANUAL_DESENVOLVEDOR.md`](docs/MANUAL_DESENVOLVEDOR.md)

## Início rápido (Windows, sem Docker)
```bash
cd services/api
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m app.seed                       # anote as senhas impressas
.venv\Scripts\python -m uvicorn app.main:app --port 8000
# outro terminal
cd apps/web && npm install && npm run dev               # http://localhost:3000
```
Testes: `cd services/api && .venv\Scripts\python -m pytest -q` (42 testes, sem chaves externas).

## Com Docker (staging)
Copie `.env.example` para `.env`, preencha `JWT_SECRET`, `ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `MINIO_PASSWORD` e rode `docker compose up --build`.
> Ainda não executado nesta máquina — ver `docs/BLOCKERS.md`.

## Modo simulado (padrão)
Sem chaves, a tradução usa um **simulador** e o Stripe é **fake** (sem cobrança). Para integrações reais veja `docs/BLOCKERS.md`.

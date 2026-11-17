# Manual do desenvolvedor (como ler e estender o projeto)

## Fluxo de uma requisição autenticada
`Cliente → SecurityMiddleware (cabeçalhos, limite de corpo, log JSON) → CORS → rota`
`→ deps.current_claims (valida JWT) → current_user → get_ctx (acha a membership, define tenant e papel)`
`→ require_member/operator/admin (papel mínimo) → handler usa scoped(db, Model, ctx.tenant_id)`.

## Como adicionar uma nova entidade de cliente (checklist)
1. Em `models.py`: coluna `tenant_id` (FK `tenants.id`, `ondelete=CASCADE`, index) e adicione o nome da tabela em `TENANT_TABLES` (gera RLS).
2. Rotas: dependência `require_*`; **toda** consulta com `scoped(db, Model, ctx.tenant_id)`; nunca ler tenant do corpo.
3. Escritas importantes: `audit(...)`.
4. Teste em `tests/test_isolation.py`: outro tenant recebe **404**.
5. Migração Alembic (`alembic revision --autogenerate -m "..."`).

## Tempo real (transcrição)
- `services/transcripts.py`: `write_segment()` cria/revisa e publica no `hub`; `fetch_since()` (replay) e `fetch_page()` (scrollback).
- `routers/live.py`: `/sessions/{id}/live` (ouvintes/membros), `/sessions/{id}/ingest` (áudio), `/public/join/*`.
- `services/channels.py`: `ChannelManager.join/leave` (contagem de ouvintes → liga/desliga IA com carência), `_run` (provedor → segmentos), medição por minuto, failover.
- Protocolo WS do ouvinte: cliente envia `{"type":"auth","token","lang","last_seq"}` → servidor `{"type":"replay","segments":[...],"live":bool}` → depois `{"type":"segment",...}`, `{"type":"status",...}`, `{"type":"resync"}`; cliente envia `{"type":"ping"}`.
- Códigos de fechamento: 4400 mensagem inválida · 4401 sem auth em 5 s · 4403 não autorizado/origem · 4409 evento não ao vivo · 4413 grande demais · 4429 limite.

## Adicionar um provedor de IA
Implemente `TranslationProvider` (`providers/base.py`): `list_languages`, `start_session` (retorna `ProviderSession` com `stream_events` assíncrono que emite `TranslationEvent`), `health`, `estimated_cost`. Registre em `channels.build_registry()` e inclua na prioridade do `FailoverRouter`. Marque idiomas `verified=True` **somente** após teste real. Escreva teste de contrato com o simulador.

## Cobrança
`services/billing.py`: `verify_stripe_signature` → `process_webhook` (dedupe) → `_fulfill_checkout`/`_renew_subscription`. Cota: `reserve_event_start` (lock) e `record_usage` (livro-razão). Planos: nunca editar `PlanVersion`; criar versão nova em `/admin/plans/{id}/versions`.

## Testes
`cd services/api && .venv\Scripts\python.exe -m pytest -q`. O `conftest.py` cria um SQLite temporário e fixtures (`tenant_a`, `tenant_b`, `superadmin`, `paid_plan`). Use sempre o simulador (sem chaves).

## Convenções
Comentários e mensagens ao usuário em pt-BR; identificadores em inglês. Nada de segredo no código. Erros ao cliente: sem stack trace. Datas em UTC.

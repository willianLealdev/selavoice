# SelaVoice — instruções para o Claude neste projeto

- **Leia `docs/PROJECT_MEMORY.md` antes de qualquer coisa** (mapa, decisões, estado, próximos passos). Não releia o código inteiro: use o mapa.
- Ao terminar uma tarefa, atualize `docs/PROJECT_MEMORY.md` (Estado atual / Próximos passos) e `docs/BUILD_STATUS.md`.
- Todo código novo é comentado em português (pt-BR); explique o "porquê" de decisões de segurança.
- Segurança é obrigatória desde o início: tenant sempre pela membership (`deps.get_ctx` + `scoped()`), 404 para outro tenant, segredos só no backend, webhook Stripe verificado+idempotente.
- Nunca afirme como provado: latência de 2 s, nº de idiomas, preços de IA, failover real. Integração sem chave = `BLOCKED_EXTERNAL` em `docs/BLOCKERS.md`.
- Rode `cd services/api && .venv\Scripts\python -m pytest -q` e `cd apps/web && npx tsc --noEmit` antes de dar algo como pronto.
- Modelos: preferir Sonnet; Opus para arquitetura/segurança/pagamentos/banco difíceis (autorizado pelo dono).

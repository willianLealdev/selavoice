# Modelo de ameaças (STRIDE resumido) e o que já está mitigado

| Ameaça | Mitigação implementada | Teste |
|---|---|---|
| Acesso entre tenants (REST) | `scoped()` + membership; 404 em vez de 403 | `test_isolation.py` |
| Acesso entre tenants (WebSocket/ingest/PDF) | token validado contra a sessão; checagem de membership; prefixo de storage | `test_websocket_cross_tenant_denied`, `test_document_cross_tenant_denied` |
| Escalada via `tenant_id` forjado | tenant nunca lido do corpo/URL; `X-Org-Slug` validado | `test_cannot_pick_foreign_org_via_header` |
| Super admin abusando | MFA, elevação 10 min só-leitura, motivo, auditoria | `test_super_admin_elevation_*` |
| Roubo/forja de JWT | HS256 fixo (rejeita `alg=none`), `iss`/`exp` obrigatórios, tipo de token, access curto | `test_forged_and_none_alg_tokens_rejected` |
| Roubo de refresh token | httpOnly, rotação, reuso fora da janela revoga família, CSRF header | `test_refresh_*` |
| Força bruta / enumeração | Argon2, lockout 5 falhas, erro genérico, hash isca (tempo constante), rate limit | `test_login_generic_error_and_lockout` |
| Webhook falso/repetido | HMAC Stripe + tolerância 300 s + dedupe por id + concessão idempotente | `test_webhook_*`, `test_verified_webhook_grants_once...` |
| Pagar via redirect | success_url só informativo; direitos só no webhook | `test_frontend_redirect_alone_grants_nothing` |
| Corrida de cota (2 eventos ao mesmo tempo) | lock da linha do tenant + contagem de LIVE | `test_one_off_cannot_start_two_simultaneous_events` |
| Abuso de WebSocket | auth em 5 s, tamanho máx., Origin, limite por IP, idioma validado, bytes/s no ingest | `test_ws_abuse_rejected`, `test_ingest_*` |
| Fila lenta/ouvinte travado | filas limitadas + `resync` (replay) | (hub) |
| XSS / clickjacking / sniffing | CSP, X-Frame-Options, nosniff, Referrer-Policy; React escapa; branding só chaves permitidas | cabeçalhos testados |
| Vazamento de segredos | só backend, `.env` fora do git, Fernet para credenciais, logs redigidos, produção recusa segredo fraco | `config.py` |
| Path traversal em PDF | caminho resolvido deve estar sob o prefixo do tenant | `documents.pdf` |
| Conteúdo não publicado vazar | estados DRAFT→IN_REVIEW→APPROVED→PUBLISHED; público só PUBLISHED | `test_unpublished_hidden_from_public...` |
| Fabricação de citações/escritura | DeepSeek só edita; material editorial rotulado; referências sinalizadas p/ humano | `test_full_flow_requires_review...` |
| Falha de provedor | circuit breaker + failover por idioma + aviso ao ouvinte | `test_channel_failover_end_to_end` |
| Dependências vulneráveis | `pip-audit` e `npm audit` = 0 (2026-11-16); repetir no CI | CI |

## Riscos residuais (conhecidos)
RLS Postgres não executado; rate limit em memória; CSP com unsafe-inline; sem WAF/DDoS de borda (usar Cloudflare/Traefik na VPS); sem backup automatizado ainda; e-mail de convite inexistente.

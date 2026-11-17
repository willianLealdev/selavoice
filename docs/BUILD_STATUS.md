# BUILD_STATUS — estado real de cada fase (sem exageros)

Legenda: ✅ feito e testado · 🟡 parcial · ⛔ não feito · 🔒 BLOCKED_EXTERNAL (falta chave/conta/infra)
Data: 2026-11-16 · Testes: `services/api` → 62 passed · `npm audit`/`pip-audit` → 0 vulnerabilidades · `next build` OK

| Fase | Status | Evidência / observações |
|---|---|---|
| 0 Baseline | 🟡 | Estrutura, README, .env.example, ADRs, ameaças, CI. `docker compose up` **não executado** (Docker não instalado) 🔒 |
| 1 Fundação/Auth | ✅ | Registro, login Argon2, lockout, refresh com rotação+detecção de reuso, MFA TOTP super admin, RBAC, isolamento (REST/WS/PDF), elevação auditada — `tests/test_auth.py`, `test_isolation.py`. RLS Postgres: migração escrita, **não executada** 🔒 |
| 2 Eventos | ✅ | CRUD, máquina de estados, histórico filtrável, QR/link, criar não consome cota — `test_events_billing.py` |
| 3 Transcrição | ✅ | Segmentos provisório/final, replay, scrollback, 240 finais sem perda/duplicata, WS reconexão; **verificado no navegador real**: sem pulo de tela, "Voltar ao vivo" — `test_realtime.py` |
| 4 Áudio | 🟡 | Ingestão WS (token efêmero, só evento AO VIVO, limites, métricas), 1 canal por idioma compartilhado (testado com 3 ouvintes). **Falta:** relay de áudio traduzido ao ouvinte (WebRTC/SFU), teste de captura com fonte real, teste de carga. Voz atual = TTS do navegador (opção do ouvinte) |
| 5 Provedores | 🟡/🔒 | Interface, matriz de capacidades, simulador, circuit breaker, failover por idioma, override admin, FailoverEvent — testados. **Gemini/Azure reais: BLOQUEADO** (sem chaves); latência/custo/cobertura reais NÃO medidos |
| 6 ASR+Apostila | 🟡 | Importar transcrição original (imutável), rascunho, detecção de referências bíblicas, revisão, aprovação humana, PDF ReportLab, público só vê PUBLICADO — `test_documents.py`. **Falta:** worker faster-whisper, Deepgram, DeepSeek real, tradução de apostilas 🔒 |
| 7 Cobrança | 🟡 | Planos/versões imutáveis, checkout, webhook verificado+idempotente, falha não concede, passe avulso sem eventos simultâneos, créditos, migração deliberada — Stripe **SIMULADO**. **Falta:** teste em modo test do Stripe real 🔒, reembolsos pela UI, cupons/trials |
| 8 Consoles | 🟡 | Painel organizador (eventos, equipe, plano/uso, apostila) e super admin (métricas, orgs, planos, provedores, auditoria). **Falta:** gráficos custo/margem por evento-idioma, exportação, notificações, E2E |
| 9 Mobile | ⛔ | Combinado: web primeiro; app depois |
| 10 Hardening | ⛔ | Falta carga/soak 40 min com áudio, backup/restore, runbooks, drill de failover real |
| 11 Expansão | ⛔ | Schema já suporta várias salas e tenants; falta onboarding avançado, domínios próprios, plano de escala |

## Adicionado depois (painel de chaves, e-mail, captura)
- ✅ Cofre de chaves cifrado + painel Super Admin (Gemini, Azure, Deepgram, DeepSeek, Resend, Stripe) com "Testar conexão" — `test_integrations.py`. O teste só confirma que a chave é ACEITA; **não prova tradução em tempo real**.
- ✅ Resend: convite por e-mail, "esqueci minha senha"/redefinição (uso único, 1 h, derruba sessões) — testado com envio interceptado; **envio real não verificado** 🔒 (precisa chave + domínio verificado).
- ✅ Captura de áudio por navegador/celular e utilitário de computador, aceitando qualquer fonte. **Não testados com hardware/celular reais.**
- ⚠️ **Gemini Live e Azure Speech: mesmo com chave, a tradução ao vivo NÃO roda** — o código do streaming real desses provedores ainda não foi escrito/validado (`providers/external.py` retorna BLOCKED_EXTERNAL). A chave no painel habilita o teste de conexão e a detecção de saúde; o adaptador de streaming é o próximo passo.

- ✅ Site todo em PT/EN/ES (seletor em todas as telas; `npm run i18n:check` = 380 textos). Mensagens do servidor: só as comuns traduzidas.
- ✅ Busca pública de igrejas + perfil/QR da igreja (`test_public_dir.py`). Demo da landing e página do ouvinte com player de áudio (voz do aparelho) — **voz real dos provedores ainda não**.
- ⛔ Apps Android/iOS/Windows (fluxo ouvinte/palestrante definido em PROJECT_MEMORY §4c) — não iniciados.

- ✅ Produto genérico (não só igreja) e idiomas de tradução dinâmicos vindos dos provedores configurados (`test_realtime.py`: lista pública, WS rejeita idioma não oferecido, parser da descoberta do Azure). **Descoberta real do Azure não foi executada** (sem chave); Gemini não oferece API de descoberta.
- ✅ Redesign visual completo (landing, acesso, painel, ouvinte). Revisado no navegador (desktop e celular).

## Itens abertos de segurança (honestos)
- RLS PostgreSQL nunca rodou (sem Postgres local). Até lá o isolamento é na camada de aplicação (testado).
- Rate limit e hub WebSocket são em memória → 1 réplica. Para escalar: Redis (ADR-006).
- CSP do site usa `'unsafe-inline'` em scripts (exigência do Next sem nonce) — ADR-009.
- Tela de pagamento real do Stripe e push não existem; e-mail (Resend) existe mas sem chave cai para mostrar o link ao admin.

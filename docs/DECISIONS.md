# DECISIONS (ADRs resumidos)

- **ADR-001 Monorepo** `apps/*`, `services/*`, `packages/*`, `docs/*` conforme a spec.
- **ADR-002 Python 3.12 / FastAPI / SQLAlchemy 2 (sync)**. A máquina tinha 3.10 como padrão; usamos 3.12 via venv. Sessões síncronas por simplicidade; WebSocket e canais são `asyncio`.
- **ADR-003 SQLite local, PostgreSQL em produção.** Sem Docker na máquina de desenvolvimento. Isolamento: filtro `scoped()` (sempre) + RLS Postgres (migração 0002, ainda não executada).
- **ADR-004 Web primeiro**, mobile depois (pedido do dono). Contratos serão extraídos do OpenAPI na Fase 9.
- **ADR-005 Auth própria** (Argon2id + JWT 15 min + refresh opaco rotacionado em cookie httpOnly SameSite=Strict, header `X-Requested-With` anti-CSRF). Mobile usa refresh no corpo (`X-Client: mobile`). Access token só em memória no navegador.
- **ADR-006 Rate limit/hub em memória** (1 processo). Para várias réplicas: Redis (mesma interface). Documentado como limite de escala.
- **ADR-007 Texto da tradução ≠ ASR do original.** Texto vem do provedor de tradução; ASR do original é pipeline separado (kind=`original`).
- **ADR-008 Stripe atrás de interface** (`FakeStripe`/`RealStripe`); `fake` é padrão; `live` só com `APP_ENV=production`.
- **ADR-009 CSP do site com `'unsafe-inline'` em script** (Next sem nonce). Mitigação: sem HTML de usuário renderizado como HTML, React escapa tudo; revisar migração para nonce.
- **ADR-010 Janela de 10 s na detecção de reuso do refresh token.** Duas abas/efeitos simultâneos geravam falso positivo de roubo. Fora da janela, reuso revoga a família inteira. Cliente também faz "single-flight".
- **ADR-011 Elevação do super admin** por token de 10 min, somente leitura, com motivo auditado; sem bypass.
- **ADR-012 Voz do ouvinte (fase atual)** = TTS do navegador sobre o texto traduzido, até o relay de áudio dos provedores existir.
- **ADR-013 Trial automático** (1 evento, 60 min-idioma) no cadastro, sem cartão, para o onboarding.
- **ADR-014 Referências bíblicas**: apenas detectadas e sinalizadas; o sistema não completa nem "corrige" versículos (evita fabricar escritura).

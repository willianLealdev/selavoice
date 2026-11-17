# SelaVoice — MEMÓRIA DO PROJETO (leia isto primeiro)

> Objetivo deste arquivo: quem pegar o projeto (pessoa ou IA) entende tudo SEM reler o código.
> **Regra de manutenção:** ao terminar qualquer tarefa, atualize as seções "Estado atual" e "Próximos passos".
> Última atualização: 2026-11-16 · Estado detalhado por fase: `docs/BUILD_STATUS.md`.

## 1. O que é
SaaS multitenant de **tradução simultânea em tempo real para QUALQUER evento** (conferências, feiras/expos, empresas, escolas, associações, igrejas…). **Não é exclusivo de igrejas**: textos e nomes são genéricos (organização/evento/documento); igreja é apenas um tipo de organização. Piloto: UFC Church (Las Vegas).
O ouvinte escaneia um QR, escolhe o idioma e vê/ouve a tradução com **transcrição acumulada** (parágrafos ficam, rola para trás, "Voltar ao vivo").
Organizadores criam eventos, operam a transmissão, revisam transcrições e publicam apostilas em PDF. O dono da plataforma é o Super Admin.
Especificações originais: `Projeto_Plataforma_Traducao_IA_SaaS.pdf` e `llms (1).txt` (em Downloads do dono). Logo: `apps/web/public/logo.webp`.

## 2. Mapa de pastas
```
SelaVocie/
├─ apps/web/                 Next.js 16 + TypeScript (landing, painel, ouvinte, super admin)
│   ├─ app/page.tsx          Landing de vendas          ├─ app/login, register
│   ├─ app/dashboard/*       Painel do organizador      ├─ app/e/[code]   Página PÚBLICA do ouvinte (QR)
│   ├─ app/admin/*           Super admin (MFA)          ├─ app/fake-checkout  Pagamento simulado (dev)
│   └─ lib/api.ts, session.ts  Cliente da API + sessão
├─ apps/mobile/              (vazio — Fase 9, depois que a web estiver validada)
├─ services/api/             FastAPI (Python)  ← o cérebro
│   ├─ app/main.py           Cria o app, middlewares, rotas
│   ├─ app/config.py         Variáveis de ambiente + trava de segurança de produção
│   ├─ app/db.py             Engine, sessão, set_tenant_context (RLS), scoped()
│   ├─ app/models.py         TODAS as tabelas (comentadas)
│   ├─ app/security.py       Argon2, JWT, TOTP, Fernet, URLs assinadas
│   ├─ app/deps.py           Auth/RBAC/tenant a partir da membership; elevação do super admin
│   ├─ app/core/             ratelimit.py, middleware.py (cabeçalhos de segurança, logs JSON)
│   ├─ app/routers/          auth, orgs, events, live (WS+público+ingest), billing, documents, admin
│   ├─ app/services/         billing.py (Stripe+cotas), channels.py (canais por idioma), transcripts.py (hub), editorial.py (apostila+PDF)
│   ├─ app/providers/        base.py (interface), mock.py, external.py (Gemini/Azure BLOQUEADOS), failover.py
│   ├─ app/seed.py           super admin + planos + UFC Church (dev)
│   ├─ alembic/              migrações (0002 = RLS PostgreSQL)
│   └─ tests/                42 testes (pytest)
├─ services/media, services/worker   (reservados — Fases 4/6 completas dependem de chaves/infra)
├─ tools/ingest-windows/     Utilitário de captura (qualquer entrada de áudio; NÃO testado com hardware real)
├─ docs/                     esta memória, status, decisões, bloqueios, ameaças, manual do dev, diagramas
├─ docker-compose.yml        Postgres+Redis+MinIO+API+Web (NÃO executado: Docker não instalado aqui)
└─ .env.example              todas as variáveis
```

## 3. Como rodar (Windows, sem Docker)
```bash
# API
cd services/api
.venv\Scripts\python.exe -m app.seed                # cria dados iniciais (anote as senhas impressas!)
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# Testes
.venv\Scripts\python.exe -m pytest -q
# Web
cd apps/web && npm install && npm run dev            # http://localhost:3000
```
O `.claude/launch.json` já tem as configs `api` e `web` para o botão de preview do Claude.
Banco local = SQLite (`selavoice.db`). Produção = PostgreSQL (`DATABASE_URL` + `alembic upgrade head`).

## 4. Conceitos-chave (decisões que não podem ser quebradas)
1. **Tenant nunca vem do cliente.** `deps.get_ctx` deriva o tenant da *membership*. `X-Org-Slug` só escolhe entre orgs às quais o usuário já pertence. Dados de outro tenant respondem **404**.
2. **Super admin não tem bypass.** Para ver dados de um cliente: `POST /admin/elevate` (motivo ≥10 chars, auditado, 10 min, SOMENTE LEITURA). Rotas `/admin` exigem MFA (TOTP).
3. **Um canal de tradução por (sessão, idioma)**, compartilhado (`services/channels.py`). Sem ouvinte = sem custo (carência `CHANNEL_GRACE_SECONDS`). Minuto-idioma é a unidade de medição (`usage_events`, append-only).
4. **Transcrição acumulada:** `(session, language, seq)` UNIQUE; provisórios aumentam `revision`; final é IMUTÁVEL; replay por `last_seq`. WebSocket autentica na 1ª mensagem (token nunca na URL).
5. **Dinheiro:** direitos só após **webhook Stripe verificado** (HMAC + tolerância) e **deduplicado** (`stripe_webhook_events.stripe_event_id` UNIQUE). Falha de pagamento não concede. Versões de plano **imutáveis**; assinante mantém a versão contratada.
6. **DeepSeek só edita texto** (nunca traduz/transcreve). Apostila só publica após **aprovação humana** e revisão das referências bíblicas sinalizadas.
7. **Nada de afirmar o que não foi medido:** latência 2 s, nº de idiomas, preços de IA — tudo é meta/estimativa até medir (matriz de capacidade com `verified`).
8. Segredos só no backend; `APP_ENV=production` **recusa subir** com segredos fracos (`config.py`).

## 4b. Chaves de API — painel (NÃO precisa editar .env)
Super Admin (com MFA) › **/admin/integrations**: Gemini, Azure, Deepgram, DeepSeek, **Resend (e-mail)** e Stripe (chaves + webhook + modo fake/test/live).
- Código: `services/secrets_store.py` (cofre: cifrado Fernet no banco, nunca devolvido, auditado sem valores; prioridade painel > .env), rotas `routers/admin.py` (`/admin/integrations*`, com "Testar conexão").
- Stripe `live` exige chave `sk_live_` + digitar "CONFIRMO COBRANCA REAL". Resend: `services/email.py` (convites, recuperação de senha; sem chave, o link do convite é mostrado ao admin).
- **Captura de áudio é agnóstica de fonte**: página `/dashboard/events/[id]/capture` (microfone do celular/notebook/qualquer entrada do navegador) e `tools/ingest-windows/capture.py` (qualquer entrada do computador: mesa, interface USB, etc.). Ambos usam o WS `/sessions/{id}/ingest`.
- Produção: definir `ENCRYPTION_KEY` fixa (se trocar, chaves salvas ficam ilegíveis e precisam ser recolocadas).

## 4c. Produto: quem usa o quê (decisões do dono, 2026-11-16)
- **GENÉRICO**: nunca usar "igreja/culto/pregador/apostila" como termo do produto. Usar organização, evento, palestrante, documento pós-evento. Tipos de organização: empresa, organizador de eventos, feira/expo, educação, associação, igreja, outro.
- **IDIOMAS DE TRADUÇÃO são dinâmicos**: `GET /public/languages` = união dos idiomas dos provedores CONFIGURADOS (`services/languages.py`, `TranslationProvider.configured()/refresh_languages()`); Azure descobre pela API (vozes + Translator); Gemini não tem descoberta (lista estática mínima, não verificada); simulador só fora de produção. O ouvinte escolhe num seletor pesquisável (`components/LanguagePicker.tsx`, nomes via `Intl.DisplayNames`). O WS recusa idioma fora da lista (4404). Os 3 idiomas (PT/EN/ES) são só da INTERFACE do site.
- **Ruído, idioma e cobrança só com fala (2026-11-17)**: (1) PORTÃO DE VOZ no servidor (`services/audio_gate.py`): descarta o que é bem mais baixo que o palestrante (Normal -12 dB, Forte -8 dB), pré-rolagem 0,2 s, retenção 0,4 s virando silêncio, e depois do fim da frase NÃO envia mais nada ao provedor (silêncio não custa); botão "Calibrar voz do palestrante" (5 s, `POST /sessions/{id}/audio-calibrate`) ensina o volume antes do evento. (2) IDIOMA DO EVENTO: o Gemini informa `inputTranscription.languageCode` por trecho; com `only_event_language` (padrão ligado) fala em outro idioma NÃO é traduzida nem vira original (testado ao vivo: inglês ignorado em evento pt); Deepgram com confiança < 0,5 em trechos de 3+ palavras = ininteligível ("línguas estranhas"/algazarra) e a tradução pausa por 4 s. (3) CONFIGURAÇÃO por organização em Perfil > Áudio e ruído (`tenant.settings.audio`: filter off|normal|strong, noise_suppression, only_event_language); a captura pelo navegador liga a supressão de ruído/eco/ganho do navegador conforme essa opção. (4) COBRANÇA de minutos-idioma só com TRADUÇÃO entregue (`ChannelManager._touch_active`, respiro máx. 3 s): silêncio não conta. As HORAS DE TRANSMISSÃO do plano continuam contando desde o início do evento (decisão anterior). Testes: `test_audio_gate.py`. LIMITE: separação por VOLUME; voz sobreposta do mesmo volume não é separada (exigiria modelo de separação de locutores).
- **Teste grátis configurável (2026-11-17)**: o DONO define no Super Admin (`/admin/teste-gratis`) se existe teste, a validade em dias e TODOS os limites (mesmo editor e mesmas regras de um plano: `components/LimitsEditor.tsx`, `plan_schema.normalize`). Guardado em `platform_settings` (`services/platform_settings.py`, migração 0005); `grant_trial` lê dali (vale só para contas NOVAS). API: `GET/PUT /admin/trial` (auditado) e `GET /public/trial` (aberta). Landing, preços, FAQ e cadastro leem `/public/trial` (`lib/trial.ts`): ligado mostra o teste configurado; desligado remove ofertas e muda os botões para "Criar conta". Padrão inicial em `DEFAULT_TRIAL`. Testes: `test_trial.py`.
- **Confirmação de e-mail no cadastro (2026-11-17)**: `User.email_verified_at` + tabela `email_verifications` (migração 0004, idempotente; contas antigas ficam confirmadas). Em PRODUÇÃO é obrigatória (`REQUIRE_EMAIL_VERIFICATION` força on/off; padrão: on em produção, off em dev/teste). Cadastro cria conta INATIVA, sem tokens; e-mail via Resend com link `/verificar?token=` (uso único, 24 h); login com conta não confirmada = 403; `POST /auth/verify-email`, `POST /auth/resend-verification` (genérico, 1 envio/min). Convite aceito e redefinição de senha também confirmam. Super Admin vê contas pendentes e pode ATIVAR manualmente com motivo (Controle de acessos). Em dev o cadastro devolve `dev_verify_token` (nunca em produção). Landing: botão Entrar leva a `/app` (ouvinte ou palestrante). Testes: `test_email_verify.py`.
- **Repositório e deploy (2026-11-17)**: código em https://github.com/willianLealdev/selavoice (PÚBLICO por enquanto — tornar privado). Segredos fora do git (`.gitignore`: `dados.txt`, `docs/ACESSOS_DEV.md`, `.env`, bancos). CI do GitHub verde (pytest, pip-audit, tsc, build, npm audit). Dockerfiles em `services/api` e `apps/web` (NUNCA executados com Docker local) + guia `docs/DEPLOY_EASYPANEL.md` (SQLite em volume `/data` no 1º teste; Postgres/RLS ainda NÃO testados). Ensaio local em modo produção (banco novo, `alembic upgrade head`, seed, API, cookie Secure, /docs 404) passou; ele achou e corrigiu a migração 0003 (agora idempotente). `STORAGE_DIR` configura a pasta de PDFs/logos.
- **Original ao vivo (2026-11-17)**: `services/original_asr.py` (Deepgram, 1 conexão por SESSÃO, abre com o 1º áudio, fecha ao fim da ingestão/evento; trechos firmes agrupados até `speech_final`; kind=`original`, `publish=False`). Reserva: Gemini devolve `inputTranscription` e o canal de menor idioma grava o original quando o Deepgram não está ativo. O documento pós-evento agora nasce da transcrição automática (+ resumo DeepSeek). Testes: `test_original_asr.py`.
- **Tradução real ligada (2026-11-16)**: caminho completo palestrante(ingest WS, PCM16 16 kHz) -> `ChannelManager.push_audio` (fila por canal/idioma) -> adaptador do provedor -> VOZ (quadro binário PCM16 24 kHz) + TEXTO ao ouvinte (`live.py`; `e/[code]/page.tsx` toca via WebAudio, voz do aparelho só como reserva). **Gemini** (`providers/gemini.py`, Live Translate, protocolo da doc oficial, conexão preguiçosa, `health()` faz aperto de mão real com cache; idiomas = tabela da DOCUMENTAÇÃO em `gemini_languages.py`, `verified=False`). **Azure** (`providers/azure_session.py`, SDK oficial; chave falsa => 401 tratado; tradução real NUNCA executada). `streaming_implemented` decide se o provedor é oferecido ao público. Testes: `test_gemini.py` (servidor FALSO que imita a doc), `test_azure.py`. **Gemini validado com chave real em teste curto (EN<->PT, ~4 s de atraso inicial)**; o servidor de API precisa ser REINICIADO após mudar código (sem hot-reload).
- **PWA (2026-11-16)**: o site é instalável como app (`app/manifest.ts`, `public/sw.js`, ícones em `public/icons/` gerados do símbolo da logo, `components/InstallApp.tsx`). Tela inicial `/app` (Ouvinte: QR por câmera via `BarcodeDetector`, código do evento, busca; Palestrante: login). O service worker guarda só `/offline` e ícones (NUNCA API/WebSocket/páginas). Instalar no celular exige HTTPS (ou localhost). iPhone: passo a passo (sem botão automático). Não é app de loja (Play Store/App Store): isso continua sendo a etapa Expo/Windows.
- **Planos completos (2026-11-16)**: plano MENSAL ou POR EVENTO, editor em `/admin/planos`. Limites em `services/plan_schema.py` (null = ilimitado; chave ausente = padrão antigo): horas de transmissão (`included_hours`, `max_event_hours`), ouvintes simultâneos, equipe, eventos ao vivo simultâneos, idiomas simultâneos, idiomas permitidos, minutos-idioma, eventos incluídos, gravação, PDF, retenção, excedente, hora extra (só informativo). HORAS: `services/event_clock.py` conta desde o INÍCIO da transmissão (um lançamento `event_minute` por minuto, idempotente), abate de `Entitlement.event_minutes_remaining`, e ENCERRA o evento sozinho ao acabar as horas ou atingir o teto por evento; `Event.entitlement_id` prende o evento ao plano. Aplicação: lotação/idiomas no WS do ouvinte (`live.py`), vagas de equipe (`orgs.py`), PDF/gravação (`documents.py`/`events.py`), `GET /events/{id}/usage`. Migração `alembic/versions/0003_plan_hours.py` (aplicada só no SQLite local; PostgreSQL NÃO executado). Testes: `tests/test_plans.py`.
- **Super Admin profissional (2026-11-16)**: `app/admin/layout.tsx` (menu lateral + guarda Super Admin/MFA) e telas Visão geral (`/admin`), Custos e receita (`/financeiro`, tarifas por provedor), Controle de acessos (`/acessos`, online agora, derrubar sessões), Organizações, Planos, Provedores, Auditoria. API em `routers/admin_stats.py` (`/admin/overview|access|finance`, `PUT /admin/providers/{n}/rate`). Gráficos SVG em `components/Charts.tsx`. "Online agora" = login/renovação nos últimos 15 min; custo = minutos × tarifa configurada (sem tarifa = estimativa); receita = vendas confirmadas por webhook (não é conciliação contábil). Dados de DEMONSTRAÇÃO: `services/api/tools_seed_demo_usage.py` (`--clear` apaga). Testes: `tests/test_admin_stats.py`.
- **Logo + dados públicos (2026-11-16)**: logo enviado em Perfil da organização (`POST/DELETE /organizations/me/logo`; Pillow decodifica e regrava como PNG ≤512 px, SVG recusado, 2 MB; servido em `GET /public/orgs/{slug}/logo`). `logo_url` só o servidor define. Contato público (`settings.contact`: descrição, endereço, cidade, site, Instagram/Facebook/YouTube/TikTok, telefone, WhatsApp, e-mail) validado em `services/contact.py` e exibido por `OrgContact`/`OrgLogo` no perfil, ouvinte e busca. Testes: `tests/test_logo.py`.
- **Voltar + histórico (2026-11-16)**: `components/BackButton.tsx` em TODAS as páginas (exceto a inicial); ouvinte redesenhado (faixa escura de título, texto em "papel", player flutuante); perfil público `/o/[slug]` com abas *Ao vivo e próximos* / *Histórico de eventos* (API `history`, opção `history_public` no perfil da organização); painel lista eventos em cartões (`components/DateBox.tsx`).
- **Design system** (redesign 2026-11-16): `app/globals.css` (tokens, Inter, bordas finas, sem gradientes/emoji), ícones em `components/Icon.tsx`, telas de acesso em `components/AuthShell.tsx`. Mockups da landing são HTML/CSS reais (`LiveDemo.tsx`).
- **Igreja/organizadora SEMPRE tem conta**, criada no SITE. **Ouvinte NUNCA precisa de conta.**
- Ouvinte entra por: QR do evento, QR do PERFIL da igreja (`/o/<slug>`, fixo/imprimível) ou BUSCA pelo nome (`/buscar`, `routers/public.py`; igreja pode sair da busca em Perfil da igreja).
- **Apps (futuros, Fase 9): Android, iOS e Windows.** Ao abrir: "ouvinte" ou "palestrante". Ouvinte vai direto (escanear QR ou buscar igreja). Palestrante faz login e transmite. **Só o app Windows (e o site) transmitem**; mobile = ouvinte (o site também transmite pelo celular). Windows: app desktop (Electron/Tauri) reaproveitando `capture` + login; mobile: Expo.
- **Ouvinte recebe ÁUDIO + TEXTO** (modos áudio+texto / só áudio / só texto, player, volume). Hoje a voz = TTS do aparelho sobre o texto traduzido; voz do provedor de IA depende do relay (BLOCKERS #13).
- **Todo o sistema em PT/EN/ES**: `apps/web/lib/i18n.tsx` (+ `lib/dict.ts`, chave = texto em português). Novo texto: use `t("...")`, adicione a linha em `dict.ts`, rode `npm run i18n:check`. Mensagens de erro do servidor passam por `t(err)` (as mais comuns estão no dict; as demais aparecem em português). Traduções feitas por IA: revisar com falantes nativos.

## 5. Estado atual (resumo — detalhes em BUILD_STATUS.md)
- ✅ Fases 0–3 funcionando e testadas; Fase 7 (cobrança) com Stripe SIMULADO testado; Fase 6 (apostila+PDF) funcionando com texto importado.
- 🟡 Fase 4 (áudio): endpoint de ingestão com token efêmero, limites e métricas — **falta** relay de áudio traduzido aos ouvintes e teste com X32.
- 🟡 Fase 5: interface, simulador, circuit breaker e failover por idioma testados — **Gemini/Azure reais BLOQUEADOS** (sem chaves).
- ⛔ Fases 9 (mobile), 10 (carga/deploy), 11 (expansão): não iniciadas. RLS do PostgreSQL escrito, **não executado** (sem Postgres/Docker).
- Testes: `pytest` = 62 verdes. Auditoria: `pip-audit` e `npm audit` = 0 vulnerabilidades (2026-11-16). `next build` OK.

## 6. Próximos passos (ordem sugerida)
1. Dono fornece chaves de teste (Gemini, Azure, Deepgram, Stripe test) → integrar adaptadores reais e medir latência/custo (ver `BLOCKERS.md`).
2. Instalar Docker → `docker compose up` e executar a migração 0002 (RLS) + testes de RLS em PostgreSQL.
3. Relay de áudio por idioma (WebRTC/SFU) + player de voz no ouvinte.
4. Gráficos de custo por evento/idioma, margem, exportações, notificações (Fase 8).
5. Worker faster-whisper + Deepgram; tradução de apostilas por provedor configurado.
6. App mobile (Expo) reaproveitando tipos/contratos.
7. Testes E2E Playwright, carga de 40 min, backup/restore, runbooks.

## 7. Como o ambiente local foi montado (para reproduzir)
Python 3.12 em `services/api/.venv`; Node 24; sem Docker; SQLite. Senhas de demo são geradas aleatoriamente pelo seed.

## Ativar plano manual + evento privado + logo (última rodada)
- **Ativar plano manual (Super Admin > Organizações)**: `GET /admin/tenants/{id}/entitlements`, `POST /admin/tenants/{id}/grant-plan` (plano existente OU vitalício ilimitado; dias opcionais; motivo ≥10 auditado; `Entitlement.source="manual"`), `POST /admin/entitlements/{id}/deactivate`. Tela mostra os saldos (explica o 402 "sem plano").
- **Evento privado**: `events.access_password_hash` (argon2, migração 0006). Criar evento: `private` + `access_password` (≥4). `GET /public/join/{code}` sem a senha (cabeçalho `X-Event-Password`) devolve só título/organização; `POST .../token` exige `{password}` (403 se errada, 10/min). Eventos privados NÃO aparecem no perfil público/histórico nem em apostilas públicas. Tela do ouvinte pede a senha (guardada só em sessionStorage).
- **Logo**: `logo.webp` agora com fundo transparente + `color-scheme: light` (Safari escuro não escurece mais o site).
- Testes: 128 passando.
- **Horas do plano só com fala** (decisão do dono): `events.active_seconds` (migração 0007) alimentado por `channels._touch_active`/`take_speech` e gravado pelo relógio; `charge`/`limit_reached` usam `speech_minutes`. Silêncio e pausas não gastam horas; o teto `max_event_hours` também conta só fala. `/events/{id}/usage` traz `speech_minutes`.
- **Recargas** (`topup_packs`, migração 0008): admin cria pacotes (horas e/ou eventos, preço) em /admin/recargas; cliente compra em /dashboard/billing (`GET /topups`, `POST /topups/checkout`, webhook com `metadata.topup_pack_id` -> `apply_topup` soma no direito ativo ou cria um `topup`). Ajuste manual: `POST /admin/tenants/{id}/topup`. Stripe real nunca testado (preço criado na 1ª compra).
- **Editar evento**: `PATCH /events/{id}` aceita título/palestrante/tema/descrição/privacidade em qualquer estado (exceto cancelado); idioma/tipo/data/gravação só AGENDADO.
- **Excluir evento**: `DELETE /events/{id}` (exclusão lógica `events.deleted_at`, migração 0009; ao vivo = 409; some das listas e do público). Lista do painel: abas "Próximos e ao vivo" x "Histórico" (encerrados/cancelados).
- Testes: 133 passando. Não verificado em navegador nesta rodada.
- **Apostilas salvas no evento**: `GET /documents/events/{id}` lista tudo que foi gerado (antes só aparecia na hora); tela do evento mostra rascunho/revisão/aprovado/publicado com Ver e editar, PDF e Excluir (`DELETE /documents/{id}`, apaga o PDF). Perfil público da organização traz `booklets` (publicadas) em cada evento. Testes: 134.
- **Apps das lojas (2026-11-17)**: `apps/mobile/` = Capacitor 7 (casco que abre `https://selavoice.com/app`, nunca a landing; `appendUserAgent: SelaVoiceApp`), `scripts/patch-native.mjs` (permissões, versão, assinatura CM_KEYSTORE_*, iPhone-only), ícone/splash em `resources/`, imagens das lojas em `store/`. `codemagic.yaml` (Android .aab + iOS .ipa/TestFlight) **NUNCA executado**; Android/iOS nativos gerados com `cap add` só foram verificados localmente (sem SDK/Mac, sem build). Windows: PWABuilder (MSIX). Guia/cronograma: `docs/PUBLICAR_LOJAS.md`. Exigências das lojas feitas: excluir conta (`POST /auth/me/delete`, Perfil), `/legal/excluir-conta`, política de privacidade real (REVISÃO JURÍDICA pendente), compras escondidas no app (`lib/native.ts`). Risco: Apple 4.2.
- **Lojas — estado (2026-11-17)**: Android .aab assinado gerado localmente (build-lojas/, chave em ~/selavoice-keys/, fora do repo; BACKUP obrigatório). iPhone: projeto Expo/EAS @willianleal/selavoice (apps/ios-expo, bundle com.selavoice.app), .ipa build 3 gerado e baixado; certificado Apple Distribution + perfil App Store criados no portal da Apple (credenciais locais em ~/selavoice-keys/ios/, credentials.json ignorado). App criado na App Store Connect (ID 6835756964; iOS 1.0 e macOS 1.0 em Prepare for Submission), ficha pt-BR preenchida (descrição, palavras-chave, URLs, notas). PENDENTE: baixar a chave de API 'SelaVoice Publicacao' (Key ID KLWD8SP56L) pelo botão da App Store Connect e então eas submit (TestFlight) + capturas (apps/mobile/store/capturas) + contato do revisor/conta de teste + enviar para revisão. macOS: precisa de build próprio. Windows: não iniciado (PWABuilder + Partner Center).
- **UX (2026-11-17)**: Ouvinte (`/e/[code]`): se não há idioma salvo no celular (`localStorage sv_lang`) pergunta "Em qual idioma você quer ouvir?" (modal com busca); depois não pergunta mais e o botão de idioma do topo troca sempre; alerta azul "Áudio em transmissão! Toque no Play" (+vibração) quando o evento está ao vivo e o áudio não está tocando. Organizador (`/dashboard/events/[id]`): captura de áudio na MESMA tela (`lib/useCapture.ts`): 1) ativar microfone (nível) -> 2) botão "Iniciar e traduzir" só habilita com o microfone pronto e já liga o envio de áudio; `/capture` agora só redireciona. Verificado no navegador local só o lado do ouvinte; a tela do organizador passou em tsc mas NÃO foi testada com microfone real.
- **Apostila AUTOMÁTICA (2026-11-17)**: ao encerrar o evento (botão Encerrar ou encerramento automático pelo relógio) `services/auto_book.py` lê a transcrição, a DeepSeek escreve os pontos (resumo, seções, frases marcantes, referências, perguntas, conclusão; transcrições longas em 2 etapas) e `editorial.render_book` gera o PDF profissional (logo da organização na capa e no cabeçalho, cor da marca, sumário, rodapé com página, aviso de IA) e PUBLICA sem revisão. Filtro anti-invenção (só frases/referências que existem na fala). Sem chave da DeepSeek = plano B local (partes numeradas). Não gera se: org desligou (`settings.auto_booklet`), plano sem `pdf_booklets`, já existe, <300 caracteres, idioma sem suporte no PDF (russo/árabe/hindi... só latino + zh/ja/ko). `POST /documents/events/{id}/auto` refaz. Fluxo manual de rascunho/revisão continua existindo em "Avançado". Testes: 142. NÃO testado com a DeepSeek real (só com resposta simulada): validar o texto num evento real.
- **App Store Connect (via API, chave SelaVoice Publicacao)**: .ipa build 3 enviado ao TestFlight (válido), build ligado à versão 1.0, categoria Produtividade, política de privacidade, subtítulo, classificação etária (userGeneratedContent=true), capturas iPhone 6.7" enviadas. FALTA: contato do revisor + conta de teste, App Privacy (questionário) e clicar em enviar para revisão.

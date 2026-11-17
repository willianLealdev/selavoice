# Rodada de testes pela WEB (2026-11-16)

Feita no navegador real (site + API locais, simulador de IA, Stripe simulado). ✅ = passou · 🔧 = achou defeito e corrigiu · ⚠️ = limitação conhecida.

| # | Fluxo | Resultado |
|---|---|---|
| 1 | 21 rotas do site respondem; API pública responde | ✅ |
| 2 | Ouvinte: busca igreja → perfil → evento ao vivo | ✅ |
| 3 | Ouvinte: modos áudio+texto / só áudio / só texto; troca de idioma da tradução (EN→ES); interface em ES | ✅ |
| 4 | Ouvinte: rolagem não pula, "Voltar ao vivo", reconexão | ✅ (testado antes) |
| 5 | Igreja: login pelo formulário, lista de eventos | ✅ |
| 6 | Igreja: criar evento pelo formulário | 🔧 hora aparecia errada (+8 h): SQLite devolvia data sem fuso → API agora sempre envia UTC (`core/timeutil.py`, teste novo) |
| 7 | Evento: QR, iniciar, limite de eventos simultâneos (2º evento recusado) | ✅ |
| 8 | Captura de áudio pelo navegador (fonte sintética): conecta, servidor recebe | 🔧 descartava ~6 % do áudio ao reamostrar → reamostrador contínuo; agora 255 kbps (esperado 256) |
| 9 | Cobrança: contratar → checkout simulado → webhook → 0 → 8 eventos, +2.400 min | ✅ |
| 10 | Apostila: importar → gerar → refs bíblicas → bloqueio sem revisão → aprovar → publicar → PDF público | ✅ |
| 11 | Perfil: QR, desmarcar/marcar "aparecer na busca" afeta a busca pública | ✅ |
| 12 | Equipe: convite (sem Resend mostra o link) → aceitar → operador login | ✅ |
| 13 | Permissões do operador: cria evento ✔; equipe/cobrança/convite/admin = 403 | ✅ · 🔧 menus de admin apareciam ao operador → agora escondidos |
| 14 | Super Admin: login com MFA, métricas, planos, provedores, auditoria | ✅ |
| 15 | Chaves: salvar (cifrado, mascarado), testar conexão, apagar | ✅ · 🔧 teste do Google (HTTP 400) agora diz "RECUSADA" |
| 16 | Celular (375 px): landing, busca, ouvinte, cadastro | ✅ |
| 17 | Celular: dashboard e admin ficavam mais largos que a tela | 🔧 tabelas rolam dentro da caixa |
| 18 | Site não pode ser embutido em iframe (anti-clickjacking) | ✅ |

## Ainda NÃO testado (precisa de chave/hardware/conta)
- Envio real de e-mail (Resend), Stripe real, Gemini/Azure/Deepgram/DeepSeek reais.
- Microfone real/celular real/mesa de som; voz traduzida dos provedores (hoje é a voz do aparelho).
- "Esqueci minha senha" ponta a ponta com e-mail real (a lógica tem teste automatizado com envio simulado).
- Telas "Perfil/Equipe/Plano" em ES/EN lidas por um falante nativo; mensagens de servidor sem tradução aparecem em português.
- Carga (muitos ouvintes), 40 min de evento, PostgreSQL/RLS, Docker.

## Pontos menores conhecidos
- Ao carregar com idioma ≠ português há um breve "piscar" em português antes de trocar.
- A página `/mapa` é só de desenvolvimento (apagar antes de publicar).

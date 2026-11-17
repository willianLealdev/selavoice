# BLOCKERS — o que depende do dono (BLOCKED_EXTERNAL)

Nada abaixo foi inventado ou simulado como "funcionando". Cada item diz o que fornecer e o que será liberado.

| # | Bloqueio | O que fornecer | O que libera |
|---|---|---|---|
| 1 | Gemini Live (primário) | `GEMINI_API_KEY` (conta de teste) | Adaptador real, medir latência/custo/idiomas com voz |
| 2 | Azure Speech (fallback) | `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` | Failover real |
| 3 | Deepgram (ASR fallback) | `DEEPGRAM_API_KEY` | Transcrição do áudio original |
| 4 | DeepSeek (editorial) | `DEEPSEEK_API_KEY` | Esboço/resumo editorial (já protegido: nunca traduz) |
| 5 | Stripe | Conta Stripe em **modo teste**: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_MODE=test` | Checkout/portal reais (NUNCA ligar `live` sem ordem explícita) |
| 6 | Docker | Instalar Docker Desktop | `docker compose up`, teste das políticas RLS no PostgreSQL |
| 7 | Teste de captura real | Qualquer fonte: celular, notebook, mesa de som (X32 ou outra) | Validar captura/latência |
| 12 | Resend | Chave `re_…` + domínio verificado no Resend (cole em Super Admin › Integrações) | Envio real de convites/recuperação de senha |
| 13 | Adaptadores de streaming Gemini/Azure | Chaves + implementação do streaming (ainda não escrita) | Tradução ao vivo real |
| 8 | VPS/Easypanel | Acesso/credenciais e domínio | Deploy de staging/produção (só com autorização explícita) |
| 9 | Apple/Google | Contas de desenvolvedor | Publicar apps (Fase 9) |
| 10 | Revisão jurídica | Advogado | Política de privacidade/termos (hoje são rascunhos) |
| 11 | faster-whisper | Máquina com CPU/RAM/GPU adequadas | ASR local pós-evento |

- **Hora extra automática** (`extra_hour_cents` do plano): o valor é só informativo; a cobrança de excedente por hora no Stripe NÃO está implementada (decisão pendente: fatura manual ou medição por uso no Stripe). Migração 0003 não foi rodada em PostgreSQL.

- **Gemini ao vivo — VALIDADO em teste real curto (2026-11-17)**: fala sintetizada do Windows (EN->PT e PT->EN) e cadeia completa pelo nosso servidor (ingest -> canal -> Gemini -> ouvinte, provider=gemini). Medido (1 execução, voz sintética, rede local): 1º texto ~4,3 s e 1ª voz ~4,8 s após o 1º quadro de áudio; o atraso cresce até ~7 s no fim de uma fala contínua de ~15 s. NÃO prova a meta de 2 s. Falta: voz humana real/sotaques/ruído, sessões longas (limite de duração do Gemini não documentado), vários idiomas ao mesmo tempo, qualidade da voz no celular, custo real (tarifa a configurar em Custos e receita).
- **Azure ao vivo NÃO validado**: adaptador pronto (SDK oficial), nunca executado com chave real (só a recusa 401 foi observada). Pendente: chave + região do usuário.
- **Voz do Azure**: reamostrada 16->24 kHz por interpolação linear (qualidade a conferir). Fim de frase do Gemini (turnComplete/silêncio de 1,5 s) é heurística a validar.

- **Transcrição do original (2026-11-17)**: Deepgram AO VIVO validado em teste curto real (PT, 3 frases corretas, 99,9% de confiança no teste prévio) e Gemini como reserva (sem vírgulas; qualidade menor). DeepSeek (esboço do documento) validado em chamada real. Pendente: voz humana/sotaques, eventos longos, custo real do Deepgram.
- **Chaves NÃO salvas até agora**: Azure (chave+região), Resend (chave+remetente) e Stripe (chave secreta; modo ainda `fake`). Sem elas esses 3 não foram testados.

- **Filtro de ruído (2026-11-17)**: medido só com vozes sintéticas do Windows (palestrante + conversa de fundo). Após o palestrante estabelecer o volume (ou após calibrar), fundo 16 dB abaixo (Forte) / 20 dB abaixo (Normal) foi 100% bloqueado; fundo a -12 dB ou mais forte passa. NÃO testado com sala real, plateia reagindo ("glória"), voz sobreposta nem "línguas estranhas" reais. Detecção de "ininteligível" (Deepgram) é heurística (limiar 0,5) a ajustar com áudio real.


## Lojas de apps (2026-11-17)
- BLOCKED_EXTERNAL: compilar/assinar Android (.aab) e iOS (.ipa) exige Codemagic + chaves do dono (keystore, App Store Connect API); `codemagic.yaml` não foi executado. Windows: pacote MSIX via PWABuilder com identidade do Partner Center.
- Pendências do dono: identificador do app (Bundle ID/pacote) confirmado, e-mail de suporte, capturas de tela, revisão jurídica da política de privacidade, conta de teste com plano ativo.

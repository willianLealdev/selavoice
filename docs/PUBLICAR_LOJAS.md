# Publicar o SelaVoice nas lojas (Google Play, App Store e Microsoft Store)

> Escrito para quem não é programador. Siga na ordem. Onde diz **"me chame"**, copie o erro e cole na conversa.

## 1. Como funciona (em uma frase)

O app das lojas é uma **"moldura"** que abre o seu site `https://selavoice.com/app` (a tela **"Como você quer entrar?"**, nunca a landing page).
Por isso **quase tudo muda sem enviar nova versão para a loja**: basta publicar o site (Deploy no Easypanel) ou mexer no painel.

| Muda SEM nova versão na loja (site/painel) | Exige NOVA versão na loja |
|---|---|
| Telas, textos, cores, idiomas da interface | Trocar o ícone, o nome ou a tela de abertura |
| Planos, preços, recargas, teste grátis, limites | Mudar o endereço do site |
| Regras de áudio, filtros, provedores de IA | Pedir uma nova permissão (ex.: notificações) |
| Correção de erros do site | Recurso nativo novo (notificação push, etc.) |
| Política de privacidade e termos | Exigência nova da Apple/Google para o app |

## 2. O que já está pronto (e o que NÃO foi testado)

Pronto no repositório:
- `apps/mobile/` — projeto da moldura (Android e iOS), com ícone, tela de abertura e permissões de microfone/câmera.
- `codemagic.yaml` — "receita" para o **Codemagic** gerar os arquivos das lojas na nuvem (você não precisa de Mac).
- `apps/mobile/store/` — imagens prontas: ícone 512 (Google Play), gráfico de destaque 1024×500 (Google Play), logo 300 (Microsoft).
- No site: **Excluir minha conta** (Perfil), página **/legal/excluir-conta**, **/legal/privacidade**; dentro do app as **compras ficam escondidas** (a Apple e o Google exigem a compra pela loja deles; aqui o cliente contrata no site).

**Honestidade:** eu criei os projetos Android e iOS aqui no computador e confirmei que a configuração e os ajustes automáticos funcionam,
mas **não compilei o app** (este computador não tem Android SDK nem Mac) e o `codemagic.yaml` **nunca rodou**. Na primeira vez pode dar erro de configuração: me chame.
A política de privacidade foi escrita por mim com base no que o sistema realmente faz; **peça a um advogado para revisar** antes de divulgar.

## 3. O que você precisa ter em mãos

1. **Identificador do app** (o mesmo nas duas lojas): padrão `com.selavoice.app`. **Se você cadastrou outro** no Google Play e na Apple, me diga qual (ou troque `APP_ID` no `codemagic.yaml`).
2. Conta **Codemagic** (codemagic.io — serviço que compila o app na nuvem; entre com o GitHub). Há plano gratuito com minutos limitados: confira o limite atual no site deles.
3. Um **e-mail de suporte** para colocar nas lojas (as lojas pedem).
4. **Capturas de tela reais do app** (veja a seção 7).
5. Uma **conta de teste** (e-mail + senha) já verificada para os revisores da Apple e do Google entrarem. **Não envie a senha por conversa**; coloque direto nos campos das lojas.

## 4. Cronograma (sugestão: ~2 semanas, a maior parte é espera de revisão)

| Dia | O que fazer | Quem |
|---|---|---|
| 1 | Dar **Deploy** (api e web) com tudo atualizado; criar conta de teste; confirmar o identificador do app | você |
| 1 | Entrar no Codemagic, conectar o repositório `selavoice` | você |
| 2 | **Android:** gerar a chave de envio no Codemagic e rodar o fluxo `android-release` → baixar o `.aab` | você (+ eu se der erro) |
| 2–3 | **Google Play Console:** criar o app, preencher ficha (textos da seção 6), segurança de dados, exclusão de conta; subir o `.aab` em **Teste interno** | você |
| 3–4 | **iOS:** criar a chave da API do App Store Connect, ligar no Codemagic, rodar `ios-release` → o app vai ao **TestFlight** | você (+ eu) |
| 4 | Testar nos celulares (Android e iPhone): entrar, ouvir evento, escanear QR, transmitir | você |
| 5 | **Windows:** gerar o pacote no PWABuilder e enviar à Microsoft Store (seção 5) | você |
| 5–6 | Enviar **Google Play** para produção (revisão costuma levar de 1 a alguns dias) | você |
| 6–7 | Enviar **App Store** para revisão (costuma levar 1 a 3 dias; pode haver pedido de ajustes) | você |
| 8–14 | Responder revisores se pedirem algo; publicar quando aprovado | você (+ eu) |

Contas novas do Google Play (pessoais) podem exigir um **período de teste fechado** antes da produção; confira o que aparece no seu painel (contas de organização costumam ter menos exigências).

## 5. Passo a passo por loja

### 5.1 Android — Google Play
1. **Codemagic** → *Team settings* → *Code signing identities* → *Android keystores* → **Generate keystore**. Nome da referência: `selavoice_upload_key`. (O Codemagic guarda a chave; **nunca** ela vai para o GitHub.)
2. Codemagic → seu app → escolha o workflow **SelaVoice Android (.aab)** → **Start new build**.
3. No fim, baixe o arquivo **`app-release.aab`** (em *Artifacts*).
4. **Google Play Console** → *Criar app* → preencha a ficha → *Testes* → *Teste interno* → **Criar versão** → envie o `.aab`.
   - Na primeira vez, aceite o **Play App Signing** (o Google guarda a chave final; a do Codemagic é só a "chave de envio").
5. Preencha: **Segurança dos dados** (coleta e-mail/nome; áudio é processado por provedores de IA), **Classificação de conteúdo**, **Público-alvo**, e em *Política do app* informe:
   - Política de privacidade: `https://selavoice.com/legal/privacidade`
   - Exclusão de conta/dados: `https://selavoice.com/legal/excluir-conta`
6. Quando o teste interno funcionar, promova para **Produção**.
- Para as próximas atualizações do app: aumente `APP_VERSION` no `codemagic.yaml` só se quiser mudar o número visível; o número interno sobe sozinho a cada build.

### 5.2 iPhone — App Store
1. **App Store Connect** → *Users and Access* → *Integrations* → *App Store Connect API* → **gerar chave** (tipo *App Manager*). Baixe o arquivo `.p8` (só baixa uma vez) e anote *Issuer ID* e *Key ID*.
2. **Codemagic** → *Team settings* → *Integrations* → **App Store Connect** → nome da integração: `selavoice_asc` → envie o `.p8` e os dois códigos. (Envie pelo site do Codemagic, **não por conversa**.)
3. No **Apple Developer** (developer.apple.com) confirme que o **Bundle ID** existe e é igual ao `APP_ID`. No **App Store Connect** crie o app (*My Apps → +*) com o mesmo Bundle ID.
4. Codemagic → workflow **SelaVoice iOS (.ipa)** → **Start new build**. O Codemagic cria os certificados sozinho e envia ao **TestFlight**.
5. No iPhone, instale o app **TestFlight**, aceite o convite e teste.
6. **App Store Connect** → versão 1.0 → preencha textos (seção 6), capturas (seção 7), *App Privacy*, URL da política, **informações de revisão** (conta de teste e a nota abaixo) → **Enviar para revisão**.

**Nota para o revisor da Apple (cole em "Notes"):**
> SelaVoice provides real-time translation for events. Listeners join without an account (scan the event QR code or type the event code). Speakers/organizers sign in with the test account provided. Subscriptions are managed on our website (not sold inside the app). Account deletion is in Profile > Delete my account. The microphone is used by the speaker to broadcast speech for live translation; the camera is used to scan the event QR code.

**Risco real de reprovação (Apple 4.2 "app que é só um site"):** a Apple às vezes recusa apps que só embrulham um site. O que ajuda: o app tem função própria (ouvir ao vivo, câmera para QR, microfone), conta de teste e explicação clara. Se recusarem, o caminho é **adicionar recursos nativos** (ex.: notificação "evento começou", compartilhar evento, áudio em segundo plano) — isso exige nova versão e eu faço. Não dá para garantir aprovação.

### 5.3 Windows — Microsoft Store
Usamos o **PWABuilder** (ferramenta gratuita apoiada pela Microsoft que transforma o site instalável em pacote para a loja).
1. **Partner Center** (partner.microsoft.com) → *Apps and games* → **New product → MSIX or PWA app** → reserve o nome **SelaVoice**.
2. No produto → *Product management → Product identity*: copie os 3 valores: **Package/Identity/Name**, **Package/Identity/Publisher** (começa com `CN=`) e **PublisherDisplayName**.
3. Abra **pwabuilder.com**, digite `https://selavoice.com`, clique em *Start* → *Package for stores* → **Windows**. Cole os 3 valores do passo 2. Escolha a versão `1.0.0.0`. Baixe o `.zip`.
4. No Partner Center → *Packages* → envie o arquivo **`.msixbundle`** que está dentro do zip.
5. Preencha a ficha (seção 6), classificação etária (questionário), política de privacidade `https://selavoice.com/legal/privacidade`, e envie para certificação.
6. A Microsoft assina o pacote ao publicar. Atualizações do site aparecem sozinhas no app (ele abre o site); só envie novo pacote para mudar ícone/nome.
- Logo da loja (300×300): `apps/mobile/store/microsoft-logo-300.png`. Capturas: mínimo 1 de desktop (1366×768 ou maior).
- Observação: no Windows o app usa o navegador Edge por dentro; microfone funciona com permissão do usuário.

## 6. Textos para as lojas (copie e cole)

**Nome:** SelaVoice — Tradução ao Vivo  
**Subtítulo / descrição curta (até 80 caracteres):** Tradução simultânea em voz e texto para qualquer evento.

**Descrição completa (PT):**
> O SelaVoice traduz eventos ao vivo, em voz e texto, para o idioma de cada pessoa. Igrejas, conferências, palestras, treinamentos, feiras e reuniões: o público escaneia o QR Code, escolhe o idioma e acompanha em tempo real, sem criar conta.
>
> • Ouça a tradução em voz ou leia a transcrição ao vivo  
> • Entre escaneando o QR Code ou digitando o código do evento  
> • Histórico de eventos e apostilas em PDF publicadas pela organização  
> • Para organizadores: transmita pelo celular ou computador, acompanhe o uso e gerencie eventos, equipe e planos pelo painel  
> • Eventos privados protegidos por senha  
> • Filtro de ruído que prioriza a voz principal do palestrante
>
> A tradução é automática e pode conter erros; não substitui intérprete certificado em situações críticas.

**Description (EN):**
> SelaVoice translates live events into each person's language, in voice and text. Churches, conferences, talks, training sessions, fairs and meetings: attendees scan the QR code, pick a language and follow in real time, no account needed. Organizers broadcast from a phone or computer and manage events, team and plans from a dashboard. Private events are password-protected. Translation is automatic and may contain errors; it does not replace a certified interpreter in critical situations.

**Palavras-chave (Apple, até 100 caracteres):** tradução,ao vivo,evento,igreja,conferência,legendas,interprete,idiomas,voz  
**Categoria:** Produtividade (ou Utilitários) — Apple: *Productivity*; Google: *Produtividade*; Microsoft: *Productivity*.  
**Classificação de idade:** responda os questionários com "sem conteúdo sensível" (o app só traduz o que o organizador transmite).  
**Site / suporte / privacidade:** `https://selavoice.com` · e-mail de suporte (o seu) · `https://selavoice.com/legal/privacidade`

## 7. Imagens que você precisa fazer

| Loja | O que | Tamanho |
|---|---|---|
| Google Play | Ícone | 512×512 — **pronto:** `apps/mobile/store/google-play-icone-512.png` |
| Google Play | Gráfico de destaque | 1024×500 — **pronto:** `apps/mobile/store/google-play-destaque-1024x500.png` |
| Google Play | Capturas de celular | 2 a 8 imagens (proporção 9:16, ex.: 1080×1920) |
| Apple | Ícone | 1024×1024 — **pronto:** `apps/mobile/resources/icon.png` |
| Apple | Capturas iPhone | 1 a 10 imagens, tela grande (ex.: 1290×2796) |
| Microsoft | Logo | 300×300 — **pronto:** `apps/mobile/store/microsoft-logo-300.png` |
| Microsoft | Capturas | 1 a 10 imagens de computador (1366×768 ou maior) |

Para as capturas: abra `https://selavoice.com/app` no celular, tire prints da tela de entrada, da escolha de idioma ouvindo um evento ao vivo, do histórico e do painel. Se quiser, **me peça que eu gere capturas organizadas** a partir do site.

**Ícone:** foi feito a partir da logo original; a qualidade depende da logo. Se você tiver o arquivo original da logo em alta resolução (PNG 2048×2048 do símbolo), me envie que eu refaço o ícone nítido.

## 8. Antes de enviar, confira (lista rápida)

- [ ] Deploy feito (api + web) e o site abre em `https://selavoice.com/app`
- [ ] Conta de teste criada e verificada (e-mail confirmado) **com um plano ativo** (use *Admin → Organizações → Ativar plano*)
- [ ] Resend funcionando (e-mails de confirmação chegando)
- [ ] Stripe: o app **não vende** nada dentro dele; a contratação é pelo site
- [ ] Política de privacidade revisada por advogado
- [ ] Capturas de tela prontas
- [ ] E-mail de suporte definido

## 9. Quando algo der erro
Copie o texto do erro (do Codemagic ou da loja) e cole na conversa. Os erros mais comuns: identificador do app diferente do cadastrado, chave de assinatura não criada, e a loja pedindo algum formulário que ainda falta preencher.

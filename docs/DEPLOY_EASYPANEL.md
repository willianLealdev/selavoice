# Publicar o SelaVoice no Easypanel (teste na prática)

> **Easypanel** = painel que roda no seu servidor (VPS) e publica aplicações a partir do GitHub, com HTTPS automático.
> Este guia publica **2 serviços**: `api` (servidor) e `web` (site). O banco do primeiro teste é **SQLite num disco persistente** (simples e sem risco).

## 0. O que você precisa antes
- Um **servidor (VPS)** com Easypanel instalado e **um domínio** seu.
- Dois endereços no MESMO domínio (isso é obrigatório para o login funcionar — o cookie de sessão é `SameSite=Strict`):
  - `app.SEUDOMINIO.com` → o site
  - `api.SEUDOMINIO.com` → a API
- No DNS do domínio, crie dois registros **A** apontando os dois nomes para o **IP do servidor**.

## 1. Gerar os segredos (no seu computador)
Rode e **guarde num lugar seguro** (gerenciador de senhas). **Nunca** coloque no git.
```bash
python -c "import secrets;print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet;print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets;print('STRIPE_WEBHOOK_SECRET=whsec_' + secrets.token_hex(24))"
```
> ⚠️ **ENCRYPTION_KEY**: cifra as chaves de IA salvas no painel. Se você a perder ou trocar, as chaves salvas ficam ilegíveis (terá de digitá-las de novo). Faça cópia.

## 2. Serviço `api`
1. Easypanel → **Create Project** `selavoice` → **+ Service → App**, nome `api`.
2. **Source → GitHub**: escolha o repositório, branch `main`, **Build → Dockerfile**, caminho de build **`services/api`**.
3. **Environment** (cole, trocando os valores):
```
APP_ENV=production
JWT_SECRET=<gerado no passo 1>
ENCRYPTION_KEY=<gerado no passo 1>
STRIPE_WEBHOOK_SECRET=<gerado no passo 1>
STRIPE_MODE=fake
CORS_ORIGINS=https://app.SEUDOMINIO.com
PUBLIC_WEB_URL=https://app.SEUDOMINIO.com
DATABASE_URL=sqlite:////data/selavoice.db
STORAGE_DIR=/data/storage
SUPER_ADMIN_EMAIL=seu-email@dominio.com
SUPER_ADMIN_PASSWORD=<uma senha FORTE sua, 16+ caracteres>
```
4. **Mounts → Volume**: nome `selavoice-data`, **caminho `/data`** (sem isto o banco some a cada deploy!).
5. **Domains**: `api.SEUDOMINIO.com`, **porta 8000**, HTTPS ligado.
6. **Deploy**. Em **Logs** deve aparecer `Application startup complete`. Teste: abra `https://api.SEUDOMINIO.com/health` → `{"status":"ok"}`.
> A API deve ter **1 única réplica** (os canais de tradução ao vivo ficam na memória).

## 3. Serviço `web`
1. **+ Service → App**, nome `web`, mesma origem GitHub, **Dockerfile**, caminho de build **`apps/web`**.
2. **Build Arguments** (não é "Environment"!): `NEXT_PUBLIC_API_URL=https://api.SEUDOMINIO.com`
   (esse endereço é gravado no site na hora do build; se mudar, faça **novo deploy**).
3. **Domains**: `app.SEUDOMINIO.com`, **porta 3000**, HTTPS ligado.
4. **Deploy** e abra `https://app.SEUDOMINIO.com`.

## 4. Primeiro acesso (Super Admin)
1. Abra `https://app.SEUDOMINIO.com/admin/login`, e-mail/senha do passo 2, **código MFA em branco**.
2. A tela mostra um **QR Code**: escaneie com Google Authenticator/Authy, digite o código e confirme. **Guarde a chave manual.**
3. Entre de novo (agora com o código) → **Chaves e integrações** → cole as chaves do Gemini, Deepgram e DeepSeek → **Salvar** e **Testar**.
4. **Custos e receita** → informe a tarifa (US$/min) de cada provedor.
5. **Planos** → crie/publique os planos.

## 5. Roteiro de teste na prática
- [ ] Criar a conta de uma organização em `/register` e fazer login.
- [ ] Criar um evento, **Iniciar**, abrir **Capturar áudio** no celular (HTTPS é obrigatório para o microfone).
- [ ] Em outro aparelho, abrir `/app` → escanear o QR do evento → escolher idioma → **play**.
- [ ] Falar e conferir: texto, voz traduzida, atraso, transcrição do original, documento pós-evento.
- [ ] Instalar o app (botão **Instalar app**) no celular.
- [ ] Super Admin: ver **Visão geral**, **Controle de acessos**, **Custos e receita** com dados reais.

## 6. Limites conhecidos deste primeiro teste
- Banco **SQLite** (1 arquivo no volume). Para produção de verdade: PostgreSQL — a migração para Postgres e as regras de isolamento por linha (RLS) **nunca foram executadas** e precisam ser testadas antes.
- **Docker nunca foi executado na máquina de desenvolvimento**: o primeiro build no Easypanel pode revelar ajustes. Mande o log de erro que eu corrijo.
- Azure, Resend (e-mail) e Stripe (pagamento) **sem chave** por enquanto: sem e-mail o convite devolve o link para você repassar; o Stripe fica em modo simulado (`fake`) — **nenhuma cobrança real**.
- O repositório está **público por enquanto**: confira que nenhum segredo foi commitado e coloque-o como **privado** assim que possível.
- Faça **backup** do volume `/data` (contém o banco e os PDFs).

"use client";
/**
 * Landing page (pública, PT/EN/ES). Produto para QUALQUER evento — não é específico de nenhum segmento.
 * Copy honesta: não prometemos latência/idiomas/preço ainda não medidos. Apps aparecem como "Em breve".
 */
import InstallApp from "@/components/InstallApp";
import Link from "next/link";
import Icon from "@/components/Icon";
import LiveDemo from "./LiveDemo";
import Pricing from "./Pricing";
import { LangSwitch, useT } from "@/lib/i18n";

export default function Landing() {
  const t = useT();
  const SEGMENTS: [string, string][] = [
    ["landmark", "Conferências e congressos"], ["store", "Feiras e expos"], ["briefcase", "Empresas e treinamentos"],
    ["graduation", "Escolas e universidades"], ["users", "Associações e comunidades"], ["building", "Igrejas e templos"],
  ];
  const FEATURES: [string, string, string][] = [
    ["headphones", "Voz no idioma de cada pessoa", "Cada participante escolhe o idioma e ouve a tradução em voz enquanto o palestrante fala, com volume e controles no próprio aparelho."],
    ["text", "Transcrição que acumula", "O texto aparece como num chat: fica na tela, dá para rolar para trás e voltar ao vivo com um toque. Use áudio, texto ou os dois."],
    ["globe", "Todos os idiomas do provedor", "A lista de idiomas vem direto dos provedores de tradução configurados: se o provedor oferece o idioma, seu público pode escolhê-lo."],
    ["qr", "Entrada sem atrito", "O público entra pelo QR Code do evento, pelo QR do perfil da organização ou buscando pelo nome. Ninguém precisa criar conta."],
    ["layers", "Só paga o que usa", "Idioma sem ouvinte não gera custo: há um canal por idioma, compartilhado por todos que o escolheram."],
    ["doc", "Documento pós-evento", "Depois do evento, a transcrição vira um documento em PDF com capítulos, revisado e aprovado por você antes de publicar."],
  ];
  const FAQ: [string, string][] = [
    ["Preciso de equipamento especial?", "Não. Qualquer fonte de áudio serve: mesa de som (de qualquer marca), interface USB ou até o microfone do celular, pelo app ou pelo navegador."],
    ["Quantos idiomas são suportados?", "Todos os que os provedores de tradução configurados oferecem. A lista é lida diretamente da API deles e exibida ao público; o painel mostra o que cada provedor cobre."],
    ["Qual é o atraso da tradução?", "Buscamos baixa latência (meta de cerca de 2 segundos em boas condições de rede), mas isso depende do provedor e da internet. Medimos e exibimos a latência real no painel."],
    ["E se o provedor de IA falhar durante o evento?", "O sistema troca automaticamente de provedor apenas no idioma afetado, avisa o público e registra tudo. Os outros idiomas não são interrompidos."],
    ["O público precisa criar conta?", "Não. Ele escaneia o QR do evento ou do perfil da organização, ou busca pelo nome. Só a organização (quem promove o evento) tem conta, criada no site."],
    ["Meus dados ficam seguros?", "Sim. Isolamento total entre organizações, criptografia de segredos, links assinados, auditoria e autenticação em dois fatores para administradores da plataforma."],
    ["Posso testar de graça?", "Sim. Ao criar a conta você ganha um evento de teste, sem cartão de crédito."],
  ];
  const li = (s: string) => <li><Icon name="check" /> <span>{t(s)}</span></li>;

  return (
    <>
      <header className="nav">
        <div className="container">
          <Link href="/"><img src="/logo.webp" alt="SelaVoice — Real-time Translation" /></Link>
          <nav className="nav-links" aria-label="principal">
            <a className="hide-m" href="#como-funciona">{t("Como funciona")}</a>
            <a className="hide-m" href="#recursos">{t("Recursos")}</a>
            <a className="hide-m" href="#organizadores">{t("Para organizadores")}</a>
            <a className="hide-m" href="#precos">{t("Preços")}</a>
            <Link className="hide-m" href="/buscar">{t("Encontrar um evento")}</Link>
            <LangSwitch />
            <InstallApp className="btn btn-ghost btn-sm hide-m" />
            <Link href="/login" className="hide-m">{t("Entrar")}</Link>
            <Link className="btn btn-primary btn-sm" href="/register">{t("Começar grátis")}</Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="container hero-grid">
            <div>
              <span className="eyebrow"><Icon name="radio" small /> {t("Tradução simultânea para qualquer evento")}</span>
              <h1 className="display">{t("Seu evento, entendido por todos,")} <em>{t("em qualquer idioma.")}</em></h1>
              <p className="lead">{t("O SelaVoice traduz a fala do palco em tempo real. Cada pessoa escolhe o idioma, ouve a tradução em voz e acompanha a transcrição, no celular ou no computador.")}</p>
              <div className="row">
                <Link className="btn btn-primary btn-lg" href="/register">{t("Criar conta grátis")} <Icon name="arrow" small /></Link>
                <Link className="btn btn-ghost btn-lg" href="/buscar"><Icon name="search" small /> {t("Encontrar um evento")}</Link>
              </div>
              <div className="checks">
                <span><Icon name="check" /> {t("Sem cartão de crédito")}</span>
                <span><Icon name="check" /> {t("Evento de teste incluso")}</span>
                <span><Icon name="check" /> {t("O público não precisa de conta")}</span>
              </div>
            </div>
            <LiveDemo />
          </div>
        </section>

        <section aria-label={t("Para quem é")} style={{ borderBottom: "1px solid var(--line)" }}>
          <div className="container">
            <p className="fine" style={{ textAlign: "center", margin: "28px 0 0", textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 600 }}>{t("Feito para qualquer tipo de evento")}</p>
            <div className="segments">{SEGMENTS.map(([ic, s]) => <span key={s}><Icon name={ic} /> {t(s)}</span>)}</div>
          </div>
        </section>

        <section className="section" id="recursos">
          <div className="container">
            <div className="sec-head"><h2>{t("Tudo para o público entender, e para você operar com tranquilidade")}</h2><p>{t("Do primeiro evento de teste à agenda completa de uma feira com várias salas em paralelo.")}</p></div>
            <div className="grid-3" style={{ gap: "36px 32px" }}>
              {FEATURES.map(([ic, ti, d]) => (
                <div className="feature" key={ti}><Icon name={ic} /><h3>{t(ti)}</h3><p>{t(d)}</p></div>
              ))}
            </div>
          </div>
        </section>

        <section className="section alt" id="como-funciona">
          <div className="container">
            <div className="sec-head"><h2>{t("Como funciona")}</h2><p>{t("Três passos, sem instalar nada para o público.")}</p></div>
            <div className="grid-3" style={{ gap: 32 }}>
              <div className="step"><span className="n">01</span><h3>{t("Conecte o áudio")}</h3><p>{t("Use qualquer fonte: mesa de som, interface USB ou o microfone do celular. A organização cria o evento no site.")}</p></div>
              <div className="step"><span className="n">02</span><h3>{t("Compartilhe o QR Code")}</h3><p>{t("O público escaneia o QR do evento ou do perfil da organização, ou busca pelo nome. Sem cadastro.")}</p></div>
              <div className="step"><span className="n">03</span><h3>{t("Todos acompanham ao vivo")}</h3><p>{t("Cada pessoa escolhe o idioma, ouve a tradução e lê a transcrição. Depois, o texto vira histórico e documento.")}</p></div>
            </div>
          </div>
        </section>

        <section className="section" id="organizadores">
          <div className="container split">
            <div>
              <h2 style={{ fontSize: "clamp(1.625rem,3vw,2.25rem)", fontWeight: 700, letterSpacing: "-0.03em" }}>{t("Um painel simples para quem organiza")}</h2>
              <p className="muted" style={{ fontSize: "1.0625rem" }}>{t("Crie eventos, agende, controle a transmissão, acompanhe quais idiomas estão ativos e veja os custos, tudo com papéis para administradores e operadores.")}</p>
              <ul className="bullets">
                {li("Agenda e histórico pesquisável por data, palestrante e tema")}
                {li("Várias salas e sessões em paralelo")}
                {li("Revisão e aprovação antes de publicar documentos")}
                {li("Troca automática de provedor só no idioma afetado")}
                {li("Isolamento total entre organizações e auditoria completa")}
              </ul>
            </div>
            <div className="mock" role="img" aria-label={t("Painel de eventos")}>
              <div className="mock-bar"><i /><i /><i /></div>
              <div className="mock-head"><b>{t("Eventos")}</b><span className="btn btn-primary btn-sm" aria-hidden="true">+ {t("Novo evento")}</span></div>
              <table style={{ border: 0, borderRadius: 0 }} aria-hidden="true">
                <thead><tr><th>{t("Título")}</th><th>{t("Palestrante")}</th><th>{t("Status")}</th></tr></thead>
                <tbody>
                  <tr><td>{t("Conferência Global 2026")}</td><td>M. Ferreira</td><td><span className="badge badge-live">{t("AO VIVO")}</span></td></tr>
                  <tr><td>{t("Workshop de Liderança")}</td><td>A. Costa</td><td><span className="badge">{t("Agendado")}</span></td></tr>
                  <tr><td>{t("Feira de Inovação")}</td><td>R. Santos</td><td><span className="badge">{t("Agendado")}</span></td></tr>
                  <tr><td>{t("Treinamento Interno")}</td><td>L. Almeida</td><td><span className="badge">{t("Encerrado")}</span></td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="section alt" id="apps">
          <div className="container">
            <div className="sec-head"><h2>{t("Aplicativos")}</h2><p>{t("Ouvintes usam o app ou o navegador. A transmissão pode ser feita pelo navegador, pelo celular ou pelo app para Windows.")}</p></div>
            <div className="grid-2">
              <div className="card"><div className="row spread" style={{ marginBottom: 10 }}><span className="row" style={{ gap: 8 }}><Icon name="phone" /><b style={{ color: "var(--ink)" }}>{t("App do ouvinte")}</b></span><span className="badge">{t("Em breve")}</span></div><p className="muted">{t("Android, iOS e Windows. Abre direto, sem login: escaneie o QR ou busque o evento ou a organização pelo nome.")}</p></div>
              <div className="card"><div className="row spread" style={{ marginBottom: 10 }}><span className="row" style={{ gap: 8 }}><Icon name="monitor" /><b style={{ color: "var(--ink)" }}>{t("App do palestrante (Windows)")}</b></span><span className="badge">{t("Em breve")}</span></div><p className="muted">{t("Ao abrir, escolha “ouvinte” ou “palestrante”. O palestrante faz login para conectar e transmitir o áudio de qualquer fonte.")}</p></div>
            </div>
            <p className="fine" style={{ marginTop: 16 }}>{t("Hoje já funciona pelo navegador (site), inclusive a transmissão pelo celular.")}</p>
          </div>
        </section>

        <section className="section" id="precos">
          <div className="container">
            <div className="sec-head center"><h2>{t("Preços simples e transparentes")}</h2><p>{t("Compre um evento avulso ou assine por mês. Cancele quando quiser. Valores em dólar (USD).")}</p></div>
            <Pricing />
            <p className="fine" style={{ textAlign: "center", marginTop: 24 }}>{t("Minuto-idioma = 1 minuto de tradução em 1 idioma. Dois idiomas durante 60 min = 120 minutos-idioma.")}</p>
          </div>
        </section>

        <section className="section alt" id="faq">
          <div className="container" style={{ maxWidth: 800 }}>
            <div className="sec-head"><h2>{t("Perguntas frequentes")}</h2></div>
            {FAQ.map(([q, a]) => (<details key={q}><summary>{t(q)}</summary><p>{t(a)}</p></details>))}
          </div>
        </section>

        <section className="band">
          <div className="container row spread" style={{ gap: 32 }}>
            <div style={{ maxWidth: 620 }}><h2>{t("Seu próximo evento pode ser entendido por todos.")}</h2><p style={{ margin: 0 }}>{t("Crie a conta da sua organização e faça o primeiro evento de teste hoje.")}</p></div>
            <Link className="btn btn-light btn-lg" href="/register">{t("Começar agora, é grátis")} <Icon name="arrow" small /></Link>
          </div>
        </section>
      </main>

      <footer className="site">
        <div className="container">
          <div className="grid-4" style={{ marginBottom: 32 }}>
            <div><img src="/logo.webp" alt="SelaVoice" style={{ height: 32 }} /><p style={{ marginTop: 12, maxWidth: 260 }}>{t("Tradução simultânea em voz e texto, para qualquer evento.")}</p></div>
            <div><h4>{t("Produto")}</h4><ul><li><a href="#recursos">{t("Recursos")}</a></li><li><a href="#precos">{t("Preços")}</a></li><li><a href="#apps">{t("Aplicativos")}</a></li></ul></div>
            <div><h4>{t("Para o público")}</h4><ul><li><Link href="/buscar">{t("Encontrar um evento")}</Link></li></ul></div>
            <div><h4>{t("Conta")}</h4><ul><li><Link href="/login">{t("Entrar")}</Link></li><li><Link href="/register">{t("Criar conta")}</Link></li></ul></div>
          </div>
          <div className="row spread"><span>© {new Date().getFullYear()} SelaVoice. {t("Todos os direitos reservados.")}</span><span><Link href="/legal/privacidade">{t("Privacidade")}</Link> · <Link href="/legal/termos">{t("Termos")}</Link></span></div>
        </div>
      </footer>
    </>
  );
}

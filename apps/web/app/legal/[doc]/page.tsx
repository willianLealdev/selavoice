"use client";
/** Páginas legais — PLACEHOLDERS para revisão jurídica (a spec exige revisão antes de produção). */
import Link from "next/link";
import { use } from "react";
import BackButton from "@/components/BackButton";
import { LangSwitch, useT } from "@/lib/i18n";

const DOCS: Record<string, { t: string; body: string[] }> = {
  privacidade: {
    t: "Política de Privacidade",
    body: [
      "Esta política explica quais dados o SelaVoice trata ao oferecer tradução simultânea de eventos em voz e texto.",
      "DADOS DE CONTA (organizadores e equipe): nome, e-mail e senha (guardada apenas em forma criptografada irreversível). Usamos para entrar na conta, confirmar o e-mail e enviar avisos do serviço.",
      "OUVINTES: não precisam criar conta. Para ouvir um evento não coletamos nome nem e-mail.",
      "ÁUDIO E TEXTO DOS EVENTOS: o áudio captado pelo organizador é enviado em tempo real a provedores de inteligência artificial (reconhecimento de fala, tradução e síntese de voz) apenas para gerar a tradução. Guardamos a transcrição e as traduções do evento para o histórico da organização. Gravações de áudio só existem se o organizador as ativar, com consentimento dos participantes.",
      "MICROFONE E CÂMERA (no aplicativo): o microfone é usado só pelo palestrante para transmitir a fala; a câmera só para ler o QR Code do evento. Nada é gravado sem a ação do usuário.",
      "COBRANÇA: pagamentos são processados pelo Stripe. Não guardamos número de cartão.",
      "COMPARTILHAMENTO: não vendemos dados e não usamos publicidade nem rastreadores de terceiros. Os dados só vão para os provedores necessários ao funcionamento do serviço (inteligência artificial, e-mail, pagamento e hospedagem).",
      "SEGURANÇA: conexões protegidas (HTTPS), senhas com criptografia forte, chaves de serviços guardadas cifradas no servidor e separação rigorosa dos dados entre organizações.",
      "SEUS DIREITOS: você pode excluir sua conta a qualquer momento no próprio aplicativo (Perfil > Excluir minha conta). Eventos, apostilas e transcrições podem ser excluídos pelo organizador. Veja também a página Excluir conta e dados.",
      "Ao excluir a conta, seus dados pessoais são apagados; registros de cobrança e segurança podem ser mantidos pelo prazo exigido em lei, sem identificar você.",
    ],
  },
  "excluir-conta": {
    t: "Excluir conta e dados",
    body: [
      "Para excluir sua conta e seus dados pessoais: entre no SelaVoice, abra Perfil e clique em Excluir minha conta. Confirme com sua senha.",
      "O que acontece: seu nome, e-mail e senha são apagados e seu acesso é removido. Se você era a única pessoa da organização, a organização também é encerrada e sai do ar.",
      "Se você é o único administrador de uma organização com outras pessoas, passe a administração para alguém antes de excluir.",
      "Para apagar apenas um evento, uma transcrição ou uma apostila, use a opção Excluir dentro do evento.",
      "Ouvintes não têm conta nem dados pessoais para excluir.",
    ],
  },
  termos: {
    t: "Termos de Uso",
    body: [
      "RASCUNHO — requer revisão de um advogado antes da publicação.",
      "O serviço fornece tradução automática; ela pode conter erros e não substitui intérprete certificado em contextos críticos.",
      "O organizador é responsável por obter autorização para gravar e publicar conteúdo de palestrantes e participantes.",
      "Cobranças são processadas pelo Stripe; direitos são liberados após a confirmação do pagamento.",
    ],
  },
};

export default function Legal({ params }: { params: Promise<{ doc: string }> }) {
  const t = useT();
  const { doc } = use(params);
  const d = DOCS[doc];
  return (
    <>
      <header className="nav"><div className="container"><Link href="/"><img src="/logo.webp" alt="SelaVoice" /></Link><div className="nav-links"><LangSwitch /></div></div></header>
      <main className="container" style={{ maxWidth: 720, padding: "48px 24px 80px" }}>
        <BackButton fallback="/" />
        <h1 style={{ fontSize: "2rem", letterSpacing: "-0.03em", marginTop: 20 }}>{d ? t(d.t) : t("Página não encontrada")}</h1>
        {d?.body.map((p) => <p key={p} className="muted" style={{ fontSize: "1.0625rem" }}>{t(p)}</p>)}
      </main>
    </>
  );
}

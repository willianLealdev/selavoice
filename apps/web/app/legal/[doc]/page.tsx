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
      "RASCUNHO — requer revisão de um advogado antes da publicação.",
      "Coletamos o mínimo necessário: dados de conta, registros de uso do serviço e, somente com consentimento explícito do organizador, gravações e transcrições dos eventos.",
      "Ouvintes públicos não precisam criar conta. Não vendemos dados. Organizadores podem exportar e solicitar exclusão dos dados do seu evento.",
      "Segredos e chaves de IA ficam apenas em servidores; registros de log têm dados pessoais removidos.",
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

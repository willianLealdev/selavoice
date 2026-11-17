"use client";
/** Moldura das telas de acesso: painel de marca à esquerda (some no celular) + formulário à direita. */
import Link from "next/link";
import Icon from "./Icon";
import BackButton from "./BackButton";
import { LangSwitch, useT } from "@/lib/i18n";

export default function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const t = useT();
  return (
    <div className="auth">
      <aside className="auth-side">
        <Link href="/" className="brandbox"><img src="/logo.webp" alt="SelaVoice" /></Link>
        <div>
          <h2>{t("Todos entendem. Em qualquer idioma, ao vivo.")}</h2>
          <p>{t("Tradução simultânea em voz e texto para conferências, feiras, empresas, escolas e igrejas.")}</p>
          <ul>
            <li><Icon name="headphones" /> {t("O público ouve a tradução no próprio celular")}</li>
            <li><Icon name="qr" /> {t("Entra por QR Code ou busca, sem criar conta")}</li>
            <li><Icon name="shield" /> {t("Dados de cada organização totalmente isolados")}</li>
          </ul>
        </div>
        <span className="fine" style={{ color: "#7f8da6" }}>© {new Date().getFullYear()} SelaVoice</span>
      </aside>
      <main className="auth-main">
        <div className="auth-top" style={{ justifyContent: "space-between" }}><BackButton fallback="/" always /><LangSwitch /></div>
        <div className="auth-card">
          <Link href="/"><img className="brand-m" src="/logo.webp" alt="SelaVoice" /></Link>
          <h1>{title}</h1>
          {subtitle && <p className="muted">{subtitle}</p>}
          {children}
        </div>
      </main>
    </div>
  );
}

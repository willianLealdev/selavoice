"use client";
/** Tela mostrada pelo service worker quando o app é aberto sem internet. */
import Icon from "@/components/Icon";
import { useT } from "@/lib/i18n";

export default function Offline() {
  const t = useT();
  return (
    <div className="auth-wrap">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <img src="/icons/icon-192.png" alt="SelaVoice" width={72} height={72} style={{ borderRadius: 18, margin: "0 auto 12px", display: "block" }} />
        <h2>{t("Sem conexão")}</h2>
        <p className="muted">{t("O SelaVoice precisa de internet para traduzir ao vivo. Verifique sua conexão e tente de novo.")}</p>
        <button className="btn btn-primary" onClick={() => location.reload()}><Icon name="zap" small /> {t("Tentar de novo")}</button>
      </div>
    </div>
  );
}

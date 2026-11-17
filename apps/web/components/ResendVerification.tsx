"use client";
/** Botão "Reenviar e-mail de confirmação" (1 envio por minuto; a API responde sempre igual, exista a conta ou não). */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function ResendVerification({ email }: { email: string }) {
  const t = useT();
  const [wait, setWait] = useState(0);
  const [msg, setMsg] = useState("");
  useEffect(() => { if (wait <= 0) return; const h = setTimeout(() => setWait(wait - 1), 1000); return () => clearTimeout(h); }, [wait]);
  async function resend() {
    setMsg("");
    try { await api("/auth/resend-verification", { method: "POST", json: { email } }); setMsg("Se a conta existir e ainda não estiver confirmada, enviamos um novo e-mail."); setWait(60); }
    catch (e: any) { setMsg(e.message); }
  }
  return (
    <div style={{ marginTop: 14 }}>
      <button type="button" className="btn btn-ghost btn-sm" disabled={wait > 0 || !email} onClick={resend}>
        {wait > 0 ? `${t("Reenviar e-mail de confirmação")} (${wait}s)` : t("Reenviar e-mail de confirmação")}
      </button>
      {msg && <p className="fine" style={{ marginTop: 8 }}>{t(msg)}</p>}
    </div>
  );
}

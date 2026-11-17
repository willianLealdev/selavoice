"use client";
/** Pede o e-mail de redefinição. A resposta é sempre a mesma (não revela se o e-mail tem conta). */
import Link from "next/link";
import { useState } from "react";
import AuthShell from "@/components/AuthShell";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Forgot() {
  const t = useT();
  const [email, setEmail] = useState(""); const [done, setDone] = useState(false); const [err, setErr] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try { await api("/auth/forgot", { method: "POST", json: { email } }); setDone(true); } catch (x: any) { setErr(x.message); }
  }
  return (
    <AuthShell title={t("Esqueci minha senha")} subtitle={t("Informe o e-mail da conta e enviaremos um link para criar uma nova senha.")}>
      {done ? <div className="ok">{t("Se o e-mail existir, enviamos as instruções. Verifique também o spam.")}</div> : (
        <form onSubmit={submit}>
          <label htmlFor="e">{t("E-mail da conta")}</label>
          <input id="e" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          {err && <div className="err">{t(err)}</div>}
          <button className="btn btn-primary btn-lg" style={{ width: "100%", marginTop: 20 }}>{t("Enviar link")}</button>
        </form>
      )}
      <p className="fine" style={{ marginTop: 24 }}><Link href="/login">{t("Voltar ao login")}</Link></p>
    </AuthShell>
  );
}

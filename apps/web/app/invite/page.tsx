"use client";
/** Aceitar convite (link recebido por e-mail). Pessoa nova define nome e senha; quem já tem conta só confirma. */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import AuthShell from "@/components/AuthShell";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

function Inner() {
  const t = useT();
  const token = useSearchParams().get("token") ?? "";
  const [f, setF] = useState({ name: "", password: "" }); const [done, setDone] = useState(false); const [err, setErr] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try { await api("/invitations/accept", { method: "POST", json: { token, ...f } }); setDone(true); } catch (x: any) { setErr(x.message); }
  }
  return (
    <AuthShell title={t("Aceitar convite")} subtitle={t("Você foi convidado para uma organização no SelaVoice.")}>
      {done ? <><div className="ok">{t("Convite aceito!")}</div><Link className="btn btn-primary" href="/login">{t("Entrar")}</Link></> : (
        <form onSubmit={submit}>
          <label htmlFor="n">{t("Seu nome")}</label><input id="n" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <label htmlFor="p">{t("Crie uma senha")}</label>
          <input id="p" type="password" autoComplete="new-password" required minLength={12} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <p className="fine" style={{ marginTop: 6 }}>{t("Se você já tem conta, use a mesma senha dela. Mínimo 12 caracteres para contas novas.")}</p>
          {err && <div className="err">{t(err)}</div>}
          <button className="btn btn-primary btn-lg" style={{ width: "100%", marginTop: 16 }} disabled={!token}>{t("Entrar na organização")}</button>
        </form>
      )}
    </AuthShell>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }

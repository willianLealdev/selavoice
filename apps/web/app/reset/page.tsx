"use client";
/** Define a nova senha com o token enviado por e-mail (uso único, vale 1 h). */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import AuthShell from "@/components/AuthShell";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

function Inner() {
  const t = useT();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState(""); const [done, setDone] = useState(false); const [err, setErr] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try { await api("/auth/reset", { method: "POST", json: { token, password } }); setDone(true); } catch (x: any) { setErr(x.message); }
  }
  return (
    <AuthShell title={t("Nova senha")}>
      {done ? <><div className="ok">{t("Senha alterada. Faça login.")}</div><Link className="btn btn-primary" href="/login">{t("Entrar")}</Link></> : (
        <form onSubmit={submit}>
          <label htmlFor="p">{t("Nova senha")}</label>
          <input id="p" type="password" autoComplete="new-password" required minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="fine" style={{ marginTop: 6 }}>{t("Mínimo 12 caracteres, com maiúscula, minúscula e número.")}</p>
          {err && <div className="err">{t(err)}</div>}
          <button className="btn btn-primary btn-lg" style={{ width: "100%", marginTop: 16 }} disabled={!token}>{t("Salvar senha")}</button>
        </form>
      )}
    </AuthShell>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }

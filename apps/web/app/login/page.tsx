"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthShell from "@/components/AuthShell";
import ResendVerification from "@/components/ResendVerification";
import { api, setToken } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Login() {
  const t = useT();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [unverified, setUnverified] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(""); setUnverified(false);
    try {
      const r = await api("/auth/login", { method: "POST", json: { email, password } });
      setToken(r.access_token);
      router.push("/dashboard");
    } catch (e: any) { setErr(e.message); setUnverified(e.status === 403); } finally { setBusy(false); }
  }
  return (
    <AuthShell title={t("Entrar")} subtitle={t("Acesso da organização que promove o evento. O público não precisa de conta.")}>
      <form onSubmit={submit}>
        <label htmlFor="e">{t("E-mail")}</label>
        <input id="e" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <div className="row spread" style={{ marginTop: 16 }}><label htmlFor="p" style={{ margin: 0 }}>{t("Senha")}</label><Link href="/forgot" className="fine">{t("Esqueci minha senha")}</Link></div>
        <input id="p" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} style={{ marginTop: 6 }} />
        {err && <div className="err" role="alert">{t(err)}</div>}
        {unverified && <ResendVerification email={email} />}
        <button className="btn btn-primary btn-lg" style={{ width: "100%", marginTop: 22 }} disabled={busy}>{busy ? t("Entrando…") : t("Entrar")}</button>
      </form>
      <p className="fine" style={{ marginTop: 24 }}>{t("Ainda não tem conta?")} <Link href="/register">{t("Criar conta grátis")}</Link></p>
      <p className="fine">{t("Quer só assistir a um evento?")} <Link href="/buscar">{t("Encontrar um evento")}</Link></p>
    </AuthShell>
  );
}

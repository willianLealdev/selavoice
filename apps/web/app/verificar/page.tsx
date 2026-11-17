"use client";
/** Destino do link do e-mail de confirmação: ativa a conta (o token vale uma vez e expira). */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import AuthShell from "@/components/AuthShell";
import ResendVerification from "@/components/ResendVerification";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

function Inner() {
  const t = useT();
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"loading" | "ok" | "err">("loading");
  const [err, setErr] = useState("");
  const [email, setEmail] = useState("");
  const done = useRef(false);   // StrictMode roda o efeito 2x em dev: o token é de uso único, então só tentamos uma vez
  useEffect(() => {
    if (done.current) return; done.current = true;
    if (!token) { setState("err"); setErr("Link inválido ou expirado. Peça um novo e-mail de confirmação."); return; }
    api("/auth/verify-email", { method: "POST", json: { token } }).then(() => setState("ok")).catch((e) => { setErr(e.message); setState("err"); });
  }, [token]);
  return (
    <AuthShell title={state === "ok" ? t("Conta ativada!") : t("Confirmando seu e-mail…")} subtitle={state === "ok" ? t("Seu e-mail foi confirmado. Agora você já pode entrar.") : undefined}>
      {state === "loading" && <p className="muted">{t("Carregando…")}</p>}
      {state === "ok" && <Link className="btn btn-primary btn-lg" style={{ width: "100%" }} href="/login">{t("Entrar")}</Link>}
      {state === "err" && <>
        <div className="err" role="alert">{t(err)}</div>
        <label htmlFor="e">{t("E-mail da conta")}</label>
        <input id="e" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <ResendVerification email={email} />
        <p className="fine" style={{ marginTop: 20 }}><Link href="/login">{t("Voltar ao login")}</Link></p>
      </>}
    </AuthShell>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }

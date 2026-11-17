"use client";
/** SOMENTE DEV (STRIPE_MODE=fake): simula a tela de pagamento. Em produção a API responde 404 a /billing/fake/complete. */
import BackButton from "@/components/BackButton";
import { useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useT } from "@/lib/i18n";

function Inner() {
  const t = useT();
  const sp = useSearchParams(); const router = useRouter(); const { loading } = useSession();
  const [msg, setMsg] = useState("");
  const session = sp.get("session") ?? "";
  async function pay() {
    try { const r = await api(`/billing/fake/complete?session_id=${encodeURIComponent(session)}`, { method: "POST" }); setMsg(`${t("Resultado do webhook:")} ${r.outcome}`); setTimeout(() => router.push("/dashboard/billing"), 1200); }
    catch (e: any) { setMsg(e.message); }
  }
  return (
    <div className="auth-wrap"><div className="auth-card"><div className="back-bar"><BackButton fallback="/dashboard/billing" /></div>
      <h2>{t("Checkout simulado")}</h2>
      <p className="fine">{t("Modo de desenvolvimento: nenhuma cobrança real. O botão envia um webhook assinado ao backend, igual ao Stripe.")}</p>
      <button className="btn btn-primary" disabled={loading} onClick={pay}>{t("Simular pagamento aprovado")}</button>
      {msg && <div className="ok">{msg}</div>}
    </div></div>
  );
}
export default function Page() { return <Suspense><Inner /></Suspense>; }

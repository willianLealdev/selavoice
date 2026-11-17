"use client";
/** Plano e uso. O botão "Assinar" abre o checkout; o acesso só é liberado quando o webhook confirma. */
import { useEffect, useState } from "react";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { countsHours, planLines } from "@/lib/plans";

export default function Billing() {
  const t = useT();
  const [plans, setPlans] = useState<any[]>([]);
  const [packs, setPacks] = useState<any[]>([]);
  const [usage, setUsage] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const load = () => { api("/plans").then(setPlans); api("/topups").then(setPacks).catch(() => {}); api("/usage").then(setUsage).catch(() => {}); };
  useEffect(load, []);

  async function buy(pv: string) {
    try {
      const r = await api("/checkout", { method: "POST", json: { plan_version_id: pv } });
      location.href = r.checkout_url;
    } catch (e: any) { setMsg(e.message); }
  }
  async function buyPack(id: string) {
    try { const r = await api("/topups/checkout", { method: "POST", json: { pack_id: id } }); location.href = r.checkout_url; } catch (e: any) { setMsg(e.message); }
  }
  const low = usage && usage.event_minutes_remaining !== null && usage.event_minutes_remaining < 60;
  return (
    <>
      <div className="page-h"><h1>{t("Plano e uso")}</h1></div>
      {new URLSearchParams(typeof location !== "undefined" ? location.search : "").get("status") === "processing" &&
        <div className="ok">{t("Pagamento em processamento. Seu acesso é liberado assim que o Stripe confirmar (atualize em instantes).")}</div>}
      {msg && <div className="err">{t(msg)}</div>}
      {usage && (
        <div className="kpi">
          <div className="card"><b>{usage.events_remaining >= 5e8 ? "∞" : usage.events_remaining}</b>{t("eventos disponíveis")}</div>
          <div className="card"><b>{usage.event_minutes_remaining === null ? "∞" : `${Math.floor(usage.event_minutes_remaining / 60)}h ${usage.event_minutes_remaining % 60}min`}</b>{t("de transmissão restantes")}</div>
          <div className="card"><b>{usage.language_minutes_remaining >= 5e8 ? "∞" : usage.language_minutes_remaining}</b>{t("minutos-idioma restantes")}</div>
          <div className="card"><b>{Math.round(usage.language_minutes_used)}</b>{t("minutos-idioma usados")}</div>
        </div>
      )}
      {packs.length > 0 && (
        <>
          <h2>{t("Recarregar")}</h2>
          <p className="fine">{low ? t("Seu saldo de horas está acabando. Recarregue sem trocar de plano.") : t("Acabou o saldo antes do fim do período? Compre horas extras, sem trocar de plano.")}</p>
          <div className="grid-3">
            {packs.map((p) => (
              <div className="card price" key={p.id}>
                <h3>{p.name}</h3>
                <div className="amount">{money(p.amount_cents, p.currency)}</div>
                <ul>{p.hours > 0 && <li>+{p.hours} {t("horas de transmissão")}</li>}{p.events > 0 && <li>+{p.events} {t("eventos")}</li>}</ul>
                <button className="btn btn-primary" onClick={() => buyPack(p.id)}>{t("Recarregar")}</button>
              </div>
            ))}
          </div>
        </>
      )}
      <h2>{t("Contratar")}</h2>
      <div className="grid-3">
        {plans.map((p) => (
          <div className="card price" key={p.plan_version_id}>
            <h3>{t(p.name)}</h3>
            <div className="amount">{money(p.amount_cents, p.currency)}<span className="fine">{p.billing_type === "MONTHLY" ? t(" /mês") : ""}</span></div>
            <ul>{planLines(p.entitlements, t as any, (c) => money(c, p.currency)).map((l) => <li key={l}>{l}</li>)}</ul>
            {countsHours(p.entitlements) && <p className="fine">{t("A contagem das horas começa quando a transmissão é iniciada.")}</p>}
            <button className="btn btn-primary" onClick={() => buy(p.plan_version_id)}>{t("Contratar")}</button>
          </div>
        ))}
      </div>
    </>
  );
}

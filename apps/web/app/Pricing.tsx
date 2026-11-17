"use client";
/** Preços: busca os planos publicados na API; se estiver offline, mostra os valores padrão do seed. */
import Link from "next/link";
import { useEffect, useState } from "react";
import Icon from "@/components/Icon";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { countsHours, planLines } from "@/lib/plans";
import { trialHeadline, useTrial } from "@/lib/trial";

type P = { name: string; amount_cents: number; currency: string; billing_type: string; entitlements: Record<string, any> };
const FALLBACK: P[] = [
  { name: "Evento Avulso", amount_cents: 14900, currency: "usd", billing_type: "ONE_OFF", entitlements: { included_events: 1, max_languages: 3, included_language_minutes: 600, listener_concurrency: 300, pdf_booklets: true } },
  { name: "Plano Mensal", amount_cents: 29900, currency: "usd", billing_type: "MONTHLY", entitlements: { included_events: 8, max_languages: 5, included_language_minutes: 2400, listener_concurrency: 500, pdf_booklets: true, admin_seats: 5 } },
  { name: "Eventos Pro", amount_cents: 89900, currency: "usd", billing_type: "MONTHLY", entitlements: { included_events: 30, max_languages: 10, included_language_minutes: 12000, listener_concurrency: 3000, pdf_booklets: true, admin_seats: 15 } },
];

export default function Pricing() {
  const t = useT();
  const [plans, setPlans] = useState<P[]>(FALLBACK);
  const trial = useTrial();
  useEffect(() => { api<P[]>("/plans").then((p) => p.length && setPlans(p)).catch(() => {}); }, []);
  return (
    <>
    {trial.ready && trial.enabled && (
      <div className="trial-banner">
        <div>
          <span className="eyebrow"><Icon name="check" small /> {t("Teste grátis")}</span>
          <h3>{trialHeadline(trial.limits, t as any)}</h3>
          <ul>{planLines(trial.limits, t as any).map((l) => <li key={l}><Icon name="check" small /> {l}</li>)}</ul>
          {trial.days && <p className="fine">{t("Válido por {n} dias.", { n: trial.days })}</p>}
        </div>
        <Link className="btn btn-primary btn-lg" href="/register">{t("Começar o teste grátis")} <Icon name="arrow" small /></Link>
      </div>
    )}
    <div className="grid-3" style={{ alignItems: "stretch" }}>
      {plans.map((p, i) => {
        const e = p.entitlements;
        return (
          <div key={p.name} className={`card price ${i === 1 ? "featured" : ""}`}>
            {i === 1 && <span className="tag">{t("MAIS ESCOLHIDO")}</span>}
            <h3>{t(p.name)}</h3>
            <div className="amount">{money(p.amount_cents, p.currency)} <small>{p.billing_type === "MONTHLY" ? t("/mês") : t("/evento")}</small></div>
            <ul>
              {planLines(e, t as any, (c) => money(c, p.currency)).map((l) => <li key={l}><Icon name="check" /> {l}</li>)}
              <li><Icon name="check" /> {t("Transcrição acumulada + histórico")}</li>
            </ul>
            {countsHours(e) && <p className="fine">{t("A contagem das horas começa quando a transmissão é iniciada.")}</p>}
            <Link className={`btn ${i === 1 ? "btn-primary" : "btn-ghost"}`} href="/register">{t("Começar grátis")}</Link>
          </div>
        );
      })}
    </div>
    </>
  );
}

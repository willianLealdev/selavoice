"use client";
/**
 * Super Admin — CUSTOS E RECEITA. Tarifas por provedor (USD por minuto-idioma) são DEFINIDAS AQUI pelo Super Admin;
 * valem para os minutos medidos DEPOIS de salvar (o histórico não é reescrito). Receita = vendas confirmadas por webhook.
 * Não é conciliação contábil: compare com a fatura do provedor e o extrato do Stripe.
 */
import { useEffect, useState } from "react";
import { Kpi, PageHead, Panel, Period, num, usd } from "@/components/AdminUI";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Financeiro() {
  const t = useT();
  const [days, setDays] = useState(30);
  const [f, setF] = useState<any>(null); const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const load = () => api(`/admin/finance?days=${days}`).then((d) => { setF(d); setDraft(Object.fromEntries(d.rates.map((r: any) => [r.provider, r.usd_per_min ?? ""]))); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [days]); // eslint-disable-line
  async function save(p: string) {
    setErr(""); setOk("");
    const v = String(draft[p] ?? "").trim().replace(",", ".");
    try { await api(`/admin/providers/${p}/rate`, { method: "PUT", json: { usd_per_min: v === "" ? null : Number(v) } }); setOk(t("Tarifa salva. Vale para os próximos minutos medidos.")); load(); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <>
      <PageHead title={t("Custos e receita")} sub={t("Quanto a plataforma ganha, quanto gasta com IA e a margem.")} right={<Period value={days} onChange={setDays} />} />
      {err && <div className="err">{t(err)}</div>}{ok && <div className="ok">{ok}</div>}
      {f && <>
        <div className="kpi-grid">
          <Kpi icon="card" tone="ok" label={`${t("Receita")} (${days}d)`} value={usd(f.revenue_usd)} sub={t("vendas confirmadas")} />
          <Kpi icon="zap" tone="warn" label={`${t("Custo de IA")} (${days}d)`} value={usd(f.ai_cost_usd, 4)} />
          <Kpi icon="layers" tone={f.margin_usd >= 0 ? "ok" : "live"} label={t("Margem")} value={usd(f.margin_usd)} sub={f.margin_pct === null ? "—" : `${f.margin_pct}%`} />
          <Kpi icon="calendar" tone="brand" label={t("Receita recorrente (MRR)")} value={usd(f.mrr_usd)} sub={t("assinaturas ativas")} />
        </div>

        <Panel title={t("Tarifas dos provedores de IA")} hint={t("Informe o preço oficial de cada provedor, em dólares por minuto-idioma. Sem tarifa, o custo é só uma estimativa.")}>
          <table><thead><tr><th>{t("Provedor")}</th><th>{t("Tarifa (US$ / min)")}</th><th>{t("Situação")}</th><th></th></tr></thead><tbody>
            {f.rates.map((r: any) => (
              <tr key={r.provider}>
                <td><b>{r.provider}</b>{r.is_mock && <div className="fine">{t("simulador (sem custo)")}</div>}</td>
                <td style={{ maxWidth: 160 }}><input inputMode="decimal" placeholder="0.0000" value={draft[r.provider] ?? ""} onChange={(e) => setDraft({ ...draft, [r.provider]: e.target.value })} /></td>
                <td>{r.configured ? <span className="badge badge-ok">{t("configurada")}</span> : <span className="badge">{r.is_mock ? t("não se aplica") : t("estimativa")}</span>}</td>
                <td><button className="btn btn-ghost btn-sm" onClick={() => save(r.provider)}>{t("Salvar")}</button></td>
              </tr>
            ))}
          </tbody></table>
        </Panel>

        <div className="grid-main">
          <Panel title={t("Custo por provedor")}>
            <table><thead><tr><th>{t("Provedor")}</th><th>{t("Minutos")}</th><th>{t("Custo")}</th><th>{t("Custo / min")}</th></tr></thead><tbody>
              {f.providers.map((p: any) => <tr key={p.provider}><td><b>{p.provider}</b></td><td>{num(p.minutes)}</td><td>{usd(p.cost_usd, 4)}</td><td>{p.cost_per_min === null ? "—" : usd(p.cost_per_min, 4)}</td></tr>)}
              {!f.providers.length && <tr><td colSpan={4} className="fine">{t("Sem uso medido no período.")}</td></tr>}
            </tbody></table>
          </Panel>
          <Panel title={t("Vendas por plano")}>
            <table><thead><tr><th>{t("Plano")}</th><th>{t("Vendas")}</th><th>{t("Receita")}</th><th>{t("Assinantes")}</th></tr></thead><tbody>
              {f.plans.map((p: any) => <tr key={p.plan}><td><b>{t(p.plan)}</b></td><td>{p.sales}</td><td>{usd(p.revenue_usd)}</td><td>{p.active_subs}</td></tr>)}
              {!f.plans.length && <tr><td colSpan={4} className="fine">{t("Nenhuma venda no período.")}</td></tr>}
            </tbody></table>
          </Panel>
        </div>
        <p className="fine">{t("Receita e custo são calculados pelo sistema e não substituem a fatura do provedor nem o extrato do Stripe.")}</p>
      </>}
    </>
  );
}

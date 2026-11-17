"use client";
/**
 * Super Admin — VISÃO GERAL: operação ao vivo, receita × custo de IA e uso.
 * Números: "online agora" é aproximado (login/renovação nos últimos 15 min); custo de IA = minutos × tarifa
 * configurada (sem tarifa, é ESTIMATIVA); receita = vendas confirmadas por webhook. Detalhes em routers/admin_stats.py.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { BarList, LineChart } from "@/components/Charts";
import { Kpi, PageHead, Panel, Period, num, usd } from "@/components/AdminUI";
import Icon from "@/components/Icon";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Overview() {
  const t = useT();
  const [days, setDays] = useState(30);
  const [o, setO] = useState<any>(null); const [err, setErr] = useState("");
  useEffect(() => { setO(null); api(`/admin/overview?days=${days}`).then(setO).catch((e) => setErr(e.message)); }, [days]);
  useEffect(() => { const h = setInterval(() => api(`/admin/overview?days=${days}`).then(setO).catch(() => {}), 30000); return () => clearInterval(h); }, [days]); // atualiza sozinho a cada 30 s
  const k = o?.kpis;
  return (
    <>
      <PageHead title={t("Visão geral")} sub={t("Operação ao vivo, receita e custos da plataforma.")} right={<Period value={days} onChange={setDays} />} />
      {err && <div className="err">{t(err)}</div>}
      {o?.cost_is_estimate && (
        <div className="notice"><Icon name="zap" small /> <span>{t("O custo de IA está ESTIMADO: nenhuma tarifa real foi configurada.")} <Link href="/admin/financeiro">{t("Configurar tarifas")}</Link></span></div>
      )}
      {!o && !err && <p className="muted">{t("Carregando…")}</p>}
      {k && <>
        <div className="kpi-grid">
          <Kpi icon="radio" tone="live" label={t("Eventos ao vivo agora")} value={num(k.live_events)} sub={`${num(k.events_total)} ${t("eventos no total")}`} />
          <Kpi icon="headphones" tone="brand" label={t("Ouvintes conectados")} value={num(k.listeners_now)} sub={t("em tempo real")} />
          <Kpi icon="users" tone="brand" label={t("Usuários online")} value={num(k.online_users)} sub={`${num(k.users)} ${t("usuários cadastrados")}`} />
          <Kpi icon="building" label={t("Organizações")} value={num(k.tenants)} sub={k.tenants_suspended ? `${k.tenants_suspended} ${t("suspensas")}` : t("todas ativas")} />
        </div>
        <div className="kpi-grid">
          <Kpi icon="card" tone="ok" label={`${t("Receita")} (${days}d)`} value={usd(k.revenue_usd)} sub={`MRR ${usd(k.mrr_usd)}`} />
          <Kpi icon="zap" tone="warn" label={`${t("Custo de IA")} (${days}d)`} value={usd(k.ai_cost_usd, 4)} sub={o.cost_is_estimate ? t("estimado") : t("tarifa configurada")} />
          <Kpi icon="layers" tone={k.margin_usd >= 0 ? "ok" : "live"} label={t("Margem")} value={usd(k.margin_usd)} sub={t("receita − custo de IA")} />
          <Kpi icon="globe" label={t("Minutos-idioma")} value={num(k.language_minutes)} sub={`${k.failovers} failovers`} />
        </div>

        <div className="grid-main">
          <Panel title={t("Receita × custo de IA por dia")} hint={t("Cada linha usa a sua própria escala.")}>
            <LineChart labels={o.series.labels} series={[
              { name: t("Receita"), color: "var(--ok)", values: o.series.revenue_usd, fmt: (n) => usd(n), area: true },
              { name: t("Custo de IA"), color: "var(--warn)", values: o.series.cost_usd, fmt: (n) => usd(n, 4) },
            ]} />
          </Panel>
          <Panel title={t("Uso de tradução por dia")} hint={t("Minutos-idioma medidos (1 idioma ouvido por 1 minuto = 1).")}>
            <LineChart labels={o.series.labels} series={[{ name: t("Minutos-idioma"), color: "var(--brand)", values: o.series.minutes, fmt: (n) => `${n.toFixed(1)} min`, area: true }]} />
          </Panel>
        </div>

        <div className="grid-3-eq">
          <Panel title={t("Custo por provedor")}>
            <BarList color="var(--warn)" empty={t("Sem uso medido no período.")}
              rows={o.cost_by_provider.map((p: any) => ({ label: p.provider, value: p.cost_usd || p.minutes / 1e6, text: usd(p.cost_usd, 4), sub: `${num(p.minutes)} min` }))} />
          </Panel>
          <Panel title={t("Organizações que mais usam")}>
            <BarList empty={t("Sem uso medido no período.")}
              rows={o.top_tenants.map((p: any) => ({ label: p.name, value: p.minutes, text: `${num(p.minutes)} min`, sub: usd(p.cost_usd, 4) }))} />
          </Panel>
          <Panel title={t("Idiomas mais ouvidos")}>
            <BarList color="var(--ok)" empty={t("Sem uso medido no período.")}
              rows={o.top_languages.map((p: any) => ({ label: p.language.toUpperCase(), value: p.minutes, text: `${num(p.minutes)} min` }))} />
          </Panel>
        </div>
      </>}
    </>
  );
}

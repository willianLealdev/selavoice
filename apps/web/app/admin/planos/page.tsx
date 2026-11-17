"use client";
/**
 * Super Admin — PLANOS. Cria planos MENSAIS (assinatura) ou POR EVENTO (pagamento único) e configura todos os limites:
 * horas de transmissão (contadas desde o INÍCIO da transmissão), pessoas, idiomas, eventos, equipe e recursos.
 * Cada campo numérico aceita "ilimitado" (salvo como null). Versões são IMUTÁVEIS: editar = criar NOVA versão; quem já
 * contratou continua na versão antiga (grandfathering). Publicar/arquivar só muda a visibilidade na página de preços.
 */
import { useEffect, useMemo, useState } from "react";
import { PageHead, Panel } from "@/components/AdminUI";
import Icon from "@/components/Icon";
import { blankLimits, LimitsFields, limitsFromEnt, limitsToEnt, type LimitsForm } from "@/components/LimitsEditor";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { countsHours, planLines } from "@/lib/plans";

type Form = LimitsForm & {
  planId?: string; name: string; slug: string; description: string; status: string; billing: "MONTHLY" | "ONE_OFF"; price: string; extraHour: string;
};

const blank = (billing: "MONTHLY" | "ONE_OFF"): Form => ({
  name: "", slug: "", description: "", status: "draft", billing, price: billing === "ONE_OFF" ? "149" : "299", extraHour: "", ...blankLimits(billing),
});

/** Plano salvo -> formulário. */
function fromVersion(p: any, v: any): Form {
  const e = v.entitlements ?? {};
  return {
    planId: p.id, name: p.name, slug: p.slug, description: p.description ?? "", status: p.status, billing: v.billing_type, price: String(v.amount_cents / 100),
    extraHour: e.extra_hour_cents ? String(e.extra_hour_cents / 100) : "", ...limitsFromEnt(e),
  };
}

/** Formulário -> limites do plano (inclui o preço da hora extra, que só existe em planos). */
function toLimits(f: Form) {
  return { ...limitsToEnt(f), extra_hour_cents: f.extraHour ? Math.round(Number(f.extraHour.replace(",", ".")) * 100) : null };
}

export default function Planos() {
  const t = useT();
  const [plans, setPlans] = useState<any[]>([]); const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const [f, setF] = useState<Form | null>(null); const [saving, setSaving] = useState(false);
  const [all, setAll] = useState<{ code: string }[]>([]);
  const load = () => api("/admin/plans").then(setPlans).catch((e) => setErr(e.message));
  useEffect(() => { load(); api("/public/languages").then(setAll).catch(() => {}); }, []);
  const set = (p: Partial<Form>) => setF((x) => (x ? { ...x, ...p } : x));

  const preview = useMemo(() => (f ? planLines(toLimits(f), t as any, (c) => money(c, "usd")) : []), [f, t]);

  async function save() {
    if (!f) return; setErr(""); setOk(""); setSaving(true);
    try {
      let id = f.planId;
      if (!id) {
        if (!f.name.trim() || !/^[a-z0-9-]{2,60}$/.test(f.slug)) throw new Error(t("Informe o nome e um identificador (letras minúsculas, números e hífen)."));
        id = (await api("/admin/plans", { method: "POST", json: { public_name: f.name.trim(), slug: f.slug, description: f.description } })).id as string;
      } else {
        await api(`/admin/plans/${id}?description=${encodeURIComponent(f.description)}`, { method: "PATCH" });
      }
      const cents = Math.round(Number(f.price.replace(",", ".")) * 100);
      if (!Number.isFinite(cents) || cents < 0) throw new Error(t("Preço inválido."));
      await api(`/admin/plans/${id}/versions`, { method: "POST", json: { billing_type: f.billing, amount_cents: cents, entitlements: toLimits(f) } });
      if (f.status !== plans.find((p) => p.id === id)?.status) await api(`/admin/plans/${id}?status=${f.status}`, { method: "PATCH" });
      setOk(t("Plano salvo. Uma nova versão foi criada; quem já contratou continua na versão anterior.")); setF(null); load();
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  }
  async function setStatus(p: any, status: string) { try { await api(`/admin/plans/${p.id}?status=${status}`, { method: "PATCH" }); load(); } catch (e: any) { setErr(e.message); } }

  return (
    <>
      <PageHead title={t("Planos")} sub={t("Crie planos mensais ou por evento e configure horas, pessoas, idiomas e recursos.")}
        right={<div className="row"><button className="btn btn-primary" onClick={() => setF(blank("MONTHLY"))}><Icon name="plus" small /> {t("Novo plano mensal")}</button>
          <button className="btn btn-ghost" onClick={() => setF(blank("ONE_OFF"))}><Icon name="plus" small /> {t("Novo plano por evento")}</button></div>} />
      {err && <div className="err">{t(err)}</div>}{ok && <div className="ok">{ok}</div>}

      {f && (
        <div className="editor">
          <div className="editor-form">
            <Panel title={f.planId ? `${t("Nova versão de")} ${f.name}` : t("Novo plano")} hint={t("Salvar cria uma NOVA versão. Quem já contratou mantém a versão anterior.")}
              right={<button className="btn btn-ghost btn-sm" onClick={() => setF(null)}><Icon name="x" small /> {t("Cancelar")}</button>}>
              <div className="pf-grid">
                <div className="pf"><label>{t("Nome público")}</label><input value={f.name} disabled={!!f.planId} onChange={(e) => set({ name: e.target.value })} /></div>
                <div className="pf"><label>{t("Identificador (slug)")}</label><input value={f.slug} disabled={!!f.planId} placeholder="evento-pequeno" onChange={(e) => set({ slug: e.target.value.toLowerCase() })} /></div>
              </div>
              <div className="pf"><label>{t("Descrição curta")}</label><input value={f.description} maxLength={200} onChange={(e) => set({ description: e.target.value })} /></div>

              <h4 className="pf-sec">{t("Cobrança")}</h4>
              <div className="choice">
                {([["MONTHLY", "Mensal", "Assinatura renovada todo mês. Os limites se renovam a cada período."], ["ONE_OFF", "Por evento", "Pagamento único. Vale para o(s) evento(s) comprado(s), sem renovação."]] as const).map(([k, title, d]) => (
                  <button type="button" key={k} className={f.billing === k ? "on" : ""} onClick={() => set({ billing: k })}><b>{t(title)}</b><span>{t(d)}</span></button>
                ))}
              </div>
              <div className="pf-grid">
                <div className="pf"><label>{f.billing === "MONTHLY" ? t("Preço por mês (US$)") : t("Preço por evento (US$)")}</label><input inputMode="decimal" value={f.price} onChange={(e) => set({ price: e.target.value })} /></div>
                <div className="pf"><label>{t("Hora extra (US$) — opcional")}</label><input inputMode="decimal" value={f.extraHour} placeholder="—" onChange={(e) => set({ extraHour: e.target.value })} /><p className="fine">{t("Informativo: o sistema mostra o valor, mas ainda não cobra horas extras automaticamente.")}</p></div>
              </div>

              <LimitsFields f={f} set={set} scope={f.billing} all={all} />

              <div className="pf-grid" style={{ alignItems: "end" }}>
                <div className="pf"><label>{t("Visibilidade")}</label>
                  <select value={f.status} onChange={(e) => set({ status: e.target.value })}>
                    <option value="draft">{t("Rascunho (não aparece para clientes)")}</option><option value="published">{t("Publicado (aparece nos preços)")}</option><option value="archived">{t("Arquivado")}</option>
                  </select></div>
                <button className="btn btn-primary btn-lg" disabled={saving} onClick={save}>{saving ? t("Salvando…") : f.planId ? t("Salvar como nova versão") : t("Criar plano")}</button>
              </div>
            </Panel>
          </div>

          <aside className="editor-preview">
            <div className="card price">
              <span className="fine">{t("Como o cliente vê")}</span>
              <h3>{f.name || t("Nome do plano")}</h3>
              <div className="amount">{money(Math.round((Number(f.price.replace(",", ".")) || 0) * 100), "usd")} <small>{f.billing === "MONTHLY" ? t("/mês") : t("/evento")}</small></div>
              {f.description && <p className="muted">{f.description}</p>}
              <ul>{preview.map((l) => <li key={l}><Icon name="check" /> {l}</li>)}</ul>
              {countsHours(toLimits(f)) && <p className="fine">{t("A contagem das horas começa quando a transmissão é iniciada.")}</p>}
            </div>
          </aside>
        </div>
      )}

      <div className="plan-grid">
        {plans.map((p) => {
          const v = p.versions.at(-1);
          return (
            <section key={p.id} className="panel plan-card">
              <header className="panel-h">
                <div><h3>{t(p.name)}</h3><p className="fine">{v ? (v.billing_type === "MONTHLY" ? t("Mensal") : t("Por evento")) : "—"} · v{v?.version ?? 0}</p></div>
                <span className={`pill ${p.status === "published" ? "PUBLISHED" : "ENDED"}`}>{p.status === "published" ? t("Publicado") : p.status === "draft" ? t("Rascunho") : t("Arquivado")}</span>
              </header>
              {v && <div className="amount-sm">{money(v.amount_cents, v.currency ?? "usd")}<small>{v.billing_type === "MONTHLY" ? t("/mês") : t("/evento")}</small></div>}
              <ul className="plan-lines">{v && planLines(v.entitlements ?? {}, t as any, (c) => money(c, "usd")).map((l) => <li key={l}><Icon name="check" small /> {l}</li>)}</ul>
              <div className="row" style={{ marginTop: "auto" }}>
                {v && <button className="btn btn-primary btn-sm" onClick={() => setF(fromVersion(p, v))}>{t("Editar (nova versão)")}</button>}
                {p.status !== "published" ? <button className="btn btn-ghost btn-sm" onClick={() => setStatus(p, "published")}>{t("Publicar")}</button>
                  : <button className="btn btn-ghost btn-sm" onClick={() => setStatus(p, "archived")}>{t("Arquivar")}</button>}
              </div>
              {p.versions.length > 1 && <p className="fine" style={{ margin: "10px 0 0" }}>{p.versions.map((x: any) => `v${x.version}: ${money(x.amount_cents)}`).join(" · ")}</p>}
            </section>
          );
        })}
      </div>
    </>
  );
}

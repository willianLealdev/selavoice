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
import { langName } from "@/components/LanguagePicker";
import { api, money } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { countsHours, planLines } from "@/lib/plans";

type Num = { u: boolean; v: string };                       // u = ilimitado
const N = (v: string | number, u = false): Num => ({ u, v: String(v) });
type Form = {
  planId?: string; name: string; slug: string; description: string; status: string; billing: "MONTHLY" | "ONE_OFF"; price: string;
  hours: Num; maxEventHours: Num; extraHour: string; listeners: Num; seats: Num; concurrent: Num; langs: Num; langMinutes: Num;
  events: Num; retention: Num; allowAll: boolean; allowed: string[]; recordings: boolean; pdf: boolean; overage: "hard_stop" | "topup";
};

const blank = (billing: "MONTHLY" | "ONE_OFF"): Form => billing === "ONE_OFF" ? {
  name: "", slug: "", description: "", status: "draft", billing, price: "149", hours: N(4), maxEventHours: N(4), extraHour: "", listeners: N(300), seats: N(2), concurrent: N(1),
  langs: N(3), langMinutes: N(600), events: N(1), retention: N(90), allowAll: true, allowed: [], recordings: true, pdf: true, overage: "hard_stop",
} : {
  name: "", slug: "", description: "", status: "draft", billing, price: "299", hours: N(20), maxEventHours: N(6), extraHour: "", listeners: N(500), seats: N(5), concurrent: N(1),
  langs: N(5), langMinutes: N(2400), events: N(8), retention: N(180), allowAll: true, allowed: [], recordings: true, pdf: true, overage: "topup",
};

/** Converte os limites salvos num formulário (chave ausente de plano antigo = ilimitado, exceto eventos). */
function fromVersion(p: any, v: any): Form {
  const e = v.entitlements ?? {};
  const g = (k: string, d: number | null): Num => (k in e ? (e[k] === null ? N("", true) : N(e[k])) : d === null ? N("", true) : N(d));
  const maxH: Num = "max_event_hours" in e ? g("max_event_hours", null) : "max_event_minutes" in e ? (e.max_event_minutes === null ? N("", true) : N(e.max_event_minutes / 60)) : N("", true);
  return {
    planId: p.id, name: p.name, slug: p.slug, description: p.description ?? "", status: p.status, billing: v.billing_type, price: String(v.amount_cents / 100),
    hours: g("included_hours", null), maxEventHours: maxH, extraHour: e.extra_hour_cents ? String(e.extra_hour_cents / 100) : "", listeners: g("listener_concurrency", null),
    seats: g("admin_seats", null), concurrent: g("max_concurrent_events", 1), langs: g("max_languages", null), langMinutes: g("included_language_minutes", 0), events: g("included_events", 1),
    retention: g("retention_days", null), allowAll: !(e.allowed_languages?.length), allowed: e.allowed_languages ?? [], recordings: !!e.recordings, pdf: !!e.pdf_booklets, overage: e.overage === "topup" ? "topup" : "hard_stop",
  };
}

const num = (x: Num) => (x.u ? null : Math.max(0, Number(String(x.v).replace(",", ".")) || 0));
function toLimits(f: Form) {
  return {
    included_events: num(f.events), included_hours: num(f.hours), max_event_hours: num(f.maxEventHours),
    extra_hour_cents: f.extraHour ? Math.round(Number(f.extraHour.replace(",", ".")) * 100) : null,
    listener_concurrency: num(f.listeners), admin_seats: num(f.seats), max_concurrent_events: num(f.concurrent),
    max_languages: num(f.langs), included_language_minutes: num(f.langMinutes), allowed_languages: f.allowAll ? [] : f.allowed,
    recordings: f.recordings, pdf_booklets: f.pdf, retention_days: num(f.retention), overage: f.overage,
  };
}

function Field({ label, hint, value, onChange, unit, unlimitedLabel }: { label: string; hint?: string; value: Num; onChange: (n: Num) => void; unit?: string; unlimitedLabel: string }) {
  return (
    <div className="pf">
      <label>{label}</label>
      <div className="pf-row">
        <input inputMode="decimal" disabled={value.u} value={value.u ? "" : value.v} placeholder={value.u ? "∞" : "0"} onChange={(e) => onChange({ ...value, v: e.target.value })} />
        {unit && <span className="fine">{unit}</span>}
        <label className="pf-inf"><input type="checkbox" checked={value.u} onChange={(e) => onChange({ ...value, u: e.target.checked })} /> {unlimitedLabel}</label>
      </div>
      {hint && <p className="fine">{hint}</p>}
    </div>
  );
}

export default function Planos() {
  const t = useT();
  const { lang } = useLang();
  const [plans, setPlans] = useState<any[]>([]); const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const [f, setF] = useState<Form | null>(null); const [saving, setSaving] = useState(false);
  const [all, setAll] = useState<{ code: string }[]>([]); const [q, setQ] = useState("");
  const load = () => api("/admin/plans").then(setPlans).catch((e) => setErr(e.message));
  useEffect(() => { load(); api("/public/languages").then(setAll).catch(() => {}); }, []);
  const set = (p: Partial<Form>) => setF((x) => (x ? { ...x, ...p } : x));
  const inf = t("Ilimitado");

  const preview = useMemo(() => (f ? planLines(toLimits(f), t as any, (c) => money(c, "usd")) : []), [f, t]);
  const langList = all.filter((l) => !q.trim() || langName(l.code, lang).toLowerCase().includes(q.trim().toLowerCase()) || l.code.startsWith(q.trim().toLowerCase()));

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

              <h4 className="pf-sec">{t("Horas de transmissão")}</h4>
              <p className="fine" style={{ marginTop: -6 }}>{t("As horas começam a contar quando a transmissão é INICIADA, e não quando o evento é agendado.")}</p>
              <div className="pf-grid">
                <Field label={f.billing === "MONTHLY" ? t("Horas incluídas por mês") : t("Horas incluídas na compra")} value={f.hours} onChange={(v) => set({ hours: v })} unit="h" unlimitedLabel={inf} />
                <Field label={t("Limite de horas por evento")} hint={t("Ao atingir, o evento é encerrado automaticamente.")} value={f.maxEventHours} onChange={(v) => set({ maxEventHours: v })} unit="h" unlimitedLabel={t("Sem limite")} />
              </div>

              <h4 className="pf-sec">{t("Pessoas")}</h4>
              <div className="pf-grid">
                <Field label={t("Ouvintes simultâneos por evento")} value={f.listeners} onChange={(v) => set({ listeners: v })} unlimitedLabel={inf} />
                <Field label={t("Pessoas na equipe (administradores/operadores)")} value={f.seats} onChange={(v) => set({ seats: v })} unlimitedLabel={inf} />
                <Field label={t("Eventos ao vivo ao mesmo tempo")} value={f.concurrent} onChange={(v) => set({ concurrent: v })} unlimitedLabel={inf} />
              </div>

              <h4 className="pf-sec">{t("Eventos")}</h4>
              <div className="pf-grid"><Field label={f.billing === "MONTHLY" ? t("Eventos incluídos por mês") : t("Eventos incluídos na compra")} value={f.events} onChange={(v) => set({ events: v })} unlimitedLabel={inf} /></div>

              <h4 className="pf-sec">{t("Idiomas")}</h4>
              <div className="pf-grid">
                <Field label={t("Idiomas simultâneos por evento")} hint={t("Quantos idiomas diferentes podem estar sendo ouvidos ao mesmo tempo.")} value={f.langs} onChange={(v) => set({ langs: v })} unlimitedLabel={inf} />
                <Field label={t("Minutos-idioma incluídos")} hint={t("1 idioma ouvido por 1 minuto = 1.")} value={f.langMinutes} onChange={(v) => set({ langMinutes: v })} unlimitedLabel={inf} />
              </div>
              <div className="pf">
                <label>{t("Quais idiomas o plano permite")}</label>
                <div className="choice small">
                  <button type="button" className={f.allowAll ? "on" : ""} onClick={() => set({ allowAll: true })}><b>{t("Todos os disponíveis")}</b></button>
                  <button type="button" className={!f.allowAll ? "on" : ""} onClick={() => set({ allowAll: false })}><b>{t("Somente os escolhidos")}</b></button>
                </div>
                {!f.allowAll && (
                  <div className="lang-pick">
                    <input placeholder={t("Buscar idioma…")} value={q} onChange={(e) => setQ(e.target.value)} />
                    <div className="chips">
                      {langList.map((l) => {
                        const on = f.allowed.includes(l.code);
                        return <button type="button" key={l.code} className={`chip-lang pick ${on ? "v" : ""}`} onClick={() => set({ allowed: on ? f.allowed.filter((c) => c !== l.code) : [...f.allowed, l.code] })}>{langName(l.code, lang)}</button>;
                      })}
                    </div>
                    <p className="fine">{f.allowed.length} {t("idiomas escolhidos")}</p>
                  </div>
                )}
              </div>

              <h4 className="pf-sec">{t("Recursos e retenção")}</h4>
              <div className="pf-grid">
                <label className="pf-check"><input type="checkbox" checked={f.recordings} onChange={(e) => set({ recordings: e.target.checked })} /> {t("Gravação do evento")}</label>
                <label className="pf-check"><input type="checkbox" checked={f.pdf} onChange={(e) => set({ pdf: e.target.checked })} /> {t("Documento pós-evento em PDF")}</label>
                <Field label={t("Guardar histórico por (dias)")} value={f.retention} onChange={(v) => set({ retention: v })} unlimitedLabel={t("Para sempre")} />
                <div className="pf"><label>{t("Quando o limite acaba")}</label>
                  <select value={f.overage} onChange={(e) => set({ overage: e.target.value as any })}>
                    <option value="hard_stop">{t("Parar (bloquear até renovar)")}</option><option value="topup">{t("Permitir créditos comprados")}</option>
                  </select></div>
              </div>

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

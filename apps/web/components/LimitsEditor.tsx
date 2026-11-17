"use client";
/**
 * Editor de LIMITES compartilhado: usado nos PLANOS e no TESTE GRÁTIS (mesmas opções, mesmas regras no servidor).
 * Cada campo numérico aceita "ilimitado" (salvo como null). Ver services/api/app/services/plan_schema.py.
 */
import { useState } from "react";
import { langName } from "@/components/LanguagePicker";
import { useLang, useT } from "@/lib/i18n";

export type Num = { u: boolean; v: string };                       // u = ilimitado
export const N = (v: string | number, u = false): Num => ({ u, v: String(v) });

export type LimitsForm = {
  hours: Num; maxEventHours: Num; listeners: Num; seats: Num; concurrent: Num; langs: Num; langMinutes: Num;
  events: Num; retention: Num; allowAll: boolean; allowed: string[]; recordings: boolean; pdf: boolean; overage: "hard_stop" | "topup";
};
export type Scope = "MONTHLY" | "ONE_OFF" | "TRIAL";

/** Valores iniciais sugeridos ao criar um plano novo. */
export const blankLimits = (scope: "MONTHLY" | "ONE_OFF"): LimitsForm => scope === "ONE_OFF" ? {
  hours: N(4), maxEventHours: N(4), listeners: N(300), seats: N(2), concurrent: N(1), langs: N(3), langMinutes: N(600), events: N(1), retention: N(90),
  allowAll: true, allowed: [], recordings: true, pdf: true, overage: "hard_stop",
} : {
  hours: N(20), maxEventHours: N(6), listeners: N(500), seats: N(5), concurrent: N(1), langs: N(5), langMinutes: N(2400), events: N(8), retention: N(180),
  allowAll: true, allowed: [], recordings: true, pdf: true, overage: "topup",
};

/** Limites salvos -> formulário (chave ausente de plano antigo = ilimitado, exceto eventos). */
export function limitsFromEnt(e: Record<string, any>): LimitsForm {
  const g = (k: string, d: number | null): Num => (k in e ? (e[k] === null ? N("", true) : N(e[k])) : d === null ? N("", true) : N(d));
  const maxH: Num = "max_event_hours" in e ? g("max_event_hours", null) : "max_event_minutes" in e ? (e.max_event_minutes === null ? N("", true) : N(e.max_event_minutes / 60)) : N("", true);
  return {
    hours: g("included_hours", null), maxEventHours: maxH, listeners: g("listener_concurrency", null), seats: g("admin_seats", null), concurrent: g("max_concurrent_events", 1),
    langs: g("max_languages", null), langMinutes: g("included_language_minutes", 0), events: g("included_events", 1), retention: g("retention_days", null),
    allowAll: !(e.allowed_languages?.length), allowed: e.allowed_languages ?? [], recordings: !!e.recordings, pdf: !!e.pdf_booklets, overage: e.overage === "topup" ? "topup" : "hard_stop",
  };
}

const num = (x: Num) => (x.u ? null : Math.max(0, Number(String(x.v).replace(",", ".")) || 0));
/** Formulário -> limites que o servidor valida e grava. */
export function limitsToEnt(f: LimitsForm) {
  return {
    included_events: num(f.events), included_hours: num(f.hours), max_event_hours: num(f.maxEventHours), listener_concurrency: num(f.listeners),
    admin_seats: num(f.seats), max_concurrent_events: num(f.concurrent), max_languages: num(f.langs), included_language_minutes: num(f.langMinutes),
    allowed_languages: f.allowAll ? [] : f.allowed, recordings: f.recordings, pdf_booklets: f.pdf, retention_days: num(f.retention), overage: f.overage,
  };
}

export function Field({ label, hint, value, onChange, unit, unlimitedLabel }: { label: string; hint?: string; value: Num; onChange: (n: Num) => void; unit?: string; unlimitedLabel: string }) {
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

/** Seções: Horas, Pessoas, Eventos, Idiomas, Recursos. `scope` só muda os rótulos ("por mês", "na compra", "no teste"). */
export function LimitsFields({ f, set, scope, all }: { f: LimitsForm; set: (p: Partial<LimitsForm>) => void; scope: Scope; all: { code: string }[] }) {
  const t = useT();
  const { lang } = useLang();
  const [q, setQ] = useState("");
  const inf = t("Ilimitado");
  const per = (m: string, o: string, tr: string) => (scope === "MONTHLY" ? t(m) : scope === "ONE_OFF" ? t(o) : t(tr));
  const langList = all.filter((l) => !q.trim() || langName(l.code, lang).toLowerCase().includes(q.trim().toLowerCase()) || l.code.startsWith(q.trim().toLowerCase()));
  return (
    <>
      <h4 className="pf-sec">{t("Horas de transmissão")}</h4>
      <p className="fine" style={{ marginTop: -6 }}>{t("As horas começam a contar quando a transmissão é INICIADA, e não quando o evento é agendado.")}</p>
      <div className="pf-grid">
        <Field label={per("Horas incluídas por mês", "Horas incluídas na compra", "Horas incluídas no teste")} value={f.hours} onChange={(v) => set({ hours: v })} unit="h" unlimitedLabel={inf} />
        <Field label={t("Limite de horas por evento")} hint={t("Ao atingir, o evento é encerrado automaticamente.")} value={f.maxEventHours} onChange={(v) => set({ maxEventHours: v })} unit="h" unlimitedLabel={t("Sem limite")} />
      </div>

      <h4 className="pf-sec">{t("Pessoas")}</h4>
      <div className="pf-grid">
        <Field label={t("Ouvintes simultâneos por evento")} value={f.listeners} onChange={(v) => set({ listeners: v })} unlimitedLabel={inf} />
        <Field label={t("Pessoas na equipe (administradores/operadores)")} value={f.seats} onChange={(v) => set({ seats: v })} unlimitedLabel={inf} />
        <Field label={t("Eventos ao vivo ao mesmo tempo")} value={f.concurrent} onChange={(v) => set({ concurrent: v })} unlimitedLabel={inf} />
      </div>

      <h4 className="pf-sec">{t("Eventos")}</h4>
      <div className="pf-grid"><Field label={per("Eventos incluídos por mês", "Eventos incluídos na compra", "Eventos incluídos no teste")} value={f.events} onChange={(v) => set({ events: v })} unlimitedLabel={inf} /></div>

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
    </>
  );
}

"use client";
/** Super Admin — ORGANIZAÇÕES: lista com plano, usuários, eventos e uso; suspender/ativar exige motivo (auditado). */
import { useEffect, useMemo, useState } from "react";
import { PageHead, Panel, num } from "@/components/AdminUI";
import Icon from "@/components/Icon";
import { api, ORG_TYPES } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Organizacoes() {
  const t = useT();
  const [rows, setRows] = useState<any[]>([]); const [q, setQ] = useState(""); const [err, setErr] = useState("");
  const load = () => api("/admin/tenants").then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const shown = useMemo(() => rows.filter((r) => !q.trim() || `${r.name} ${r.slug}`.toLowerCase().includes(q.trim().toLowerCase())), [rows, q]);
  const toggle = async (x: any) => {
    const reason = prompt(`${x.status === "active" ? t("Motivo para SUSPENDER") : t("Motivo para ATIVAR")} ${x.name} (${t("mín. 10 caracteres")}):`);
    if (!reason) return;
    try { await api(`/admin/tenants/${x.id}/${x.status === "active" ? "suspend" : "activate"}`, { method: "POST", json: { reason } }); load(); } catch (e: any) { setErr(e.message); }
  };
  // ---- Ativar plano manualmente (sem pagamento) ----
  const [gx, setGx] = useState<any>(null);                 // organização escolhida
  const [ents, setEnts] = useState<any[]>([]); const [plans, setPlans] = useState<any[]>([]);
  const [g, setG] = useState({ plan: "unlimited", days: "", reason: "" });
  async function openGrant(x: any) {
    setGx(x); setErr(""); setG({ plan: "unlimited", days: "", reason: "" });
    api(`/admin/tenants/${x.id}/entitlements`).then(setEnts).catch((e) => setErr(e.message));
    api("/admin/plans").then(setPlans).catch(() => {});
  }
  async function grant(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try {
      await api(`/admin/tenants/${gx.id}/grant-plan`, { method: "POST", json: { unlimited: g.plan === "unlimited", plan_version_id: g.plan === "unlimited" ? null : g.plan, days: g.days ? Number(g.days) : null, reason: g.reason } });
      setG({ ...g, reason: "" }); api(`/admin/tenants/${gx.id}/entitlements`).then(setEnts); load();
    } catch (e: any) { setErr(e.message); }
  }
  async function off(en: any) {
    const reason = prompt(`${t("Motivo para DESATIVAR este plano")} (${t("mín. 10 caracteres")}):`); if (!reason) return;
    try { await api(`/admin/entitlements/${en.id}/deactivate`, { method: "POST", json: { reason } }); api(`/admin/tenants/${gx.id}/entitlements`).then(setEnts); } catch (e: any) { setErr(e.message); }
  }
  const fmt = (v: any) => v === null || v >= 500000000 ? t("ilimitado") : `${v}`;
  const SRC: Record<string, string> = { trial: "Teste grátis", manual: "Ativado por você", plan: "Plano", subscription: "Assinatura", oneoff: "Compra" };
  return (
    <>
      <PageHead title={t("Organizações")} sub={`${rows.length} ${t("organizações cadastradas")}`} />
      {err && <div className="err">{t(err)}</div>}
      <div className="search-box" style={{ maxWidth: 360 }}><Icon name="search" /><input placeholder={t("Buscar organização…")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
      {gx && (
        <Panel title={`${t("Ativar plano")} — ${gx.name}`}>
          <p className="fine">{t("Libera uso para esta organização sem pagamento. Você escolhe o plano, ou Vitalício (tudo ilimitado, sem data para acabar).")}</p>
          <form onSubmit={grant}>
            <div className="grid-2">
              <div><label>{t("Plano")}</label>
                <select value={g.plan} onChange={(e) => setG({ ...g, plan: e.target.value })}>
                  <option value="unlimited">{t("Vitalício — tudo ilimitado")}</option>
                  {plans.flatMap((p) => p.versions.map((v: any) => <option key={v.id} value={v.id}>{p.name} (v{v.version})</option>))}
                </select></div>
              <div><label>{t("Validade em dias (vazio = sem fim)")}</label><input type="number" min={1} value={g.days} onChange={(e) => setG({ ...g, days: e.target.value })} placeholder={t("Vitalício")} /></div>
            </div>
            <label>{t("Motivo (fica registrado)")}</label>
            <input required minLength={10} value={g.reason} onChange={(e) => setG({ ...g, reason: e.target.value })} placeholder={t("Ex.: parceria com a igreja X")} />
            <div className="row" style={{ marginTop: 12 }}><button className="btn btn-primary">{t("Ativar plano")}</button><button type="button" className="btn btn-ghost" onClick={() => setGx(null)}>{t("Fechar")}</button></div>
          </form>
          <h4 style={{ margin: "20px 0 8px" }}>{t("Saldos atuais desta organização")}</h4>
          <table><thead><tr><th>{t("Origem")}</th><th>{t("Eventos restantes")}</th><th>{t("Horas restantes")}</th><th>{t("Validade")}</th><th>{t("Status")}</th><th></th></tr></thead><tbody>
            {ents.map((en) => (
              <tr key={en.id}><td>{t(SRC[en.source] ?? en.source)}</td><td>{fmt(en.events_remaining)}</td><td>{en.event_minutes_remaining === null ? t("ilimitado") : `${(en.event_minutes_remaining / 60).toFixed(1)} h`}</td>
                <td>{en.expires_at ? new Date(en.expires_at).toLocaleDateString() : t("sem fim")}</td><td>{en.active ? t("Ativa") : t("Desativado")}</td>
                <td>{en.active && <button type="button" className="btn btn-ghost btn-sm" onClick={() => off(en)}>{t("Desativar")}</button>}</td></tr>
            ))}
            {!ents.length && <tr><td colSpan={6} className="fine">{t("Nenhum plano ou saldo — por isso o evento é recusado.")}</td></tr>}
          </tbody></table>
        </Panel>
      )}
      <Panel title={t("Todas as organizações")}>
        <table><thead><tr><th>{t("Organização")}</th><th>{t("Tipo")}</th><th>{t("Plano")}</th><th>{t("Usuários")}</th><th>{t("Eventos")}</th><th>{t("Min-idioma")}</th><th>{t("Status")}</th><th></th></tr></thead><tbody>
          {shown.map((x) => (
            <tr key={x.id}>
              <td><b>{x.name}</b><div className="fine">/o/{x.slug}</div></td><td>{t(ORG_TYPES[x.type] ?? "Outro")}</td>
              <td>{x.plan === "Sem plano" ? <span className="pill CANCELED">{t("Sem plano")}</span> : <b>{x.plan.startsWith("Manual até") ? `${t("Manual até")} ${x.plan.slice(11)}` : t(x.plan)}</b>}</td><td>{x.users}</td><td>{x.events}</td><td>{num(x.language_minutes)}</td>
              <td><span className={`pill ${x.status === "active" ? "PUBLISHED" : "CANCELED"}`}>{x.status === "active" ? t("Ativa") : t("Suspensa")}</span></td>
              <td><button className="btn btn-primary btn-sm" onClick={() => openGrant(x)}>{t("Ativar plano")}</button> <button className="btn btn-ghost btn-sm" onClick={() => toggle(x)}>{x.status === "active" ? t("Suspender") : t("Ativar")}</button></td>
            </tr>
          ))}
          {!shown.length && <tr><td colSpan={8} className="fine">{t("Nada encontrado.")}</td></tr>}
        </tbody></table>
      </Panel>
    </>
  );
}

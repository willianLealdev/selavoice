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
  return (
    <>
      <PageHead title={t("Organizações")} sub={`${rows.length} ${t("organizações cadastradas")}`} />
      {err && <div className="err">{t(err)}</div>}
      <div className="search-box" style={{ maxWidth: 360 }}><Icon name="search" /><input placeholder={t("Buscar organização…")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <Panel title={t("Todas as organizações")}>
        <table><thead><tr><th>{t("Organização")}</th><th>{t("Tipo")}</th><th>{t("Plano")}</th><th>{t("Usuários")}</th><th>{t("Eventos")}</th><th>{t("Min-idioma")}</th><th>{t("Status")}</th><th></th></tr></thead><tbody>
          {shown.map((x) => (
            <tr key={x.id}>
              <td><b>{x.name}</b><div className="fine">/o/{x.slug}</div></td><td>{t(ORG_TYPES[x.type] ?? "Outro")}</td>
              <td>{x.plan ? t(x.plan) : <span className="fine">—</span>}</td><td>{x.users}</td><td>{x.events}</td><td>{num(x.language_minutes)}</td>
              <td><span className={`pill ${x.status === "active" ? "PUBLISHED" : "CANCELED"}`}>{x.status === "active" ? t("Ativa") : t("Suspensa")}</span></td>
              <td><button className="btn btn-ghost btn-sm" onClick={() => toggle(x)}>{x.status === "active" ? t("Suspender") : t("Ativar")}</button></td>
            </tr>
          ))}
          {!shown.length && <tr><td colSpan={8} className="fine">{t("Nada encontrado.")}</td></tr>}
        </tbody></table>
      </Panel>
    </>
  );
}

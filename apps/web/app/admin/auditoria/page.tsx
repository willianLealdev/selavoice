"use client";
/** Super Admin — AUDITORIA: registro de ações sensíveis (quem, o quê, motivo). Somente leitura. */
import { useEffect, useMemo, useState } from "react";
import { PageHead, Panel } from "@/components/AdminUI";
import Icon from "@/components/Icon";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Auditoria() {
  const t = useT();
  const [rows, setRows] = useState<any[]>([]); const [q, setQ] = useState(""); const [err, setErr] = useState("");
  useEffect(() => { api("/admin/audit?limit=300").then(setRows).catch((e) => setErr(e.message)); }, []);
  const shown = useMemo(() => rows.filter((r) => !q.trim() || `${r.action} ${r.reason} ${r.target}`.toLowerCase().includes(q.trim().toLowerCase())), [rows, q]);
  return (
    <>
      <PageHead title={t("Auditoria")} sub={t("Ações sensíveis ficam registradas com motivo. Somente leitura.")} />
      {err && <div className="err">{t(err)}</div>}
      <div className="search-box" style={{ maxWidth: 360 }}><Icon name="search" /><input placeholder={t("Filtrar por ação ou motivo…")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <Panel title={`${shown.length} ${t("registros")}`}>
        <table><thead><tr><th>{t("Quando")}</th><th>{t("Ação")}</th><th>{t("Motivo")}</th><th>{t("Alvo")}</th></tr></thead><tbody>
          {shown.map((a, i) => <tr key={i}><td>{new Date(a.at).toLocaleString()}</td><td><span className="badge">{a.action}</span></td><td>{a.reason || "—"}</td><td className="fine">{a.target || "—"}</td></tr>)}
        </tbody></table>
      </Panel>
    </>
  );
}

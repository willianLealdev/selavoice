"use client";
/** Super Admin — RECARGAS: o dono cria pacotes (horas e/ou eventos extras) que o cliente compra quando o saldo acaba antes do fim do período. */
import { useEffect, useState } from "react";
import { PageHead, Panel } from "@/components/AdminUI";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Recargas() {
  const t = useT();
  const [rows, setRows] = useState<any[]>([]); const [err, setErr] = useState("");
  const [f, setF] = useState({ name: "", hours: "5", events: "0", price: "15", currency: "usd" });
  const load = () => api("/admin/topups").then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try {
      await api("/admin/topups", { method: "POST", json: { name: f.name.trim(), hours: Number(f.hours) || 0, events: Number(f.events) || 0, amount_cents: Math.round(Number(f.price) * 100), currency: f.currency } });
      setF({ ...f, name: "" }); load();
    } catch (x: any) { setErr(x.message); }
  }
  const toggle = (p: any) => api(`/admin/topups/${p.id}?status=${p.status === "published" ? "archived" : "published"}`, { method: "PATCH" }).then(load).catch((x) => setErr(x.message));
  return (
    <>
      <PageHead title={t("Recargas")} sub={t("Pacotes de horas ou eventos extras que o cliente compra quando o saldo acaba antes do fim do período.")} />
      {err && <div className="err">{t(err)}</div>}
      <Panel title={t("Novo pacote de recarga")}>
        <form onSubmit={create}>
          <div className="grid-2">
            <div><label>{t("Nome do pacote")}</label><input required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder={t("Ex.: +5 horas")} /></div>
            <div><label>{t("Preço")}</label><div className="row"><input type="number" min={0} step="0.01" required value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /><select value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}><option value="usd">USD</option><option value="brl">BRL</option><option value="eur">EUR</option></select></div></div>
            <div><label>{t("Horas de transmissão")}</label><input type="number" min={0} value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value })} /></div>
            <div><label>{t("Eventos extras")}</label><input type="number" min={0} value={f.events} onChange={(e) => setF({ ...f, events: e.target.value })} /></div>
          </div>
          <p className="fine">{t("As horas contam só enquanto há fala. A recarga soma no saldo que a organização já tem; se ela não tiver nenhum plano, a compra libera 1 evento com essas horas.")}</p>
          <button className="btn btn-primary">{t("Criar pacote")}</button>
        </form>
      </Panel>
      <Panel title={t("Pacotes")}>
        <table><thead><tr><th>{t("Nome do pacote")}</th><th>{t("Horas")}</th><th>{t("Eventos extras")}</th><th>{t("Preço")}</th><th>{t("Status")}</th><th></th></tr></thead><tbody>
          {rows.map((p) => (
            <tr key={p.id}><td><b>{p.name}</b></td><td>{p.hours}</td><td>{p.events}</td><td>{money(p.amount_cents, p.currency)}</td>
              <td><span className={`pill ${p.status === "published" ? "PUBLISHED" : "CANCELED"}`}>{p.status === "published" ? t("À venda") : t("Arquivado")}</span></td>
              <td><button className="btn btn-ghost btn-sm" onClick={() => toggle(p)}>{p.status === "published" ? t("Arquivar") : t("Publicar")}</button></td></tr>
          ))}
          {!rows.length && <tr><td colSpan={6} className="fine">{t("Nenhum pacote ainda.")}</td></tr>}
        </tbody></table>
      </Panel>
    </>
  );
}

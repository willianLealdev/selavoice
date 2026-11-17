"use client";
/** Equipe: lista membros e cria convites (o token do convite aparece uma única vez). */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Team() {
  const t = useT();
  const [members, setMembers] = useState<any[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("EVENT_OPERATOR");
  const [invite, setInvite] = useState("");
  const [err, setErr] = useState("");
  const load = () => api("/organizations/me/members").then(setMembers).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  async function send(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try { const r = await api("/organizations/me/invitations", { method: "POST", json: { email, role } });
      setInvite(r.emailed ? "__emailed__" : r.invite_token); setEmail(""); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <>
      <div className="page-h"><h1>{t("Equipe")}</h1></div>
      {err && <div className="err">{t(err)}</div>}
      <table><thead><tr><th>{t("Nome")}</th><th>{t("E-mail")}</th><th>{t("Papel")}</th></tr></thead>
        <tbody>{members.map((m) => <tr key={m.user_id}><td>{m.name}</td><td>{m.email}</td><td>{m.role}</td></tr>)}</tbody></table>
      <form className="card" onSubmit={send} style={{ marginTop: 20 }}>
        <h3>{t("Convidar pessoa")}</h3>
        <div className="row">
          <input style={{ maxWidth: 280 }} type="email" required placeholder="email@exemplo.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <select style={{ maxWidth: 200 }} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="EVENT_OPERATOR">{t("Operador de eventos")}</option><option value="TENANT_ADMIN">{t("Administrador")}</option><option value="MEMBER">{t("Membro (leitura)")}</option>
          </select>
          <button className="btn btn-primary btn-sm">{t("Criar convite")}</button>
        </div>
        {invite === "__emailed__" && <div className="ok">{t("Convite enviado por e-mail.")}</div>}
        {invite && invite !== "__emailed__" && <p className="fine" style={{ wordBreak: "break-all" }}>{t("E-mail (Resend) ainda não configurado. Envie este link à pessoa (aparece só agora):")} <code>{`${location.origin}/invite?token=${invite}`}</code></p>}
      </form>
    </>
  );
}

"use client";
/**
 * Super Admin — CONTROLE DE ACESSOS: quem está logado agora, sessões ativas, bloqueios e atividade de login.
 * "Online agora" = fez login ou renovou a sessão nos últimos 15 min (aproximação). Derrubar sessões exige motivo e é auditado.
 */
import { useEffect, useState } from "react";
import { Kpi, PageHead, Panel, num } from "@/components/AdminUI";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { roleLabel } from "@/lib/roles";

const STATUS: Record<string, string> = {
  "auth.login": "Login", "auth.register": "Cadastro", "auth.lockout": "Conta bloqueada", "auth.refresh_reuse": "Token reutilizado (suspeito)",
  "auth.password_reset": "Senha redefinida", "auth.forgot": "Pedido de nova senha", "auth.mfa_enabled": "MFA ativado",
};

export default function Acessos() {
  const t = useT();
  const [pend, setPend] = useState<any>(null);
  const [a, setA] = useState<any>(null); const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const load = () => { api("/admin/access").then(setA).catch((e) => setErr(e.message)); api("/admin/users/pending").then(setPend).catch(() => {}); };
  useEffect(() => { load(); const h = setInterval(load, 20000); return () => clearInterval(h); }, []); // atualiza a cada 20 s
  async function revoke(u: any) {
    const reason = prompt(`${t("Motivo para derrubar as sessões de")} ${u.email} (${t("mín. 10 caracteres")}):`);
    if (!reason) return;
    try { const r = await api(`/admin/users/${u.user_id}/revoke-sessions`, { method: "POST", json: { reason } }); setOk(`${r.revoked} ${t("sessão(ões) derrubada(s).")}`); load(); }
    catch (e: any) { setErr(e.message); }
  }
  async function activate(u: any) {
    const reason = prompt(`${t("Motivo para ATIVAR manualmente")} ${u.email} (${t("mín. 10 caracteres")}):`);
    if (!reason) return;
    try { await api(`/admin/users/${u.user_id}/verify`, { method: "POST", json: { reason } }); setOk(t("Conta ativada.")); load(); } catch (e: any) { setErr(e.message); }
  }
  const w = a?.events_week ?? {};
  return (
    <>
      <PageHead title={t("Controle de acessos")} sub={t("Quem está logado agora e o que aconteceu nos logins. Atualiza sozinho.")} />
      {err && <div className="err">{t(err)}</div>}{ok && <div className="ok">{ok}</div>}
      {a && <>
        <div className="kpi-grid">
          <Kpi icon="users" tone="brand" label={t("Online agora")} value={num(a.online_now)} sub={t("últimos 15 min")} />
          <Kpi icon="key" label={t("Sessões ativas")} value={num(a.active_sessions)} sub={t("logins ainda válidos")} />
          <Kpi icon="check" tone="ok" label={t("Logins (7 dias)")} value={num(w["auth.login"] ?? 0)} sub={`${w["auth.register"] ?? 0} ${t("novos cadastros")}`} />
          <Kpi icon="shield" tone={(w["auth.lockout"] ?? 0) + (w["auth.refresh_reuse"] ?? 0) ? "warn" : "ok"} label={t("Alertas de segurança (7d)")} value={num((w["auth.lockout"] ?? 0) + (w["auth.refresh_reuse"] ?? 0))}
            sub={`${w["auth.lockout"] ?? 0} ${t("bloqueios")} · ${w["auth.refresh_reuse"] ?? 0} ${t("reusos de token")}`} />
        </div>

        <Panel title={t("Usuários logados")} hint={t("Cada linha é uma pessoa com pelo menos uma sessão válida.")}>
          <table><thead><tr><th>{t("Usuário")}</th><th>{t("Organização")}</th><th>{t("Papel")}</th><th>{t("Última atividade")}</th><th>IP</th><th>{t("Sessões")}</th><th></th></tr></thead><tbody>
            {a.sessions.map((s: any) => (
              <tr key={s.user_id}>
                <td><span className={`dot ${s.active_now ? "on" : ""}`} /><b>{s.email}</b>{s.name && <div className="fine">{s.name}</div>}</td>
                <td>{s.org}</td><td><span className="badge">{roleLabel(s.role, t)}</span></td>
                <td>{s.last_seen ? new Date(s.last_seen).toLocaleString() : "—"}</td><td className="fine">{s.ip || "—"}</td><td>{s.sessions}</td>
                <td><button className="btn btn-ghost btn-sm" onClick={() => revoke(s)}>{t("Derrubar sessões")}</button></td>
              </tr>
            ))}
            {!a.sessions.length && <tr><td colSpan={7} className="fine">{t("Ninguém logado no momento.")}</td></tr>}
          </tbody></table>
        </Panel>

        {pend && pend.users.length > 0 && (
          <Panel title={t("Contas aguardando confirmação de e-mail")} hint={pend.email_configured ? t("O e-mail de confirmação foi enviado; você pode ativar manualmente se necessário.") : t("O envio de e-mails (Resend) ainda não está configurado: ative manualmente as contas de teste.")}>
            <table><thead><tr><th>{t("Usuário")}</th><th>{t("Organização")}</th><th>{t("Criada em")}</th><th></th></tr></thead><tbody>
              {pend.users.map((u: any) => <tr key={u.user_id}><td><b>{u.email}</b><div className="fine">{u.name}</div></td><td>{u.org}</td><td>{new Date(u.created_at).toLocaleString()}</td>
                <td><button className="btn btn-ghost btn-sm" onClick={() => activate(u)}>{t("Ativar manualmente")}</button></td></tr>)}
            </tbody></table>
          </Panel>
        )}

        {a.locked.length > 0 && (
          <Panel title={t("Contas bloqueadas por tentativas erradas")}>
            <table><tbody>{a.locked.map((l: any) => <tr key={l.email}><td><b>{l.email}</b></td><td className="fine">{t("até")} {new Date(l.until).toLocaleString()}</td></tr>)}</tbody></table>
          </Panel>
        )}

        <Panel title={t("Atividade recente de acesso")}>
          <table><thead><tr><th>{t("Quando")}</th><th>{t("Evento")}</th><th>{t("Usuário")}</th><th>IP</th></tr></thead><tbody>
            {a.recent.map((r: any, i: number) => (
              <tr key={i}><td>{new Date(r.at).toLocaleString()}</td>
                <td><span className={`badge ${r.action === "auth.lockout" || r.action === "auth.refresh_reuse" ? "badge-live" : ""}`}>{t(STATUS[r.action] ?? r.action)}</span></td>
                <td>{r.email}</td><td className="fine">{r.ip || "—"}</td></tr>
            ))}
          </tbody></table>
        </Panel>
      </>}
    </>
  );
}

"use client";
/**
 * Super Admin › Integrações: onde você cola as chaves de API.
 * - As chaves vão direto para o servidor (HTTPS), são cifradas no banco e NUNCA voltam para esta tela
 *   (só aparece "configurada ••••1234").
 * - Campo em branco = mantém o valor atual. "Apagar" remove.
 * - "Testar conexão" só confirma que a chave é ACEITA pelo serviço; não prova a tradução em tempo real.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { API, api } from "@/lib/api";
import Icon from "@/components/Icon";
import BackButton from "@/components/BackButton";
import { useSession } from "@/lib/session";
import { LangSwitch, useT } from "@/lib/i18n";

type Field = { label: string; secret: boolean; set: boolean; source: string; hint?: string };
type Integ = { name: string; label: string; enabled: boolean; fields: Record<string, Field> };

const HELP: Record<string, string> = {
  gemini: "Crie em aistudio.google.com › Get API key. Usada na tradução principal (voz + texto).",
  azure: "Portal Azure › recurso Speech › Keys and Endpoint. Copie a Key 1 e a Região (ex.: eastus). Tradução reserva.",
  deepgram: "console.deepgram.com › API Keys. Transcreve o áudio ORIGINAL (reserva do faster-whisper).",
  deepseek: "platform.deepseek.com › API keys. Usada SÓ para estruturar o documento pós-evento (nunca traduz).",
  resend: "resend.com › API Keys (re_…). Verifique seu domínio em Domains e informe o remetente (ex.: no-reply@seudominio.com). Envia convites e recuperação de senha.",
  stripe: "dashboard.stripe.com › Developers › API keys (comece com sk_test_). O Webhook Secret (whsec_…) vem ao criar o endpoint abaixo.",
};

export default function Integrations() {
  const t = useT();
  const { me, loading } = useSession({ requireSuper: true });
  const [items, setItems] = useState<Integ[]>([]);
  const [form, setForm] = useState<Record<string, Record<string, string>>>({});
  const [msg, setMsg] = useState<Record<string, { ok: boolean; t: string }>>({});
  const [confirmLive, setConfirmLive] = useState("");

  const load = () => api<Integ[]>("/admin/integrations").then(setItems).catch((e) => alert(e.message));
  useEffect(() => { if (me?.is_super_admin && me.mfa_session) load(); }, [me]); // eslint-disable-line

  if (loading) return <div className="auth-wrap">{t("Carregando…")}</div>;
  if (!me?.is_super_admin || !me.mfa_session) return <div className="auth-wrap"><div className="auth-card">{t("Entre em")} <a href="/admin/login">/admin/login</a> {t("com MFA.")}</div></div>;

  const set = (n: string, k: string, v: string) => setForm({ ...form, [n]: { ...form[n], [k]: v } });
  const flash = (n: string, ok: boolean, m: string) => setMsg((x) => ({ ...x, [n]: { ok, t: m } }));

  async function save(n: string, extra: object = {}) {
    try {
      const r = await api<Integ>(`/admin/integrations/${n}`, { method: "PUT", json: { values: form[n] ?? {}, confirm_live: confirmLive || undefined, ...extra } });
      setItems((xs) => xs.map((x) => (x.name === n ? r : x)));
      setForm({ ...form, [n]: {} });  // limpa o que foi digitado: o valor não fica na tela
      flash(n, true, t("Salvo com segurança (cifrado)."));
    } catch (e: any) { flash(n, false, t(e.message)); }
  }
  async function test(n: string) {
    try { const r = await api(`/admin/integrations/${n}/test`, { method: "POST" }); flash(n, r.ok, t(r.detail)); }
    catch (e: any) { flash(n, false, t(e.message)); }
  }

  return (
    <div style={{ maxWidth: 900 }}>
            <div className="page-h"><h1>{t("Integrações e chaves")}</h1></div>
      <div className="card" style={{ marginBottom: 20 }}>
        {t("As chaves ficam cifradas no servidor e nunca são exibidas de volta. Somente o Super Admin com MFA pode trocá-las; toda alteração é auditada (sem o valor). Sem chave, o sistema usa o simulador — nada é cobrado.")}
      </div>
      {items.map((it) => (
        <div className="card" key={it.name} style={{ marginBottom: 16 }}>
          <div className="row spread">
            <h3 style={{ margin: 0 }}>{t(it.label)}</h3>
            <label style={{ margin: 0, display: "flex", gap: 6, alignItems: "center", fontWeight: 500 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={it.enabled} onChange={(e) => save(it.name, { enabled: e.target.checked })} /> {t("ativa")}
            </label>
          </div>
          <p className="fine">{t(HELP[it.name] ?? "")}</p>
          {it.name === "stripe" && (
            <p className="fine">{t("URL do webhook para colar no Stripe:")} <code>{API}/billing/webhook/stripe</code> (checkout.session.completed, invoice.paid, invoice.payment_failed, customer.subscription.deleted)</p>
          )}
          {Object.entries(it.fields).map(([k, f]) => (
            <div key={k}>
              <label htmlFor={`${it.name}-${k}`}>{t(f.label)} {f.set ? <span className="pill PUBLISHED">{t("configurada")} {f.hint}{f.source === "ambiente" ? " (.env)" : ""}</span> : <span className="pill ENDED">{t("não configurada")}</span>}</label>
              <div className="row">
                {k === "mode" ? (
                  <select id={`${it.name}-${k}`} style={{ maxWidth: 300 }} value={form[it.name]?.[k] ?? ""} onChange={(e) => set(it.name, k, e.target.value)}>
                    <option value="">{t("(manter atual)")}</option><option value="fake">{t("fake — simulado, sem cobrança")}</option><option value="test">{t("test — Stripe modo teste")}</option><option value="live">{t("live — COBRANÇA REAL")}</option>
                  </select>
                ) : (
                  <input id={`${it.name}-${k}`} type={f.secret ? "password" : "text"} autoComplete="off" spellCheck={false}
                    placeholder={f.set ? t("deixe vazio para manter") : t("cole aqui")} value={form[it.name]?.[k] ?? ""} onChange={(e) => set(it.name, k, e.target.value)} />
                )}
                {f.set && f.source === "painel" && <button className="btn btn-ghost btn-sm" type="button" onClick={() => confirm(t("Apagar este valor?")) && save(it.name, { values: {}, clear: [k] })}>{t("Apagar")}</button>}
              </div>
            </div>
          ))}
          {it.name === "stripe" && form.stripe?.mode === "live" && (
            <div><label>{t("Para ativar COBRANÇA REAL digite: CONFIRMO COBRANCA REAL")}</label>
              <input value={confirmLive} onChange={(e) => setConfirmLive(e.target.value)} /></div>
          )}
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn btn-primary btn-sm" onClick={() => save(it.name)}>{t("Salvar")}</button>
            <button className="btn btn-ghost btn-sm" onClick={() => test(it.name)}>{t("Testar conexão")}</button>
          </div>
          {msg[it.name] && <div className={msg[it.name].ok ? "ok" : "err"} role="status">{msg[it.name].t}</div>}
        </div>
      ))}
    </div>
  );
}

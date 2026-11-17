"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthShell from "@/components/AuthShell";
import Icon from "@/components/Icon";
import ResendVerification from "@/components/ResendVerification";
import { api, setToken } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { trialHeadline, useTrial } from "@/lib/trial";

export default function Register() {
  const t = useT();
  const { lang } = useLang();
  const trial = useTrial();
  const router = useRouter();
  const [f, setF] = useState({ name: "", email: "", password: "", org_name: "", org_type: "corporate" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<null | { email: string; emailSent: boolean; devToken?: string }>(null);
  const set = (k: string) => (e: React.ChangeEvent<any>) => setF({ ...f, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api("/auth/register", { method: "POST", json: { ...f, lang } });
      if (r.verification_required) { setSent({ email: f.email, emailSent: !!r.email_sent, devToken: r.dev_verify_token ?? undefined }); return; }
      setToken(r.access_token);
      router.push("/dashboard");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  if (sent) return (
    <AuthShell title={t("Verifique seu e-mail")} subtitle={t("Sua conta foi criada, mas ainda não está ativa.")}>
      <div className="check-mail">
        <div className="cm-ic"><Icon name="mail" /></div>
        <p className="cm-lead">{sent.emailSent
          ? <>{t("Enviamos um e-mail de confirmação para")} <b>{sent.email}</b></>
          : <>{t("Não conseguimos enviar o e-mail de confirmação para")} <b>{sent.email}</b>. {t("Tente reenviar em instantes ou fale com o suporte.")}</>}</p>
      </div>
      <div className="notice" style={{ marginTop: 16 }}><Icon name="shield" small /> <span><b>{t("Você precisa confirmar o e-mail para ativar a conta.")}</b> {t("Sem isso, não é possível entrar.")}</span></div>
      <ol className="steps" style={{ marginTop: 18 }}>
        <li>{t("Abra o e-mail que enviamos (veja também a caixa de spam).")}</li>
        <li>{t("Clique em “Confirmar e ativar minha conta”. O link vale por 24 horas.")}</li>
        <li>{t("Volte aqui e entre com seu e-mail e senha.")}</li>
      </ol>
      <ResendVerification email={sent.email} />
      {sent.devToken && <p className="fine" style={{ marginTop: 16 }}>[{t("modo desenvolvimento")}] <Link href={`/verificar?token=${sent.devToken}`}>{t("Confirmar agora")}</Link></p>}
      <p className="fine" style={{ marginTop: 22 }}><Link href="/login">{t("Já confirmei: entrar")}</Link></p>
    </AuthShell>
  );
  return (
    <AuthShell title={t("Criar conta da organização")} subtitle={trial.ready && trial.enabled ? t("Você ganha um teste grátis: {resumo}. Sem cartão de crédito.", { resumo: trialHeadline(trial.limits, t as any) }) : t("Crie a conta da sua organização.")}>
      <form onSubmit={submit}>
        <label htmlFor="n">{t("Seu nome")}</label>
        <input id="n" required autoComplete="name" value={f.name} onChange={set("name")} />
        <label htmlFor="o">{t("Nome da organização")}</label>
        <input id="o" required minLength={2} placeholder={t("Ex.: Acme Eventos")} value={f.org_name} onChange={set("org_name")} />
        <label htmlFor="t">{t("Tipo de organização")}</label>
        <select id="t" value={f.org_type} onChange={set("org_type")}>
          <option value="corporate">{t("Empresa")}</option>
          <option value="conference">{t("Organizador de eventos")}</option>
          <option value="expo">{t("Feira ou expo")}</option>
          <option value="education">{t("Educação")}</option>
          <option value="association">{t("Associação ou comunidade")}</option>
          <option value="church">{t("Igreja ou templo")}</option>
          <option value="other">{t("Outro")}</option>
        </select>
        <label htmlFor="e">{t("E-mail")}</label>
        <input id="e" type="email" autoComplete="username" required value={f.email} onChange={set("email")} />
        <label htmlFor="p">{t("Senha")}</label>
        <input id="p" type="password" autoComplete="new-password" required minLength={12} value={f.password} onChange={set("password")} />
        <p className="fine" style={{ marginTop: 6 }}>{t("Mínimo 12 caracteres, com maiúscula, minúscula e número.")}</p>
        {err && <div className="err" role="alert">{t(err)}</div>}
        <button className="btn btn-primary btn-lg" style={{ width: "100%", marginTop: 16 }} disabled={busy}>{busy ? t("Criando…") : t("Criar conta")}</button>
      </form>
      <p className="fine" style={{ marginTop: 24 }}>{t("Já tem conta?")} <Link href="/login">{t("Entrar")}</Link></p>
    </AuthShell>
  );
}

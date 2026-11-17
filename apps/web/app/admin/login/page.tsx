"use client";
/** Login do Super Admin: senha + código TOTP (MFA obrigatório). Primeiro acesso: configure o MFA. */
import BackButton from "@/components/BackButton";
import { useRouter } from "next/navigation";
import { useState } from "react";
import QRCode from "qrcode";
import { api, setToken } from "@/lib/api";
import { LangSwitch, useT } from "@/lib/i18n";

export default function AdminLogin() {
  const t = useT();
  const router = useRouter();
  const [f, setF] = useState({ email: "", password: "", totp_code: "" });
  const [err, setErr] = useState(""); const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null);
  const [code, setCode] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try {
      const r = await api("/auth/login", { method: "POST", json: { ...f, totp_code: f.totp_code || undefined } });
      setToken(r.access_token);
      if (r.mfa_required_setup) {
        const s = await api("/auth/mfa/setup", { method: "POST" });
        setSetup({ secret: s.secret, qr: await QRCode.toDataURL(s.otpauth_uri, { width: 200 }) });
      } else router.push("/admin");
    } catch (e: any) { setErr(e.message); }
  }
  async function verify(e: React.FormEvent) {
    e.preventDefault();
    try { const r = await api("/auth/mfa/verify", { method: "POST", json: { code } }); setToken(r.access_token); router.push("/admin"); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <div className="auth-wrap">
      {!setup ? (
        <form className="auth-card" onSubmit={submit}>
          <div className="row spread"><BackButton fallback="/" always /><LangSwitch /></div><img src="/logo.webp" alt="SelaVoice" style={{ height: 36, width: "auto", display: "block", margin: "20px 0 16px" }} /><h2>Super Admin</h2>
          <label>{t("E-mail")}</label><input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <label>{t("Senha")}</label><input type="password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <label>{t("Código MFA (6 dígitos)")}</label><input inputMode="numeric" value={f.totp_code} onChange={(e) => setF({ ...f, totp_code: e.target.value })} placeholder={t("Deixe vazio só no 1º acesso")} />
          {err && <div className="err">{t(err)}</div>}
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 16 }}>{t("Entrar")}</button>
        </form>
      ) : (
        <form className="auth-card" onSubmit={verify}>
          <h2>{t("Ative o MFA")}</h2>
          <p className="fine">{t("Escaneie com Google Authenticator/Authy e digite o código gerado.")}</p>
          <img src={setup.qr} alt="QR MFA" style={{ height: 200 }} />
          <p className="fine" style={{ wordBreak: "break-all" }}>{t("Chave manual:")} {setup.secret}</p>
          <input inputMode="numeric" required value={code} onChange={(e) => setCode(e.target.value)} placeholder="000000" />
          {err && <div className="err">{t(err)}</div>}
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 16 }}>{t("Confirmar")}</button>
        </form>
      )}
    </div>
  );
}

"use client";
/**
 * TELA INICIAL DO APP (PWA): "Sou ouvinte" ou "Sou palestrante/organizador".
 *  - Ouvinte: entra sem conta — escaneia QR, digita o código do evento ou busca a organização; vê os eventos abertos recentemente.
 *  - Palestrante/organizador: faz login e vai para o painel (a transmissão é feita pelo navegador/Windows; o celular ouve).
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Icon from "@/components/Icon";
import InstallApp from "@/components/InstallApp";
import QrScan from "@/components/QrScan";
import { LangSwitch, useT } from "@/lib/i18n";

type Recent = { code: string; title: string; org: string };

export default function AppHome() {
  const t = useT();
  const router = useRouter();
  const [scan, setScan] = useState(false);
  const [code, setCode] = useState(""); const [err, setErr] = useState("");
  const [recent, setRecent] = useState<Recent[]>([]);
  useEffect(() => { try { setRecent(JSON.parse(localStorage.getItem("sv_recent") ?? "[]")); } catch {} }, []);
  const go = useCallback((p: string) => { setScan(false); router.push(p); }, [router]);
  function open(e: React.FormEvent) {
    e.preventDefault();
    const c = code.trim().toLowerCase().replace(/^.*\/e\//, "").replace(/[^a-z0-9_-]/g, "");
    if (c.length < 4) return setErr("Código inválido.");
    go(`/e/${c}`);
  }
  return (
    <div className="home-app">
      <header className="home-top"><img src="/logo.webp" alt="SelaVoice" /><LangSwitch /></header>
      <main className="home-main">
        <h1>{t("Como você quer entrar?")}</h1>
        <p className="muted">{t("Ouvintes não precisam de conta.")}</p>

        <section className="role-card">
          <div className="role-h"><span className="role-ic"><Icon name="headphones" /></span><div><h2>{t("Sou ouvinte")}</h2><p className="fine">{t("Ouça a tradução em voz e texto.")}</p></div></div>
          <button className="btn btn-primary btn-lg" style={{ width: "100%" }} onClick={() => setScan(true)}><Icon name="qr" /> {t("Escanear QR Code")}</button>
          <form onSubmit={open} className="code-row">
            <input aria-label={t("Código do evento")} placeholder={t("Código do evento")} value={code} onChange={(e) => { setCode(e.target.value); setErr(""); }} autoCapitalize="none" autoCorrect="off" />
            <button className="btn btn-ghost">{t("Abrir")}</button>
          </form>
          {err && <div className="err" style={{ margin: "10px 0 0" }}>{t(err)}</div>}
          <Link className="btn btn-ghost" style={{ width: "100%", marginTop: 10 }} href="/buscar"><Icon name="search" /> {t("Buscar organização pelo nome")}</Link>
          {recent.length > 0 && (
            <div className="recent">
              <span className="fine">{t("Abertos recentemente")}</span>
              {recent.map((r) => <Link key={r.code} href={`/e/${r.code}`} className="recent-row"><b>{r.title}</b><span className="fine">{r.org}</span><Icon name="arrow" small /></Link>)}
            </div>
          )}
        </section>

        <section className="role-card">
          <div className="role-h"><span className="role-ic dark"><Icon name="mic" /></span><div><h2>{t("Sou palestrante ou organizador")}</h2><p className="fine">{t("Entre na sua conta para criar e transmitir eventos.")}</p></div></div>
          <Link className="btn btn-dark btn-lg" style={{ width: "100%" }} href="/login">{t("Entrar na minha conta")}</Link>
          <Link className="btn btn-ghost" style={{ width: "100%", marginTop: 10 }} href="/register">{t("Criar conta da organização")}</Link>
        </section>
        <div style={{ textAlign: "center", marginTop: 8 }}><InstallApp /></div>
      </main>
      {scan && <QrScan onPath={go} onClose={() => setScan(false)} />}
    </div>
  );
}

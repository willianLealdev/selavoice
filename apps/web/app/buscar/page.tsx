"use client";
/** Público (sem conta): busca a organização pelo nome e abre o perfil com os eventos ao vivo e agendados. */
import Link from "next/link";
import { useEffect, useState } from "react";
import Icon from "@/components/Icon";
import OrgLogo from "@/components/OrgLogo";
import BackButton from "@/components/BackButton";
import { api, ORG_TYPES } from "@/lib/api";
import { LangSwitch, useT } from "@/lib/i18n";

type Org = { slug: string; name: string; type: string };

export default function Buscar() {
  const t = useT();
  const [q, setQ] = useState(""); const [res, setRes] = useState<Org[] | null>(null); const [err, setErr] = useState("");
  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); return; }
    const h = setTimeout(() => api<Org[]>(`/public/orgs?q=${encodeURIComponent(q.trim())}`).then(setRes).catch((e) => setErr(e.message)), 300);
    return () => clearTimeout(h);
  }, [q]);
  return (
    <>
      <header className="nav"><div className="container"><Link href="/"><img src="/logo.webp" alt="SelaVoice" /></Link><div className="nav-links"><LangSwitch /><Link className="btn btn-ghost btn-sm" href="/login">{t("Entrar")}</Link></div></div></header>
      <main className="container" style={{ maxWidth: 640, padding: "64px 24px" }}>
        <div className="back-bar"><BackButton fallback="/" /></div>
        <h1 style={{ fontSize: "2rem", letterSpacing: "-0.03em" }}>{t("Encontre um evento")}</h1>
        <p className="muted">{t("Digite o nome da organização que promove o evento. Você não precisa criar conta para ouvir.")}</p>
        <div style={{ position: "relative", marginTop: 20 }}>
          <span style={{ position: "absolute", left: 14, top: 12, color: "var(--faint)" }}><Icon name="search" /></span>
          <input autoFocus aria-label={t("Nome da organização")} placeholder={t("Nome da organização")} value={q} onChange={(e) => setQ(e.target.value)} style={{ height: 48, paddingLeft: 44, fontSize: "1rem" }} />
        </div>
        {err && <div className="err">{t(err)}</div>}
        <div style={{ marginTop: 16 }}>
          {res?.map((o) => (
            <Link key={o.slug} href={`/o/${o.slug}`} className="card" style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 10, color: "inherit", padding: "16px 18px", textDecoration: "none" }}>
              <OrgLogo name={o.name} url={(o as any).logo_url} size={40} />
              <span><b style={{ color: "var(--ink)" }}>{o.name}</b><br /><span className="fine">{t(ORG_TYPES[o.type] ?? "Outro")}</span></span>
              <span style={{ marginLeft: "auto", color: "var(--faint)" }}><Icon name="arrow" small /></span>
            </Link>
          ))}
          {res && !res.length && <p className="muted">{t("Nada encontrado. Confira o nome ou peça o QR Code ao organizador.")}</p>}
        </div>
      </main>
    </>
  );
}

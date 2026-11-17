"use client";
/**
 * Perfil PÚBLICO da organização (destino do QR do perfil). Sem login.
 * Abas: "Ao vivo e próximos" e "Histórico" (eventos encerrados, com busca) — quem perdeu um evento pode reabrir
 * a transcrição. A organização pode ocultar o histórico em Perfil da organização.
 */
import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import BackButton from "@/components/BackButton";
import DateBox from "@/components/DateBox";
import Icon from "@/components/Icon";
import OrgContact from "@/components/OrgContact";
import OrgLogo from "@/components/OrgLogo";
import { api, API, ORG_TYPES } from "@/lib/api";
import { LangSwitch, useLang, useT } from "@/lib/i18n";

type Ev = { booklets?: { id: string; title: string; language: string }[]; title: string; type: string; presenter: string; theme: string; status: string; starts_at: string; join_code: string };

export default function Perfil({ params }: { params: Promise<{ slug: string }> }) {
  const t = useT();
  const { lang } = useLang();
  const { slug } = use(params);
  const [org, setOrg] = useState<any>(null); const [err, setErr] = useState("");
  const [tab, setTab] = useState<"now" | "past">("now");
  const [q, setQ] = useState("");
  useEffect(() => {
    api(`/public/orgs/${slug}`).then((o: any) => { setOrg(o); if (!o.events.length && o.history?.length) setTab("past"); })
      .catch(() => setErr("Organização não encontrada."));
  }, [slug]);

  const past: Ev[] = useMemo(() => (org?.history ?? []).filter((e: Ev) =>
    !q.trim() || `${e.title} ${e.presenter} ${e.theme}`.toLowerCase().includes(q.trim().toLowerCase())), [org, q]);

  const card = (e: Ev) => (
    <div key={e.join_code}>
    <Link href={`/e/${e.join_code}`} className={`ev-card ${e.status === "LIVE" ? "is-live" : ""}`}>
      <DateBox iso={e.starts_at} locale={lang} />
      <div className="ev-body">
        <div className="ev-title">{e.title}</div>
        <div className="ev-meta">
          {e.presenter && <span><Icon name="mic" small /> {e.presenter}</span>}
          <span><Icon name="calendar" small /> {new Date(e.starts_at).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })}</span>
        </div>
        {e.theme && <div className="ev-theme">{e.theme}</div>}
      </div>
      <div className="ev-side">
        {e.status === "LIVE" ? <span className="badge badge-live">{t("AO VIVO")}</span> : e.status === "ENDED" ? <span className="badge">{t("Encerrado")}</span> : <span className="badge badge-brand">{t("Agendado")}</span>}
        <span className="ev-go">{e.status === "LIVE" ? t("Entrar e ouvir") : e.status === "ENDED" ? t("Ver transcrição") : t("Ver evento")} <Icon name="arrow" small /></span>
      </div>
    </Link>
    {!!e.booklets?.length && (
      <div className="l-docs" style={{ margin: "6px 0 14px 4px" }}><Icon name="doc" small /> <span>{t("Apostilas")}:</span> {e.booklets.map((b) => <a key={b.id} href={`${API}/public/booklets/${e.join_code}/${b.id}/pdf`} target="_blank" rel="noreferrer">{b.title}</a>)}</div>
    )}
    </div>
  );

  return (
    <div className="org-page">
      <header className="org-hero">
        <div className="org-hero-in">
          <div className="l-nav">
            <BackButton className="on-dark" fallback="/buscar" />
            <LangSwitch />
          </div>
          {org && (
            <div className="org-id">
              <OrgLogo name={org.name} url={org.logo_url} size={72} />
              <div>
                <h1>{org.name}</h1>
                <div className="l-sub"><span><Icon name="building" small /> {t(ORG_TYPES[org.type] ?? "Outro")}</span>
                  {org.events.some((e: Ev) => e.status === "LIVE") && <span className="badge badge-live">{t("AO VIVO")}</span>}</div>
              </div>
            </div>
          )}
          {org && <OrgContact contact={org.contact} dark />}
        </div>
      </header>
      <main className="org-main">
        {err && <div className="err">{t(err)}</div>}
        {org && <>
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === "now"} onClick={() => setTab("now")}>{t("Ao vivo e próximos")} <span>{org.events.length}</span></button>
            <button role="tab" aria-selected={tab === "past"} onClick={() => setTab("past")}>{t("Histórico de eventos")} <span>{org.history?.length ?? 0}</span></button>
          </div>
          {tab === "now" && <>
            {!org.events.length && (
              <div className="empty-card"><Icon name="calendar" /><b>{t("Nenhum evento ao vivo ou agendado no momento.")}</b>
                {!!org.history?.length && <button className="btn btn-ghost btn-sm" onClick={() => setTab("past")}>{t("Ver eventos anteriores")}</button>}</div>
            )}
            <div className="ev-list">{org.events.map(card)}</div>
          </>}
          {tab === "past" && <>
            <div className="search-box">
              <Icon name="search" />
              <input aria-label={t("Buscar no histórico")} placeholder={t("Buscar no histórico")} value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {!past.length && <div className="empty-card"><Icon name="doc" /><b>{q ? t("Nada encontrado.") : t("Ainda não há eventos anteriores.")}</b></div>}
            <div className="ev-list">{past.map(card)}</div>
          </>}
        </>}
      </main>
    </div>
  );
}

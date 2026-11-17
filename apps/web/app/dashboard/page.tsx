"use client";
/** Lista/histórico de eventos com busca e criação. Criar NÃO consome IA; só "Iniciar" consome cota. */
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Icon from "@/components/Icon";
import DateBox from "@/components/DateBox";
import { useLang, useT } from "@/lib/i18n";

type Ev = { id: string; title: string; type: string; status: string; starts_at: string; presenter: string; join_code: string };
const STATUS: Record<string, string> = { SCHEDULED: "Agendado", LIVE: "AO VIVO", ENDED: "Encerrado", CANCELED: "Cancelado" };

export default function Events() {
  const t = useT();
  const { lang } = useLang();
  const [events, setEvents] = useState<Ev[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState("");
  const [f, setF] = useState({ title: "", type: "conference", starts_at: "", presenter: "", theme: "", original_language: "pt", recording_policy: "none" });
  const [priv, setPriv] = useState(false); const [pw, setPw] = useState("");   // evento privado + senha de acesso

  const load = () => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (status) p.set("status", status);
    api<Ev[]>(`/events?${p}`).then(setEvents).catch((e) => setErr(e.message));
  };
  useEffect(load, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try {
      await api("/events", { method: "POST", json: { ...f, starts_at: new Date(f.starts_at).toISOString(), private: priv, access_password: priv ? pw : null } });
      setShow(false); setPriv(false); setPw(""); load();
    } catch (e: any) { setErr(e.message); }
  }
  const set = (k: string) => (e: React.ChangeEvent<any>) => setF({ ...f, [k]: e.target.value });

  return (
    <>
      <div className="page-h"><div><h1>{t("Eventos")}</h1><p className="muted" style={{ margin: "4px 0 0" }}>{t("Crie, agende e opere os eventos da sua organização.")}</p></div><button className="btn btn-primary" onClick={() => setShow(!show)}><Icon name="plus" small /> {t("Novo evento")}</button></div>
      {err && <div className="err">{t(err)}</div>}
      {show && (
        <form className="card" onSubmit={create} style={{ marginBottom: 20 }}>
          <div className="grid-2">
            <div><label>{t("Título")}</label><input required value={f.title} onChange={set("title")} placeholder={t("Ex.: Conferência anual")} /></div>
            <div><label>{t("Tipo")}</label>
              <select value={f.type} onChange={set("type")}>
                <option value="conference">{t("Conferência ou congresso")}</option><option value="lecture">{t("Palestra")}</option><option value="training">{t("Treinamento")}</option>
                <option value="meeting">{t("Reunião")}</option><option value="expo">Expo</option><option value="fair">{t("Feira")}</option>
                <option value="service">{t("Culto ou cerimônia")}</option><option value="other">{t("Outro")}</option>
              </select></div>
            <div><label>{t("Data e hora")}</label><input type="datetime-local" required value={f.starts_at} onChange={set("starts_at")} /></div>
            <div><label>{t("Palestrante")}</label><input value={f.presenter} onChange={set("presenter")} /></div>
            <div><label>{t("Tema")}</label><input value={f.theme} onChange={set("theme")} /></div>
            <div><label>{t("Idioma original da fala")}</label>
              <select value={f.original_language} onChange={set("original_language")}><option value="pt">Português</option><option value="en">English</option><option value="es">Español</option><option value="fr">Français</option><option value="de">Deutsch</option><option value="it">Italiano</option><option value="zh">中文</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="ar">العربية</option><option value="ru">Русский</option></select></div>
            <div><label>{t("Gravação (requer consentimento)")}</label>
              <select value={f.recording_policy} onChange={set("recording_policy")}>
                <option value="none">{t("Não gravar")}</option><option value="transcript_only">{t("Somente transcrição")}</option><option value="audio_and_transcript">{t("Áudio e transcrição")}</option>
              </select></div>
          </div>
          <label className="pf-check" style={{ marginTop: 14 }}><input type="checkbox" checked={priv} onChange={(e) => setPriv(e.target.checked)} /> {t("Evento privado (só entra quem tem a senha)")}</label>
          {priv ? (
            <div style={{ maxWidth: 360 }}><label>{t("Senha do evento")}</label><input required minLength={4} maxLength={60} value={pw} onChange={(e) => setPw(e.target.value)} placeholder={t("Ex.: culto2026")} autoComplete="off" />
              <p className="fine">{t("Passe esta senha só para quem pode ouvir. Ela aparece na lista pública? Não: evento privado não aparece em nenhuma lista, só abre com o código e a senha.")}</p></div>
          ) : <p className="fine">{t("Evento público: aparece na página da sua organização e qualquer pessoa com o código entra.")}</p>}
          <button className="btn btn-primary" style={{ marginTop: 16 }}>{t("Agendar evento")}</button>
        </form>
      )}
      <div className="row" style={{ marginBottom: 14 }}>
        <input style={{ maxWidth: 280 }} placeholder={t("Buscar por título…")} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
        <select style={{ maxWidth: 200 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t("Todos os status")}</option><option value="SCHEDULED">{t("Agendado")}</option><option value="LIVE">{t("AO VIVO")}</option><option value="ENDED">{t("Encerrado")}</option><option value="CANCELED">{t("Cancelado")}</option>
        </select>
        <button className="btn btn-ghost btn-sm" onClick={load}>{t("Buscar")}</button>
      </div>
      <div className="ev-list">
        {events.map((e) => (
          <Link key={e.id} href={`/dashboard/events/${e.id}`} className={`ev-card ${e.status === "LIVE" ? "is-live" : ""}`}>
            <DateBox iso={e.starts_at} locale={lang} />
            <div className="ev-body">
              <div className="ev-title">{e.title}</div>
              <div className="ev-meta">
                {e.presenter && <span><Icon name="mic" small /> {e.presenter}</span>}
                <span><Icon name="calendar" small /> {new Date(e.starts_at).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })}</span>
              </div>
            </div>
            <div className="ev-side">
              <span className={`pill ${e.status}`}>{t(STATUS[e.status] ?? e.status)}</span>
              <span className="ev-go">{t("Abrir")} <Icon name="arrow" small /></span>
            </div>
          </Link>
        ))}
        {!events.length && <div className="empty-card"><Icon name="calendar" /><b>{t("Nenhum evento ainda. Clique em “Novo evento”.")}</b></div>}
      </div>
    </>
  );
}

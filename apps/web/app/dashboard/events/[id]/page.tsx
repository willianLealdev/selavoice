"use client";
/**
 * Detalhe/controle do evento: iniciar/encerrar, link+QR de entrada, captura de áudio,
 * transcrição original, apostila (rascunho → revisão → aprovação → publicação).
 */
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import Icon from "@/components/Icon";
import { api, API, getToken } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
  const [ev, setEv] = useState<any>(null);
  const [qr, setQr] = useState("");
  const [msg, setMsg] = useState<{ t: "ok" | "err"; m: string } | null>(null);
  const [token, setToken] = useState("");
  const [text, setText] = useState("");
  const [docs, setDocs] = useState<any[]>([]);   // apostilas SALVAS no evento (ficam aqui até você excluir)
  const [openDoc, setOpenDoc] = useState("");
  const DOC_ST: Record<string, string> = { DRAFT: "Rascunho", IN_REVIEW: "Em revisão", APPROVED: "Aprovado", PUBLISHED: "Publicado" };
  const loadDocs = useCallback(() => api(`/documents/events/${id}`).then(setDocs).catch(() => {}), [id]);
  useEffect(() => { loadDocs(); }, [loadDocs]);
  const editCh = (docId: string, i: number, k: "title" | "body", v: string) =>
    setDocs((all) => all.map((d) => d.id !== docId ? d : { ...d, content: { ...d.content, chapters: d.content.chapters.map((c: any, j: number) => j === i ? { ...c, [k]: v } : c) } }));
  async function delDoc(d: any) {
    if (!confirm(`${t("Excluir este documento?")} “${d.title}”\n${t("Ele some do evento, da página da organização e do público.")}`)) return;
    try { await api(`/documents/${d.id}`, { method: "DELETE" }); setMsg({ t: "ok", m: "Documento excluído." }); loadDocs(); } catch (e: any) { setMsg({ t: "err", m: e.message }); }
  }
  async function pdf(d: any) {   // o PDF exige login: baixa com o token e abre numa aba
    try {
      const r = await fetch(`${API}/documents/${d.id}/pdf`, { headers: { Authorization: `Bearer ${getToken()}` }, credentials: "include" });
      if (!r.ok) throw new Error("PDF indisponível.");
      window.open(URL.createObjectURL(await r.blob()), "_blank");
    } catch (e: any) { setMsg({ t: "err", m: e.message }); }
  }
  const [edit, setEdit] = useState<any>(null);   // formulário de edição (null = fechado)
  const [pw, setPw] = useState("");
  const [use_, setUse] = useState<any>(null);  // horas de transmissão (contam desde o início)

  const load = useCallback(async () => {
    const e = await api(`/events/${id}`);
    setEv(e);
    setQr(await QRCode.toDataURL(`${location.origin}/e/${e.join_code}`, { width: 220, margin: 1 }));
  }, [id]);
  useEffect(() => { load().catch((e) => setMsg({ t: "err", m: e.message })); }, [load]);
  useEffect(() => {  // atualiza o relógio a cada 30 s enquanto o evento está ao vivo
    const get = () => api(`/events/${id}/usage`).then(setUse).catch(() => {});
    get(); const h = setInterval(get, 30000); return () => clearInterval(h);
  }, [id, ev?.status]);

  const act = async (fn: () => Promise<any>, ok: string) => {
    try { await fn(); setMsg({ t: "ok", m: ok }); await load(); } catch (e: any) { setMsg({ t: "err", m: e.message }); }
  };
  function openEdit() {
    const d = new Date(ev.starts_at); const loc = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    setPw(""); setEdit({ title: ev.title, presenter: ev.presenter, theme: ev.theme, description: ev.description, starts_at: loc, original_language: ev.original_language, type: ev.type, private: !!ev.private });
  }
  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    const body: any = { title: edit.title, presenter: edit.presenter, theme: edit.theme, description: edit.description, private: edit.private };
    if (edit.private && pw) body.access_password = pw;
    if (ev.status === "SCHEDULED") { body.starts_at = new Date(edit.starts_at).toISOString(); body.original_language = edit.original_language; body.type = edit.type; }
    await act(() => api(`/events/${id}`, { method: "PATCH", json: body }), "Evento atualizado.");
    setEdit(null);
  }
  async function remove() {
    if (!confirm(`${t("Excluir este evento?")} “${ev.title}”\n${t("Ele some da lista e do público. Isso não pode ser desfeito.")}`)) return;
    try { await api(`/events/${id}`, { method: "DELETE" }); location.href = "/dashboard"; } catch (e: any) { setMsg({ t: "err", m: e.message }); }
  }
  if (!ev) return <p>{t("Carregando…")}</p>;
  const url = `${location.origin}/e/${ev.join_code}`;
  const sid = ev.sessions[0]?.id;
  const st: Record<string, string> = { SCHEDULED: "Agendado", LIVE: "AO VIVO", ENDED: "Encerrado", CANCELED: "Cancelado" };

  return (
    <>
      <div className="row spread"><h1>{ev.title}</h1><span className={`pill ${ev.status}`}>{t(st[ev.status] ?? ev.status)}</span></div>
      {msg && <div className={msg.t === "ok" ? "ok" : "err"}>{t(msg.m)}</div>}
      <div className="row" style={{ marginBottom: 12 }}>
        {ev.status !== "CANCELED" && <button className="btn btn-ghost btn-sm" onClick={() => (edit ? setEdit(null) : openEdit())}>{edit ? t("Fechar edição") : t("Editar evento")}</button>}
        {ev.status !== "LIVE" && <button className="btn btn-ghost btn-sm" onClick={remove}>{t("Excluir evento")}</button>}
      </div>
      {edit && (
        <form className="card" onSubmit={saveEdit} style={{ marginBottom: 20 }}>
          <h3>{t("Editar evento")}</h3>
          {ev.status !== "SCHEDULED" && <p className="fine">{t("Com o evento em andamento ou encerrado, só dá para mudar título, palestrante, tema, descrição e privacidade.")}</p>}
          <div className="grid-2">
            <div><label>{t("Título")}</label><input required value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></div>
            <div><label>{t("Palestrante")}</label><input value={edit.presenter} onChange={(e) => setEdit({ ...edit, presenter: e.target.value })} /></div>
            <div><label>{t("Tema")}</label><input value={edit.theme} onChange={(e) => setEdit({ ...edit, theme: e.target.value })} /></div>
            {ev.status === "SCHEDULED" && <div><label>{t("Data e hora")}</label><input type="datetime-local" required value={edit.starts_at} onChange={(e) => setEdit({ ...edit, starts_at: e.target.value })} /></div>}
            {ev.status === "SCHEDULED" && <div><label>{t("Idioma original da fala")}</label>
              <select value={edit.original_language} onChange={(e) => setEdit({ ...edit, original_language: e.target.value })}><option value="pt">Português</option><option value="en">English</option><option value="es">Español</option><option value="fr">Français</option><option value="de">Deutsch</option><option value="it">Italiano</option><option value="zh">中文</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="ar">العربية</option><option value="ru">Русский</option></select></div>}
          </div>
          <label>{t("Descrição")}</label><textarea rows={3} value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
          <label className="pf-check" style={{ marginTop: 10 }}><input type="checkbox" checked={edit.private} onChange={(e) => setEdit({ ...edit, private: e.target.checked })} /> {t("Evento privado (só entra quem tem a senha)")}</label>
          {edit.private && <div style={{ maxWidth: 360 }}><label>{ev.private ? t("Nova senha (deixe vazio para manter a atual)") : t("Senha do evento")}</label><input minLength={4} maxLength={60} required={!ev.private} value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="off" /></div>}
          <button className="btn btn-primary" style={{ marginTop: 14 }}>{t("Salvar alterações")}</button>
        </form>
      )}
      <div className="grid-2">
        <div className="card">
          <h3>{t("Controle")}</h3>
          <p className="fine">{t("Agendar não gasta IA. A cota só é consumida ao iniciar e enquanto houver ouvintes.")}</p>
          {use_ && ev.status !== "SCHEDULED" && ev.status !== "CANCELED" && (
            <div className="clock">
              <div><span className="fine">{t("Tempo de transmissão")}</span><b>{Math.floor(use_.elapsed_minutes / 60)}h {Math.floor(use_.elapsed_minutes % 60)}min</b></div>
              <div><span className="fine">{t("Horas restantes do plano")}</span><b>{use_.plan_minutes_remaining === null ? "∞" : `${Math.floor(use_.plan_minutes_remaining / 60)}h ${use_.plan_minutes_remaining % 60}min`}</b></div>
              {use_.event_minutes_left !== null && <div><span className="fine">{t("Até o limite do evento")}</span><b>{Math.floor(use_.event_minutes_left / 60)}h {Math.floor(use_.event_minutes_left % 60)}min</b></div>}
            </div>
          )}
          {ev.status === "SCHEDULED" && <p className="fine">{t("As horas do plano começam a contar quando você clicar em Iniciar.")}</p>}
          <div className="row">
            {ev.status === "SCHEDULED" && <>
              <button className="btn btn-primary" onClick={() => act(() => api(`/events/${id}/start`, { method: "POST" }), "Evento iniciado!")}><Icon name="play" small /> {t("Iniciar")}</button>
              <button className="btn btn-ghost" onClick={() => act(() => api(`/events/${id}/cancel`, { method: "POST" }), "Evento cancelado.")}>{t("Cancelar")}</button>
            </>}
            {ev.status === "LIVE" && <button className="btn btn-danger" onClick={() => act(() => api(`/events/${id}/stop`, { method: "POST" }), "Evento encerrado.")}>{t("Encerrar")}</button>}
          </div>
          {sid && ev.status !== "CANCELED" && <>
            <hr />
            <Link className="btn btn-primary btn-sm" href={`/dashboard/events/${id}/capture`}><Icon name="mic" small /> {t("Capturar áudio (celular ou computador)")}</Link>{" "}
            <button className="btn btn-ghost btn-sm" onClick={async () => setToken((await api(`/events/sessions/${sid}/audio-token`)).token)}>{t("Token para utilitário externo (mesa/computador)")}</button>
            {token && <p className="fine" style={{ wordBreak: "break-all" }}>{t("Cole no utilitário de captura (válido por 4 h, mostrado só agora):")}<br /><code>{token}</code></p>}
          </>}
        </div>
        <div className="card" style={{ textAlign: "center" }}>
          <h3>{t("Entrada do público")}</h3>
          {qr && <img src={qr} alt={t("QR Code de entrada do evento")} width={220} height={220} />}
          <p><a href={url} target="_blank" rel="noreferrer">{url}</a></p>
          <p className="fine">{t("O público também encontra este evento pelo perfil da organização ou buscando pelo nome.")}</p>
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h3>{t("Transcrição e documento pós-evento")}</h3>
        <p className="fine">{t("Cole a transcrição original (um parágrafo por linha em branco) — vinda do faster-whisper/Deepgram ou revisada à mão. Depois gere o documento.")}</p>
        <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("Cole aqui a transcrição…")} />
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn btn-ghost btn-sm" disabled={!text.trim()} onClick={() => act(() => api(`/documents/events/${id}/original-transcript`, { method: "POST", json: { paragraphs: text.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean) } }), "Transcrição importada.")}>{t("Importar transcrição")}</button>
          <button className="btn btn-primary btn-sm" onClick={() => act(() => api(`/documents/events/${id}/generate`, { method: "POST" }), "Rascunho do documento criado.").then(loadDocs)}>{t("Gerar documento")}</button>
        </div>
        {docs.length === 0 && <p className="fine" style={{ marginTop: 14 }}>{t("Nenhum documento salvo neste evento ainda.")}</p>}
        {docs.map((d) => (
          <div key={d.id} style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div className="row spread"><div className="row"><b>{d.title}</b><span className={`pill ${d.status}`}>{t(DOC_ST[d.status] ?? d.status)}</span><span className="fine">v{d.version} · {d.language}</span></div>
              <div className="row">
                <button className="btn btn-ghost btn-sm" onClick={() => setOpenDoc(openDoc === d.id ? "" : d.id)}>{openDoc === d.id ? t("Fechar") : t("Ver e editar")}</button>
                {(d.status === "APPROVED" || d.status === "PUBLISHED") && <button className="btn btn-ghost btn-sm" onClick={() => pdf(d)}>PDF</button>}
                <button className="btn btn-ghost btn-sm" onClick={() => delDoc(d)}>{t("Excluir")}</button>
              </div></div>
            {openDoc === d.id && (
              <div style={{ marginTop: 10 }}>
                {d.status === "APPROVED" || d.status === "PUBLISHED"
                  ? <p className="fine">{t("Documento aprovado não pode ser editado. Exclua e gere outro se algo estiver errado.")}</p>
                  : <p className="fine">{t("Corrija o que estiver errado e salve. Salvar volta o documento para rascunho.")}</p>}
                {(d.content?.chapters ?? []).map((c: any, i: number) => (
                  <div key={i} style={{ marginBottom: 10 }}>
                    <input value={c.title} disabled={d.status === "APPROVED" || d.status === "PUBLISHED"} onChange={(e) => editCh(d.id, i, "title", e.target.value)} style={{ fontWeight: 600 }} />
                    <textarea rows={5} value={c.body} disabled={d.status === "APPROVED" || d.status === "PUBLISHED"} onChange={(e) => editCh(d.id, i, "body", e.target.value)} />
                  </div>
                ))}
                {d.status !== "APPROVED" && d.status !== "PUBLISHED" && <button className="btn btn-primary btn-sm" onClick={() => act(() => api(`/documents/${d.id}`, { method: "PUT", json: { content: d.content } }), "Documento salvo.").then(loadDocs)}>{t("Salvar correções")}</button>}
              </div>
            )}
            {d.flags.length > 0 && <>
              <p className="fine">{t("Referências detectadas (ex.: citações bíblicas): confira cada uma na fonte antes de aprovar. Não inventamos citações.")}</p>
              {d.flags.map((f: any) => (
                <div key={f.ref} className="row">
                  <span>{f.reviewed ? "✓" : "○"} {f.ref}</span>
                  {!f.reviewed && <button className="btn btn-ghost btn-sm" onClick={() => act(() => api(`/documents/${d.id}/review-flag`, { method: "POST", json: { ref: f.ref } }), "Referência revisada.").then(loadDocs)}>{t("Marcar revisada")}</button>}
                </div>
              ))}
            </>}
            <div className="row" style={{ marginTop: 12 }}>
              {d.status === "DRAFT" && <button className="btn btn-ghost btn-sm" onClick={() => act(() => api(`/documents/${d.id}/submit`, { method: "POST" }), "Enviado para revisão.").then(loadDocs)}>{t("Enviar para revisão")}</button>}
              {d.status === "IN_REVIEW" && <button className="btn btn-primary btn-sm" onClick={() => act(() => api(`/documents/${d.id}/approve`, { method: "POST", json: {} }), "Aprovado; PDF gerado.").then(loadDocs)}>{t("Aprovar")}</button>}
              {d.status === "APPROVED" && <button className="btn btn-primary btn-sm" onClick={() => act(() => api(`/documents/${d.id}/publish`, { method: "POST" }), "Publicado para o público.").then(loadDocs)}>{t("Publicar")}</button>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

"use client";
/**
 * Página PÚBLICA do ouvinte (QR do evento, QR/busca da organização). Sem login.
 *
 * ÁUDIO + TEXTO: modos "Áudio + texto", "Só áudio" e "Só texto", com play, volume e equalizador. Hoje a voz vem do
 * sintetizador do aparelho lendo cada frase FINAL traduzida (a voz dos provedores de IA depende de chaves — BLOCKERS #13).
 *
 * IDIOMAS: a lista vem da API (/public/join -> languages): são os idiomas que os provedores configurados oferecem.
 *
 * Transcrição ACUMULADA (não efêmera):
 *  - segmentos num Map por `seq`; provisório é substituído pela revisão mais nova; final é imutável;
 *  - a rolagem NÃO pula sozinha: só acompanha o fim se o usuário já estava no fim; senão aparece "Voltar ao vivo";
 *  - ao rolar ao topo carrega páginas antigas (scrollback), preservando a posição de leitura;
 *  - reconexão automática com backoff, retomando do último `seq` (replay do servidor).
 */
import { use, useCallback, useEffect, useRef, useState } from "react";
import BackButton from "@/components/BackButton";
import Icon from "@/components/Icon";
import OrgContact from "@/components/OrgContact";
import OrgLogo from "@/components/OrgLogo";
import LanguagePicker, { Lang, langName } from "@/components/LanguagePicker";
import { API, WS } from "@/lib/api";
import { LangSwitch, useLang, useT } from "@/lib/i18n";

type Seg = { seq: number; rev: number; final: boolean; text: string };
type Mode = "both" | "audio" | "text";

export default function Listen({ params }: { params: Promise<{ code: string }> }) {
  const t = useT();
  const { lang: uiLang } = useLang();
  const { code } = use(params);
  const [info, setInfo] = useState<any>(null);
  const [lang, setLang] = useState("");
  const [segs, setSegs] = useState<Map<number, Seg>>(new Map());
  const [status, setStatus] = useState("");
  const [conn, setConn] = useState<"connecting" | "online" | "offline">("connecting");
  const [live, setLive] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const [unseen, setUnseen] = useState(0);
  const [mode, setMode] = useState<Mode>("both");
  const [playing, setPlaying] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [vol, setVol] = useState(1);
  const [books, setBooks] = useState<any[]>([]);
  const [ready, setReady] = useState(false);
  const [about, setAbout] = useState(false);
  const [pw, setPw] = useState(""); const [pwErr, setPwErr] = useState("");   // senha de evento privado
  const tokenRef = useRef(""); const sidRef = useRef("");
  const boxRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  const playRef = useRef(false); const volRef = useRef(1); const langRef = useRef("en");
  const lastSeq = useRef(0);
  // VOZ do provedor (Gemini/Azure): chega como quadros binários PCM16 24 kHz. Tocamos com WebAudio, em fila.
  const actx = useRef<AudioContext | null>(null); const gain = useRef<GainNode | null>(null);
  const nextAt = useRef(0); const providerVoice = useRef(false);
  playRef.current = playing; volRef.current = vol; langRef.current = lang;
  useEffect(() => { if (gain.current) gain.current.gain.value = vol; }, [vol]);

  const playPcm = useCallback((buf: ArrayBuffer) => {
    if (!playRef.current) return;                       // pausado: descarta (não acumula atraso)
    const ctx = actx.current; if (!ctx || buf.byteLength < 2) return;
    providerVoice.current = true;                       // a partir daqui NÃO usamos a voz do aparelho
    window.speechSynthesis?.cancel();
    const i16 = new Int16Array(buf, 0, Math.floor(buf.byteLength / 2));
    const f32 = new Float32Array(i16.length); for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const ab = ctx.createBuffer(1, f32.length, 24000); ab.copyToChannel(f32, 0);
    const src = ctx.createBufferSource(); src.buffer = ab; src.connect(gain.current!);
    if (nextAt.current - ctx.currentTime > 1.5) nextAt.current = 0;   // ficou mais de 1,5 s atrás: recomeça ao vivo
    const at = Math.max(ctx.currentTime + 0.05, nextAt.current);
    src.start(at); nextAt.current = at + ab.duration;
    setSpeaking(true); setTimeout(() => setSpeaking(false), ab.duration * 1000 + 200);
  }, []);

  const speak = useCallback((text: string) => {
    if (providerVoice.current) return;                  // já vem voz de verdade do provedor
    if (!("speechSynthesis" in window)) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = langRef.current; u.volume = volRef.current;
    u.onstart = () => setSpeaking(true);
    u.onend = u.onerror = () => setSpeaking(window.speechSynthesis.speaking || window.speechSynthesis.pending);
    window.speechSynthesis.speak(u);
  }, []);

  const merge = useCallback((list: Seg[], fromLive = false) => {
    setSegs((prev) => {
      const m = new Map(prev);
      for (const s of list) {
        const cur = m.get(s.seq);
        if (cur && (cur.final || cur.rev > s.rev)) continue;
        m.set(s.seq, { seq: s.seq, rev: s.rev, final: s.final, text: s.text });
        if (s.final) {
          lastSeq.current = Math.max(lastSeq.current, s.seq);
          if (fromLive && playRef.current) speak(s.text); // só fala o que chega AO VIVO (não relê o histórico)
        }
      }
      return m;
    });
    if (!atBottomRef.current) setUnseen((n) => n + list.length);
  }, [speak]);

  // dados do evento + token de ouvinte
  // entrar: evento público abre direto; privado pede a senha (guardada só nesta aba, não no aparelho)
  const enter = useCallback(async (password?: string) => {
    {
      const hdr: Record<string, string> = {}; if (password) hdr["X-Event-Password"] = password;
      const r = await fetch(`${API}/public/join/${code}`, { headers: hdr });
      if (!r.ok) return setStatus("Evento não encontrado.");
      const i = await r.json(); setInfo(i); sidRef.current = i.session_id;
      if (i.private) { if (password) setPwErr("Senha incorreta."); return; }
      if (password) try { sessionStorage.setItem(`sv_pw_${code}`, password); } catch {}
      try {  // "abertos recentemente" na tela inicial do app (fica só neste aparelho)
        const cur = JSON.parse(localStorage.getItem("sv_recent") ?? "[]").filter((x: any) => x.code !== code);
        localStorage.setItem("sv_recent", JSON.stringify([{ code, title: i.title, org: i.organization }, ...cur].slice(0, 5)));
      } catch {}
      const tk = await fetch(`${API}/public/join/${code}/token`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: password ?? null }) });
      if (!tk.ok) return setPwErr("Senha incorreta.");
      tokenRef.current = (await tk.json()).token; setReady(true);
      fetch(`${API}/public/booklets/${code}`).then((x) => x.json()).then(setBooks).catch(() => {});
    }
  }, [code]);
  useEffect(() => {
    let saved = ""; try { saved = sessionStorage.getItem(`sv_pw_${code}`) ?? ""; } catch {}
    enter(saved || undefined);
    try { const m = localStorage.getItem("sv_mode") as Mode | null; if (m) setMode(m); } catch {}
  }, [code, enter]);

  // IDIOMA: se o ouvinte já escolheu um antes (guardado no celular) e ele existe neste evento, usamos direto, sem perguntar.
  // Senão mostramos a pergunta "Em qual idioma você quer ouvir?" (a tradução só começa depois da escolha).
  // O botão de idioma no topo continua disponível para trocar quando quiser.
  const langs: Lang[] = info?.languages ?? [];
  const [askLang, setAskLang] = useState("");
  useEffect(() => {
    if (!langs.length) return;
    const has = (c: string) => langs.some((l) => l.code === c);
    let saved = ""; try { saved = localStorage.getItem("sv_lang") ?? ""; } catch {}
    if (lang && has(lang)) return;
    if (saved && has(saved)) setLang(saved);
  }, [info]); // eslint-disable-line
  // vibra de leve quando a transmissão começa (avisa quem está com o celular na mão)
  const wasLive = useRef(false);
  useEffect(() => { if (live && !wasLive.current) { try { navigator.vibrate?.(200); } catch {} } wasLive.current = live; }, [live]);

  // WebSocket com reconexão e retomada
  useEffect(() => {
    if (!ready || !lang) return;
    let ws: WebSocket | null = null; let stop = false; let retry = 0; let ping: any;
    setSegs(new Map()); lastSeq.current = 0; providerVoice.current = false; nextAt.current = 0;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    const open = () => {
      if (stop || !tokenRef.current) return;
      setConn("connecting");
      ws = new WebSocket(`${WS}/sessions/${sidRef.current}/live`);
      ws.binaryType = "arraybuffer";
      ws.onopen = () => ws!.send(JSON.stringify({ type: "auth", token: tokenRef.current, lang, last_seq: lastSeq.current }));
      ws.onmessage = (e) => {
        if (typeof e.data !== "string") { playPcm(e.data as ArrayBuffer); return; }   // voz traduzida
        const m = JSON.parse(e.data);
        if (m.type === "replay") { retry = 0; setConn("online"); setLive(m.live); merge(m.segments, false); }
        else if (m.type === "segment") merge([m], true);
        else if (m.type === "status") setStatus(m.state === "live" ? "" : m.message || "");
        else if (m.type === "error") {
          stop = true;
          setStatus(({ event_full: "Este evento atingiu o limite de ouvintes do plano. Tente de novo em instantes.", language_limit: "Este evento já usa o máximo de idiomas simultâneos. Escolha um dos idiomas em uso.", language_not_in_plan: "Este idioma não está incluído no plano do evento. Escolha outro." } as Record<string, string>)[m.code] ?? "Idioma indisponível no momento. Escolha outro.");
        }
        else if (m.type === "resync") ws?.close();
      };
      ws.onclose = () => { clearInterval(ping); if (stop) return; setConn("offline"); setTimeout(open, Math.min(1000 * 2 ** retry++, 15000)); };
      ping = setInterval(() => ws?.readyState === 1 && ws.send('{"type":"ping"}'), 25000);
    };
    open();
    return () => { stop = true; clearInterval(ping); ws?.close(); };
  }, [ready, lang, merge, playPcm]);

  const ordered = [...segs.values()].sort((a, b) => a.seq - b.seq);
  const prevH = useRef(0); const prevFirst = useRef(0);
  useEffect(() => {
    const el = boxRef.current; if (!el) return;
    const wasAtBottom = prevH.current === 0 || prevH.current - el.scrollTop - el.clientHeight < 60;
    if (wasAtBottom) el.scrollTo({ top: el.scrollHeight });
    else {
      atBottomRef.current = false; setAtBottom(false);
      const first = ordered[0]?.seq ?? 0;
      if (prevFirst.current && first && first < prevFirst.current) el.scrollTop += el.scrollHeight - prevH.current;
    }
    prevFirst.current = ordered[0]?.seq ?? 0; prevH.current = el.scrollHeight;
  }, [segs]); // eslint-disable-line

  async function loadOlder() {
    const first = ordered[0]?.seq; if (!first || first <= 1) return;
    const r = await fetch(`${API}/sessions/${sidRef.current}/transcripts?language=${lang}&before_seq=${first}&limit=50`, { headers: { "X-Token": tokenRef.current } });
    if (r.ok) merge((await r.json()).segments, false);
  }
  function onScroll() {
    const el = boxRef.current!;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    atBottomRef.current = nearBottom; setAtBottom(nearBottom);
    if (nearBottom) setUnseen(0);
    if (el.scrollTop < 40) loadOlder();
  }
  const backToLive = () => {
    const el = boxRef.current; if (!el) return;
    atBottomRef.current = true; setAtBottom(true); setUnseen(0); el.scrollTo({ top: el.scrollHeight });
  };

  function togglePlay() {
    if (!("speechSynthesis" in window)) return alert(t("Seu navegador não suporta voz. Use o modo texto."));
    if (playing) { window.speechSynthesis.cancel(); setSpeaking(false); setPlaying(false); }
    else {
      setPlaying(true); speak(" ");  // gesto do usuário libera o áudio no navegador/celular
      if (!actx.current) {            // contexto de áudio criado NO toque (exigência do iPhone/Chrome)
        const AC = window.AudioContext || (window as any).webkitAudioContext;
        actx.current = new AC(); gain.current = actx.current!.createGain(); gain.current.gain.value = volRef.current; gain.current.connect(actx.current!.destination);
      }
      actx.current?.resume();
      nextAt.current = 0;
    }
  }
  const chooseMode = (m: Mode) => {
    setMode(m); try { localStorage.setItem("sv_mode", m); } catch {}
    if (m === "text" && playing) togglePlay();
    if (m !== "text" && !playing) togglePlay();
  };
  const pick = (c: string) => { setLang(c); setStatus(""); try { localStorage.setItem("sv_lang", c); } catch {} };

  if (!info) return <div className="auth-wrap">{status ? t(status) : t("Carregando…")}</div>;
  if (info.private && !ready) return (
    <div className="auth-wrap"><form className="card" style={{ maxWidth: 380, width: "100%" }} onSubmit={(e) => { e.preventDefault(); setPwErr(""); enter(pw); }}>
      <h2 style={{ marginTop: 0 }}>{info.title}</h2><p className="muted">{info.organization} · {t("Evento privado")}</p>
      <label>{t("Senha do evento")}</label><input type="password" required autoFocus value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="off" />
      {pwErr && <div className="err" style={{ margin: "10px 0 0" }}>{t(pwErr)}</div>}
      <button className="btn btn-primary" style={{ width: "100%", marginTop: 14 }}>{t("Entrar")}</button>
      <p className="fine">{t("Peça a senha a quem organizou o evento.")}</p>
    </form></div>
  );
  const showText = mode !== "audio";
  const stateBadge = live ? <span className="badge badge-live">{t("AO VIVO")}</span>
    : <span className="badge on-dark">{info.status === "ENDED" ? t("Encerrado") : t("Aguardando início")}</span>;
  return (
    <div className="listen">
      {/* Faixa de título: contexto do evento sempre visível (quem, o quê, em que idioma) */}
      <header className="l-hero">
        <div className="l-hero-in">
          <div className="l-nav">
            <BackButton className="on-dark" fallback={info.organization_slug ? `/o/${info.organization_slug}` : "/buscar"} />
            <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
              <button className="chip on-dark-chip" onClick={() => setAbout(true)} aria-haspopup="dialog"><Icon name="building" small /> <span>{t("Sobre")}</span></button>
              <LanguagePicker languages={langs} value={lang} onChange={pick} />
            </div>
          </div>
          <div className="l-meta">
            <div className="l-org"><OrgLogo name={info.organization} url={info.branding?.logo_url} size={30} />{info.organization}</div>
            <h1>{info.title}</h1>
            <div className="l-sub">
              {stateBadge}
              {info.presenter && <span><Icon name="mic" small /> {info.presenter}</span>}
              {info.theme && <span>{info.theme}</span>}
              <span><Icon name="calendar" small /> {new Date(info.starts_at).toLocaleDateString(uiLang, { day: "numeric", month: "short", year: "numeric" })}</span>
            </div>
          </div>
        </div>
      </header>
      {about && (
        <div className="modal-bg" onClick={() => setAbout(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label={t("Sobre a organização")} onClick={(e) => e.stopPropagation()}>
            <div className="modal-h">
              <OrgLogo name={info.organization} url={info.branding?.logo_url} size={44} />
              <h3>{info.organization}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setAbout(false)} aria-label={t("Fechar")}><Icon name="x" small /></button>
            </div>
            <div style={{ padding: "16px 18px 20px", overflowY: "auto" }}>
              {info.contact && Object.keys(info.contact).filter((k) => k !== "links").length > 0
                ? <OrgContact contact={info.contact} />
                : <p className="muted" style={{ margin: 0 }}>{t("A organização ainda não preencheu os dados públicos.")}</p>}
              <div className="row" style={{ marginTop: 16, gap: 10 }}><span className="fine">{t("Idioma da tela")}</span><LangSwitch /></div>
              {info.organization_slug && <a className="btn btn-primary btn-sm" style={{ marginTop: 16 }} href={`/o/${info.organization_slug}`}>{t("Ver todos os eventos")} <Icon name="arrow" small /></a>}
            </div>
          </div>
        </div>
      )}
      {langs.length > 0 && !lang && (
        <div className="modal-bg" role="dialog" aria-modal="true" aria-label={t("Em qual idioma você quer ouvir?")}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-h"><h3>{t("Em qual idioma você quer ouvir?")}</h3></div>
            <p className="fine" style={{ margin: "0 16px" }}>{t("Vamos lembrar da sua escolha neste aparelho. Você pode trocar quando quiser no botão de idioma, no topo.")}</p>
            <div style={{ padding: "12px 12px 4px" }}>
              <input value={askLang} onChange={(e) => setAskLang(e.target.value)} placeholder={t("Buscar idioma…")} aria-label={t("Buscar idioma…")} autoFocus />
            </div>
            <div className="modal-list" role="listbox">
              {langs.map((l) => ({ ...l, name: langName(l.code, uiLang) }))
                .sort((a, b) => a.name.localeCompare(b.name, uiLang))
                .filter((l) => !askLang.trim() || l.name.toLowerCase().includes(askLang.toLowerCase()) || l.code.toLowerCase().startsWith(askLang.toLowerCase()))
                .map((l) => (
                  <button key={l.code} role="option" aria-selected={false} className="lang-row" onClick={() => pick(l.code)}>
                    {l.name}
                    {l.speech && <span title={t("Voz")}><Icon name="volume" /></span>}
                    {l.text && <span title={t("Texto")}><Icon name="text" /></span>}
                    <span className="code">{l.code}</span>
                  </button>
                ))}
            </div>
          </div>
        </div>
      )}
      {live && lang && mode !== "text" && !playing && (
        <div className="status-bar" role="alert" style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "center", flexWrap: "wrap", background: "#0b57d0", color: "#fff" }}>
          <span><b>{t("Áudio em transmissão!")}</b> {t("Toque no botão Play para ouvir a tradução.")}</span>
          <button className="btn btn-sm" style={{ background: "#fff", color: "#0b57d0" }} onClick={togglePlay}><Icon name="play" small /> {t("Ouvir agora")}</button>
        </div>
      )}
      {!langs.length && <div className="status-bar" role="status">{t("Tradução indisponível no momento.")}</div>}
      {status && <div className="status-bar" role="status">{t(status)}</div>}
      {showText ? (
        <div className="transcript" ref={boxRef} onScroll={onScroll}>
          <div className="paper">
            {!ordered.length && (
              <div className="empty"><Icon name="radio" /><b>{live ? t("Aguardando a fala…") : t("A transcrição aparece aqui quando o evento começar.")}</b></div>
            )}
            {ordered.map((s) => <p key={s.seq} className={`seg ${s.final ? "" : "prov"}`}>{s.text}</p>)}
          </div>
          {!atBottom && <button className="btn btn-dark btn-sm to-live" onClick={backToLive}><Icon name="chevron" small /> {t("Voltar ao vivo")}{unseen ? ` (${unseen})` : ""}</button>}
        </div>
      ) : (
        <div className="transcript audio-only">
          <div className={`orb ${playing && speaking ? "on" : ""}`}><Icon name="headphones" /></div>
          <b>{playing ? t("Tocando a tradução em voz") : t("Toque ▶ para ouvir a tradução")}</b>
        </div>
      )}
      <div className="l-dock">
        {books.length > 0 && <div className="l-docs"><Icon name="doc" small /> <span>{t("Documento")}:</span> {books.map((b) => <a key={b.id} href={`${API}/public/booklets/${code}/${b.id}/pdf`}>{b.title}</a>)}</div>}
        <div className="l-player" role="group" aria-label={t("Player de áudio da tradução")}>
          <button className="round big" onClick={togglePlay} aria-pressed={playing} aria-label={playing ? t("Pausar áudio") : t("Ouvir tradução")}><Icon name={playing ? "pause" : "play"} /></button>
          <div className="grow">
            <div className={`eq ${playing && speaking ? "on" : ""}`} aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /></div>
            <Icon name="volume" small />
            <input type="range" min={0} max={1} step={0.05} value={vol} style={{ width: 90 }} onChange={(e) => setVol(+e.target.value)} aria-label={t("Volume")} />
          </div>
          <div className="seg-control" role="radiogroup" aria-label={t("Modo")}>
            {([["both", t("Áudio + texto")], ["audio", t("Só áudio")], ["text", t("Só texto")]] as [Mode, string][]).map(([m, label]) => (
              <button key={m} role="radio" aria-checked={mode === m} onClick={() => chooseMode(m)}>{label}</button>
            ))}
          </div>
          <span className={`conn ${conn}`} aria-live="polite"><i />{conn === "online" ? t("conectado") : conn === "connecting" ? t("conectando…") : t("reconectando…")}</span>
        </div>
      </div>
    </div>
  );
}

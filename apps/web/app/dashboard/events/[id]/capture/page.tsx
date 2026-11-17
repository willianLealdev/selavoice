"use client";
/**
 * Captura de áudio pelo NAVEGADOR — funciona em computador e em CELULAR (Chrome/Safari).
 * Aceita qualquer entrada de áudio que o aparelho enxergue: microfone do celular/notebook, interface USB,
 * mesa de som digital (X32, Yamaha, Allen&Heath…), placa de captura, etc. A fonte NÃO importa.
 *
 * Como funciona: pede permissão do microfone, converte para PCM 16-bit mono 16 kHz em quadros de 20 ms e envia por
 * WebSocket seguro (/sessions/{id}/ingest) usando um token efêmero. Reconecta sozinho se a rede cair.
 * Requer HTTPS em produção (navegadores só liberam microfone em HTTPS ou localhost).
 * RUÍDO: com microfone de sala/celular ligamos a supressão de ruído, eco e ganho do navegador (padrão da organização, ajustável aqui);
 * com mesa de som (linha limpa) deixe desligado. Além disso o SERVIDOR filtra tudo que não é a voz mais alta (ver audio_gate.py)
 * e o botão "Calibrar" ensina ao sistema o volume do palestrante antes do evento.
 */
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { WS, api } from "@/lib/api";
import { useT } from "@/lib/i18n";

const RATE = 16000, FRAME = 320; // 20 ms a 16 kHz

export default function Capture({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
  const [ev, setEv] = useState<any>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [running, setRunning] = useState(false);
  const [level, setLevel] = useState(0);
  const [net, setNet] = useState("parado");
  const [diag, setDiag] = useState<any>(null);
  const [err, setErr] = useState("");
  const [ns, setNs] = useState(true);              // supressão de ruído/eco/ganho do navegador
  const [cal, setCal] = useState(0);              // segundos restantes da calibração
  const ref = useRef<{ stop: () => void } | null>(null);

  useEffect(() => { api(`/events/${id}`).then(setEv).catch((e) => setErr(e.message)); api("/organizations/me").then((o: any) => setNs(o.audio?.noise_suppression !== false)).catch(() => {}); return () => ref.current?.stop(); }, [id]);
  useEffect(() => { if (cal <= 0) return; const h = setTimeout(() => setCal(cal - 1), 1000); return () => clearTimeout(h); }, [cal]);
  async function calibrate() { try { await api(`/sessions/${sid}/audio-calibrate`, { method: "POST" }); setCal(5); setErr(""); } catch (e: any) { setErr(e.message); } }
  const sid = ev?.sessions?.[0]?.id;

  async function listDevices() {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true }); // pede permissão para ver os nomes
      s.getTracks().forEach((t) => t.stop());
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput"));
    } catch { setErr(t("Permissão de microfone negada ou indisponível (use HTTPS).")); }
  }

  async function start() {
    setErr("");
    if (!navigator.mediaDevices?.getUserMedia) return setErr(t("Este navegador não permite captura de áudio (precisa de HTTPS)."));
    let stopped = false, ws: WebSocket | null = null, retry = 0, wake: any = null;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { deviceId: deviceId ? { exact: deviceId } : undefined, channelCount: 1, echoCancellation: ns, noiseSuppression: ns, autoGainControl: ns },
    }).catch((e) => { setErr(t("Não consegui abrir a entrada de áudio:") + " " + e.message); return null; });
    if (!stream) return;
    const ctx = new AudioContext();
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    const mute = ctx.createGain(); mute.gain.value = 0; // não reproduz o áudio capturado (evita microfonia)
    const ratio = ctx.sampleRate / RATE;
    let pending: number[] = [];
    let acc = 0, count = 0, phase = 0; // estado do reamostrador (persiste entre blocos)

    proc.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      let sum = 0; for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      setLevel(Math.min(1, Math.sqrt(sum / input.length) * 4));
      // Reduz a taxa para 16 kHz com média por janela (filtro simples contra aliasing). O estado (acc/count/phase)
      // atravessa os blocos: NADA é descartado entre um bloco e o próximo (descartar causaria "falhas" no áudio).
      for (let i = 0; i < input.length; i++) {
        acc += input[i]; count++; phase += 1;
        if (phase >= ratio) { pending.push(acc / count); acc = 0; count = 0; phase -= ratio; }
      }
      // envia em quadros fixos de 20 ms; o que sobrar fica para o próximo bloco
      while (pending.length >= FRAME) {
        const frame = new Int16Array(FRAME);
        for (let i = 0; i < FRAME; i++) frame[i] = Math.max(-1, Math.min(1, pending[i])) * 0x7fff;
        pending = pending.slice(FRAME);
        if (ws?.readyState === 1) ws.send(frame.buffer);
      }
    };
    src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);

    const connect = async () => {
      if (stopped) return;
      setNet("conectando…");
      try {
        const { token } = await api(`/events/sessions/${sid}/audio-token`);
        ws = new WebSocket(`${WS}/sessions/${sid}/ingest`);
        ws.onopen = () => ws!.send(JSON.stringify({ token }));
        ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.type === "ready") { setNet("enviando ●"); retry = 0; } };
        ws.onclose = (c) => {
          if (stopped) return;
          if (c.code === 4409) { setNet("evento não está AO VIVO"); setErr("Inicie o evento antes de transmitir."); return; }
          setNet("reconectando…"); setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000));
        };
      } catch { setNet("reconectando…"); setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000)); }
    };
    connect();
    try { wake = await (navigator as any).wakeLock?.request("screen"); } catch {} // mantém a tela do celular acesa
    const poll = setInterval(() => api(`/sessions/${sid}/ingest-status`).then(setDiag).catch(() => {}), 3000);

    ref.current = { stop: () => {
      stopped = true; clearInterval(poll); ws?.close(); proc.disconnect(); src.disconnect(); mute.disconnect();
      stream.getTracks().forEach((t) => t.stop()); ctx.close(); wake?.release?.(); setRunning(false); setNet("parado"); setLevel(0);
    } };
    setRunning(true);
  }

  return (
    <>
      <Link href={`/dashboard/events/${id}`} className="fine row" style={{ gap: 6 }}><Icon name="back" small /> {t("Voltar ao evento")}</Link>
      <div className="page-h" style={{ marginTop: 16 }}><h1>{t("Capturar áudio")}</h1></div>
      <p className="fine">{t("Use o microfone do celular, do notebook ou qualquer entrada: mesa de som (de qualquer marca), interface USB, placa de captura. O sistema aceita qualquer fonte de áudio.")}</p>
      {err && <div className="err">{t(err)}</div>}
      {ev && ev.status !== "LIVE" && <div className="err">{t("O evento ainda não está ao vivo. Clique em Iniciar na página do evento antes de transmitir.")}</div>}
      <div className="card">
        <label htmlFor="dev">{t("Entrada de áudio")}</label>
        <div className="row">
          <select id="dev" style={{ maxWidth: 420 }} value={deviceId} onChange={(e) => setDeviceId(e.target.value)} disabled={running}>
            <option value="">{t("Padrão do aparelho")}</option>
            {devices.map((d) => <option key={d.deviceId} value={d.deviceId}>{d.label || d.deviceId.slice(0, 8)}</option>)}
          </select>
          <button className="btn btn-ghost btn-sm" onClick={listDevices} disabled={running}>{t("Listar entradas")}</button>
        </div>
        <label className="pf-check" style={{ marginTop: 14 }}><input type="checkbox" checked={ns} disabled={running} onChange={(e) => setNs(e.target.checked)} /> {t("Reduzir ruído do ambiente (microfone de sala ou celular)")}</label>
        <p className="fine" style={{ marginTop: -6 }}>{t("Desligue se o áudio vem limpo de uma mesa de som.")}</p>
        <div style={{ margin: "18px 0", height: 16, background: "#e1e8f5", borderRadius: 8, overflow: "hidden" }} aria-label={t("Nível do áudio")}>
          <div style={{ width: `${level * 100}%`, height: "100%", background: level > 0.9 ? "var(--bad)" : "var(--ok)", transition: "width .08s" }} />
        </div>
        <div className="row">
          {!running ? <button className="btn btn-primary" disabled={!sid || ev?.status !== "LIVE"} onClick={start}><Icon name="mic" small /> {t("Começar a transmitir")}</button>
                    : <button className="btn btn-danger" onClick={() => ref.current?.stop()}>{t("Parar")}</button>}
          <span className="fine">{t("Conexão")}: {t(net)}</span>
        </div>
        {running && (
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn btn-ghost btn-sm" disabled={cal > 0} onClick={calibrate}><Icon name="mic" small /> {cal > 0 ? `${t("Fale normalmente")}… ${cal}s` : t("Calibrar voz do palestrante")}</button>
            <span className="fine">{t("Antes de começar: o palestrante fala por 5 segundos e o sistema aprende o volume dele, para ignorar conversas ao redor.")}</span>
          </div>
        )}
        {diag?.filter && (
          <p className="fine">{t("Filtro de voz")}: <b>{t(({ off: "desligado", normal: "normal", strong: "forte" } as Record<string, string>)[diag.filter.mode] ?? diag.filter.mode)}</b> · {diag.filter.dropped_pct}% {t("do áudio descartado (ruído e silêncio)")} · {diag.filter.calibrated ? t("calibrado") : t("aprendendo a voz")}</p>
        )}
        {diag?.receiving !== undefined && (
          <p className="fine">{t("Servidor")}: {diag.receiving ? `${t("recebendo áudio")} (${diag.avg_kbps} kbps)` : t("aguardando áudio")}</p>
        )}
        <p className="fine">{t("No celular: mantenha esta página aberta e a tela ligada. O nível deve oscilar no verde ao falar; vermelho = sinal alto demais (reduza o ganho).")}</p>
      </div>
    </>
  );
}

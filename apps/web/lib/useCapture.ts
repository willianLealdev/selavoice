"use client";
/**
 * CAPTURA DE ÁUDIO NA TELA DO EVENTO (computador ou celular; qualquer entrada: microfone, mesa de som, interface USB).
 *
 * Duas etapas separadas, para o organizador configurar ANTES de iniciar o evento:
 *   1) openMic(): abre o microfone e mostra o nível (nada é enviado ao servidor ainda). Quando abrir, "micReady" = true
 *      e o botão Iniciar do evento é liberado.
 *   2) startSending(sid): liga o envio ao servidor (WebSocket /sessions/{id}/ingest, PCM16 mono 16 kHz, quadros de 20 ms).
 *      É chamado logo depois de o evento ficar AO VIVO, então a tradução começa no mesmo clique em "Iniciar".
 * Reconecta sozinho se a rede cair. Requer HTTPS (navegadores só liberam microfone em HTTPS ou localhost).
 * RUÍDO: com microfone de sala/celular a supressão de ruído/eco/ganho do navegador fica ligada (padrão da organização);
 * com mesa de som (linha limpa) deixe desligada. O servidor ainda filtra o que não é a voz mais alta (audio_gate.py).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { WS, api } from "@/lib/api";

const RATE = 16000, FRAME = 320; // 20 ms a 16 kHz

export function useCapture() {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [ns, setNs] = useState(true);
  const [level, setLevel] = useState(0);
  const [micReady, setMicReady] = useState(false);
  const [sending, setSending] = useState(false);
  const [net, setNet] = useState("parado");
  const [diag, setDiag] = useState<any>(null);
  const [cal, setCal] = useState(0);
  const [err, setErr] = useState("");
  const eng = useRef<{ ctx?: AudioContext; stream?: MediaStream; proc?: ScriptProcessorNode; src?: MediaStreamAudioSourceNode; mute?: GainNode; wake?: any }>({});
  const net_ = useRef<{ ws: WebSocket | null; stopped: boolean; retry: number; sid: string; poll?: any }>({ ws: null, stopped: true, retry: 0, sid: "" });
  const sendingRef = useRef(false);

  // padrão de ruído vem da organização (Perfil > Áudio e ruído)
  useEffect(() => { api("/organizations/me").then((o: any) => setNs(o.audio?.noise_suppression !== false)).catch(() => {}); }, []);
  useEffect(() => { if (cal <= 0) return; const h = setTimeout(() => setCal(cal - 1), 1000); return () => clearTimeout(h); }, [cal]);

  const listDevices = useCallback(async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true }); // pede permissão para ver os nomes
      s.getTracks().forEach((t) => t.stop());
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput"));
    } catch { setErr("Permissão de microfone negada ou indisponível (use HTTPS)."); }
  }, []);

  /** Etapa 1: abre o microfone (mede o nível, não envia nada). */
  const openMic = useCallback(async () => {
    setErr("");
    if (eng.current.stream) return;
    if (!navigator.mediaDevices?.getUserMedia) { setErr("Este navegador não permite captura de áudio (precisa de HTTPS)."); return; }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { deviceId: deviceId ? { exact: deviceId } : undefined, channelCount: 1, echoCancellation: ns, noiseSuppression: ns, autoGainControl: ns },
      });
    } catch (e: any) { setErr("Não consegui abrir a entrada de áudio: " + e.message); return; }
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
      if (!sendingRef.current) { pending = []; acc = 0; count = 0; return; } // antes de iniciar só medimos o nível
      // Reduz a taxa para 16 kHz com média por janela. O estado atravessa os blocos: nada é descartado entre eles.
      for (let i = 0; i < input.length; i++) {
        acc += input[i]; count++; phase += 1;
        if (phase >= ratio) { pending.push(acc / count); acc = 0; count = 0; phase -= ratio; }
      }
      while (pending.length >= FRAME) {
        const frame = new Int16Array(FRAME);
        for (let i = 0; i < FRAME; i++) frame[i] = Math.max(-1, Math.min(1, pending[i])) * 0x7fff;
        pending = pending.slice(FRAME);
        const ws = net_.current.ws;
        if (ws?.readyState === 1) ws.send(frame.buffer);
      }
    };
    src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);
    let wake: any = null;
    try { wake = await (navigator as any).wakeLock?.request("screen"); } catch {} // mantém a tela do celular acesa
    eng.current = { ctx, stream, proc, src, mute, wake };
    setMicReady(true);
  }, [deviceId, ns]);

  /** Etapa 2: envia o áudio ao servidor (o evento já deve estar AO VIVO). */
  const startSending = useCallback((sid: string) => {
    const n = net_.current;
    if (!sid || (sendingRef.current && !n.stopped)) return;
    n.sid = sid; n.stopped = false; n.retry = 0;
    sendingRef.current = true; setSending(true);
    const connect = async () => {
      if (n.stopped) return;
      setNet("conectando…");
      try {
        const { token } = await api(`/events/sessions/${sid}/audio-token`);
        const ws = new WebSocket(`${WS}/sessions/${sid}/ingest`);
        n.ws = ws;
        ws.onopen = () => ws.send(JSON.stringify({ token }));
        ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.type === "ready") { setNet("enviando ●"); n.retry = 0; } };
        ws.onclose = (c) => {
          if (n.stopped) return;
          if (c.code === 4409) { setNet("evento não está AO VIVO"); return; }
          setNet("reconectando…"); setTimeout(connect, Math.min(1000 * 2 ** n.retry++, 15000));
        };
      } catch { setNet("reconectando…"); setTimeout(connect, Math.min(1000 * 2 ** n.retry++, 15000)); }
    };
    connect();
    n.poll = setInterval(() => api(`/sessions/${sid}/ingest-status`).then(setDiag).catch(() => {}), 3000);
  }, []);

  /** Para só o envio (o microfone continua aberto e medindo). */
  const stopSending = useCallback(() => {
    const n = net_.current;
    n.stopped = true; clearInterval(n.poll); n.ws?.close(); n.ws = null;
    sendingRef.current = false; setSending(false); setNet("parado");
  }, []);

  /** Fecha tudo: envio e microfone. */
  const stopAll = useCallback(() => {
    stopSending();
    const e = eng.current;
    try { e.proc?.disconnect(); e.src?.disconnect(); e.mute?.disconnect(); } catch {}
    e.stream?.getTracks().forEach((t) => t.stop()); e.ctx?.close().catch(() => {}); e.wake?.release?.();
    eng.current = {}; setMicReady(false); setLevel(0);
  }, [stopSending]);

  useEffect(() => () => { stopAll(); }, [stopAll]);

  const calibrate = useCallback(async (sid: string) => {
    try { await api(`/sessions/${sid}/audio-calibrate`, { method: "POST" }); setCal(5); setErr(""); } catch (e: any) { setErr(e.message); }
  }, []);

  return { devices, deviceId, setDeviceId, ns, setNs, level, micReady, sending, net, diag, cal, err, setErr, listDevices, openMic, startSending, stopSending, stopAll, calibrate };
}

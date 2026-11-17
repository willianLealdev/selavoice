"use client";
/**
 * Mockup do que o ouvinte vê E ouve: voz da tradução + transcrição acumulada.
 * É uma demonstração local: o botão de som usa a voz do próprio navegador só para ilustrar (nada vai a servidores).
 * O texto de exemplo é de um evento genérico (conferência), não de um segmento específico.
 */
import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { useT } from "@/lib/i18n";

const LINES = [
  "Welcome, everyone, to the opening session of this year's conference.",
  "Today we will cover three topics: growth, partnerships and the road ahead.",
  "Please take a moment to find your seat and silence your phones.",
  "Our first speaker joins us all the way from São Paulo.",
  "Questions are welcome at the end of each talk.",
];

export default function LiveDemo() {
  const t = useT();
  const [n, setN] = useState(1);
  const [typing, setTyping] = useState("");
  const [sound, setSound] = useState(false);
  const [vol, setVol] = useState(0.8);
  const soundRef = useRef(false); const volRef = useRef(0.8);
  soundRef.current = sound; volRef.current = vol;

  useEffect(() => {
    const full = LINES[n % LINES.length];
    if (soundRef.current && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(full); u.lang = "en-US"; u.volume = volRef.current; u.rate = 0.95;
      window.speechSynthesis.speak(u);
    }
    let i = 0;
    const timer = setInterval(() => {
      i += 3; setTyping(full.slice(0, i));
      if (i >= full.length) { clearInterval(timer); setTimeout(() => setN((x) => x + 1), 1800); }
    }, 60);
    return () => clearInterval(timer);
  }, [n]);
  useEffect(() => () => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); }, []);

  const done = Array.from({ length: Math.min(n - 1, 2) }, (_, k) => LINES[(n - 1 - k + LINES.length * 4) % LINES.length]).reverse();
  return (
    <div className="mock" role="img" aria-label={t("Demonstração: voz e transcrição ao vivo")}>
      <div className="mock-bar"><i /><i /><i /></div>
      <div className="mock-head">
        <div><b>{t("Conferência Global 2026")}</b><span className="s">Acme Events</span></div>
        <div className="row" style={{ gap: 8 }}><span className="chip"><Icon name="globe" small /> English</span><span className="badge badge-live">{t("AO VIVO")}</span></div>
      </div>
      <div className="mock-body">
        {done.map((l, i) => <div key={n + "-" + i} className="mock-line">{l}</div>)}
        <div className="mock-line prov">{typing}</div>
      </div>
      <div className="mock-player">
        <button className="round" onClick={() => { setSound(!sound); if (sound && "speechSynthesis" in window) window.speechSynthesis.cancel(); }}
          aria-pressed={sound} aria-label={sound ? t("Desligar som") : t("Ouvir demonstração")}><Icon name={sound ? "pause" : "play"} /></button>
        <div className={`eq ${sound ? "on" : ""}`} aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /></div>
        <Icon name="volume" small />
        <input type="range" min={0} max={1} step={0.05} value={vol} style={{ width: 84 }} onChange={(e) => setVol(+e.target.value)} aria-label={t("Volume")} />
      </div>
    </div>
  );
}

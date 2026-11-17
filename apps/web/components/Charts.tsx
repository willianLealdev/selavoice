"use client";
/**
 * Gráficos leves em SVG puro (sem biblioteca): linhas/área com dica ao passar o mouse, barras horizontais.
 * Cores vêm dos tokens do design system (var(--...)) para funcionar igual no claro/escuro.
 */
import { useState } from "react";

export type Series = { name: string; color: string; values: number[]; fmt?: (n: number) => string; area?: boolean };

/** Gráfico de linhas com eixo X por data. Cada série tem a própria escala (receita e minutos têm unidades diferentes). */
export function LineChart({ labels, series, height = 220 }: { labels: string[]; series: Series[]; height?: number }) {
  const W = 720, H = height, P = { l: 8, r: 8, t: 14, b: 26 };
  const [hover, setHover] = useState<number | null>(null);
  const n = labels.length;
  const x = (i: number) => P.l + (n <= 1 ? 0 : (i * (W - P.l - P.r)) / (n - 1));
  const scaled = series.map((s) => {
    const max = Math.max(...s.values, 0.0001);
    return { ...s, y: (v: number) => P.t + (H - P.t - P.b) * (1 - v / max), max };
  });
  const path = (s: (typeof scaled)[number]) => s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${s.y(v).toFixed(1)}`).join(" ");
  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => P.t + (H - P.t - P.b) * f);
  const ticks = n > 1 ? [0, Math.floor((n - 1) / 3), Math.floor(((n - 1) * 2) / 3), n - 1] : [0];
  const short = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
  return (
    <div className="chart" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="gráfico" preserveAspectRatio="none"
        onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; setHover(Math.max(0, Math.min(n - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (n - 1))))); }}>
        {grid.map((g, i) => <line key={i} x1={P.l} x2={W - P.r} y1={g} y2={g} stroke="var(--line)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
        {scaled.map((s) => (
          <g key={s.name}>
            {s.area && <path d={`${path(s)} L${x(n - 1)},${H - P.b} L${x(0)},${H - P.b} Z`} fill={s.color} opacity=".1" />}
            <path d={path(s)} fill="none" stroke={s.color} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          </g>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="var(--faint)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
        {hover !== null && scaled.map((s) => <circle key={s.name} cx={x(hover)} cy={s.y(s.values[hover])} r="4" fill="#fff" stroke={s.color} strokeWidth="2" vectorEffect="non-scaling-stroke" />)}
        {ticks.map((i) => <text key={i} x={x(i)} y={H - 6} fontSize="11" fill="var(--faint)" textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}>{short(labels[i])}</text>)}
      </svg>
      {hover !== null && (
        <div className="chart-tip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <b>{labels[hover].split("-").reverse().join("/")}</b>
          {series.map((s) => <div key={s.name}><i style={{ background: s.color }} />{s.name}: <b>{(s.fmt ?? String)(s.values[hover])}</b></div>)}
        </div>
      )}
      <div className="chart-legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
    </div>
  );
}

/** Barras horizontais com valor à direita (ranking). */
export function BarList({ rows, color = "var(--brand)", empty }: { rows: { label: string; value: number; text: string; sub?: string }[]; color?: string; empty?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 0.0001);
  if (!rows.length) return <p className="fine" style={{ margin: 0 }}>{empty}</p>;
  return (
    <div className="barlist">
      {rows.map((r) => (
        <div key={r.label} className="bl-row">
          <div className="bl-top"><span className="bl-label">{r.label}</span><b>{r.text}</b></div>
          <div className="bl-track"><div className="bl-fill" style={{ width: `${Math.max(2, (r.value / max) * 100)}%`, background: color }} /></div>
          {r.sub && <span className="fine">{r.sub}</span>}
        </div>
      ))}
    </div>
  );
}

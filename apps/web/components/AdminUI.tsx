"use client";
/** Peças visuais do Super Admin: cartão de indicador (KPI), cabeçalho de página e formatadores. */
import Icon from "./Icon";

export const usd = (n: number, d = 2) => `US$ ${n.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
export const num = (n: number) => n.toLocaleString("pt-BR");

export function Kpi({ icon, label, value, sub, tone }: { icon: string; label: string; value: string; sub?: string; tone?: "ok" | "warn" | "live" | "brand" }) {
  return (
    <div className={`kpi-card ${tone ?? ""}`}>
      <div className="kpi-ic"><Icon name={icon} /></div>
      <div className="kpi-body">
        <span className="kpi-label">{label}</span>
        <b className="kpi-value">{value}</b>
        {sub && <span className="kpi-sub">{sub}</span>}
      </div>
    </div>
  );
}

export function Panel({ title, hint, right, children }: { title: string; hint?: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <header className="panel-h"><div><h3>{title}</h3>{hint && <p className="fine">{hint}</p>}</div>{right}</header>
      {children}
    </section>
  );
}

export function PageHead({ title, sub, right }: { title: string; sub?: string; right?: React.ReactNode }) {
  return <div className="page-h"><div><h1>{title}</h1>{sub && <p className="muted" style={{ margin: "4px 0 0" }}>{sub}</p>}</div>{right}</div>;
}

export function Period({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="seg-control" role="radiogroup">
      {[7, 30, 90].map((d) => <button key={d} role="radio" aria-checked={value === d} onClick={() => onChange(d)}>{d}d</button>)}
    </div>
  );
}

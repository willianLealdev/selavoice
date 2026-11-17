"use client";
/**
 * Seletor de idioma de TRADUÇÃO. A lista vem da API (/public/languages): são os idiomas que os provedores
 * configurados oferecem — pode ter dezenas. Por isso há busca. Nomes dos idiomas vêm do próprio navegador
 * (Intl.DisplayNames) no idioma da interface, então não há tabela de nomes para manter.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon";
import { useLang, useT } from "@/lib/i18n";

export type Lang = { code: string; text: boolean; speech: boolean };

export function langName(code: string, ui: string): string {
  try {
    const n = new Intl.DisplayNames([ui === "pt" ? "pt-BR" : ui], { type: "language" }).of(code);
    return n ? n.charAt(0).toUpperCase() + n.slice(1) : code;
  } catch { return code; }
}

export default function LanguagePicker({ languages, value, onChange }: { languages: Lang[]; value: string; onChange: (code: string) => void }) {
  const t = useT();
  const { lang: ui } = useLang();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open) { setQ(""); setTimeout(() => ref.current?.focus(), 30); } }, [open]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    if (open) window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);

  const items = useMemo(() => languages.map((l) => ({ ...l, name: langName(l.code, ui) }))
    .sort((a, b) => a.name.localeCompare(b.name, ui)), [languages, ui]);
  const shown = items.filter((l) => !q.trim() || l.name.toLowerCase().includes(q.toLowerCase()) || l.code.toLowerCase().startsWith(q.toLowerCase()));
  const cur = items.find((l) => l.code === value);

  return (
    <>
      <button className="chip" style={{ cursor: "pointer", height: 36 }} onClick={() => setOpen(true)} aria-haspopup="dialog" aria-label={t("Idioma da tradução")} disabled={!items.length}>
        <Icon name="globe" small /> {cur ? cur.name : value || t("Escolher idioma")} <Icon name="chevron" small />
      </button>
      {open && (
        <div className="modal-bg" onClick={() => setOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label={t("Idioma da tradução")} onClick={(e) => e.stopPropagation()}>
            <div className="modal-h">
              <h3>{t("Idioma da tradução")}</h3>
              <span className="fine">{items.length} {t("idiomas")}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)} aria-label={t("Fechar")}><Icon name="x" small /></button>
            </div>
            <div style={{ padding: "12px 12px 4px" }}>
              <input ref={ref} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Buscar idioma…")} aria-label={t("Buscar idioma…")} />
            </div>
            <div className="modal-list" role="listbox">
              {shown.map((l) => (
                <button key={l.code} role="option" aria-selected={l.code === value} className="lang-row" onClick={() => { onChange(l.code); setOpen(false); }}>
                  {l.name}
                  {l.speech && <span title={t("Voz")}><Icon name="volume" /></span>}
                  {l.text && <span title={t("Texto")}><Icon name="text" /></span>}
                  <span className="code">{l.code}</span>
                </button>
              ))}
              {!shown.length && <p className="fine" style={{ padding: 16 }}>{t("Nenhum idioma encontrado.")}</p>}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

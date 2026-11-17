"use client";
/**
 * Internacionalização (pt-BR, en, es) — leve, sem dependências.
 *
 * COMO USAR nas telas:   const t = useT();   ...   {t("Entrar")}   ou   {t("Olá, {nome}", { nome })}
 * A CHAVE é o próprio texto em português; as traduções ficam em lib/dict.ts → [inglês, espanhol].
 * Se faltar tradução, mostra o português (nunca quebra). `npm run i18n:check` lista chaves faltantes.
 *
 * O idioma da interface é guardado no aparelho (localStorage) e, na 1ª visita, segue o idioma do navegador.
 * Atenção: isto é o idioma do SITE. O idioma da TRADUÇÃO que o ouvinte escuta é outra escolha (página do ouvinte).
 */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { DICT } from "./dict";

export type Lang = "pt" | "en" | "es";
export const UI_LANGS: { code: Lang; label: string }[] = [
  { code: "pt", label: "Português" }, { code: "en", label: "English" }, { code: "es", label: "Español" },
];

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "pt", setLang: () => {} });

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setL] = useState<Lang>("pt");
  useEffect(() => {
    let l: Lang | null = null;
    try { l = localStorage.getItem("sv_ui_lang") as Lang | null; } catch {}
    if (!l || !["pt", "en", "es"].includes(l)) {
      const n = (navigator.language || "pt").slice(0, 2);
      l = n === "en" ? "en" : n === "es" ? "es" : "pt";
    }
    setL(l);
  }, []);
  useEffect(() => { document.documentElement.lang = lang === "pt" ? "pt-BR" : lang; }, [lang]);
  const setLang = (l: Lang) => { setL(l); try { localStorage.setItem("sv_ui_lang", l); } catch {} };
  return <Ctx.Provider value={{ lang, setLang }}>{children}</Ctx.Provider>;
}

export const useLang = () => useContext(Ctx);

/** Retorna t(texto_em_português, variáveis?) → texto no idioma atual. */
export function useT() {
  const { lang } = useLang();
  return useCallback((s: string, vars?: Record<string, string | number>) => {
    let out = lang === "pt" ? s : DICT[s]?.[lang === "en" ? 0 : 1] ?? s;
    if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
    return out;
  }, [lang]);
}

/** Seletor de idioma da INTERFACE (pt/en/es). Não confundir com o idioma da tradução. */
export function LangSwitch({ dark = false }: { dark?: boolean }) {
  const { lang, setLang } = useLang();
  return (
    <select aria-label="Language / Idioma" value={lang} onChange={(e) => setLang(e.target.value as Lang)}
      style={{ width: "auto", height: 34, fontSize: ".8125rem", padding: "0 28px 0 10px", borderRadius: 8 }} data-dark={dark ? "1" : undefined}>
      {UI_LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
    </select>
  );
}

"use client";
/**
 * Registro do service worker + botão "Instalar app".
 *  - Android/Chrome/Edge (desktop e celular): usa o evento `beforeinstallprompt` (instala com 1 toque).
 *  - iPhone/iPad (Safari): não existe botão automático; mostramos o passo a passo "Compartilhar -> Adicionar à Tela de Início".
 *  - Já instalado (modo standalone): o botão some.
 * O service worker só guarda a telinha offline e os ícones (ver public/sw.js).
 */
import { useEffect, useState } from "react";
import Icon from "./Icon";
import { useT } from "@/lib/i18n";

type Deferred = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
let deferred: Deferred | null = null; // guardado fora do componente: vários botões na tela usam o mesmo evento
const listeners = new Set<() => void>();

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e as Deferred; listeners.forEach((f) => f()); });
  window.addEventListener("appinstalled", () => { deferred = null; listeners.forEach((f) => f()); });
}

/** Registra o service worker (chamado uma vez no layout). */
export function PwaRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  }, []);
  return null;
}

export default function InstallApp({ className = "btn btn-ghost btn-sm", label }: { className?: string; label?: string }) {
  const t = useT();
  const [, tick] = useState(0);
  const [standalone, setStandalone] = useState(true); // começa escondido até medir (evita piscar)
  const [ios, setIos] = useState(false);
  const [help, setHelp] = useState(false);
  useEffect(() => {
    const f = () => tick((n) => n + 1);
    listeners.add(f);
    const inApp = window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone === true;
    setStandalone(inApp);
    setIos(/iphone|ipad|ipod/i.test(navigator.userAgent) && !(window as any).MSStream);
    return () => { listeners.delete(f); };
  }, []);
  if (standalone) return null;
  async function install() {
    if (deferred) { await deferred.prompt(); await deferred.userChoice.catch(() => {}); deferred = null; tick((n) => n + 1); }
    else setHelp(true); // iPhone ou navegador sem instalação automática: mostra como fazer
  }
  return (
    <>
      <button className={className} onClick={install}><Icon name="download" small /> {label ?? t("Instalar app")}</button>
      {help && (
        <div className="modal-bg" onClick={() => setHelp(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label={t("Instalar app")} onClick={(e) => e.stopPropagation()}>
            <div className="modal-h"><h3>{t("Instalar o SelaVoice")}</h3><button className="btn btn-ghost btn-sm" onClick={() => setHelp(false)} aria-label={t("Fechar")}><Icon name="x" small /></button></div>
            <div style={{ padding: "16px 18px 22px" }}>
              {ios ? (
                <ol className="steps">
                  <li>{t("Toque no botão Compartilhar do Safari (o quadrado com a seta para cima).")}</li>
                  <li>{t("Role e toque em “Adicionar à Tela de Início”.")}</li>
                  <li>{t("Confirme em “Adicionar”. O app aparece na sua tela inicial.")}</li>
                </ol>
              ) : (
                <ol className="steps">
                  <li>{t("Abra o menu do navegador (⋮ ou …).")}</li>
                  <li>{t("Escolha “Instalar app” ou “Adicionar à tela inicial”.")}</li>
                  <li>{t("Se a opção não aparecer, abra o site em HTTPS no Chrome (Android) ou no Safari (iPhone).")}</li>
                </ol>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

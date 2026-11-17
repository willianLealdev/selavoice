"use client";
/**
 * Botão "Voltar" padrão, usado em TODAS as páginas (exceto a inicial).
 * Volta para a página anterior do navegador; se a pessoa chegou direto por link/QR (sem histórico),
 * vai para `fallback`. Assim o botão nunca "não faz nada".
 */
import { useRouter } from "next/navigation";
import Icon from "./Icon";
import { useT } from "@/lib/i18n";

export default function BackButton({ fallback = "/", label, className = "" }: { fallback?: string; label?: string; className?: string }) {
  const t = useT();
  const router = useRouter();
  const go = () => (typeof window !== "undefined" && window.history.length > 1 ? router.back() : router.push(fallback));
  return (
    <button type="button" className={`back ${className}`} onClick={go} aria-label={label ?? t("Voltar")}>
      <Icon name="back" small /> <span>{label ?? t("Voltar")}</span>
    </button>
  );
}

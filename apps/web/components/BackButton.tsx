"use client";
/**
 * Botão "Voltar" padrão, usado em TODAS as páginas (exceto a inicial).
 * Volta para a página anterior do navegador; se a pessoa chegou direto por link/QR (sem histórico),
 * vai para `fallback`. Assim o botão nunca "não faz nada".
 */
import { useRouter } from "next/navigation";
import Icon from "./Icon";
import { useT } from "@/lib/i18n";

/**
 * `always`: SEMPRE vai para `fallback` (usado nas telas de entrada: login, cadastro, esqueci a senha...). Nelas "voltar pelo histórico" não
 * funciona direito: depois de sair da conta o histórico volta ao painel, que manda de novo para o login, e o botão parecia "não ir a lugar nenhum".
 */
export default function BackButton({ fallback = "/", label, className = "", always = false }: { fallback?: string; label?: string; className?: string; always?: boolean }) {
  const t = useT();
  const router = useRouter();
  const go = () => (!always && typeof window !== "undefined" && window.history.length > 1 ? router.back() : router.push(fallback));
  return (
    <button type="button" className={`back ${className}`} onClick={go} aria-label={label ?? t("Voltar")}>
      <Icon name="back" small /> <span>{label ?? t("Voltar")}</span>
    </button>
  );
}

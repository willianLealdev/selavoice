/** Logo da organização; sem logo, mostra a inicial do nome (mesmo visual em toda a plataforma). */
import { API } from "@/lib/api";

export default function OrgLogo({ name, url, size = 28, className = "" }: { name: string; url?: string; size?: number; className?: string }) {
  const r = Math.round(size * 0.28);
  return url ? (
    // fundo branco: logos transparentes/escuros continuam legíveis sobre a faixa escura
    <img src={`${API}${url}`} alt={name} width={size} height={size} className={className} style={{ width: size, height: size, borderRadius: r, background: "#fff", objectFit: "contain", flex: "none", padding: Math.round(size * 0.06) }} />
  ) : (
    <span className={`avatar ${className}`} style={{ width: size, height: size, borderRadius: r, fontSize: size * 0.44 }}>{(name || "?").trim().charAt(0).toUpperCase()}</span>
  );
}

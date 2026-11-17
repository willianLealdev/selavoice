"use client";
/** Moldura do painel da organização: barra lateral + proteção de rota (redireciona se não logado). */
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "@/components/Icon";
import InstallApp from "@/components/InstallApp";
import BackButton from "@/components/BackButton";
import { useSession } from "@/lib/session";
import { LangSwitch, useT } from "@/lib/i18n";

export default function DashLayout({ children }: { children: React.ReactNode }) {
  const t = useT();
  const { me, loading, logout } = useSession();
  const path = usePathname();
  if (loading) return <div className="auth-wrap muted">{t("Carregando…")}</div>;
  if (!me) return null;
  const org = me.memberships[0];
  const item = (href: string, icon: string, label: string) => (
    <Link href={href} className={`nav-i ${path === href || (href !== "/dashboard" && path.startsWith(href)) ? "active" : ""}`}><Icon name={icon} /> {label}</Link>
  );
  return (
    <div className="app">
      <aside className="side">
        <Link href="/dashboard" className="logo"><img src="/logo.webp" alt="SelaVoice" /></Link>
        {item("/dashboard", "calendar", t("Eventos"))}
        {/* Só administradores veem perfil/cobrança/equipe (o servidor também bloqueia: 403). */}
        {org?.role === "TENANT_ADMIN" && <>
          {item("/dashboard/profile", "building", t("Perfil da organização"))}
          {item("/dashboard/billing", "card", t("Plano e uso"))}
          {item("/dashboard/team", "users", t("Equipe"))}
        </>}
        {me.is_super_admin && item("/admin", "shield", "Super Admin")}
        <div className="spacer" style={{ flex: 1 }} />
        <div className="who">
          <div><b>{org ? org.name : t("Sem organização")}</b><span className="fine">{me.email}{org ? ` · ${org.role}` : ""}</span></div>
          <InstallApp className="btn btn-ghost btn-sm" />
          <div className="row" style={{ gap: 8 }}>
            <LangSwitch />
            <button className="btn btn-ghost btn-sm" onClick={logout} aria-label={t("Sair")}><Icon name="logout" small /> {t("Sair")}</button>
          </div>
        </div>
      </aside>
      <main className="main">{path !== "/dashboard" && <div className="back-bar"><BackButton fallback="/dashboard" /></div>}{children}</main>
    </div>
  );
}

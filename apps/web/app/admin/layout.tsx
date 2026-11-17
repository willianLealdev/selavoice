"use client";
/**
 * Moldura do Super Admin: menu lateral + proteção (só Super Admin COM MFA vê o conteúdo).
 * A tela /admin/login fica fora da moldura. O servidor também exige Super Admin + MFA em toda rota /admin/*.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import BackButton from "@/components/BackButton";
import Icon from "@/components/Icon";
import { useSession } from "@/lib/session";
import { LangSwitch, useT } from "@/lib/i18n";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  // /admin/login fica FORA da moldura; ao sair dela a moldura monta do zero e recarrega a sessão (já com MFA).
  const path = usePathname();
  if (path.startsWith("/admin/login")) return <>{children}</>;
  return <Frame>{children}</Frame>;
}

function Frame({ children }: { children: React.ReactNode }) {
  const t = useT();
  const path = usePathname();
  const { me, loading, logout } = useSession({ requireSuper: true });
  if (loading) return <div className="auth-wrap muted">{t("Carregando…")}</div>;
  if (!me?.is_super_admin) return (
    <div className="auth-wrap"><div className="auth-card">
      <div className="back-bar"><BackButton fallback="/dashboard" /></div>
      <h2>{t("Acesso restrito.")}</h2>
      <p className="muted">{t("Esta área é só do Super Admin da plataforma. Sua conta atual é de uma organização.")}</p>
      <div className="row"><a className="btn btn-primary" href="/admin/login">{t("Entrar como Super Admin")}</a><a className="btn btn-ghost" href="/dashboard">{t("Ir para o painel")}</a></div>
    </div></div>
  );
  if (!me.mfa_session) return (
    <div className="auth-wrap"><div className="auth-card">
      <div className="back-bar"><BackButton fallback="/dashboard" /></div>
      <h2>{t("Confirme com MFA")}</h2>
      <p className="muted">{t("Para abrir o Super Admin, entre com e-mail, senha e o código MFA.")}</p>
      <a className="btn btn-primary" href="/admin/login">{t("Entrar como Super Admin")}</a>
    </div></div>
  );
  const item = (href: string, icon: string, label: string) => (
    <Link href={href} className={`nav-i ${path === href || (href !== "/admin" && path.startsWith(href)) ? "active" : ""}`}><Icon name={icon} /> {label}</Link>
  );
  return (
    <div className="app admin">
      <aside className="side">
        <Link href="/admin" className="logo"><img src="/logo.webp" alt="SelaVoice" /></Link>
        <div className="side-sec">{t("Gestão")}</div>
        {item("/admin", "layers", t("Visão geral"))}
        {item("/admin/financeiro", "card", t("Custos e receita"))}
        {item("/admin/acessos", "users", t("Controle de acessos"))}
        {item("/admin/organizacoes", "building", t("Organizações"))}
        <div className="side-sec">{t("Plataforma")}</div>
        {item("/admin/planos", "doc", t("Planos"))}
        {item("/admin/teste-gratis", "check", t("Teste grátis"))}
        {item("/admin/provedores", "zap", t("Provedores de IA"))}
        {item("/admin/integrations", "key", t("Chaves e integrações"))}
        {item("/admin/auditoria", "shield", t("Auditoria"))}
        <div className="spacer" style={{ flex: 1 }} />
        <div className="who">
          <div><b>Super Admin</b><span className="fine">{me.email}</span></div>
          <div className="row" style={{ gap: 8 }}>
            <LangSwitch />
            <button className="btn btn-ghost btn-sm" onClick={logout} aria-label={t("Sair")}><Icon name="logout" small /> {t("Sair")}</button>
          </div>
        </div>
      </aside>
      <main className="main wide">{path !== "/admin" && <div className="back-bar"><BackButton fallback="/admin" /></div>}{children}</main>
    </div>
  );
}

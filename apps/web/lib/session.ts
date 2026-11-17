"use client";
/** Hook de sessão: restaura o login pelo cookie de refresh e carrega /auth/me. */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, refreshSession, setOrg, setToken } from "./api";

export type Me = {
  id: string; email: string; name: string; is_super_admin: boolean; mfa_enabled: boolean; mfa_session: boolean;
  memberships: { tenant_id: string; slug: string; name: string; role: string; branding: any }[];
};

export function useSession(opts: { requireSuper?: boolean } = {}) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      if (!(await refreshSession())) return router.replace(opts.requireSuper ? "/admin/login" : "/login");
      try {
        const m = await api<Me>("/auth/me");
        if (m.memberships[0]) setOrg(m.memberships[0].slug);
        setMe(m);
      } catch {
        router.replace("/login");
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    setToken(null);
    router.replace("/login");
  };
  return { me, loading, logout };
}

/**
 * Cliente da API (navegador).
 *
 * SEGURANÇA:
 *  - O access token (15 min) fica SÓ em memória (variável do módulo) — não vai para localStorage,
 *    então um XSS não consegue roubá-lo de lá.
 *  - O refresh token é cookie httpOnly (o JS nem enxerga); a renovação exige o cabeçalho
 *    X-Requested-With (proteção CSRF).
 *  - Nenhuma chave de provedor (Gemini/Stripe/etc.) existe no front-end.
 */
export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS = API.replace(/^http/, "ws");

let accessToken: string | null = null;
let orgSlug: string | null = null;

export const setOrg = (slug: string | null) => (orgSlug = slug);
export const getToken = () => accessToken;
export const setToken = (t: string | null) => (accessToken = t);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Tenta renovar a sessão pelo cookie httpOnly. Retorna true se conseguiu. */
let inflight: Promise<boolean> | null = null;
export function refreshSession(): Promise<boolean> {
  // "single-flight": chamadas simultâneas (StrictMode, várias abas/requests) compartilham UMA renovação,
  // senão o cookie rotacionado seria reutilizado e o servidor trataria como roubo de token.
  inflight ??= doRefresh().finally(() => { inflight = null; });
  return inflight;
}

async function doRefresh(): Promise<boolean> {
  try {
    const r = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-Requested-With": "selavoice" },
      body: "{}",
    });
    if (!r.ok) return false;
    accessToken = (await r.json()).access_token;
    return true;
  } catch {
    return false;
  }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData; // upload: o navegador define o Content-Type
  const doFetch = () =>
    fetch(`${API}${path}`, {
      ...opts,
      credentials: "include",
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(orgSlug ? { "X-Org-Slug": orgSlug } : {}),
        ...(opts.headers as Record<string, string>),
      },
      body: opts.json !== undefined ? JSON.stringify(opts.json) : opts.body,
    });
  let r = await doFetch();
  if (r.status === 401 && (await refreshSession())) r = await doFetch();
  if (!r.ok) {
    let msg = "Erro inesperado.";
    try {
      const d = await r.json();
      msg = typeof d.detail === "string" ? d.detail : "Dados inválidos.";
    } catch {}
    throw new ApiError(r.status, msg);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export const LANGS: Record<string, string> = {
  en: "English", es: "Español", pt: "Português", fr: "Français", de: "Deutsch", it: "Italiano", zh: "中文", ko: "한국어",
};

export const money = (cents: number, cur = "usd") =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: cur.toUpperCase() }).format(cents / 100);

/** Rótulos (em português, chaves de tradução) dos tipos de organização. */
export const ORG_TYPES: Record<string, string> = {
  corporate: "Empresa", conference: "Organizador de eventos", expo: "Feira ou expo", fair: "Feira ou expo",
  education: "Educação", association: "Associação ou comunidade", church: "Igreja ou templo", other: "Outro",
};

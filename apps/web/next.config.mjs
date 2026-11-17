// Configuração do Next.js + cabeçalhos de segurança (CSP, anti-clickjacking, etc.).
const isDev = process.env.NODE_ENV !== "production";
const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ws = api.replace(/^http/, "ws");

// CSP: só carrega recursos do próprio site; conexões apenas para a nossa API.
// 'unsafe-inline' em script é exigido pelo Next sem nonce; trade-off documentado em docs/DECISIONS.md (ADR-009).
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${api}`,
  `connect-src 'self' ${api} ${ws}${isDev ? " ws://localhost:3000" : ""}`,
  "font-src 'self' data:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  "worker-src 'self'",
  "manifest-src 'self'",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // gera o pacote enxuto usado pelo Dockerfile
  poweredByHeader: false, // não anuncia "X-Powered-By: Next.js"
  reactStrictMode: true,
  async headers() {
    return [
      {
        // O service worker NUNCA pode ficar em cache longo (senão a atualização do app não chega).
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(self), geolocation=(), microphone=(self)" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        ],
      },
    ];
  },
};
export default nextConfig;

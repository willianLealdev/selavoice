/*
 * Service worker do SelaVoice (PWA).
 *
 * O QUE FAZ: guarda uma telinha "sem internet" e os ícones, e a devolve se a pessoa abrir o app sem rede.
 * O QUE NÃO FAZ (de propósito, por segurança e para não mostrar dado velho):
 *   - NÃO guarda respostas da API (login, eventos, transcrição, dados de organização) nem WebSocket;
 *   - NÃO guarda páginas nem os arquivos de código do site (/_next/): o navegador já cuida disso;
 *   - só intercepta GET do próprio site.
 * Para forçar atualização, mude VERSION.
 */
const VERSION = "sv-v1";
const CACHE = `selavoice-${VERSION}`;
const SHELL = ["/offline", "/icons/icon-192.png", "/icons/icon-512.png", "/logo.webp"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("selavoice-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return; // API (outro endereço), POST etc.: direto na rede
  // Navegação (abrir/recarregar uma página): rede primeiro; sem rede => telinha offline.
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline")));
    return;
  }
  // Ícones e logo: cache primeiro (mudam raramente).
  if (url.pathname.startsWith("/icons/") || url.pathname === "/logo.webp") {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return r; })));
  }
});

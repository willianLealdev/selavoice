import type { MetadataRoute } from "next";

/**
 * Manifesto do app instalável (PWA). `display: standalone` abre sem barra do navegador, como app de verdade.
 * `start_url` leva à tela "Ouvinte ou Palestrante". Ícones gerados do símbolo da logo (public/icons).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/app",
    name: "SelaVoice — Tradução em tempo real",
    short_name: "SelaVoice",
    description: "Tradução ao vivo em voz e texto para qualquer evento.",
    start_url: "/app?source=pwa",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f6f8fb",
    theme_color: "#0b1220",
    lang: "pt-BR",
    categories: ["productivity", "business", "utilities"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Ouvir um evento", short_name: "Ouvir", url: "/app", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Painel da organização", short_name: "Painel", url: "/dashboard", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}

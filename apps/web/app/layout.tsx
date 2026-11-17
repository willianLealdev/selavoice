import type { Metadata, Viewport } from "next";
import { PwaRegister } from "@/components/InstallApp";
import { LangProvider } from "@/lib/i18n";
import "./globals.css";

// Fonte Inter em arquivos ESTÁTICOS de peso fixo (400/500/600/700), servidos pelo próprio site (@fontsource/inter): sem chamadas a
// terceiros no navegador e SEM fonte "variável" — alguns Safari/WebKit ignoram o eixo de peso da variável e desenham todo o texto
// no peso mais fino (tudo fica "apagado"). Fontes estáticas aparecem igual em qualquer versão do Safari.
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
import "@fontsource/inter/latin-ext-400.css";
import "@fontsource/inter/latin-ext-600.css";
import "@fontsource/inter/latin-ext-700.css";

export const metadata: Metadata = {
  title: "SelaVoice — Real-time translation · Tradução em tempo real · Traducción en tiempo real",
  description: "Tradução ao vivo, em voz e texto, para conferências, feiras, empresas, escolas e igrejas. Live voice and text translation for any event. Traducción en vivo por voz y texto para cualquier evento.",
  icons: { icon: "/icons/favicon-64.png", apple: "/icons/apple-touch-icon.png" },
  applicationName: "SelaVoice",
  // iPhone: abre em tela cheia quando adicionado à tela inicial
  appleWebApp: { capable: true, title: "SelaVoice", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: "#0b1220",       // cor da barra de status do celular
  width: "device-width", initialScale: 1,
  viewportFit: "cover",        // usa a tela toda (respeita o "notch" via env(safe-area-inset-*))
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body><PwaRegister /><LangProvider>{children}</LangProvider></body>
    </html>
  );
}

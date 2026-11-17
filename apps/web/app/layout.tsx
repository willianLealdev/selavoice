import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { PwaRegister } from "@/components/InstallApp";
import { LangProvider } from "@/lib/i18n";
import "./globals.css";

// Inter é servida pelo próprio site (next/font baixa na compilação): sem chamadas a terceiros no navegador do usuário.
const inter = Inter({ subsets: ["latin", "latin-ext"], variable: "--font-inter", display: "swap" });

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
    <html lang="pt-BR" className={inter.variable}>
      <body><PwaRegister /><LangProvider>{children}</LangProvider></body>
    </html>
  );
}

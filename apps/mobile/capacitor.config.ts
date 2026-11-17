import type { CapacitorConfig } from "@capacitor/cli";

/**
 * CASCO NATIVO DO SELAVOICE (Android e iOS).
 *
 * COMO FUNCIONA: o app das lojas abre o SITE em /app (a tela "Como você quer entrar?"; nunca a landing page).
 * Por isso quase tudo (telas, textos, planos, idiomas, regras) muda publicando o site / mexendo no painel,
 * SEM enviar nova versão para a Apple/Google. Só exige nova versão da loja:
 *   - trocar ícone, nome, permissões ou o endereço do site;
 *   - adicionar recurso nativo novo (ex.: notificação push);
 *   - atualização obrigatória do Android/iOS que peça isso.
 *
 * IDENTIFICADOR DO APP (appId): precisa ser IDÊNTICO ao cadastrado na Apple (Bundle ID) e no Google Play (nome do pacote).
 * Se você cadastrou outro, rode o build com APP_ID=seu.identificador (ou troque o valor padrão abaixo).
 */
const config: CapacitorConfig = {
  appId: process.env.APP_ID ?? "com.selavoice.app",
  appName: "SelaVoice",
  webDir: "www", // só a tela de "sem internet"; o app real vem de server.url
  server: {
    url: process.env.APP_URL ?? "https://selavoice.com/app",
    cleartext: false, // só HTTPS
    androidScheme: "https",
    // O app só navega dentro do nosso site. Links externos abrem no navegador do aparelho.
    allowNavigation: ["selavoice.com", "*.selavoice.com"],
  },
  // O site detecta este texto no navegador interno para esconder compras dentro do app (Apple/Google exigem a compra pela loja deles).
  appendUserAgent: "SelaVoiceApp",
  backgroundColor: "#ffffff",
  ios: { contentInset: "automatic" },
  android: { allowMixedContent: false, webContentsDebuggingEnabled: false },
  plugins: {
    SplashScreen: { launchShowDuration: 1200, backgroundColor: "#ffffff", showSpinner: false },
    StatusBar: { style: "DARK", backgroundColor: "#ffffff" },
  },
};

export default config;

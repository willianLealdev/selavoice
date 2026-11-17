/**
 * SELAVOICE — app do iPhone (Expo). É uma "moldura" que abre o SITE em /app (tela "Como você quer entrar?", nunca a landing).
 * Por isso telas, textos, planos e regras mudam publicando o site/painel, SEM nova versão na App Store.
 *
 * - O navegador interno se identifica como "SelaVoiceApp": o site esconde compras dentro do app (regra da Apple: bens digitais
 *   vendidos no app precisam usar a compra da loja; aqui o cliente contrata pelo site).
 * - Só navega dentro de selavoice.com; links externos abrem no Safari.
 * - Mantém a tela ligada enquanto o app está aberto (quem ouve tradução ao vivo não pode ter a tela apagada).
 */
import { useKeepAwake } from "expo-keep-awake";
import * as Linking from "expo-linking";
import { StatusBar } from "expo-status-bar";
import { useRef, useState } from "react";
import { ActivityIndicator, Pressable, SafeAreaView, StyleSheet, Text, View } from "react-native";
import { WebView as WebViewBase } from "react-native-webview";

// O tipo da biblioteca ainda não combina com o React 19 (só o TypeScript reclama; funciona em execução).
const WebView: any = WebViewBase;

const SITE = "https://selavoice.com";
const START = `${SITE}/app`;
const interno = (u: string) => /^https:\/\/([a-z0-9-]+\.)*selavoice\.com(\/|$|\?|#)/i.test(u) || u === "about:blank";

export default function App() {
  useKeepAwake();
  const web = useRef<any>(null);
  const [erro, setErro] = useState(false);
  const [carregando, setCarregando] = useState(true);

  return (
    <SafeAreaView style={s.tela}>
      <StatusBar style="dark" />
      {erro ? (
        <View style={s.centro}>
          <Text style={s.titulo}>SelaVoice</Text>
          <Text style={s.texto}>Sem conexão com a internet.{"\n"}Conecte-se e tente novamente.</Text>
          <Pressable style={s.botao} onPress={() => { setErro(false); setCarregando(true); web.current?.reload(); }}>
            <Text style={s.botaoTexto}>Tentar de novo</Text>
          </Pressable>
        </View>
      ) : (
        <WebView
          ref={web}
          source={{ uri: START }}
          applicationNameForUserAgent="SelaVoiceApp"
          // câmera (QR) e microfone (palestrante): o iPhone pergunta ao usuário; o texto do pedido está em app.json
          mediaCapturePermissionGrantType="grant"
          allowsInlineMediaPlayback
          mediaPlaybackRequiresUserAction={false}
          allowsBackForwardNavigationGestures
          sharedCookiesEnabled
          pullToRefreshEnabled
          setSupportMultipleWindows={false}
          onShouldStartLoadWithRequest={(r: any) => {
            if (interno(r.url)) return true;
            Linking.openURL(r.url).catch(() => {});   // fora do nosso site: abre no navegador do aparelho
            return false;
          }}
          onLoadEnd={() => setCarregando(false)}
          onError={() => { setErro(true); setCarregando(false); }}
          onHttpError={() => {}}
        />
      )}
      {carregando && !erro && <View style={s.spinner}><ActivityIndicator size="large" color="#0b57d0" /></View>}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  tela: { flex: 1, backgroundColor: "#ffffff" },
  centro: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  titulo: { fontSize: 28, fontWeight: "700", color: "#0b1220", marginBottom: 8 },
  texto: { fontSize: 16, textAlign: "center", color: "#334155" },
  botao: { marginTop: 18, backgroundColor: "#0b57d0", paddingVertical: 12, paddingHorizontal: 22, borderRadius: 10 },
  botaoTexto: { color: "#fff", fontSize: 16 },
  spinner: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, alignItems: "center", justifyContent: "center", pointerEvents: "none" },
});

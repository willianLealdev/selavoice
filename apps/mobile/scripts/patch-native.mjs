// Ajusta os projetos nativos recém-criados por `cap add` (permissões de microfone/câmera, versão do app).
// Uso: node scripts/patch-native.mjs android|ios
// Variáveis: APP_VERSION (ex.: 1.0.0) e BUILD_NUMBER (número inteiro que SOBE a cada envio à loja).
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const alvo = process.argv[2];
const versao = process.env.APP_VERSION ?? "1.0.0";
const build = process.env.BUILD_NUMBER ?? "1";

function editar(arquivo, fn) {
  if (!existsSync(arquivo)) throw new Error(`Arquivo não encontrado: ${arquivo} (rode "cap add ${alvo}" antes)`);
  const antes = readFileSync(arquivo, "utf8");
  const depois = fn(antes);
  if (depois === antes) console.warn(`(sem mudança) ${arquivo}`);
  writeFileSync(arquivo, depois);
  console.log(`ok: ${arquivo}`);
}

if (alvo === "android") {
  // Permissões: o ouvinte não precisa de microfone, mas o palestrante transmite pelo celular e o QR usa a câmera.
  editar("android/app/src/main/AndroidManifest.xml", (s) => {
    const perms = ["android.permission.RECORD_AUDIO", "android.permission.CAMERA", "android.permission.MODIFY_AUDIO_SETTINGS"];
    let out = s;
    for (const p of perms) {
      if (!out.includes(p)) out = out.replace("<application", `<uses-permission android:name="${p}" />\n    <application`);
    }
    if (!out.includes("android.hardware.camera")) {
      out = out.replace("<application", '<uses-feature android:name="android.hardware.camera" android:required="false" />\n    <application');
    }
    return out;
  });
  // versionCode precisa SUBIR a cada envio ao Google Play; versionName é o número que o usuário vê.
  editar("android/app/build.gradle", (s) =>
    s.replace(/versionCode\s+\d+/, `versionCode ${parseInt(build, 10)}`).replace(/versionName\s+"[^"]*"/, `versionName "${versao}"`),
  );
  // ASSINATURA: o Codemagic entrega a chave de envio nas variáveis CM_KEYSTORE_*. A chave NUNCA fica no repositório.
  if (process.env.CM_KEYSTORE_PATH) {
    editar("android/app/build.gradle", (s) => {
      if (s.includes("signingConfigs")) return s;
      const cfg = `    signingConfigs {
        release {
            storeFile file(System.getenv("CM_KEYSTORE_PATH"))
            storePassword System.getenv("CM_KEYSTORE_PASSWORD")
            keyAlias System.getenv("CM_KEY_ALIAS")
            keyPassword System.getenv("CM_KEY_PASSWORD")
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release`;
      return s.replace(/    buildTypes \{\s*release \{/, cfg);
    });
  }
} else if (alvo === "ios") {
  // Textos que a Apple EXIGE para pedir permissão (aparecem para o usuário). Sem eles a Apple rejeita o app.
  editar("ios/App/App/Info.plist", (s) => {
    const chaves = {
      NSMicrophoneUsageDescription: "O microfone é usado para transmitir a fala do palestrante para tradução ao vivo.",
      NSCameraUsageDescription: "A câmera é usada para escanear o QR Code do evento.",
    };
    let out = s;
    for (const [k, v] of Object.entries(chaves)) {
      if (!out.includes(k)) out = out.replace(/<\/dict>\s*<\/plist>/, `\t<key>${k}</key>\n\t<string>${v}</string>\n</dict>\n</plist>`);
    }
    // Declara que o app não usa criptografia própria além do HTTPS padrão (evita perguntas de exportação a cada envio).
    if (!out.includes("ITSAppUsesNonExemptEncryption")) {
      out = out.replace(/<\/dict>\s*<\/plist>/, "\t<key>ITSAppUsesNonExemptEncryption</key>\n\t<false/>\n</dict>\n</plist>");
    }
    return out;
  });
  // Versão visível (MARKETING_VERSION) e número do envio (CURRENT_PROJECT_VERSION: precisa SUBIR a cada envio à App Store).
  editar("ios/App/App.xcodeproj/project.pbxproj", (s) =>
    s.replace(/MARKETING_VERSION = [^;]+;/g, `MARKETING_VERSION = ${versao};`).replace(/CURRENT_PROJECT_VERSION = [^;]+;/g, `CURRENT_PROJECT_VERSION = ${parseInt(build, 10)};`),
  );
  // Só iPhone: evita a Apple exigir capturas de tela de iPad (o app é pensado para o celular).
  editar("ios/App/App.xcodeproj/project.pbxproj", (s) => s.replace(/TARGETED_DEVICE_FAMILY = "?1,2"?;/g, "TARGETED_DEVICE_FAMILY = 1;"),
  );
} else {
  console.error('Use: node scripts/patch-native.mjs android|ios');
  process.exit(1);
}

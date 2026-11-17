/** O app das lojas (Android/iOS) é um "casco" que abre o site e acrescenta "SelaVoiceApp" ao identificador do navegador.
 *  Dentro dele NÃO vendemos nada: Apple e Google exigem a compra pela loja deles (com comissão) para bens digitais.
 *  Planos e recargas são contratados no site; o app só mostra o uso. */
export const isNativeApp = () => typeof navigator !== "undefined" && /SelaVoiceApp/i.test(navigator.userAgent);

"use client";
/**
 * Leitor de QR Code pela câmera (ouvinte escaneia o QR do evento ou da organização).
 * Usa a API nativa BarcodeDetector (Chrome/Edge/Android). Onde não existe (Safari/Firefox), avisa e o ouvinte pode usar a
 * câmera do celular ou digitar o código.
 * SEGURANÇA: do QR só aproveitamos o CAMINHO (/e/código ou /o/organização) e navegamos dentro do nosso site; o endereço
 * (domínio) do QR é ignorado, então um QR malicioso não leva a outro site.
 */
import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { useT } from "@/lib/i18n";

const PATH = /^\/(e|o)\/[A-Za-z0-9_-]{2,80}$/;

export function pathFromQr(text: string): string | null {
  try {
    const u = new URL(text, "http://x.local");
    return PATH.test(u.pathname) ? u.pathname : null;
  } catch { return null; }
}

export default function QrScan({ onPath, onClose }: { onPath: (p: string) => void; onClose: () => void }) {
  const t = useT();
  const video = useRef<HTMLVideoElement>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let stop = false; let stream: MediaStream | null = null; let timer: any;
    (async () => {
      const BD = (window as any).BarcodeDetector;
      if (!BD) return setErr("Este navegador não lê QR Code aqui. Use a câmera do celular para abrir o link do QR, ou digite o código do evento.");
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
        if (stop) { stream.getTracks().forEach((x) => x.stop()); return; }
        const v = video.current!; v.srcObject = stream; await v.play();
        const det = new BD({ formats: ["qr_code"] });
        const loop = async () => {
          if (stop) return;
          try {
            const codes = await det.detect(v);
            const p = codes.map((c: any) => pathFromQr(c.rawValue)).find(Boolean);
            if (p) { onPath(p); return; }
          } catch {}
          timer = setTimeout(loop, 300);
        };
        loop();
      } catch { setErr("Não foi possível abrir a câmera. Permita o acesso à câmera ou digite o código do evento."); }
    })();
    return () => { stop = true; clearTimeout(timer); stream?.getTracks().forEach((x) => x.stop()); };
  }, [onPath]);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={t("Escanear QR Code")} onClick={(e) => e.stopPropagation()}>
        <div className="modal-h"><h3>{t("Escanear QR Code")}</h3><button className="btn btn-ghost btn-sm" onClick={onClose} aria-label={t("Fechar")}><Icon name="x" small /></button></div>
        <div style={{ padding: 16 }}>
          {err ? <p className="muted" style={{ margin: 0 }}>{t(err)}</p> : (
            <div className="scan"><video ref={video} muted playsInline /><span className="scan-frame" /><p className="fine" style={{ textAlign: "center", margin: "10px 0 0" }}>{t("Aponte para o QR Code do evento ou da organização.")}</p></div>
          )}
        </div>
      </div>
    </div>
  );
}

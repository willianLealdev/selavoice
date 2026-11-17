"""Utilitário de captura de áudio (computador) -> SelaVoice. Aceita QUALQUER entrada de áudio do computador:
mesa de som (X32, Yamaha, Allen&Heath…), interface USB, placa de captura, microfone. A fonte não importa.
Alternativa sem instalar nada: no painel do evento, "Capturar áudio" (navegador do computador OU do celular).

STATUS: NÃO TESTADO com hardware real (ver docs/BLOCKERS.md #7). Escrito conforme o
protocolo testado do servidor (WS /sessions/{id}/ingest: 1ª msg {"token"} e depois frames binários).

Uso:
  pip install sounddevice websockets
  python capture.py --list                                   # lista as entradas de áudio do computador
  python capture.py --server wss://api.seusite.com --session <SESSION_ID> --token <TOKEN> --device 3

O TOKEN é gerado no painel (Evento > "Gerar token de captura"). Expira em 4 h; não o compartilhe.
Formato enviado: PCM 16-bit mono 16 kHz em frames de 20 ms (640 bytes). Codec Opus fica para a fase do relay.
"""
import argparse
import asyncio
import json

try:
    import sounddevice as sd
    import websockets
except ImportError:  # mensagem amigável para quem não instalou
    raise SystemExit("Instale as dependências:  pip install sounddevice websockets")

RATE, FRAME_MS = 16000, 20


async def run(args) -> None:
    backoff = 1
    while True:  # reconecta sozinho se a rede cair
        try:
            async with websockets.connect(f"{args.server}/sessions/{args.session}/ingest", max_size=2**16) as ws:
                await ws.send(json.dumps({"token": args.token}))
                ready = json.loads(await ws.recv())
                if ready.get("type") != "ready":
                    raise SystemExit("Servidor recusou o token ou o evento não está AO VIVO.")
                print("Conectado. Enviando áudio… (Ctrl+C para parar)")
                backoff = 1
                loop = asyncio.get_running_loop()
                q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)

                def cb(indata, frames, t, status):  # thread de áudio -> fila
                    loop.call_soon_threadsafe(lambda b=bytes(indata): q.full() or q.put_nowait(b))

                with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", device=args.device,
                                       blocksize=RATE * FRAME_MS // 1000, callback=cb):
                    while True:
                        await ws.send(await q.get())
        except (OSError, websockets.ConnectionClosed) as e:
            print(f"Conexão perdida ({e}); tentando de novo em {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 15)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--server"); p.add_argument("--session"); p.add_argument("--token")
    p.add_argument("--device", type=int, default=None)
    a = p.parse_args()
    if a.list:
        print(sd.query_devices())
        return
    if not (a.server and a.session and a.token):
        p.error("--server, --session e --token são obrigatórios")
    asyncio.run(run(a))


if __name__ == "__main__":
    main()

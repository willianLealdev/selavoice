"""PORTÃO DE VOZ: deixa passar só a voz do palestrante e descarta ruído de fundo e conversa ao redor.

PROBLEMA REAL (relato do dono): o microfone captava pessoas conversando ao redor e a tradução saía "embaralhada".
COMO FUNCIONA (por energia, no servidor, antes de o áudio ir ao provedor de IA):
  - "piso de ruído": estimativa adaptativa do barulho ambiente (sobe devagar, desce rápido);
  - "nível do palestrante": média do volume dos trechos de voz forte (quem fala PERTO do microfone é sempre mais alto);
  - um trecho só passa se (a) está acima do piso de ruído E (b) não é muito mais baixo que o palestrante
    (Normal: até -12 dB abaixo; Forte: até -8 dB). Conversa de fundo costuma ficar bem abaixo => é descartada;
  - "pré-rolagem" (0,2 s) e "retenção" (0,4 s) evitam cortar o começo/fim das palavras;
  - ao terminar a fala, mandamos 0,6 s de silêncio (marca o fim da frase para o provedor) e DEPOIS paramos de enviar:
    silêncio não vai ao provedor => não gasta e não é cobrado.
LIMITES HONESTOS: separação por VOLUME. Se alguém falar tão alto quanto o palestrante (ex.: o povo gritando "glória!" bem perto do
microfone), passa. Vozes sobrepostas com o mesmo volume não são separadas (isso exigiria um modelo de separação de locutores).
O modo "off" não filtra nada (use para mesa de som com linha limpa) mas continua medindo a fala.
"""
import array
import math
from collections import deque

SR = 16000
BPS = SR * 2                     # bytes por segundo (PCM16 mono)
MODES = ("off", "normal", "strong")
DEFAULT_AUDIO = {"filter": "normal", "noise_suppression": True, "only_event_language": True}

# modo -> (dB abaixo do palestrante ainda aceitos, múltiplo do piso de ruído para ser "voz")
PARAMS = {"normal": (12.0, 3.0), "strong": (8.0, 3.5)}
ABS_MIN = 180.0                  # RMS mínimo (escala int16) para considerar voz, mesmo num ambiente muito quieto
PREROLL_S, HANG_S, TAIL_S = 0.2, 0.4, 0.6


def get_audio(settings: dict | None) -> dict:
    """Configuração de áudio da organização (com padrões)."""
    a = dict((settings or {}).get("audio") or {})
    out = dict(DEFAULT_AUDIO)
    if a.get("filter") in MODES:
        out["filter"] = a["filter"]
    for k in ("noise_suppression", "only_event_language"):
        if k in a:
            out[k] = bool(a[k])
    return out


def clean_audio(raw: dict) -> dict:
    """Valida o que o painel envia."""
    out = {}
    if "filter" in raw:
        if raw["filter"] not in MODES:
            raise ValueError("Filtro de voz inválido.")
        out["filter"] = raw["filter"]
    for k in ("noise_suppression", "only_event_language"):
        if k in raw:
            out[k] = bool(raw[k])
    return out


def _rms(chunk: bytes) -> float:
    a = array.array("h")
    a.frombytes(chunk[: len(chunk) // 2 * 2])
    if not a:
        return 0.0
    s = a[::2] if len(a) > 400 else a        # amostra metade: barato e suficiente para volume
    return math.sqrt(sum(x * x for x in s) / len(s))


class AudioGate:
    def __init__(self, mode: str = "normal") -> None:
        self.mode = mode if mode in MODES else "normal"
        self.floor = 120.0           # piso de ruído estimado (RMS int16)
        self.level = 0.0             # volume típico do palestrante
        self.is_open = False
        self._hold = 0.0             # retenção restante (s)
        self._tail = 0.0             # silêncio ainda a enviar após fechar (s)
        self._pre: deque[bytes] = deque()
        self._pre_s = 0.0
        self.speech_s = self.passed_s = self.dropped_s = 0.0   # contadores (s)
        self.last_rms = 0.0
        # CALIBRAÇÃO: o palestrante fala ~5 s e o sistema aprende o volume dele ANTES do evento, em vez de aprender com o 1º som
        # que aparecer (que pode ser conversa de fundo). Durante a calibração tudo passa.
        self._cal_left = 0.0
        self._cal: list[float] = []
        self.calibrated = False

    # ---- estimativas ----
    def _update_floor(self, rms: float, dur: float) -> None:
        if rms < self.floor:
            self.floor = 0.8 * self.floor + 0.2 * rms          # desce rápido
        else:
            self.floor += (rms - self.floor) * 0.002 * (dur / 0.02)   # sobe muito devagar (voz não vira "ruído")
        self.floor = min(max(self.floor, 30.0), 3000.0)

    def _classify(self, rms: float) -> bool:
        """True = este trecho é a voz do palestrante."""
        db_below, k = PARAMS.get(self.mode, PARAMS["normal"])
        voice = rms > max(self.floor * k, ABS_MIN)
        if not voice:
            return False
        if self.mode == "off":
            return True
        rel = 10 ** (-db_below / 20)
        if self.level > 0 and rms < self.level * rel:
            return False                                          # voz, mas MUITO mais baixa que o palestrante: fundo
        return True

    def _track_level(self, rms: float, speech: bool) -> None:
        if speech:
            # sobe até +3 dB por vez (um grito curto não "sequestra" o nível), desce devagar
            target = min(rms, self.level * 1.41) if self.level > 0 else rms
            self.level = self.level * 0.97 + target * 0.03 if self.level > 0 else target
        elif self.level > 0:
            self.level *= 0.9995                                  # esquece devagar se ninguém fala

    # ---- processamento ----
    def start_calibration(self, seconds: float = 5.0) -> None:
        self._cal_left, self._cal = seconds, []
        self.calibrated = False

    @property
    def calibrating(self) -> bool:
        return self._cal_left > 0

    def _calibrate(self, rms: float, dur: float) -> None:
        if rms > max(self.floor * 2.5, ABS_MIN):
            self._cal.append(rms)
        self._cal_left -= dur
        if self._cal_left <= 0:
            self._cal_left = 0.0
            if len(self._cal) >= 25:                          # pelo menos ~0,5 s de voz de verdade
                xs = sorted(self._cal)
                self.level = xs[int(len(xs) * 0.6)]           # um pouco acima da mediana: o "volume normal" de quem fala
                self.calibrated = True

    def process(self, chunk: bytes) -> list[bytes]:
        """Recebe um pedaço de PCM16 16 kHz e devolve os pedaços a ENVIAR ao provedor (pode ser nenhum)."""
        if not chunk:
            return []
        dur = len(chunk) / BPS
        rms = _rms(chunk)
        self.last_rms = rms
        self._update_floor(rms, dur)
        if self._cal_left > 0:
            self._calibrate(rms, dur)
            self.passed_s += dur
            if rms > max(self.floor * 2.5, ABS_MIN):
                self.speech_s += dur
            return [chunk]                                     # durante a calibração nada é filtrado
        speech = self._classify(rms)
        self._track_level(rms, speech)
        if speech:
            self.speech_s += dur
        if self.mode == "off":
            self.passed_s += dur
            return [chunk]
        out: list[bytes] = []
        if speech:
            if not self.is_open:                                  # começou a falar: manda a pré-rolagem para não cortar a 1ª sílaba
                out.extend(self._pre)
                self._pre.clear(); self._pre_s = 0.0
                self.is_open = True
            self._hold, self._tail = HANG_S, 0.0
            out.append(chunk)
        elif self.is_open:
            self._hold -= dur
            # Retenção: ainda dentro de uma pausa curta entre palavras. NÃO repassamos o áudio cru (poderia ser a conversa de fundo
            # logo após a frase): mandamos silêncio no lugar, que mantém o ritmo e fecha a frase sem deixar o fundo entrar.
            out.append(b"\x00" * len(chunk))
            if self._hold <= 0:
                self.is_open, self._tail = False, TAIL_S
        elif self._tail > 0:
            out.append(b"\x00" * len(chunk))                      # silêncio curto: marca o fim da frase para o provedor
            self._tail -= dur
        else:
            self._pre.append(chunk); self._pre_s += dur           # guarda só o último trecho (pré-rolagem)
            while self._pre_s > PREROLL_S and self._pre:
                self._pre_s -= len(self._pre.popleft()) / BPS
        sent = sum(len(c) for c in out) / BPS
        self.passed_s += sent
        self.dropped_s += max(0.0, dur - sent)
        return out

    def stats(self) -> dict:
        tot = max(self.passed_s + self.dropped_s, 1e-6)
        return {"mode": self.mode, "floor": round(self.floor), "level": round(self.level), "last_rms": round(self.last_rms),
                "speech_seconds": round(self.speech_s, 1), "dropped_pct": round(100 * self.dropped_s / tot), "open": self.is_open,
                "calibrating": self.calibrating, "calibrated": self.calibrated}


# Um portão por sessão (alimentado pelo WebSocket de ingestão; lido pelo diagnóstico do operador)
gates: dict[str, AudioGate] = {}

"""Circuit breaker e roteador de failover POR IDIOMA.

- Falhas consecutivas abrem o circuito do par (provedor, idioma) -> troca só aquele idioma.
- Cooldown + histerese: depois de trocar, não troca de novo antes de `min_switch_seconds`
  (evita "flapping"). Circuito aberto vira "meio-aberto" após o cooldown para testar de volta.
"""
import time
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold and self.opened_at is None:
            self.opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.cooldown_seconds:
            return False  # meio-aberto: permite uma tentativa
        return True


@dataclass
class FailoverRouter:
    """Escolhe o provedor para cada (sessão, idioma) conforme prioridade e saúde."""
    priority: list[str]  # ex.: ["gemini", "azure", "mock"]
    threshold: int = 3
    cooldown: float = 30.0
    min_switch_seconds: float = 20.0
    _breakers: dict = field(default_factory=dict)
    _current: dict = field(default_factory=dict)       # (sid, lang) -> provider
    _last_switch: dict = field(default_factory=dict)   # (sid, lang) -> t
    admin_override: dict = field(default_factory=dict)  # (sid, lang) -> provider forçado

    def breaker(self, provider: str, lang: str) -> CircuitBreaker:
        return self._breakers.setdefault((provider, lang), CircuitBreaker(self.threshold, self.cooldown))

    def choose(self, sid: str, lang: str, available: set[str]) -> str | None:
        key = (sid, lang)
        if key in self.admin_override and self.admin_override[key] in available:
            return self.admin_override[key]
        cur = self._current.get(key)
        # histerese: se o atual está saudável, mantém
        if cur and cur in available and not self.breaker(cur, lang).is_open:
            return cur
        for p in self.priority:
            if p in available and not self.breaker(p, lang).is_open:
                if cur and p != cur:
                    last = self._last_switch.get(key, 0)
                    if time.monotonic() - last < self.min_switch_seconds and cur in available \
                            and not self.breaker(cur, lang).is_open:
                        return cur
                    self._last_switch[key] = time.monotonic()
                self._current[key] = p
                return p
        return None

    def report_failure(self, sid: str, lang: str, provider: str) -> None:
        self.breaker(provider, lang).record_failure()

    def report_success(self, sid: str, lang: str, provider: str) -> None:
        self.breaker(provider, lang).record_success()

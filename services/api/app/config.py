"""Configuração central (variáveis de ambiente).

REGRAS DE SEGURANÇA:
- Nenhum segredo fica no código. Tudo vem do ambiente (.env).
- Em produção (APP_ENV=production) a API RECUSA subir com segredos fracos/padrão.
- Chaves de provedores de IA e do Stripe existem SOMENTE no backend.
"""
from functools import lru_cache
from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor padrão só para desenvolvimento/testes; é bloqueado em produção.
_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"  # development | test | production
    # Padrão local: arquivo SEMPRE em services/api/selavoice.db (caminho absoluto, independe de onde o servidor roda).
    # Produção: postgresql+psycopg://...
    database_url: str = "sqlite:///" + (Path(__file__).resolve().parents[1] / "selavoice.db").as_posix()
    redis_url: str = ""  # vazio = hub em memória (1 processo)

    # --- Autenticação ---
    jwt_secret: str = _DEV_SECRET
    jwt_issuer: str = "selavoice"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    listener_token_minutes: int = 120
    # Chave Fernet (base64 32 bytes) para cifrar segredos de provedores no banco.
    encryption_key: str = ""

    # --- Limites / proteção ---
    max_login_failures: int = 5
    lockout_minutes: int = 15
    rate_limit_per_minute: int = 120  # por IP (rotas gerais)
    auth_rate_limit_per_minute: int = 10  # por IP (login/registro)
    max_body_bytes: int = 1_000_000
    cors_origins: str = "http://localhost:3000"
    ws_max_connections_per_ip: int = 20

    # --- Pilot / seed ---
    super_admin_email: str = "admin@selavoice.local"
    super_admin_password: str = ""  # se vazio o seed gera uma senha aleatória e imprime 1x

    # --- Stripe (modo teste primeiro; NUNCA cobra em produção sem ordem explícita) ---
    stripe_mode: str = "fake"  # fake | test | live
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = "whsec_dev_fake_secret"
    stripe_tolerance_seconds: int = 300
    public_web_url: str = "http://localhost:3000"

    # --- Provedores de IA (vazio = simulador determinístico) ---
    gemini_api_key: str = ""
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    deepgram_api_key: str = ""
    deepseek_api_key: str = ""
    resend_api_key: str = ""        # e-mail transacional (Resend)
    resend_from_email: str = ""      # ex.: no-reply@seudominio.com (domínio verificado no Resend)

    # --- Mídia ---
    media_signing_secret: str = ""  # se vazio, usa jwt_secret derivado
    channel_grace_seconds: int = 30  # espera antes de desligar canal sem ouvintes
    event_clock_seconds: int = 30    # intervalo do relógio de horas de transmissão (0 = desligado)

    @model_validator(mode="after")
    def _validar_producao(self):
        """Trava de segurança: produção não sobe com configuração insegura."""
        if self.app_env == "production":
            problemas = []
            if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
                problemas.append("JWT_SECRET fraco/padrão")
            if not self.encryption_key:
                problemas.append("ENCRYPTION_KEY ausente")
            if self.stripe_mode == "live" and not self.stripe_secret_key:
                problemas.append("STRIPE_SECRET_KEY ausente")
            # Segredo do webhook do Stripe pode vir SÓ do painel (banco). Em produção o valor padrão de desenvolvimento
            # nunca é aceito: ver services/billing.py::webhook_secret (sem segredo real => webhooks são recusados).
            if "*" in self.cors_origins:
                problemas.append("CORS aberto (*)")
            if problemas:
                raise ValueError("Configuração insegura para produção: " + ", ".join(problemas))
        return self

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

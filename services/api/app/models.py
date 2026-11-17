"""Modelos do banco (SQLAlchemy 2).

CONVENÇÕES
- PK = UUID. Todo registro de cliente tem `tenant_id` (FK para tenants) -> isolamento/RLS.
- Tabelas globais (sem tenant_id): users, plans, plan_versions, stripe_webhook_events, audit_logs*.
  (*audit_logs tem tenant_id opcional: ações globais do super admin ficam sem tenant.)
- Livros-razão (usage_events, credit_ledger) são APPEND-ONLY: nunca atualizar/apagar linhas.
- Datas sempre em UTC (timezone-aware).
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer,
                        Numeric, String, Text, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------- Enums ----------------
class Role(str, enum.Enum):
    TENANT_ADMIN = "TENANT_ADMIN"
    EVENT_OPERATOR = "EVENT_OPERATOR"
    MEMBER = "MEMBER"


class EventStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    ENDED = "ENDED"
    CANCELED = "CANCELED"


class ChannelState(str, enum.Enum):
    IDLE = "IDLE"          # sem ouvintes: não consome IA
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"  # provedor em falha / fallback em uso
    CLOSED = "CLOSED"


class DocStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"


class BillingType(str, enum.Enum):
    ONE_OFF = "ONE_OFF"
    MONTHLY = "MONTHLY"


class _Mixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------- Tenants / usuários ----------------
class Tenant(_Mixin, Base):
    __tablename__ = "tenants"
    type: Mapped[str] = mapped_column(String(30), default="other")  # church|conference|expo|fair|corporate|education|association|other
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    locale: Mapped[str] = mapped_column(String(10), default="pt-BR")
    timezone: Mapped[str] = mapped_column(String(60), default="America/Los_Angeles")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|suspended
    branding: Mapped[dict] = mapped_column(JSON, default=dict)  # logo, cores
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class User(_Mixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # cifrado (Fernet)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Quando o dono do e-mail confirmou (link enviado no cadastro). NULL = conta ainda NÃO ativada (não consegue entrar).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Membership(_Mixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.MEMBER)


class Invitation(_Mixin, Base):
    __tablename__ = "invitations"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.MEMBER)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordReset(_Mixin, Base):
    """Token de redefinição de senha: guardado só como hash, uso único, expira em 1 h."""
    __tablename__ = "password_resets"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailVerification(_Mixin, Base):
    """Token de confirmação de e-mail: guardado só como hash, uso único, expira (padrão 24 h)."""
    __tablename__ = "email_verifications"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(_Mixin, Base):
    """Refresh token com rotação. `family_id` agrupa a cadeia; reuso => revoga a família."""
    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------- Eventos ----------------
class Venue(_Mixin, Base):
    __tablename__ = "venues"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(300), default="")


class Event(_Mixin, Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_tenant_starts", "tenant_id", "starts_at"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30), default="service")  # service|expo|fair|conference|lecture|other
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(60), default="America/Los_Angeles")
    original_language: Mapped[str] = mapped_column(String(10), default="pt")
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.SCHEDULED, index=True)
    presenter: Mapped[str] = mapped_column(String(160), default="")
    theme: Mapped[str] = mapped_column(String(200), default="")
    scripture: Mapped[str] = mapped_column(String(200), default="")
    # none | transcript_only | audio_and_transcript  (consentimento explícito)
    recording_policy: Mapped[str] = mapped_column(String(30), default="none")
    join_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    # Direito (plano/compra) que este evento está consumindo; fixado ao INICIAR. Dele vêm os limites do evento.
    entitlement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sessions: Mapped[list["EventSession"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventSession(_Mixin, Base):
    """Sala/sessão de um evento (feiras têm várias em paralelo)."""
    __tablename__ = "event_sessions"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    room: Mapped[str] = mapped_column(String(80), default="main")
    state: Mapped[str] = mapped_column(String(20), default="idle")  # idle|live|ended
    event: Mapped[Event] = relationship(back_populates="sessions")


class TranslationChannel(_Mixin, Base):
    """UM canal por idioma-alvo ativo por sessão, compartilhado por todos os ouvintes."""
    __tablename__ = "translation_channels"
    __table_args__ = (UniqueConstraint("session_id", "target_language"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event_sessions.id", ondelete="CASCADE"), index=True)
    target_language: Mapped[str] = mapped_column(String(10))
    provider: Mapped[str] = mapped_column(String(30), default="mock")
    state: Mapped[ChannelState] = mapped_column(Enum(ChannelState), default=ChannelState.IDLE)
    listeners: Mapped[int] = mapped_column(Integer, default=0)
    active_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TranscriptSegment(_Mixin, Base):
    """Segmento de transcrição acumulada. (session, language, seq) é único e monotônico.
    Provisórios aumentam `revision`; depois de `is_final=True` o texto é IMUTÁVEL."""
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("session_id", "language", "seq"),
        Index("ix_seg_replay", "session_id", "language", "seq"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event_sessions.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(String(10))
    seq: Mapped[int] = mapped_column(BigInteger)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(12), default="translated")  # translated|original
    text: Mapped[str] = mapped_column(Text, default="")
    start_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    end_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    provider: Mapped[str] = mapped_column(String(30), default="mock")


class Recording(_Mixin, Base):
    __tablename__ = "recordings"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    storage_key: Mapped[str] = mapped_column(String(400))  # prefixo por tenant
    consent_recorded: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------- Documentos / apostilas ----------------
class Document(_Mixin, Base):
    __tablename__ = "documents"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(10), default="pt")
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.DRAFT)
    # Conteúdo editorial estruturado: {"chapters":[{"title","body","editorial":bool}], "references":[...]}
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[list] = mapped_column(JSON, default=list)  # referências bíblicas a revisar
    version: Mapped[int] = mapped_column(Integer, default=1)
    pdf_key: Mapped[str | None] = mapped_column(String(400), nullable=True)


class PublicationApproval(_Mixin, Base):
    __tablename__ = "publication_approvals"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")


# ---------------- Planos e cobrança ----------------
class Plan(_Mixin, Base):
    __tablename__ = "plans"
    public_name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|published|archived
    versions: Mapped[list["PlanVersion"]] = relationship(back_populates="plan", order_by="PlanVersion.version")


class PlanVersion(_Mixin, Base):
    """Versão IMUTÁVEL do plano. Mudar preço/limites = nova versão (histórico preservado)."""
    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version"),)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    stripe_price_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    billing_type: Mapped[BillingType] = mapped_column(Enum(BillingType))
    currency: Mapped[str] = mapped_column(String(3), default="usd")
    amount_cents: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # {included_events, max_event_minutes, included_language_minutes, max_languages,
    #  listener_concurrency, retention_days, pdf_booklets, recordings, admin_seats,
    #  trial_days, overage: "hard_stop"|"degrade"|"topup", max_concurrent_events}
    entitlements: Mapped[dict] = mapped_column(JSON, default=dict)
    plan: Mapped[Plan] = relationship(back_populates="versions")


class TenantSubscription(_Mixin, Base):
    __tablename__ = "tenant_subscriptions"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    plan_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan_versions.id"))  # trava a versão (grandfathering)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="incomplete")  # active|past_due|canceled|incomplete
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OneOffPurchase(_Mixin, Base):
    __tablename__ = "one_off_purchases"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    plan_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan_versions.id"))
    stripe_session_id: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|paid|refunded|failed
    events_remaining: Mapped[int] = mapped_column(Integer, default=0)


class Entitlement(_Mixin, Base):
    """Direitos concedidos (SOMENTE após webhook verificado). Saldos em minutos-idioma."""
    __tablename__ = "entitlements"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # subscription|one_off|trial|manual
    source_ref: Mapped[str] = mapped_column(String(120), default="")
    limits: Mapped[dict] = mapped_column(JSON, default=dict)
    events_remaining: Mapped[int] = mapped_column(Integer, default=0)
    language_minutes_remaining: Mapped[int] = mapped_column(Integer, default=0)
    # Minutos de TRANSMISSÃO restantes (contados desde o início do evento). NULL = ilimitado.
    event_minutes_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("source", "source_ref"),)  # idempotência da concessão


class UsageEvent(_Mixin, Base):
    """Livro-razão APPEND-ONLY. Unidade: language-minute (não event-minute)."""
    __tablename__ = "usage_events"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="")
    provider: Mapped[str] = mapped_column(String(30), default="")
    kind: Mapped[str] = mapped_column(String(20), default="language_minute")
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    provider_cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)  # custo do provedor (µUSD), à parte
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)


class CreditLedger(_Mixin, Base):
    """Créditos manuais/top-ups. APPEND-ONLY (saldo = soma)."""
    __tablename__ = "credit_ledger"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    delta_language_minutes: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200), default="")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class StripeWebhookEvent(_Mixin, Base):
    """Dedupe/replay: o id do evento Stripe é único. Reprocessar = ignorado."""
    __tablename__ = "stripe_webhook_events"
    stripe_event_id: Mapped[str] = mapped_column(String(120), unique=True)
    type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(40), default="processed")


# ---------------- Provedores / operação ----------------
class ProviderConfig(_Mixin, Base):
    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("name"),)
    name: Mapped[str] = mapped_column(String(30))  # gemini|azure|deepgram|deepseek|mock
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet; nunca texto puro
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=100)


class FailoverEvent(_Mixin, Base):
    __tablename__ = "failover_events"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    language: Mapped[str] = mapped_column(String(10))
    from_provider: Mapped[str] = mapped_column(String(30))
    to_provider: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(200), default="")


class AuditLog(_Mixin, Base):
    """Auditoria. Ações do super admin em tenants DEVEM ter reason."""
    __tablename__ = "audit_logs"
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_role: Mapped[str] = mapped_column(String(30), default="")
    action: Mapped[str] = mapped_column(String(80), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")
    reason: Mapped[str] = mapped_column(String(300), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class PlatformSetting(_Mixin, Base):
    """Configurações da plataforma editáveis no painel (ex.: o teste grátis). Chave -> valor JSON."""
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(_Mixin, Base):
    __tablename__ = "notifications"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(400))
    read: Mapped[bool] = mapped_column(Boolean, default=False)


# Tabelas com tenant_id (usado para gerar as políticas RLS e testes de isolamento).
TENANT_TABLES = [
    "memberships", "invitations", "venues", "events", "event_sessions", "translation_channels",
    "transcript_segments", "recordings", "documents", "publication_approvals",
    "tenant_subscriptions", "one_off_purchases", "entitlements", "usage_events", "credit_ledger",
    "failover_events", "notifications",
]

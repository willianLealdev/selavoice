"""Envio de e-mail transacional via Resend (https://resend.com).

- Chave e remetente vêm do cofre (painel Super Admin › Integrações) ou do .env.
- Sem chave configurada: NÃO envia (retorna ok=False) e o chamador usa um plano B (ex.: mostrar o link ao admin).
- Todo conteúdo dinâmico é escapado (html.escape) para evitar injeção de HTML em e-mails.
- Nunca registra a chave nem o corpo do e-mail nos logs.
"""
import html
import logging

import httpx

from ..config import get_settings
from .secrets_store import get_secret, is_enabled

log = logging.getLogger("selavoice.email")
settings = get_settings()


def email_configured() -> bool:
    return bool(get_secret("resend", "api_key") and get_secret("resend", "from_email") and is_enabled("resend"))


def send_email(to: str, subject: str, html_body: str, text_body: str) -> tuple[bool, str]:
    """Envia 1 e-mail. Retorna (ok, detalhe_para_log_sem_segredos)."""
    if not email_configured():
        return False, "resend_not_configured"
    try:
        r = httpx.post(
            "https://api.resend.com/emails", timeout=15,
            headers={"Authorization": f"Bearer {get_secret('resend', 'api_key')}"},
            json={"from": f"SelaVoice <{get_secret('resend', 'from_email')}>", "to": [to],
                  "subject": subject, "html": html_body, "text": text_body})
    except httpx.HTTPError:
        log.warning("resend: falha de rede")
        return False, "network_error"
    if r.status_code >= 300:
        log.warning("resend: HTTP %s", r.status_code)  # sem corpo/chave
        return False, f"http_{r.status_code}"
    return True, "sent"


def _layout(title: str, inner: str) -> str:
    return (f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:24px;color:#0f1a33">'
            f'<h2 style="color:#0b63ce">SelaVoice</h2><h3>{html.escape(title)}</h3>{inner}'
            f'<p style="color:#5b6b8a;font-size:12px;margin-top:28px">Se você não esperava este e-mail, ignore-o.</p></div>')


def send_invite(to: str, org_name: str, token: str) -> bool:
    link = f"{settings.public_web_url}/invite?token={token}"
    inner = (f"<p>Você foi convidado para a organização <b>{html.escape(org_name)}</b>.</p>"
             f'<p><a href="{html.escape(link)}" style="background:#0b63ce;color:#fff;padding:12px 20px;'
             f'border-radius:8px;text-decoration:none;font-weight:bold">Aceitar convite</a></p>'
             f"<p>O link vale por 7 dias.</p>")
    return send_email(to, f"Convite para {org_name} no SelaVoice", _layout("Você foi convidado", inner),
                      f"Você foi convidado para {org_name}. Aceite em: {link} (vale 7 dias)")[0]


def send_password_reset(to: str, token: str) -> bool:
    link = f"{settings.public_web_url}/reset?token={token}"
    inner = (f'<p>Recebemos um pedido para redefinir sua senha.</p><p><a href="{html.escape(link)}" '
             f'style="background:#0b63ce;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;'
             f'font-weight:bold">Criar nova senha</a></p><p>O link vale por 1 hora e só pode ser usado uma vez.</p>')
    return send_email(to, "Redefinição de senha — SelaVoice", _layout("Redefinir senha", inner),
                      f"Redefina sua senha em: {link} (vale 1 hora, uso único)")[0]


def send_verification(to: str, name: str, token: str) -> bool:
    """E-mail de CONFIRMAÇÃO do cadastro. O link leva a /verificar?token=... (uso único, vale 24 h)."""
    link = f"{settings.public_web_url}/verificar?token={token}"
    inner = (f"<p>Olá, {html.escape(name or 'tudo bem')}! Para <b>ativar sua conta</b> no SelaVoice, confirme este e-mail:</p>"
             f'<p><a href="{html.escape(link)}" style="background:#0b63ce;color:#fff;padding:12px 20px;'
             f'border-radius:8px;text-decoration:none;font-weight:bold">Confirmar e ativar minha conta</a></p>'
             f"<p>O link vale por {settings.email_verification_hours} horas e só pode ser usado uma vez.</p>")
    return send_email(to, "Confirme seu e-mail — SelaVoice", _layout("Confirme seu e-mail", inner),
                      f"Confirme seu e-mail para ativar a conta: {link} (vale {settings.email_verification_hours} h, uso único)")[0]

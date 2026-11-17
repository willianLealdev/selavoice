"""Envio de e-mail transacional via Resend (https://resend.com) + modelos de e-mail do SelaVoice.

- Chave e remetente vêm do cofre (painel Super Admin › Integrações) ou do .env.
- Sem chave configurada: NÃO envia (retorna ok=False) e o chamador usa um plano B (ex.: mostrar o link ao admin).
- Todo conteúdo dinâmico é escapado (html.escape) para evitar injeção de HTML em e-mails.
- Nunca registra a chave nem o corpo do e-mail nos logs.

VISUAL DOS E-MAILS (um único modelo para todos): cartão branco de 600 px sobre fundo claro, logo no topo (PNG hospedado no
site: <PUBLIC_WEB_URL>/email/logo.png — e-mail não carrega WebP direito), título, texto, BOTÃO grande, link alternativo,
aviso de segurança e rodapé. Feito com TABELAS e estilos inline, que é o que Gmail/Outlook/Apple Mail entendem.
Idiomas: pt (padrão), en, es.
"""
import html
import logging

import httpx

from ..config import get_settings
from .secrets_store import get_secret, is_enabled

log = logging.getLogger("selavoice.email")
settings = get_settings()

BRAND = "#0a5bd3"
INK = "#0b1220"


def email_configured() -> bool:
    return bool(get_secret("resend", "api_key") and get_secret("resend", "from_email") and is_enabled("resend"))


def send_email(to: str, subject: str, html_body: str, text_body: str) -> tuple[bool, str]:
    """Envia 1 e-mail. Retorna (ok, detalhe_para_log_sem_segredos)."""
    if not email_configured():
        log.warning("resend: NÃO configurado (falta a chave, o e-mail remetente ou está desativado no painel)")
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
        try:   # a mensagem de erro do Resend (ex.: "domínio não verificado") ajuda a achar o problema; não contém segredos
            why = str((r.json() or {}).get("message", ""))[:200]
        except ValueError:
            why = ""
        log.warning("resend: HTTP %s %s", r.status_code, why)
        return False, f"http_{r.status_code}"
    return True, "sent"


# ------------------------------------------------------------------ textos (pt / en / es)
T = {
    "pt": {
        "tagline": "Tradução simultânea em tempo real",
        "fallback": "Se o botão não funcionar, copie e cole este endereço no navegador:",
        "ignore": "Se você não fez esta solicitação, pode ignorar este e-mail com segurança.",
        "footer": "Você recebeu este e-mail porque ele foi usado no SelaVoice.",
        "verify_subject": "Confirme seu e-mail para ativar sua conta — SelaVoice",
        "verify_pre": "Falta só um passo: confirme seu e-mail para ativar sua conta.",
        "verify_title": "Confirme seu e-mail",
        "verify_hi": "Olá, {name}!",
        "verify_body": "Sua conta no <b>SelaVoice</b> foi criada, mas ainda está <b>inativa</b>. Para ativá-la, confirme que este e-mail é seu clicando no botão abaixo.",
        "verify_btn": "Confirmar e ativar minha conta",
        "verify_note": "Este link vale por <b>{n} horas</b> e só pode ser usado <b>uma vez</b>.",
        "invite_subject": "Convite para {org} no SelaVoice",
        "invite_pre": "Você foi convidado para fazer parte de uma organização no SelaVoice.",
        "invite_title": "Você foi convidado",
        "invite_body": "Você foi convidado(a) para a organização <b>{org}</b> no <b>SelaVoice</b>, a plataforma de tradução simultânea em tempo real.",
        "invite_btn": "Aceitar convite",
        "invite_note": "Este convite vale por <b>7 dias</b>.",
        "reset_subject": "Redefinição de senha — SelaVoice",
        "reset_pre": "Recebemos um pedido para criar uma nova senha.",
        "reset_title": "Redefinir sua senha",
        "reset_body": "Recebemos um pedido para <b>redefinir a senha</b> da sua conta no SelaVoice. Clique no botão abaixo para criar uma nova senha.",
        "reset_btn": "Criar nova senha",
        "reset_note": "Este link vale por <b>1 hora</b> e só pode ser usado <b>uma vez</b>. Se não foi você, sua senha continua a mesma.",
    },
    "en": {
        "tagline": "Real-time simultaneous translation",
        "fallback": "If the button does not work, copy and paste this address into your browser:",
        "ignore": "If you did not request this, you can safely ignore this email.",
        "footer": "You received this email because it was used on SelaVoice.",
        "verify_subject": "Confirm your email to activate your account — SelaVoice",
        "verify_pre": "One last step: confirm your email to activate your account.",
        "verify_title": "Confirm your email",
        "verify_hi": "Hello, {name}!",
        "verify_body": "Your <b>SelaVoice</b> account was created, but it is still <b>inactive</b>. To activate it, confirm this email address is yours by clicking the button below.",
        "verify_btn": "Confirm and activate my account",
        "verify_note": "This link is valid for <b>{n} hours</b> and can be used <b>only once</b>.",
        "invite_subject": "Invitation to {org} on SelaVoice",
        "invite_pre": "You have been invited to join an organization on SelaVoice.",
        "invite_title": "You have been invited",
        "invite_body": "You have been invited to the organization <b>{org}</b> on <b>SelaVoice</b>, the real-time simultaneous translation platform.",
        "invite_btn": "Accept invitation",
        "invite_note": "This invitation is valid for <b>7 days</b>.",
        "reset_subject": "Password reset — SelaVoice",
        "reset_pre": "We received a request to create a new password.",
        "reset_title": "Reset your password",
        "reset_body": "We received a request to <b>reset the password</b> of your SelaVoice account. Click the button below to create a new password.",
        "reset_btn": "Create new password",
        "reset_note": "This link is valid for <b>1 hour</b> and can be used <b>only once</b>. If it was not you, your password stays the same.",
    },
    "es": {
        "tagline": "Traducción simultánea en tiempo real",
        "fallback": "Si el botón no funciona, copie y pegue esta dirección en su navegador:",
        "ignore": "Si usted no hizo esta solicitud, puede ignorar este correo con tranquilidad.",
        "footer": "Recibió este correo porque fue utilizado en SelaVoice.",
        "verify_subject": "Confirme su correo para activar su cuenta — SelaVoice",
        "verify_pre": "Solo falta un paso: confirme su correo para activar su cuenta.",
        "verify_title": "Confirme su correo",
        "verify_hi": "¡Hola, {name}!",
        "verify_body": "Su cuenta de <b>SelaVoice</b> fue creada, pero aún está <b>inactiva</b>. Para activarla, confirme que este correo es suyo haciendo clic en el botón de abajo.",
        "verify_btn": "Confirmar y activar mi cuenta",
        "verify_note": "Este enlace vale por <b>{n} horas</b> y solo puede usarse <b>una vez</b>.",
        "invite_subject": "Invitación a {org} en SelaVoice",
        "invite_pre": "Lo invitaron a unirse a una organización en SelaVoice.",
        "invite_title": "Lo invitaron",
        "invite_body": "Lo invitaron a la organización <b>{org}</b> en <b>SelaVoice</b>, la plataforma de traducción simultánea en tiempo real.",
        "invite_btn": "Aceptar invitación",
        "invite_note": "Esta invitación vale por <b>7 días</b>.",
        "reset_subject": "Restablecimiento de contraseña — SelaVoice",
        "reset_pre": "Recibimos una solicitud para crear una nueva contraseña.",
        "reset_title": "Restablezca su contraseña",
        "reset_body": "Recibimos una solicitud para <b>restablecer la contraseña</b> de su cuenta de SelaVoice. Haga clic en el botón de abajo para crear una nueva contraseña.",
        "reset_btn": "Crear nueva contraseña",
        "reset_note": "Este enlace vale por <b>1 hora</b> y solo puede usarse <b>una vez</b>. Si no fue usted, su contraseña sigue igual.",
    },
}


def _t(lang: str) -> dict:
    return T.get(lang, T["pt"])


def _render(lang: str, *, preheader: str, title: str, greeting: str = "", body: str, button: str, link: str, note: str) -> str:
    """Modelo único de e-mail. `body`/`note` já chegam com HTML SEGURO (partes dinâmicas escapadas por quem chama)."""
    tx = _t(lang)
    base = settings.public_web_url.rstrip("/")
    logo = f"{base}/email/logo.png"
    link_h = html.escape(link)
    return f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{html.escape(title)}</title></head>
<body style="margin:0;padding:0;background:#eef2f8;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{html.escape(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f8;padding:32px 12px;">
 <tr><td align="center">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #dde4f0;">
   <tr><td style="height:5px;background:{BRAND};font-size:0;line-height:0;">&nbsp;</td></tr>
   <tr><td align="center" style="padding:30px 32px 6px;">
     <a href="{html.escape(base)}" style="text-decoration:none;"><img src="{html.escape(logo)}" width="190" alt="SelaVoice" style="display:block;border:0;height:auto;max-width:190px;"></a>
   </td></tr>
   <tr><td style="padding:22px 40px 8px;font-family:Arial,Helvetica,sans-serif;">
     <h1 style="margin:0 0 14px;font-size:26px;line-height:1.25;color:{INK};font-weight:700;">{html.escape(title)}</h1>
     {f'<p style="margin:0 0 10px;font-size:16px;line-height:1.6;color:{INK};font-weight:600;">{greeting}</p>' if greeting else ''}
     <p style="margin:0 0 26px;font-size:16px;line-height:1.65;color:#3b4760;">{body}</p>
     <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto 26px;"><tr>
       <td align="center" bgcolor="{BRAND}" style="border-radius:12px;">
         <a href="{link_h}" style="display:inline-block;padding:16px 34px;font-family:Arial,Helvetica,sans-serif;font-size:17px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:12px;background:{BRAND};">{html.escape(button)}</a>
       </td></tr></table>
     <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f8fd;border-radius:12px;"><tr><td style="padding:16px 18px;font-size:14px;line-height:1.6;color:#3b4760;">
       {note}
     </td></tr></table>
     <p style="margin:22px 0 6px;font-size:13px;line-height:1.5;color:#6b7a94;">{html.escape(tx['fallback'])}</p>
     <p style="margin:0 0 6px;font-size:13px;line-height:1.5;word-break:break-all;"><a href="{link_h}" style="color:{BRAND};text-decoration:underline;">{link_h}</a></p>
   </td></tr>
   <tr><td style="padding:22px 40px 30px;font-family:Arial,Helvetica,sans-serif;">
     <hr style="border:0;border-top:1px solid #e3e9f4;margin:0 0 18px;">
     <p style="margin:0 0 6px;font-size:13px;line-height:1.5;color:#6b7a94;">{html.escape(tx['ignore'])}</p>
     <p style="margin:0;font-size:12px;line-height:1.5;color:#98a3b8;"><b style="color:#6b7a94;">SelaVoice</b> · {html.escape(tx['tagline'])}<br>{html.escape(tx['footer'])}</p>
   </td></tr>
  </table>
 </td></tr>
</table></body></html>"""


def send_verification(to: str, name: str, token: str, lang: str = "pt") -> bool:
    """E-mail de CONFIRMAÇÃO do cadastro. O link leva a /verificar?token=... (uso único, vale 24 h)."""
    tx = _t(lang)
    link = f"{settings.public_web_url}/verificar?token={token}"
    who = html.escape((name or "").strip().split(" ")[0] or "")
    h = _render(lang, preheader=tx["verify_pre"], title=tx["verify_title"], greeting=html.escape(tx["verify_hi"].format(name=who)) if who else "",
                body=tx["verify_body"], button=tx["verify_btn"], link=link, note=tx["verify_note"].format(n=settings.email_verification_hours))
    text = f"{tx['verify_title']}\n\n{tx['verify_pre']}\n{tx['verify_btn']}: {link} ({settings.email_verification_hours} h)\n\n{tx['ignore']}"
    return send_email(to, tx["verify_subject"], h, text)[0]


def send_invite(to: str, org_name: str, token: str, lang: str = "pt") -> bool:
    tx = _t(lang)
    link = f"{settings.public_web_url}/invite?token={token}"
    h = _render(lang, preheader=tx["invite_pre"], title=tx["invite_title"], body=tx["invite_body"].format(org=html.escape(org_name)),
                button=tx["invite_btn"], link=link, note=tx["invite_note"])
    text = f"{tx['invite_title']}: {org_name}\n{tx['invite_btn']}: {link} (7 d)\n\n{tx['ignore']}"
    return send_email(to, tx["invite_subject"].format(org=org_name), h, text)[0]


def send_password_reset(to: str, token: str, lang: str = "pt") -> bool:
    tx = _t(lang)
    link = f"{settings.public_web_url}/reset?token={token}"
    h = _render(lang, preheader=tx["reset_pre"], title=tx["reset_title"], body=tx["reset_body"], button=tx["reset_btn"], link=link, note=tx["reset_note"])
    text = f"{tx['reset_title']}\n{tx['reset_btn']}: {link} (1 h)\n\n{tx['ignore']}"
    return send_email(to, tx["reset_subject"], h, text)[0]

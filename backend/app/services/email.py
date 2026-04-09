"""
Email service using Resend for transactional emails.
"""

import logging

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_verification_email(to_email: str, name: str, verification_url: str) -> bool:
    """Send a verification email to a newly registered user."""
    if not settings.resend_api_key:
        logger.warning("[Email] RESEND_API_KEY not set — skipping email to %s", to_email)
        return False

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": "Verifica tu cuenta — EcoRuta",
            "html": f"""
            <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 2rem;">
                <h2 style="color: #16a34a;">¡Bienvenido a EcoRuta, {name}!</h2>
                <p style="color: #374151; line-height: 1.6;">
                    Gracias por registrarte. Para activar tu cuenta, haz clic en el siguiente enlace:
                </p>
                <a href="{verification_url}"
                   style="display: inline-block; background: linear-gradient(135deg, #22c55e, #15803d);
                          color: white; padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: 700; margin: 1.5rem 0;">
                    Verificar mi cuenta
                </a>
                <p style="color: #6b7280; font-size: 0.875rem; line-height: 1.5;">
                    Si no creaste esta cuenta, puedes ignorar este correo.
                </p>
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 2rem 0;" />
                <p style="color: #9ca3af; font-size: 0.75rem;">EcoRuta — Sistema de Gestión de Residuos</p>
            </div>
            """,
        })
        logger.info("[Email] Verification email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("[Email] Failed to send to %s: %s", to_email, e)
        return False

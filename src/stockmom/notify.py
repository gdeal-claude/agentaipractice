"""리포트 전달: 이메일 (SMTP). 환경변수가 없으면 조용히 건너뛴다.

필요한 환경변수:
    SMTP_HOST      예: smtp.gmail.com
    SMTP_PORT      예: 587
    SMTP_USER      보내는 계정
    SMTP_PASSWORD  앱 비밀번호 (Gmail 은 2단계 인증 후 '앱 비밀번호' 발급)
    MAIL_TO        받는 사람 (쉼표로 여러 명)
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

__all__ = ["email_configured", "send_email"]

_REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_TO")


def email_configured(env: dict[str, str] | None = None) -> bool:
    env = env if env is not None else dict(os.environ)
    return all(env.get(k) for k in _REQUIRED)


def send_email(subject: str, body_markdown: str, *, env: dict[str, str] | None = None, smtp_factory=None) -> None:
    env = env if env is not None else dict(os.environ)
    if not email_configured(env):
        raise RuntimeError("이메일 환경변수가 설정되지 않았습니다: " + ", ".join(_REQUIRED))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env["SMTP_USER"]
    msg["To"] = env["MAIL_TO"]
    msg.set_content(body_markdown)

    factory = smtp_factory or smtplib.SMTP
    with factory(env["SMTP_HOST"], int(env.get("SMTP_PORT", "587"))) as smtp:
        smtp.ehlo()
        try:
            smtp.starttls()
        except smtplib.SMTPNotSupportedError:
            pass
        smtp.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
        smtp.send_message(msg)

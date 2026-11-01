"""Envío de mensajes por la API de bots de Telegram."""

import requests

MAX_LEN = 4000  # Telegram admite 4096; dejamos margen.


def _chunks(text: str) -> list[str]:
    """Trocea por líneas para no partir etiquetas HTML."""
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN and current:
            parts.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        parts.append(current)
    return parts


def send_message(token: str, chat_id: str, text: str) -> None:
    for chunk in _chunks(text):
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            },
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Telegram respondió {resp.status_code}: {resp.text[:300]}")

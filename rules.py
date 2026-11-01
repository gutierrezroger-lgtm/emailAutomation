"""Reglas previas baratas: deciden lo obvio y dejan el resto para la IA."""

from gmail_client import Email

VIP = "vip"          # importante sin pasar por la IA
DISCARD = "discard"  # no importante sin pasar por la IA
AI = "ai"            # lo decide Claude


def _matches(addr: str, entries: list[str]) -> bool:
    domain = "@" + addr.split("@")[-1] if "@" in addr else ""
    for entry in entries:
        entry = entry.strip().lower()
        if entry and (addr == entry or (entry.startswith("@") and domain == entry)):
            return True
    return False


def has_security_signal(mail: Email, keywords: list[str]) -> bool:
    text = f"{mail.subject} {mail.snippet}".lower()
    return any(k.lower() in text for k in keywords)


def triage(mail: Email, config: dict) -> tuple[str, str]:
    """Devuelve (decisión, motivo)."""
    if _matches(mail.from_addr, config.get("vip") or []):
        return VIP, "remitente VIP"
    if _matches(mail.from_addr, config.get("ignore") or []):
        return DISCARD, "remitente en lista de ignorados"
    if mail.category:
        return DISCARD, f"categoría Gmail: {mail.category}"
    if mail.is_bulk and not has_security_signal(mail, config.get("security_keywords") or []):
        return DISCARD, "correo masivo/newsletter"
    return AI, "dudoso"

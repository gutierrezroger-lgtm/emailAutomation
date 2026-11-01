"""Lectura de Gmail por IMAP en modo solo lectura (no marca nada como leído)."""

import email
import email.message
import email.policy
import imaplib
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup

IMAP_HOST = "imap.gmail.com"
# Solo se descargan los primeros 300 KB de cada email: suficiente para cabeceras y texto,
# y evita bajar adjuntos pesados.
PARTIAL_BYTES = 300_000


@dataclass
class Email:
    uid: str
    msgid: str
    from_name: str
    from_addr: str
    subject: str
    date: datetime
    snippet: str
    link: str
    is_bulk: bool
    category: str | None = None
    labels: list[str] = field(default_factory=list)


def _quote(query: str) -> str:
    return '"' + query.replace('"', '\\"') + '"'


def _search(conn: imaplib.IMAP4_SSL, query: str) -> list[str]:
    status, data = conn.uid("SEARCH", "X-GM-RAW", _quote(query))
    if status != "OK":
        raise RuntimeError(f"Búsqueda IMAP fallida: {query}")
    return data[0].decode().split() if data and data[0] else []


def _text_snippet(msg: email.message.EmailMessage, limit: int) -> str:
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
        if body is None:
            return ""
        try:
            content = body.get_content()
        except Exception:
            payload = body.get_payload(decode=True) or b""
            content = payload.decode(body.get_content_charset() or "utf-8", errors="replace")
        if body.get_content_type() == "text/html":
            content = BeautifulSoup(content, "html.parser").get_text(" ")
    except Exception:
        # Email truncado o mal formado: seguimos sin fragmento.
        return ""
    content = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", content)   # imágenes/enlaces markdown
    content = re.sub(r"https?://\S+", " ", content)            # URLs sueltas
    content = re.sub(r"[͏­᠎​-‏⁠-⁤﻿]", "", content)  # invisibles
    content = re.sub(r"[|\-]{3,}", " ", content)                # restos de tablas
    return re.sub(r"\s+", " ", content).strip()[:limit]


def _is_bulk(msg: email.message.EmailMessage) -> bool:
    precedence = str(msg.get("Precedence", "")).lower()
    auto = str(msg.get("Auto-Submitted", "")).lower()
    return bool(
        msg.get("List-Unsubscribe")
        or msg.get("List-Id")
        or precedence in ("bulk", "list", "junk")
        or (auto and auto != "no")
    )


def fetch_emails(user: str, app_password: str, start: datetime, end: datetime,
                 categories: list[str], snippet_chars: int) -> list[Email]:
    """Devuelve los emails de la bandeja de entrada recibidos en [start, end)."""
    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        conn.login(user, app_password)
        status, _ = conn.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("No se pudo abrir la bandeja de entrada")

        window = f"after:{int(start.timestamp())} before:{int(end.timestamp())}"
        uids = _search(conn, window)

        category_of: dict[str, str] = {}
        for cat in categories:
            for uid in _search(conn, f"{window} category:{cat}"):
                category_of[uid] = cat

        emails = []
        for uid in uids:
            status, data = conn.uid(
                "FETCH", uid, f"(X-GM-MSGID X-GM-LABELS BODY.PEEK[]<0.{PARTIAL_BYTES}>)"
            )
            if status != "OK" or not data or not isinstance(data[0], tuple):
                continue
            # Los atributos pueden llegar antes o después del cuerpo literal.
            trailing = b" ".join(part for part in data[1:] if isinstance(part, bytes))
            meta = (data[0][0] + b" " + trailing).decode(errors="replace")
            raw = data[0][1]
            msg = email.message_from_bytes(raw, policy=email.policy.default)

            msgid_match = re.search(r"X-GM-MSGID (\d+)", meta)
            msgid = msgid_match.group(1) if msgid_match else ""
            labels_match = re.search(r"X-GM-LABELS \((.*?)\)", meta)
            labels = re.findall(r'"[^"]*"|\S+', labels_match.group(1)) if labels_match else []

            try:
                date = parsedate_to_datetime(str(msg.get("Date")))
            except Exception:
                date = start
            if date.tzinfo is None:
                date = date.replace(tzinfo=start.tzinfo)

            name, addr = parseaddr(str(msg.get("From", "")))
            emails.append(Email(
                uid=uid,
                msgid=msgid,
                from_name=name or addr,
                from_addr=addr.lower(),
                subject=str(msg.get("Subject", "(sin asunto)")).strip() or "(sin asunto)",
                date=date,
                snippet=_text_snippet(msg, snippet_chars),
                link=f"https://mail.google.com/mail/u/0/#inbox/{int(msgid):x}" if msgid else "",
                is_bulk=_is_bulk(msg),
                category=category_of.get(uid),
                labels=[label.strip('"') for label in labels],
            ))
        return emails
    finally:
        try:
            conn.logout()
        except Exception:
            pass

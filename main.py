"""Resumen diario de emails importantes de Gmail enviado por Telegram.

Uso:
  python main.py                      ejecución normal (ventana ayer 10:00 -> hoy 10:00)
  python main.py --dry-run            muestra el resultado sin enviar nada a Telegram
  python main.py --since "2026-10-17 10:00"   ventana desde esa fecha hasta ahora
  python main.py --test-telegram      envía un mensaje de prueba
"""

import argparse
import html
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import rules
from classifier import classify
from gmail_client import Email, fetch_emails
from telegram_client import send_message

BASE_DIR = Path(__file__).resolve().parent


def load_env_file() -> None:
    """Carga un .env local si existe (en GitHub Actions se usan los Secrets)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name}")
    return value


def should_run_scheduled(tz: ZoneInfo, run_hour: int) -> bool:
    """GitHub programa dos crons UTC (verano/invierno); solo sigue el que cae a la hora local."""
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return True
    schedule = os.environ.get("GITHUB_SCHEDULE", "")
    offset_hours = int(datetime.now(tz).utcoffset().total_seconds() // 3600)
    expected_utc_hour = (run_hour - offset_hours) % 24
    cron_hour = schedule.split()[1] if len(schedule.split()) > 1 else ""
    return cron_hour == str(expected_utc_hour)


def compute_window(tz: ZoneInfo, run_hour: int, since: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(tz)
    if since:
        start = datetime.strptime(since, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        return start, now
    today_cut = datetime(now.year, now.month, now.day, run_hour, tzinfo=tz)
    end = today_cut if now >= today_cut else today_cut - timedelta(days=1)
    prev = end.date() - timedelta(days=1)
    start = datetime(prev.year, prev.month, prev.day, run_hour, tzinfo=tz)
    return start, end


def format_item(mail: Email, summary: str) -> str:
    sender = html.escape(mail.from_name)
    subject = html.escape(mail.subject)
    line = f"• <b>{sender}</b> — \"{subject}\""
    if summary:
        line += f"\n  {html.escape(summary)}"
    if mail.link:
        line += f" <a href=\"{mail.link}\">Abrir</a>"
    return line


def build_message(groups: dict[str, list[tuple[Email, str]]], total: int,
                  start: datetime, end: datetime, ai_failed: bool) -> str:
    count = sum(len(items) for items in groups.values())
    window = f"{start:%d/%m %H:%M} → {end:%d/%m %H:%M}"
    if count == 0:
        text = f"✅ Sin emails importantes ({total} revisados, {window})."
    else:
        text = f"📬 <b>Emails importantes</b> — {count} de {total} revisados\n<i>{window}</i>\n"
        titles = {"vip": "⭐ VIP", "persona": "👤 Personas", "seguridad": "🔐 Seguridad y cuentas"}
        for key, title in titles.items():
            if groups.get(key):
                text += f"\n<b>{title}</b>\n"
                text += "\n".join(format_item(m, s) for m, s in groups[key]) + "\n"
    if ai_failed:
        text += "\n⚠️ La IA no respondió: se clasificó solo con reglas (puede haber falsos positivos)."
    return text


def run(args: argparse.Namespace) -> None:
    config = yaml.safe_load((BASE_DIR / "config.yaml").read_text(encoding="utf-8"))
    tz = ZoneInfo(config.get("timezone", "Europe/Madrid"))
    run_hour = int(config.get("run_hour", 10))

    if args.test_telegram:
        send_message(env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID"),
                     "🤖 Prueba: el bot de resumen de emails funciona.")
        print("Mensaje de prueba enviado.")
        return

    if not should_run_scheduled(tz, run_hour):
        print("Cron fuera de la hora local configurada (cambio horario); no se hace nada.")
        return

    start, end = compute_window(tz, run_hour, args.since)
    print(f"Ventana: {start.isoformat()} -> {end.isoformat()}")

    emails = fetch_emails(env("GMAIL_USER"), env("GMAIL_APP_PASSWORD"), start, end,
                          config.get("discard_categories") or [],
                          int(config.get("snippet_chars", 300)))
    print(f"Emails encontrados: {len(emails)}")

    groups: dict[str, list[tuple[Email, str]]] = {"vip": [], "persona": [], "seguridad": []}
    vips: list[Email] = []
    pending: list[Email] = []
    for mail in emails:
        decision, reason = rules.triage(mail, config)
        print(f"  [{decision:7}] {mail.from_addr} | {mail.subject[:60]} ({reason})")
        if decision == rules.VIP:
            vips.append(mail)
        elif decision == rules.AI:
            pending.append(mail)

    ai_failed = False
    if pending or vips:
        # Los VIP también van a la IA, pero solo para obtener su resumen.
        try:
            decisions = classify(vips + pending, config.get("model", "claude-haiku-5-5"))
        except Exception as exc:
            print(f"Fallo de la IA, se usan solo reglas: {exc}")
            ai_failed = True
            decisions = {}
        for mail in vips:
            d = decisions.get(mail.uid)
            groups["vip"].append((mail, d.summary if d else mail.snippet[:150]))
        for mail in pending:
            d = decisions.get(mail.uid)
            if d is None:
                # Sin IA: lo que tiene señales de seguridad va a seguridad, el resto a personas.
                security = rules.has_security_signal(mail, config.get("security_keywords") or [])
                category = "seguridad" if security else "persona"
                groups[category].append((mail, mail.snippet[:150]))
                continue
            print(f"  [IA {'SÍ' if d.important else 'no'}] {mail.from_addr} | {d.reason}")
            if d.important and d.category in ("persona", "seguridad"):
                groups[d.category].append((mail, d.summary))

    message = build_message(groups, len(emails), start, end, ai_failed)
    print("\n--- Mensaje ---\n" + message)
    if args.dry_run:
        print("(dry-run: no se envía a Telegram)")
        return
    send_message(env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID"), message)
    print("Enviado a Telegram.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="no envía nada a Telegram")
    parser.add_argument("--since", help='inicio de la ventana, formato "YYYY-MM-DD HH:MM"')
    parser.add_argument("--test-telegram", action="store_true", help="envía un mensaje de prueba")
    args = parser.parse_args()
    args.dry_run = args.dry_run or os.environ.get("DRY_RUN", "").lower() == "true"
    args.since = args.since or os.environ.get("SINCE") or None

    load_env_file()
    try:
        run(args)
        return 0
    except Exception as exc:
        traceback.print_exc()
        if not args.dry_run:
            try:
                send_message(env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID"),
                             f"⚠️ La automatización de emails falló:\n<code>{html.escape(str(exc))[:500]}</code>")
            except Exception:
                traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

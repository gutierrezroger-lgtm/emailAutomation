"""Muestra el chat_id de Telegram. Antes, escribe cualquier mensaje a tu bot.

Uso: TELEGRAM_BOT_TOKEN=... python get_chat_id.py
"""

import os
import sys

import requests

token = os.environ.get("TELEGRAM_BOT_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not token:
    sys.exit("Pasa el token: python get_chat_id.py <TOKEN>")

updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
chats = {}
for update in updates.get("result", []):
    chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat")
    if chat:
        chats[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name")
if not chats:
    sys.exit("No hay mensajes. Escribe /start a tu bot en Telegram y vuelve a ejecutar.")
for chat_id, name in chats.items():
    print(f"chat_id = {chat_id}  ({name})")

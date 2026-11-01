# Resumen diario de emails importantes → Telegram

Todos los días a las **10:00 (hora de Madrid)**, GitHub Actions revisa la bandeja de entrada de Gmail. Analiza los emails recibidos entre **ayer a las 10:00 y hoy a las 10:00** y envía **un único mensaje por Telegram** con los importantes. Si no hay ninguno, envía un aviso corto de "sin novedades".

## Cómo decide qué es importante

1. **Reglas** (gratis, en [rules.py](rules.py) y [config.yaml](config.yaml)):
   - Los remitentes **VIP** se notifican siempre.
   - Se descartan los **ignorados**, las categorías Promociones, Social y Foros de Gmail, y los **correos masivos** (newsletters) que no traen señales de seguridad.
2. **Claude Haiku** ([classifier.py](classifier.py)) revisa el resto en una sola llamada. Marca como importante:
   - 👤 lo escrito por **personas reales**;
   - 🔐 los avisos de **seguridad y de cuentas**.

**Privacidad:** a Claude solo le llega el remitente, el asunto y unos 300 caracteres del inicio del email. Gmail se abre en **solo lectura**: no se marca nada como leído ni se modifica nada.

## Puesta en marcha (una sola vez, ~20 min)

### 1. Contraseña de aplicación de Gmail
1. Activa la verificación en 2 pasos: <https://myaccount.google.com/signinoptions/twosv>
2. Crea una contraseña de aplicación: <https://myaccount.google.com/apppasswords>. Ponle de nombre, por ejemplo, "Resumen emails" y copia los 16 caracteres sin espacios.
3. En Gmail, ve a ⚙️ → *Ver todos los ajustes* → *Reenvío y correo POP/IMAP* y comprueba que el **IMAP** está habilitado.

### 2. Bot de Telegram
1. En Telegram, abre **@BotFather** → `/newbot` → elige un nombre y copia el **token**.
2. Abre tu bot nuevo y envíale `/start`.
3. En el navegador, abre `https://api.telegram.org/bot<TOKEN>/getUpdates`, cambiando `<TOKEN>` por el tuyo. Busca `"chat":{"id":123456789` en la respuesta: ese número es tu **chat_id**.

   Si tienes Python, también puedes usar `python get_chat_id.py <TOKEN>`.

### 3. API key de Anthropic
1. Entra en <https://console.anthropic.com>, ve a *Billing* y añade crédito: con 5 $ sobra para muchos meses, porque con Haiku cuesta céntimos al mes.
2. Ve a *API Keys* → *Create Key* y copia la clave ().

### 4. Repositorio privado en GitHub
1. Crea un repo **privado** (por ejemplo `email-digest`) y sube esta carpeta.
2. Ve a *Settings* → *Secrets and variables* → *Actions* → *New repository secret* y crea estos secretos:

| Secreto | Valor |
|---|---|
| `GMAIL_USER` | gutierrez.roger@gmail.com |
| `GMAIL_APP_PASSWORD` | la contraseña de aplicación (16 caracteres) |
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `ANTHROPIC_WORKSPACE_ID` | solo si la clave es `sk-ant-usr-...`: el ID del workspace (`wrkspc_...`) |
| `TELEGRAM_BOT_TOKEN` | el token de BotFather |
| `TELEGRAM_CHAT_ID` | tu chat_id |

### 5. Primera prueba
1. Ve a la pestaña *Actions* → *Resumen diario de emails* → **Run workflow**.
2. Déjalo con `dry_run` marcado y pulsa *Run*. En los logs verás cada email y la decisión que se ha tomado (`vip`, `discard`, `ai` y el veredicto de la IA). También verás el mensaje que se enviaría.
3. Repítelo con `dry_run` **desmarcado** para recibir el mensaje en Telegram.

A partir de ahí se ejecuta solo cada día a las 10:00. GitHub puede retrasarlo unos minutos, pero la ventana de emails es siempre exacta.

## Ajustes
Edita [config.yaml](config.yaml) directamente en GitHub:
- `vip`: direcciones (`alguien@x.com`) o dominios (`@x.com`) que se notifican siempre.
- `ignore`: direcciones o dominios que no se notifican nunca.
- `security_keywords`: palabras que hacen que un email automático pase a revisión de la IA.
- `model`, `snippet_chars`, `run_hour`.

## Si algo falla
Si falla la conexión a Gmail o a Telegram, o falta un secreto, recibirás por Telegram "⚠️ La automatización de emails falló". Además, GitHub te enviará un email. Si la IA no responde, el resumen se envía igualmente, clasificado solo con reglas, y lo indica al final.

## Prueba en local (opcional, requiere Python 3.10+)
```bash
pip install -r requirements.txt
cp .env.example .env      # y rellénalo
python main.py --dry-run
python main.py --dry-run --since "2026-10-17 10:00"
python main.py --test-telegram
```

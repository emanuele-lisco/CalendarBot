from flask import Flask, request
import requests
import dateparser
from datetime import timedelta
import os, json

from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# --- ENV VARS (Render) ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "909404")
WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]
PHONE_NUMBER_ID = os.environ["PHONE_NUMBER_ID"]

# --- GOOGLE CALENDAR (Service Account via ENV JSON) ---
SCOPES = ["https://www.googleapis.com/auth/calendar"]

creds_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
creds = service_account.Credentials.from_service_account_info(
    creds_info, scopes=SCOPES
)
service = build("calendar", "v3", credentials=creds)


def invia_risposta(numero, testo):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "text": {"body": testo}
    }
    # Non blocchiamo il bot se WhatsApp API fallisce
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception:
        pass


def crea_evento(testo, numero):
    try:
        data = dateparser.parse(testo, languages=["it"])
        if not data:
            invia_risposta(
                numero,
                "Non sono riuscito ad aggiungere il nuovo impegno, questo è il mio messaggio di errore: 'data e ora non riconosciute'"
            )
            return

        evento = {
            "summary": testo,
            "start": {"dateTime": data.isoformat(), "timeZone": "Europe/Rome"},
            "end": {"dateTime": (data + timedelta(hours=1)).isoformat(), "timeZone": "Europe/Rome"},
        }

        service.events().insert(calendarId="primary", body=evento).execute()

        invia_risposta(
            numero,
            f"ho aggiunto un nuovo impegno il {data.strftime('%d/%m/%y')}. Evento: {testo}"
        )

    except Exception as e:
        invia_risposta(
            numero,
            f"Non sono riuscito ad aggiungere il nuovo impegno, questo è il mio messaggio di errore: '{str(e)}'"
        )


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # --- Verification handshake (Meta) ---
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge", "")
        return "Errore", 403

    # --- Incoming events (Meta) ---
    data = request.json
    try:
        value = data["entry"][0]["changes"][0]["value"]

        # a volte arrivano status / other events senza "messages"
        messages = value.get("messages", [])
        if not messages:
            return "ok", 200

        msg_obj = messages[0]
        numero = msg_obj.get("from")

        # supporto solo testo per ora
        testo = (msg_obj.get("text") or {}).get("body")
        if not testo or not numero:
            return "ok", 200

        crea_evento(testo, numero)

    except Exception:
        # non facciamo fallire la chiamata webhook di Meta
        return "ok", 200

    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

from flask import Flask, request
import requests
import dateparser
from datetime import timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

VERIFY_TOKEN = "909404"
WHATSAPP_TOKEN = "EAFyhS7Og6AgBQna7XPQHl568dbWSDZBwz10hpWZBvpcBohlFTWHeo6C5X6ZBKkoUzK0hcfdFDybHEZBAZCrWqt5hnSMhlxirgXymZAnvHJkEv78uHuZC1MHHiEUSIAa0zrjNgvALxxnZCE4TOWZC5opPEg5x6t62w6rSmTfAfDqZCkZBZAKUlTM1FnThS8seG8giOvjIDYDOcyxE41Gb5fZBQJz0UBlg4ZBzVCYQQ2yZAqizgwrtQcjsGIZBu5eIWQ6vucZCQtQLuktzPAk5UZBjnVNSLHoqSaH0Rv"
PHONE_NUMBER_ID = "1049838774869249"

SCOPES = ['https://www.googleapis.com/auth/calendar']
creds = service_account.Credentials.from_service_account_file(
    'credentials.json', scopes=SCOPES)
service = build('calendar', 'v3', credentials=creds)

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
    requests.post(url, headers=headers, json=payload)

def crea_evento(testo, numero):
    try:
        data = dateparser.parse(testo, languages=['it'])
        if not data:
            invia_risposta(numero, "Non riesco a capire data e ora.")
            return

        evento = {
            'summary': testo,
            'start': {'dateTime': data.isoformat(), 'timeZone': 'Europe/Rome'},
            'end': {'dateTime': (data + timedelta(hours=1)).isoformat(), 'timeZone': 'Europe/Rome'}
        }

        service.events().insert(calendarId='primary', body=evento).execute()

        invia_risposta(numero, f"Ho aggiunto un nuovo impegno il {data.strftime('%d/%m/%y')}. Evento: {testo}")

    except Exception as e:
        invia_risposta(numero, f"Errore: {str(e)}")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Errore", 403

    data = request.json
    msg = data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
    numero = data["entry"][0]["changes"][0]["value"]["messages"][0]["from"]

    crea_evento(msg, numero)
    return "ok", 200

app.run(host="0.0.0.0", port=10000)

from flask import Flask, request
import requests
from datetime import datetime, timedelta
import os, json
import re

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
creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
service = build("calendar", "v3", credentials=creds)

MONTHS_IT = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
}
WEEKDAYS_IT = [
    "lunedì", "lunedi", "martedì", "martedi", "mercoledì", "mercoledi",
    "giovedì", "giovedi", "venerdì", "venerdi", "sabato", "domenica"
]


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
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception:
        pass


def _clean_text(t: str) -> str:
    t = (t or "").strip().lower()
    t = t.replace("alle", " ").replace("ore", " ")
    t = t.replace("di mattina", " am").replace("del mattino", " am")
    t = t.replace("di sera", " pm").replace("della sera", " pm")
    t = t.replace("di pomeriggio", " pm")
    t = re.sub(r"[,\.;]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _apply_am_pm(hour: int, marker):
    if not marker:
        return hour
    marker = str(marker).strip().lower()
    if marker == "pm" and hour < 12:
        return hour + 12
    if marker == "am" and hour == 12:
        return 0
    return hour


def estrai_data_ora(testo: str):
    """
    Estrae datetime da testo in IT per formati comuni.
    Restituisce datetime (naive, Europe/Rome) oppure None.
    """
    t = _clean_text(testo)
    today = datetime.now().date()
    year_default = today.year

    # 0) rimuovi giorno settimana se presente (es. "mercoledì 11 marzo ...")
    for wd in WEEKDAYS_IT:
        if t.startswith(wd + " "):
            t = t[len(wd):].strip()

    # 1) relativo: oggi/domani/dopodomani + ora
    m = re.search(r"\b(oggi|domani|dopodomani)\b\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if m:
        rel = m.group(1)
        hh = int(m.group(2))
        mm = int(m.group(3) or 0)
        ampm = m.group(4)
        hh = _apply_am_pm(hh, ampm)

        base = today
        if rel == "domani":
            base = today + timedelta(days=1)
        elif rel == "dopodomani":
            base = today + timedelta(days=2)

        return datetime(base.year, base.month, base.day, hh, mm)

    # 2) formato numerico: dd/mm[/yyyy] + ora
    m = re.search(
        r"\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        t
    )
    if m:
        dd = int(m.group(1))
        mo = int(m.group(2))
        yy = m.group(3)
        hh = int(m.group(4))
        mm = int(m.group(5) or 0)
        ampm = m.group(6)
        hh = _apply_am_pm(hh, ampm)

        if yy:
            yy = int(yy)
            if yy < 100:
                yy += 2000
        else:
            yy = year_default

        try:
            return datetime(yy, mo, dd, hh, mm)
        except ValueError:
            return None

    # 3) formato testuale: dd mese [yyyy] + ora
    mesi_regex = "|".join(MONTHS_IT.keys())
    m = re.search(
        rf"\b(\d{{1,2}})\s+({mesi_regex})(?:\s+(\d{{2,4}}))?\b\s+(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)?",
        t
    )
    if m:
        dd = int(m.group(1))
        mo = MONTHS_IT[m.group(2)]
        yy = m.group(3)
        hh = int(m.group(4))
        mm = int(m.group(5) or 0)
        ampm = m.group(6)
        hh = _apply_am_pm(hh, ampm)

        if yy:
            yy = int(yy)
            if yy < 100:
                yy += 2000
        else:
            yy = year_default

        try:
            return datetime(yy, mo, dd, hh, mm)
        except ValueError:
            return None

    return None


def estrai_titolo_evento(testo: str) -> str:
    """
    Rimuove la parte di data/ora dal messaggio e lascia solo il titolo evento.
    Esempio: "11/02 09:00 lezione" -> "lezione"
    """
    t = (testo or "").strip()

    # Rimuove "oggi/domani/dopodomani HH[:MM]"
    t = re.sub(r"(?i)\b(oggi|domani|dopodomani)\b\s+\d{1,2}(?::\d{2})?\s*(am|pm)?", "", t).strip()

    # Rimuove "dd/mm[/yyyy] HH[:MM]"
    t = re.sub(r"(?i)\b\d{1,2}[\/\-]\d{1,2}(?:[\/\-]\d{2,4})?\b\s+\d{1,2}(?::\d{2})?\s*(am|pm)?", "", t).strip()

    # Rimuove "dd mese [yyyy] HH[:MM]"
    mesi_regex = "|".join(MONTHS_IT.keys())
    t = re.sub(
        rf"(?i)\b\d{{1,2}}\s+({mesi_regex})(?:\s+\d{{2,4}})?\b\s+\d{{1,2}}(?::\d{{2}})?\s*(am|pm)?",
        "",
        t
    ).strip()

    # Ripulisce eventuali separatori rimasti all'inizio
    t = re.sub(r"^[\-\:\,\.]+\s*", "", t).strip()
    t = re.sub(r"\s+", " ", t).strip()

    return t if t else "Impegno"


def crea_evento(testo, numero):
    try:
        dt = estrai_data_ora(testo)

        if not dt:
            invia_risposta(
                numero,
                "Non sono riuscito ad aggiungere il nuovo impegno: non riconosco data/ora.\n"
                "Esempi validi:\n"
                "- 11/03 09:00 lezione\n"
                "- 11 marzo 9 lezione\n"
                "- domani 18:30 cena"
            )
            return

        titolo = estrai_titolo_evento(testo)

        evento = {
            "summary": titolo,                 # titolo pulito (es. "lezione")
            "description": testo,              # (opzionale) salva il testo originale
            "start": {"dateTime": dt.isoformat(), "timeZone": "Europe/Rome"},
            "end": {"dateTime": (dt + timedelta(hours=1)).isoformat(), "timeZone": "Europe/Rome"},
        }

        calendar_id = os.environ.get("GCAL_CALENDAR_ID", "primary")
        created = service.events().insert(calendarId=calendar_id, body=evento).execute()

        if not created or not created.get("id"):
            raise Exception("Inserimento evento fallito (nessun id restituito).")

        event_id = created.get("id")
        html_link = created.get("htmlLink", "")

        msg = (
            f"ho aggiunto un nuovo impegno il {dt.strftime('%d/%m/%y')} alle {dt.strftime('%H:%M')}.\n"
            f"Evento: {titolo}\n"
            f"CalendarId: {calendar_id}\n"
            f"EventId: {event_id}"
        )

        if html_link:
            msg += f"\nLink: {html_link}"

        invia_risposta(numero, msg)

    except Exception as e:
        invia_risposta(
            numero,
            f"Non sono riuscito ad aggiungere il nuovo impegno, questo è il mio messaggio di errore: '{str(e)}'"
        )


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge", "")
        return "Errore", 403

    data = request.json
    try:
        value = data["entry"][0]["changes"][0]["value"]
        messages = value.get("messages", [])
        if not messages:
            return "ok", 200

        msg_obj = messages[0]
        numero = msg_obj.get("from")
        testo = (msg_obj.get("text") or {}).get("body")
        if not testo or not numero:
            return "ok", 200

        crea_evento(testo, numero)

    except Exception:
        return "ok", 200

    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

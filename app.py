import csv
import json
import hmac
import os
import re
import sqlite3
import secrets
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, time, timedelta
from io import BytesIO, StringIO
from pathlib import Path

APP_BASE_URL = os.getenv(
    "APP_BASE_URL",
    "https://smart-sports-event-system-bkdq4n4rdxpgw8xf8vrvjx.streamlit.app",
).strip().rstrip("/")

import qrcode
import reportlab
import streamlit as st
from PIL import Image
from pyzbar.pyzbar import decode
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sklearn.tree import DecisionTreeClassifier
import sports_db
from registration_links import get_registration_url
from sports_locations import CHENNAI_AREAS, SPORTS_LOCATIONS, filter_locations
from tournament_scheduler import build_matchups, schedule_matchups
from weather_planner import assess_weather_readiness


# ---------------- DATABASE ----------------

DATABASE_PATH = Path(
    os.environ.get("SPORTS_DATABASE_PATH", Path(__file__).with_name("sports_event.db"))
)
conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
cursor = conn.cursor()
CERTIFICATE_TEMPLATE = Path(__file__).parent / "assets" / "sports_certificate_template.png"
WEATHER_FORECAST_DAYS = 16
FONT_PATH = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
pdfmetrics.registerFont(TTFont("SportsCertificate", str(FONT_PATH)))


def ensure_schema():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            "class" TEXT,
            date_of_birth TEXT,
            emis_number TEXT,
            event TEXT,
            document_type TEXT,
            document_name TEXT,
            email TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT,
            participants INTEGER,
            allocated_event TEXT,
            competition_type TEXT NOT NULL DEFAULT 'individual'
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            competition_format TEXT NOT NULL,
            event_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            match_duration_minutes INTEGER NOT NULL,
            rest_minutes INTEGER NOT NULL,
            venues_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER NOT NULL REFERENCES tournament_schedules(id),
            match_number INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            participant_a TEXT NOT NULL,
            participant_b TEXT NOT NULL,
            venue TEXT NOT NULL DEFAULT '',
            event_date TEXT NOT NULL,
            start_time TEXT NOT NULL DEFAULT '',
            end_time TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            conflict_reason TEXT NOT NULL DEFAULT ''
        )
        """
    )

    cursor.execute("PRAGMA table_info(events)")
    event_columns = {row[1] for row in cursor.fetchall()}
    event_additions = {
        "event_date": "TEXT",
        "location": "TEXT NOT NULL DEFAULT ''",
        "venue_type": "TEXT NOT NULL DEFAULT 'indoor'",
        "competition_type": "TEXT NOT NULL DEFAULT 'individual'",
    }
    for column_name, column_definition in event_additions.items():
        if column_name not in event_columns:
            cursor.execute(
                f'ALTER TABLE events ADD COLUMN "{column_name}" {column_definition}'
            )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS organizer_inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            student_class TEXT,
            date_of_birth TEXT,
            emis_number TEXT,
            event TEXT,
            document_type TEXT,
            status TEXT,
            birth_certificate_name TEXT,
            birth_certificate_data BLOB,
            aadhar_card_name TEXT,
            aadhar_card_data BLOB,
            tenth_marksheet_name TEXT,
            tenth_marksheet_data BLOB,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            registration_id INTEGER,
            competition_type TEXT NOT NULL DEFAULT 'individual',
            team_name TEXT NOT NULL DEFAULT '',
            identity_verified INTEGER NOT NULL DEFAULT 0,
            identity_verified_at TEXT,
            review_reason TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT
        )
        """
    )

    cursor.execute('PRAGMA table_info(registrations)')
    registration_columns = [row[1] for row in cursor.fetchall()]
    required_registration_columns = {
        "name": "TEXT",
        "class": "TEXT",
        "date_of_birth": "TEXT",
        "emis_number": "TEXT",
        "event": "TEXT",
        "document_type": "TEXT",
        "document_name": "TEXT",
        "email": "TEXT",
        "competition_type": "TEXT NOT NULL DEFAULT 'individual'",
        "team_name": "TEXT NOT NULL DEFAULT ''",
        "roll_number": "TEXT NOT NULL DEFAULT ''",
        "gender": "TEXT NOT NULL DEFAULT ''",
        "mobile_number": "TEXT NOT NULL DEFAULT ''",
        "address": "TEXT NOT NULL DEFAULT ''",
        "guardian_contact_number": "TEXT NOT NULL DEFAULT ''",
        "institution_name": "TEXT NOT NULL DEFAULT ''",
        "department": "TEXT NOT NULL DEFAULT ''",
        "year_of_study": "TEXT NOT NULL DEFAULT ''",
        "class_section": "TEXT NOT NULL DEFAULT ''",
        "playing_position": "TEXT NOT NULL DEFAULT ''",
        "team_members_details": "TEXT NOT NULL DEFAULT ''",
        "previous_sports_experience": "TEXT NOT NULL DEFAULT ''",
        "medical_certificate_required": "INTEGER NOT NULL DEFAULT 0",
    }

    for column_name, column_type in required_registration_columns.items():
        if column_name not in registration_columns:
            try:
                cursor.execute(
                    f'ALTER TABLE registrations ADD COLUMN "{column_name}" {column_type}'
                )
            except sqlite3.OperationalError:
                pass

    cursor.execute("PRAGMA table_info(organizer_inbox)")
    organizer_columns = [row[1] for row in cursor.fetchall()]
    required_organizer_columns = {
        "birth_certificate_name": "TEXT",
        "birth_certificate_data": "BLOB",
        "aadhar_card_name": "TEXT",
        "aadhar_card_data": "BLOB",
        "tenth_marksheet_name": "TEXT",
        "tenth_marksheet_data": "BLOB",
        "registration_id": "INTEGER",
        "competition_type": "TEXT NOT NULL DEFAULT 'individual'",
        "team_name": "TEXT NOT NULL DEFAULT ''",
        "identity_verified": "INTEGER NOT NULL DEFAULT 0",
        "identity_verified_at": "TEXT",
        "review_reason": "TEXT NOT NULL DEFAULT ''",
        "reviewed_at": "TEXT",
        "student_id_card_name": "TEXT",
        "student_id_card_data": "BLOB",
        "photograph_name": "TEXT",
        "photograph_data": "BLOB",
        "bonafide_certificate_name": "TEXT",
        "bonafide_certificate_data": "BLOB",
        "date_of_birth_proof_name": "TEXT",
        "date_of_birth_proof_data": "BLOB",
        "medical_certificate_name": "TEXT",
        "medical_certificate_data": "BLOB",
    }

    for column_name, column_type in required_organizer_columns.items():
        if column_name not in organizer_columns:
            cursor.execute(
                f'ALTER TABLE organizer_inbox ADD COLUMN "{column_name}" {column_type}'
            )

    conn.commit()


ensure_schema()

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'organizer', 'student')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """
)
conn.commit()
sports_db.seed_admin_from_environment(db_path=DATABASE_PATH)


# ---------------- AI/ML EVENT ALLOCATION ----------------

X = [
    [1, 1],
    [1, 0],
    [0, 1],
    [0, 0],
    [1, 1],
    [1, 0],
]

y = [1, 0, 0, 0, 1, 0]

model = DecisionTreeClassifier(random_state=42)
model.fit(X, y)


# ---------------- PROFESSIONAL UI STYLING ----------------

st.set_page_config(
    page_title="Smart Sports Event Planning System",
    page_icon="🏆",
    layout="wide",
)

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        html, body, [class*="stApp"] {
            font-family: 'Inter', sans-serif;
            background: #f3f6fb;
            color: #17243b;
        }
        .block-container {
            max-width: 1280px;
            padding-top: 1.5rem;
            padding-bottom: 3rem;
        }
        [data-testid="stSidebar"] {
            background: #101d33;
        }
        .main-header {
            position: relative;
            overflow: hidden;
            padding: 1.6rem 2rem;
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 22px;
            background: linear-gradient(115deg, #101d33 0%, #18375a 60%, #145c61 100%);
            box-shadow: 0 16px 36px rgba(16, 29, 51, 0.14);
            color: #ffffff;
            font-size: 1.75rem;
            font-weight: 750;
            letter-spacing: -0.035em;
            margin-bottom: 0.35rem;
        }
        .sub-header {
            margin: -4.1rem 0 2.4rem 2rem;
            position: relative;
            color: #d3e2f1;
            font-size: 0.95rem;
            font-weight: 450;
        }
        .card {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 16px;
            padding: 1.25rem;
            box-shadow: 0 8px 22px rgba(15, 35, 65, 0.045);
        }
        .metric-box {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-top: 3px solid #2878b8;
            border-radius: 14px;
            padding: 1.1rem;
            margin-bottom: 1rem;
            min-height: 112px;
            box-shadow: 0 6px 18px rgba(15, 35, 65, 0.045);
        }
        .section-card {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 16px;
            padding: 1.35rem;
            margin: 0.85rem 0;
            box-shadow: 0 8px 22px rgba(15, 35, 65, 0.045);
        }
        .home-hero {
            padding: clamp(1.5rem, 4vw, 2.5rem);
            margin: 0.5rem 0 1.4rem;
            border-radius: 20px;
            background: linear-gradient(115deg, #12213a 0%, #1c4265 62%, #17615f 100%);
            color: #ffffff;
            box-shadow: 0 16px 34px rgba(16, 37, 63, 0.14);
        }
        .home-eyebrow {
            margin: 0 0 0.7rem;
            color: #a9d8d1;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.13em;
            text-transform: uppercase;
        }
        .home-hero h1 {
            margin: 0;
            color: #ffffff;
            font-size: clamp(2rem, 4.5vw, 3.2rem);
            font-weight: 750;
            letter-spacing: -0.045em;
            line-height: 1.08;
        }
        .home-hero p {
            max-width: 720px;
            margin: 0.9rem 0 0;
            color: #d7e5f0;
            font-size: 1.02rem;
            line-height: 1.7;
        }
        .home-hero h1 span {
            color: #a9d8d1;
        }
        .home-section-title {
            margin: 1.7rem 0 0.25rem;
            color: #17243b;
            font-size: 1.3rem;
            font-weight: 700;
            letter-spacing: -0.025em;
        }
        .home-section-caption {
            margin: 0 0 1rem;
            color: #64748b;
            font-size: 0.92rem;
        }
        .home-feature {
            height: 100%;
            min-height: 150px;
            padding: 1.2rem;
            border: 1px solid #e3eaf3;
            border-radius: 15px;
            background: #ffffff;
            box-shadow: 0 6px 18px rgba(15, 35, 65, 0.04);
        }
        .home-feature h3 {
            margin: 0 0 0.55rem;
            color: #1b3857;
            font-size: 1rem;
            font-weight: 700;
        }
        .home-feature p {
            margin: 0;
            color: #64748b;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        .home-workflow {
            padding: 1.15rem;
            border-left: 3px solid #2a8b86;
            border-radius: 0 12px 12px 0;
            background: #f8fafc;
        }
        .home-workflow strong {
            display: block;
            margin-bottom: 0.35rem;
            color: #1b3857;
        }
        .home-workflow span {
            color: #64748b;
            font-size: 0.88rem;
            line-height: 1.5;
        }
        .reference-card {
            background: #f8fafc;
            border: 1px solid #e3eaf3;
            border-radius: 14px;
            padding: 1rem;
            margin-bottom: 0.75rem;
        }
        .faq-card {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 14px;
            padding: 1rem;
            margin-bottom: 0.8rem;
        }
        .stButton > button {
            border-radius: 10px;
            font-weight: 650;
            transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
        }
        .stButton > button[kind="secondary"] {
            border: 1px solid #dce5ef;
            background: #ffffff;
            color: #334b66;
        }
        .stButton > button:hover {
            border-color: #7aa6c9;
            color: #163d60;
            transform: translateY(-1px);
        }
        .stButton > button[kind="primary"] {
            border: 1px solid #174d74;
            background: #174d74;
            color: #ffffff;
        }
        .stDownloadButton > button {
            border-radius: 10px;
            background: #176f68;
            color: #ffffff;
            font-weight: 650;
            border: 1px solid #176f68;
        }
        .stFileUploader > div {
            background: #ffffff;
            border-radius: 12px;
            border: 1px solid #dce5ef;
        }
        .stTextInput > div > div > input,
        .stSelectbox > div > div > div,
        .stDateInput > div > div > input {
            border-radius: 9px;
            background: #ffffff;
            border: 1px solid #dce5ef;
        }
        @media (max-width: 700px) {
            .block-container {
                padding-top: 0.8rem;
            }
            .main-header {
                padding: 1.2rem 1rem 3.5rem;
                font-size: 1.35rem;
            }
            .sub-header {
                margin: -3.2rem 0 2rem 1rem;
                font-size: 0.82rem;
            }
            .home-feature {
                min-height: auto;
                margin-bottom: 0.6rem;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------- QR CODE GENERATION ----------------

def create_qr(student_data):
    payload = (
        student_data
        if isinstance(student_data, str)
        else json.dumps({"SPORTS_EVENT": student_data})
    )
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------- CERTIFICATE ----------------

def create_certificate(
    name,
    event,
    award,
    team_name=None,
    event_date=None,
    event_time=None,
):
    buffer = BytesIO()
    page_width, page_height = landscape(letter)
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    pdf.setTitle(f"Sports Certificate - {name}")
    pdf.drawImage(ImageReader(str(CERTIFICATE_TEMPLATE)), 0, 0, page_width, page_height)

    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(105, 220, page_width - 210, 98, stroke=0, fill=1)
    pdf.rect(130, 326, page_width - 260, 42, stroke=0, fill=1)
    pdf.setFillColorRGB(0.08, 0.08, 0.08)
    font_size = 24
    while font_size > 12 and pdfmetrics.stringWidth(name, "SportsCertificate", font_size) > page_width - 190:
        font_size -= 1
    pdf.setFont("SportsCertificate", font_size)
    pdf.drawCentredString(page_width / 2, 344, name)
    pdf.setStrokeColorRGB(0.25, 0.25, 0.25)
    pdf.setLineWidth(1)
    pdf.line(145, 337, page_width - 145, 337)

    pdf.setFillColorRGB(0.48, 0.29, 0.12)
    pdf.setFont("SportsCertificate", 15)
    pdf.drawCentredString(page_width / 2, 297, award)
    pdf.setFillColorRGB(0.08, 0.08, 0.08)
    pdf.setFont("SportsCertificate", 13)
    pdf.drawCentredString(page_width / 2, 270, f"Event: {event}")
    if event_date is not None and event_time is not None:
        pdf.setFont("SportsCertificate", 11)
        pdf.drawCentredString(
            page_width / 2,
            246,
            f"Conducted: {event_date:%d/%m/%Y} at {event_time:%I:%M %p}",
        )
    if team_name:
        pdf.setFont("SportsCertificate", 11)
        pdf.drawCentredString(page_width / 2, 228, f"Team: {team_name}")
    certificate_id = f"SSP-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"
    pdf.setFont("SportsCertificate", 8)
    pdf.drawRightString(page_width - 105, 207, f"Certificate ID: {certificate_id}")

    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(120, 145, 230, 29, stroke=0, fill=1)
    pdf.setFillColorRGB(0.08, 0.08, 0.08)
    pdf.setFont("SportsCertificate", 12)
    pdf.drawCentredString(235, 155, f"Date: {date.today():%d/%m/%Y}")
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def certificate_access_granted():
    access_code = ""
    try:
        access_code = str(
            st.secrets.get("SPORTS_CERTIFICATE_ACCESS_CODE", "")
        ).strip()
    except FileNotFoundError:
        pass
    if not access_code:
        access_code = os.environ.get("SPORTS_CERTIFICATE_ACCESS_CODE", "").strip()
    if not access_code:
        st.error(
            "Certificate generation is locked. Configure "
            "SPORTS_CERTIFICATE_ACCESS_CODE on the server."
        )
        return False
    if st.session_state.get("certificate_access_granted"):
        return True

    with st.form("certificate_access_gate"):
        entered_code = st.text_input("Organizer certificate password", type="password")
        submitted = st.form_submit_button("Unlock certificate generation")
    if submitted:
        if hmac.compare_digest(entered_code, access_code):
            st.session_state["certificate_access_granted"] = True
            st.rerun()
        st.error("Organizer certificate password is incorrect.")
    return False


def get_outdoor_forecast(location, event_date):
    location = location.strip()
    if len(location) < 2:
        raise ValueError("Enter a city or location to look up the outdoor forecast.")
    if not date.today() <= event_date <= date.today() + timedelta(days=WEATHER_FORECAST_DAYS - 1):
        raise ValueError("Weather forecasts are available only for today through the next 15 days.")

    def request_json(url):
        request = urllib.request.Request(url, headers={"User-Agent": "SmartSportsEventPlanningSystem/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))

    geocoding_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": location, "count": 1, "language": "en", "format": "json"}
    )
    try:
        locations = request_json(geocoding_url).get("results", [])
        if not locations:
            raise ValueError(f"No matching location was found for '{location}'.")
        selected_location = locations[0]
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {
                "latitude": selected_location["latitude"],
                "longitude": selected_location["longitude"],
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,wind_speed_10m_max"
                ),
                "forecast_days": WEATHER_FORECAST_DAYS,
                "timezone": "auto",
            }
        )
        daily = request_json(forecast_url)["daily"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Weather service returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach the weather service: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"The weather service returned an invalid response: {exc}") from exc

    try:
        index = daily["time"].index(event_date.isoformat())
        forecast = {
            "location": ", ".join(
                part for part in (
                    selected_location.get("name"),
                    selected_location.get("admin1"),
                    selected_location.get("country"),
                ) if part
            ),
            "temperature_max": daily["temperature_2m_max"][index],
            "temperature_min": daily["temperature_2m_min"][index],
            "precipitation_probability": daily["precipitation_probability_max"][index],
            "wind_speed": daily["wind_speed_10m_max"][index],
            "weather_code": daily["weather_code"][index],
        }
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RuntimeError("The forecast does not contain all required conditions for this date.") from exc

    if any(
        forecast[key] is None
        for key in ("temperature_max", "temperature_min", "precipitation_probability", "wind_speed", "weather_code")
    ):
        raise RuntimeError("The weather service did not provide complete forecast values for this date.")
    weather_descriptions = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle",
        55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Heavy freezing drizzle",
        61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain",
        67: "Heavy freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
        77: "Snow grains", 80: "Light rain showers", 81: "Rain showers",
        82: "Heavy rain showers", 85: "Light snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
    }
    forecast["description"] = weather_descriptions.get(
        forecast["weather_code"], "Unclassified weather conditions"
    )
    precipitation = forecast["precipitation_probability"]
    wind_speed = forecast["wind_speed"]
    high_temperature = forecast["temperature_max"]
    if (
        precipitation >= 60
        or wind_speed >= 40
        or high_temperature >= 38
        or forecast["weather_code"] in {65, 67, 75, 82, 86, 95, 96, 99}
    ):
        forecast["advice"] = "High weather risk: consider postponing and check local safety guidance."
    elif precipitation >= 30 or wind_speed >= 30 or high_temperature >= 35:
        forecast["advice"] = "Conditions may affect play: monitor updates and prepare a backup plan."
    else:
        forecast["advice"] = "No major risk indicated by these forecast thresholds; continue monitoring updates."
    return forecast


# ---------------- APPLICATION ----------------

st.markdown(
    '<div class="main-header">🏆 Smart Sports Event Planning System</div>',
    unsafe_allow_html=True,
)
feature_options = [
    "Home",
    "QR Event Registration",
    "Organizer Inbox",
    "Registration Records",
    "Event Allocation",
    "Tournament Scheduler",
    "Certificate Generation",
    "Sports Locations",
    "Help Center",
]
staff_only_pages = {
    "Organizer Inbox",
    "Registration Records",
    "Event Allocation",
    "Tournament Scheduler",
    "Certificate Generation",
}
registration_link_requested = st.query_params.get("register") == "1"
if "selected_menu" not in st.session_state:
    st.session_state["selected_menu"] = "Home"

if (
    registration_link_requested
    and st.session_state["selected_menu"] == "Home"
):
    st.session_state["selected_menu"] = "QR Event Registration"

menu = st.session_state["selected_menu"]

st.caption("WORKSPACE")
for row_start in range(0, len(feature_options), 3):
    navigation_columns = st.columns(3)
    for column, option_index in zip(
        navigation_columns,
        range(row_start, min(row_start + 3, len(feature_options))),
    ):
        option = feature_options[option_index]
        with column:
            if st.button(
                option,
                key=f"navigate_{option_index}",
                type="primary" if menu == option else "secondary",
                use_container_width=True,
            ):
                st.session_state["selected_menu"] = option
                st.rerun()

if st.session_state.get("certificate_access_granted"):
    if st.sidebar.button("Lock certificate access", key="lock_certificate_access"):
        st.session_state.pop("certificate_access_granted", None)
        st.rerun()

staff_user = st.session_state.get("staff_user")
if staff_user and staff_user.get("role") in {"admin", "organizer"}:
    st.sidebar.caption(f"Signed in as {staff_user['name']} ({staff_user['role']})")
    if st.sidebar.button("Sign out", key="staff_sign_out"):
        st.session_state.pop("staff_user", None)
        st.session_state.pop("certificate_access_granted", None)
        st.rerun()


def staff_login_required():
    staff_user = st.session_state.get("staff_user")
    if staff_user and staff_user.get("role") in {"admin", "organizer"}:
        return True

    st.header("Staff sign in")
    st.info("Staff sign-in is required to view registration records and manage events.")
    if not os.environ.get("SPORTS_ADMIN_EMAIL") or not os.environ.get(
        "SPORTS_ADMIN_PASSWORD"
    ):
        st.warning(
            "Configure SPORTS_ADMIN_EMAIL and SPORTS_ADMIN_PASSWORD on the server "
            "to create the first administrator account."
        )
    with st.form("staff_login_form"):
        email = st.text_input("Staff email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        staff_user = sports_db.authenticate(email, password, db_path=DATABASE_PATH)
        if staff_user and staff_user["role"] in {"admin", "organizer"}:
            st.session_state["staff_user"] = staff_user
            st.rerun()
        st.error("The email or password is incorrect, or the account is not staff.")
    return False


if menu in staff_only_pages and not staff_login_required():
    st.stop()

# ---------------- ORGANIZER INBOX ----------------

def add_to_organizer_inbox(
    student_name,
    student_class,
    dob,
    emis_number,
    event,
    document_type,
    birth_certificate,
    aadhar_card,
    tenth_marksheet,
    registration_id,
    competition_type,
    team_name,
    student_id_card,
    photograph,
    bonafide_certificate,
    date_of_birth_proof,
    medical_certificate,
):
    cursor.execute(
        """
        INSERT INTO organizer_inbox
        (student_name, student_class, date_of_birth, emis_number, event, document_type, status,
         birth_certificate_name, birth_certificate_data, aadhar_card_name, aadhar_card_data,
         tenth_marksheet_name, tenth_marksheet_data, registration_id, competition_type, team_name,
         student_id_card_name, student_id_card_data, photograph_name, photograph_data,
         bonafide_certificate_name, bonafide_certificate_data, date_of_birth_proof_name,
         date_of_birth_proof_data, medical_certificate_name, medical_certificate_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            student_name,
            student_class,
            dob,
            emis_number,
            event,
            document_type,
            "Pending",
            birth_certificate.name if birth_certificate else None,
            birth_certificate.getvalue() if birth_certificate else None,
            aadhar_card.name if aadhar_card else None,
            aadhar_card.getvalue() if aadhar_card else None,
            tenth_marksheet.name if tenth_marksheet else None,
            tenth_marksheet.getvalue() if tenth_marksheet else None,
            registration_id,
            competition_type,
            team_name,
            student_id_card.name if student_id_card else None,
            student_id_card.getvalue() if student_id_card else None,
            photograph.name if photograph else None,
            photograph.getvalue() if photograph else None,
            bonafide_certificate.name if bonafide_certificate else None,
            bonafide_certificate.getvalue() if bonafide_certificate else None,
            date_of_birth_proof.name if date_of_birth_proof else None,
            date_of_birth_proof.getvalue() if date_of_birth_proof else None,
            medical_certificate.name if medical_certificate else None,
            medical_certificate.getvalue() if medical_certificate else None,
        ),
    )
    conn.commit()


# ---------------- HOME PAGE ----------------

if menu == "Home":
    st.markdown('<div class="home-section-title">School Event Registration Hub</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <section class="home-hero">
            <h1>Register. Verify.<br><span>Compete.</span></h1>
            <p>Student registration, document verification, event allocation and
            certificates — all in one place.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "Start a registration →",
        key="home_start_registration",
        type="primary",
    ):
        st.session_state["selected_menu"] = "QR Event Registration"
        st.rerun()

    cursor.execute(
        """
        SELECT
            (SELECT COUNT(DISTINCT event_name) FROM events
             WHERE TRIM(COALESCE(event_name, '')) != ''),
            (SELECT COUNT(*) FROM registrations),
            (SELECT COUNT(*) FROM events
             WHERE LOWER(TRIM(COALESCE(allocated_event, ''))) = 'allocated')
        """
    )
    sport_count, registration_count, allocated_count = cursor.fetchone()

    metric_data = (
        ("Sports", sport_count),
        ("Registrations", registration_count),
        ("Allocated", allocated_count),
    )
    metric_columns = st.columns(3)
    for column, (label, value) in zip(metric_columns, metric_data):
        with column:
            st.markdown(
                f'<div class="metric-box"><div style="color:#64748b;font-size:.84rem;font-weight:600">{label}</div>'
                f'<div style="color:#173b5b;font-size:2rem;font-weight:750;line-height:1.35">{value}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="home-section-title">Why this portal matters</div>', unsafe_allow_html=True)
    st.markdown(
        """
        - Fast and transparent student registration
        - Direct submission to the organizer inbox
        - Document verification for age and eligibility
        - Event allocation based on slot availability
        - Digital certificate generation
        """
    )

    st.markdown('<div class="home-section-title">Event preparation checklist</div>', unsafe_allow_html=True)
    st.markdown(
        """
        1. Confirm the student's class, EMIS ID, DOB, and sports event.
        2. Upload the required document for the grade level.
        3. Review the organizer inbox for approval updates.
        4. Download the QR code and certificate after confirmation.
        """
    )

    st.markdown('<div class="home-section-title">Organizer contact</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="section-card">
            <strong>Mr. Anban Daniel</strong><br>
            <a href="mailto:organizer@sportsportal.edu">organizer@sportsportal.edu</a><br>
            <code>+91 98765 43210</code><br>
            Mon–Sat · 9:00 AM – 5:00 PM
        </div>
        """,
        unsafe_allow_html=True,
    )

# =================================================
# SPORTS LOCATIONS
# =================================================

elif menu == "Sports Locations":
    from html import escape
    from urllib.parse import quote_plus

    st.header("Sports Locations")
    st.caption(
        "Explore sample indoor and outdoor sports facilities across Chennai and Chengalpattu. "
        "Use the filters to find a sport or area."
    )
    st.info(
        "Sample directory only: venue names, addresses, hours, and availability are illustrative, "
        "not verified live listings. Confirm details directly before travelling or paying."
    )
    st.markdown(
        """
        <style>
        .sports-locations-visual {
            width: 100%;
            overflow: hidden;
            border-radius: 0.75rem;
            margin-bottom: 0.6rem;
        }
        .sports-locations-visual svg {
            display: block;
            width: 100%;
            height: auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def clear_sports_location_filters():
        st.session_state["sports_locations_search"] = ""
        st.session_state["sports_locations_category"] = "All"
        st.session_state["sports_locations_sport"] = "All"
        st.session_state["sports_locations_area_filter"] = "All"
        st.session_state["sports_locations_nearby"] = False
        st.session_state["sports_locations_nearby_area"] = sorted(CHENNAI_AREAS)[0]
        st.session_state["sports_locations_nearby_radius"] = 10

    search_columns = st.columns([2, 1, 1, 1])
    with search_columns[0]:
        location_query = st.text_input(
            "Search by venue or area",
            placeholder="Try Tambaram, Chengalpattu, or badminton",
            key="sports_locations_search",
        )
    with search_columns[1]:
        category_filter = st.selectbox(
            "Indoor or outdoor",
            ["All", "Indoor", "Outdoor"],
            key="sports_locations_category",
        )
    with search_columns[2]:
        sport_filter = st.selectbox(
            "Sport",
            ["All"] + sorted({location.sport for location in SPORTS_LOCATIONS}),
            key="sports_locations_sport",
        )
    with search_columns[3]:
        area_filter = st.selectbox(
            "Place / area",
            ["All"] + sorted(CHENNAI_AREAS),
            key="sports_locations_area_filter",
        )

    nearby_columns = st.columns([1, 2, 1])
    with nearby_columns[0]:
        show_nearby = st.checkbox("Show nearby locations", key="sports_locations_nearby")
    nearby_area = None
    nearby_radius = None
    if show_nearby:
        with nearby_columns[1]:
            nearby_area = st.selectbox(
                "Choose an area",
                sorted(CHENNAI_AREAS),
                key="sports_locations_nearby_area",
            )
        with nearby_columns[2]:
            nearby_radius = st.slider(
                "Within (km)",
                min_value=1,
                max_value=30,
                value=10,
                key="sports_locations_nearby_radius",
            )
        st.caption(
            "Nearby distances are approximate straight-line distances from the selected area, "
            "not road travel distances."
        )

    center = CHENNAI_AREAS[nearby_area] if nearby_area else None
    filtered_locations = filter_locations(
        query=location_query,
        category=category_filter,
        sport=sport_filter,
        center=center,
        radius_km=nearby_radius,
        area=area_filter,
    )

    booking_location_name = st.session_state.get("sports_location_booking")
    booking_location = next(
        (location for location in SPORTS_LOCATIONS if location.name == booking_location_name),
        None,
    )
    if booking_location:
        with st.container(border=True):
            st.subheader(f"Request a ground booking: {booking_location.name}")
            st.caption(
                "This demo prepares a request only; it is not sent to the venue and does not "
                "reserve a ground. Availability must be confirmed directly."
            )
            with st.form("sports_location_booking_form"):
                player_name = st.text_input("Player name")
                player_contact = st.text_input(
                    "Contact number",
                    help="Used only to display your request here; it is not saved or sent.",
                )
                booking_date = st.date_input(
                    "Preferred date",
                    min_value=date.today(),
                    key="sports_location_booking_date",
                )
                booking_time = st.time_input(
                    "Preferred start time",
                    value=time(9, 0),
                    key="sports_location_booking_time",
                )
                booking_submitted = st.form_submit_button("Prepare booking request")
            if booking_submitted:
                if not player_name.strip() or not player_contact.strip():
                    st.error("Enter your name and contact number to prepare the request.")
                else:
                    st.success(
                        f"Request prepared for {player_name.strip()} — "
                        f"{booking_location.sport} at {booking_location.area} on "
                        f"{booking_date:%d/%m/%Y} at {booking_time:%I:%M %p}. "
                        "This was not sent or booked; contact the venue to confirm."
                    )
            if st.button("Close booking request", key="sports_location_booking_close"):
                st.session_state.pop("sports_location_booking", None)
                st.rerun()

    if not filtered_locations:
        st.info(
            "No sample locations match these filters. Clear the place selection or try "
            "another venue search, sport, or category."
        )
        st.button(
            "Clear all filters",
            key="sports_locations_clear_filters",
            on_click=clear_sports_location_filters,
        )
    else:
        st.caption(
            f"Showing {len(filtered_locations)} sample location(s)"
            + (f" nearest to {nearby_area}." if nearby_area else ".")
        )
        card_columns = st.columns(3)
        for index, (location, distance) in enumerate(filtered_locations):
            with card_columns[index % len(card_columns)]:
                with st.container(border=True):
                    background = "#dcefe4" if location.category == "Outdoor" else "#e2edf8"
                    court_color = "#28734b" if location.category == "Outdoor" else "#285f91"
                    sport_icons = {
                        "Badminton": (
                            '<path d="M296 88h48l13 35-37 25-37-25z"/>'
                            '<path d="m296 88 24 60m24-60-24 60m-37-25 61 0"/>'
                            '<ellipse cx="320" cy="157" rx="13" ry="8"/>'
                        ),
                        "Table Tennis": (
                            '<ellipse cx="304" cy="102" rx="25" ry="30"/>'
                            '<path d="m318 126 22 24m35-60a11 11 0 1 0 0 .1"/>'
                            '<path d="M271 155h98"/>'
                        ),
                        "Chess": (
                            '<path d="M294 151h52l-5-12h-42zM301 139l5-25h28l5 25"/>'
                            '<path d="m307 114 4-13h20l4 13m-25-13h22l-5-12h-12z"/>'
                            '<path d="M298 157h44"/>'
                        ),
                        "Carrom": (
                            '<rect x="282" y="77" width="76" height="76" rx="5"/>'
                            '<circle cx="291" cy="86" r="5"/><circle cx="349" cy="86" r="5"/>'
                            '<circle cx="291" cy="144" r="5"/><circle cx="349" cy="144" r="5"/>'
                            '<circle cx="320" cy="115" r="11"/>'
                            '<circle cx="305" cy="104" r="6"/><circle cx="335" cy="126" r="6"/>'
                        ),
                        "Basketball (Indoor Court)": (
                            '<circle cx="320" cy="115" r="43"/>'
                            '<path d="M279 101q41 16 82 0M279 129q41-16 82 0"/>'
                            '<path d="M306 74q28 41 0 82m28-82q-28 41 0 82"/>'
                        ),
                        "Cricket": (
                            '<path d="m297 145 39-66 15 9-39 66z"/>'
                            '<path d="m298 145-8 13 14 2 8-13m48-52v55m16-55v55m-20-42h24"/>'
                            '<path d="M346 148h24"/>'
                        ),
                        "Football": (
                            '<circle cx="320" cy="115" r="43"/>'
                            '<path d="m320 96 18 13-7 21h-22l-7-21z"/>'
                            '<path d="m320 96 2-23m16 36 22-8m-22 29 14 20m-32-20-14 20m-7-41-22-8"/>'
                        ),
                        "Volleyball": (
                            '<circle cx="320" cy="115" r="43"/>'
                            '<path d="M290 83q17 30 61 48m-73 1q34-4 64-43m-33 68q12-38 49-53"/>'
                        ),
                        "Hockey": (
                            '<path d="M299 78v58q0 17 18 17h18"/>'
                            '<path d="m299 113 37-36 11 11-35 35"/>'
                            '<circle cx="365" cy="147" r="7"/>'
                        ),
                        "Kabaddi": (
                            '<circle cx="320" cy="83" r="11"/>'
                            '<path d="m314 96-15 24 25 12 16-18m-26-18 25 7 15-15m-39 30-12 30m26-18 20 18"/>'
                            '<path d="m299 120-17 1m58-7 17 6"/>'
                        ),
                    }
                    illustration = (
                        f'<div class="sports-locations-visual">'
                        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 230" '
                        f'role="img" aria-label="{escape(location.sport)} facility illustration">'
                        f'<rect width="640" height="230" rx="18" fill="{background}"/>'
                        f'<rect x="22" y="24" width="596" height="182" rx="12" fill="{court_color}"/>'
                        f'<path d="M320 24v182M22 115h596" stroke="white" stroke-opacity=".62" '
                        f'stroke-width="3"/>'
                        f'<rect x="110" y="52" width="420" height="126" fill="none" '
                        f'stroke="white" stroke-opacity=".65" stroke-width="3"/>'
                        f'<circle cx="320" cy="115" r="44" fill="{background}" '
                        f'stroke="white" stroke-opacity=".72" stroke-width="3"/>'
                        f'<g fill="none" stroke="#173b5b" stroke-width="5" '
                        f'stroke-linecap="round" stroke-linejoin="round">'
                        f'{sport_icons[location.sport]}</g>'
                        f'<text x="42" y="55" fill="white" font-size="15" font-weight="700" '
                        f'font-family="Arial, sans-serif">{escape(location.category.upper())} '
                        f'FACILITY</text></svg></div>'
                    )
                    st.markdown(illustration, unsafe_allow_html=True)
                    st.subheader(location.name)
                    st.markdown(
                        f"**{location.sport}** · {location.category}  \n"
                        f"**Area:** {location.area}"
                        + (
                            f" · **{distance:.1f} km away**"
                            if distance is not None
                            else ""
                        )
                    )
                    st.write(f"**Address:** {location.address}")
                    st.write(f"**Facilities:** {location.facilities}")
                    opening_time, closing_time = location.opening_hours.split(" - ", maxsplit=1)
                    st.write(f"**Opens:** {opening_time} · **Closes:** {closing_time}")
                    st.write(f"**Contact:** {location.contact}")
                    st.write(f"**Ground availability:** {location.availability}")
                    map_query = quote_plus(
                        f"{location.sport} sports facilities near {location.area}, Tamil Nadu"
                    )
                    map_url = (
                        "https://www.google.com/maps/search/?api=1&query="
                        f"{map_query}"
                    )
                    if center:
                        directions_url = (
                            "https://www.google.com/maps/dir/?api=1&origin="
                            f"{quote_plus(nearby_area + ', Tamil Nadu')}&destination={map_query}"
                        )
                        st.link_button(
                            "Get directions",
                            directions_url,
                            use_container_width=True,
                        )
                    else:
                        st.link_button(
                            "Open in Google Maps",
                            map_url,
                            use_container_width=True,
                        )
                    if st.button(
                        "Request booking",
                        key=f"sports_location_book_{index}",
                        use_container_width=True,
                    ):
                        st.session_state["sports_location_booking"] = location.name
                        st.rerun()

# =================================================
# 1. QR EVENT REGISTRATION
# =================================================

elif menu == "QR Event Registration":
    st.header("📱 Student QR Event Registration")

    cursor.execute(
        """SELECT event_name, competition_type FROM events
           WHERE allocated_event='Allocated' ORDER BY id DESC"""
    )
    allocated_events = cursor.fetchall()
    event_formats = {}
    for allocated_event_name, allocated_format, *_ in allocated_events:
        event_formats.setdefault(allocated_event_name, allocated_format)

    event_options = list(event_formats) or [
        "Athletics",
        "Basketball",
        "Cricket",
        "Football",
        "Volleyball",
        "Table Tennis",
        "Badminton",
    ]

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write(
        "Enter the student's name, class/section, and EMIS number. The QR will open "
        "the registration form with these details prefilled."
    )
    qr_col1, qr_col2 = st.columns(2)
    with qr_col1:
        qr_student_name = st.text_input("Student Name", key="qr_student_name")
        qr_class_section = st.text_input("Class / Section", key="qr_class_section")
    with qr_col2:
        qr_emis_number = st.text_input("EMIS Number", key="qr_emis_number")

    qr_ready = bool(
        qr_student_name.strip()
        and qr_class_section.strip()
        and qr_emis_number.strip()
    )
    if qr_ready:
        registration_url = get_registration_url(
            qr_student_name.strip(),
            qr_emis_number.strip(),
            qr_class_section.strip(),
            base_url=APP_BASE_URL,
        )
        qr_image = create_qr(registration_url)
        st.image(qr_image, caption="Scan to open the prefilled registration form")
        st.download_button(
            "Download Registration QR Code",
            data=qr_image,
            file_name=f"{qr_student_name.strip().replace(' ', '_')}_registration_qr.png",
            mime="image/png",
        )
    else:
        st.info("Enter the student's name, class/section, and EMIS number to create the QR.")

    registration_url = get_registration_url(base_url=APP_BASE_URL)
    st.caption(f"Registration link: {registration_url}")
    st.warning(
        "This QR contains the student's name, class/section, and EMIS number in its link. "
        "Treat the QR as private and share it only with the intended student or guardian."
    )
    if urllib.parse.urlparse(registration_url).scheme == "https":
        st.info(
            "This HTTPS link can open from different Wi-Fi networks while the deployed app is running."
        )
    else:
        st.info(
            "This local link works only when the phone can reach this computer on the "
            "same Wi-Fi. To use different networks, deploy the app and set APP_BASE_URL "
            "to its public HTTPS address."
        )
    if "127.0.0.1" in registration_url or "localhost" in registration_url:
        st.warning(
            "The detected address is only reachable on this computer. Set APP_BASE_URL "
            "to the computer's Wi-Fi address (for example http://192.168.1.150:8501) "
            "to scan from a phone on the same network."
        )

    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    st.subheader("In-app QR Image Scanner (optional)")
    st.caption(
        "The generated link QR opens the form directly on a phone. You can also upload "
        "an older QR image here to prefill the form."
    )
    uploaded_file = st.file_uploader("Upload scanned QR code image", type=["png", "jpg", "jpeg"])

    if uploaded_file or registration_link_requested:
        try:
            decoded = []
            if uploaded_file:
                image = Image.open(uploaded_file)
                decoded = decode(image)

            if decoded or registration_link_requested:
                decoded_text = (
                    decoded[0].data.decode("utf-8").strip()
                    if decoded
                    else json.dumps({"SPORTS_EVENT": {}})
                )
                if decoded_text.startswith(("https://", "http://")):
                    query_values = urllib.parse.parse_qs(
                        urllib.parse.urlsplit(decoded_text).query
                    )
                    student_info = {
                        "name": query_values.get("name", [""])[0],
                        "emis_number": query_values.get("emis", [""])[0],
                        "class": query_values.get("class", [""])[0],
                    }
                elif registration_link_requested:
                    student_info = {
                        "name": st.query_params.get("name", ""),
                        "emis_number": st.query_params.get("emis", ""),
                        "class": st.query_params.get("class", ""),
                    }
                else:
                    payload = json.loads(decoded_text)
                    student_info = payload.get("SPORTS_EVENT", {})

                st.success("QR Code successfully decoded.")
                try:
                    scanned_dob = datetime.strptime(
                        str(student_info.get("date_of_birth", "")), "%d-%m-%Y"
                    ).date()
                except ValueError:
                    scanned_dob = date.today()
                gender_options = [
                    "Select",
                    "Female",
                    "Male",
                    "Other",
                    "Prefer not to say",
                ]
                scanned_gender = student_info.get("gender", "Select")
                gender_index = (
                    gender_options.index(scanned_gender)
                    if scanned_gender in gender_options
                    else 0
                )

                sport_options = list(
                    dict.fromkeys(
                        [
                            "Cricket",
                            "Football",
                            "Volleyball",
                            "Kabaddi",
                            "Badminton",
                            "Basketball",
                            "Athletics",
                            "Table Tennis",
                        ]
                        + event_options
                        + ["Other"]
                    )
                )
                default_sport = student_info.get("event", event_options[0])
                if default_sport not in sport_options:
                    sport_options.insert(0, default_sport)

                with st.container():
                    st.subheader("Student Registration Form")
                    form_col1, form_col2 = st.columns(2)
                    with form_col1:
                        reg_name = st.text_input(
                            "Student Name *",
                            value=student_info.get("name", ""),
                            key="scan_registration_name",
                        )
                        reg_emis_number = st.text_input(
                            "EMIS Number *",
                            value=student_info.get(
                                "emis_number", student_info.get("roll_number", "")
                            ),
                            key="scan_registration_emis_number",
                        )
                        reg_dob = st.date_input(
                            "Date of Birth *", value=scanned_dob, key="scan_registration_dob"
                        )
                        reg_gender = st.selectbox(
                            "Gender *",
                            gender_options,
                            index=gender_index,
                            key="scan_registration_gender",
                        )
                        reg_mobile = st.text_input(
                            "Mobile Number *",
                            value=student_info.get("mobile_number", ""),
                            key="scan_registration_mobile",
                        )
                        reg_email = st.text_input(
                            "Email ID *",
                            value=student_info.get("email", ""),
                            key="scan_registration_email",
                        )
                        reg_address = st.text_area(
                            "Address *",
                            value=student_info.get("address", ""),
                            key="scan_registration_address",
                        )
                        reg_guardian_contact = st.text_input(
                            "Parent / Guardian Contact Number *",
                            value=student_info.get("guardian_contact_number", ""),
                            key="scan_registration_guardian_contact",
                        )
                        reg_institution = st.text_input(
                            "College / School Name *",
                            value=student_info.get("institution_name", ""),
                            key="scan_registration_institution",
                        )
                    with form_col2:
                        reg_department = st.text_input(
                            "Department *",
                            value=student_info.get("department", ""),
                            key="scan_registration_department",
                        )
                        reg_year = st.text_input(
                            "Year of Study *",
                            value=student_info.get("year_of_study", ""),
                            key="scan_registration_year",
                        )
                        reg_class_section = st.text_input(
                            "Class / Section *",
                            value=student_info.get(
                                "class_section", student_info.get("class", "")
                            ),
                            key="scan_registration_class_section",
                        )
                        reg_sport = st.selectbox(
                            "Sport Name *",
                            sport_options,
                            index=sport_options.index(default_sport),
                            key="scan_registration_sport",
                        )
                        if reg_sport == "Other":
                            reg_sport = st.text_input(
                                "Enter Sport Name *", key="scan_registration_custom_sport"
                            )
                        if reg_sport in event_formats:
                            reg_competition_type = event_formats[reg_sport]
                            st.caption(
                                f"Match Category: {reg_competition_type.title()} "
                                "(set for this event)"
                            )
                        else:
                            scanned_format = student_info.get("competition_type", "individual")
                            format_index = 1 if scanned_format == "team" else 0
                            reg_competition_type = st.selectbox(
                                "Match Category *",
                                ["individual", "team"],
                                index=format_index,
                                key="scan_registration_competition_type",
                            )
                        reg_playing_position = st.text_input(
                            "Playing Position (if applicable)",
                            value=student_info.get("playing_position", ""),
                            key="scan_registration_playing_position",
                        )
                        reg_team_name = ""
                        reg_team_members = ""
                        if reg_competition_type == "team":
                            reg_team_name = st.text_input(
                                "Team Name *",
                                value=student_info.get("team_name", ""),
                                key="scan_registration_team_name",
                            )
                            reg_team_members = st.text_area(
                                "Team Members' Details * (names and EMIS numbers)",
                                value=student_info.get("team_members_details", ""),
                                key="scan_registration_team_members",
                            )
                        reg_experience = st.text_area(
                            "Previous Sports Experience (optional)",
                            value=student_info.get("previous_sports_experience", ""),
                            key="scan_registration_experience",
                        )

                    st.markdown("#### Required Documents")
                    document_col1, document_col2 = st.columns(2)
                    with document_col1:
                        student_id_card = st.file_uploader(
                            "Student ID Card *",
                            type=["pdf", "png", "jpg", "jpeg"],
                            key="scan_student_id_card",
                        )
                        photograph = st.file_uploader(
                            "Passport-size Photograph *",
                            type=["png", "jpg", "jpeg"],
                            key="scan_student_photograph",
                        )
                        bonafide_certificate = st.file_uploader(
                            "Bonafide Certificate *",
                            type=["pdf", "png", "jpg", "jpeg"],
                            key="scan_bonafide_certificate",
                        )
                    with document_col2:
                        date_of_birth_proof = st.file_uploader(
                            "Date of Birth Proof *",
                            type=["pdf", "png", "jpg", "jpeg"],
                            key="scan_date_of_birth_proof",
                        )
                        medical_certificate_required = st.checkbox(
                            "Medical fitness certificate is required for this event",
                            value=bool(
                                student_info.get("medical_certificate_required", False)
                            ),
                            key="scan_medical_certificate_required",
                        )
                        medical_certificate = (
                            st.file_uploader(
                                "Medical Fitness Certificate *",
                                type=["pdf", "png", "jpg", "jpeg"],
                                key="scan_medical_certificate",
                            )
                            if medical_certificate_required
                            else None
                        )

                    register_submitted = st.button("Register Student")

                if register_submitted:
                    required_text_fields = {
                        "student name": reg_name,
                        "EMIS number": reg_emis_number,
                        "mobile number": reg_mobile,
                        "email ID": reg_email,
                        "address": reg_address,
                        "parent / guardian contact number": reg_guardian_contact,
                        "college / school name": reg_institution,
                        "department": reg_department,
                        "year of study": reg_year,
                        "class / section": reg_class_section,
                        "sport name": reg_sport,
                    }
                    missing_fields = [
                        label for label, value in required_text_fields.items()
                        if not value.strip()
                    ]
                    if missing_fields or reg_gender == "Select":
                        if reg_gender == "Select":
                            missing_fields.append("gender")
                        st.warning("Please complete required fields: " + ", ".join(missing_fields) + ".")
                    elif (
                        not re.fullmatch(r"[0-9+() .-]{7,20}", reg_mobile.strip())
                        or not 7 <= len(re.sub(r"\D", "", reg_mobile)) <= 15
                    ):
                        st.warning("Enter a valid mobile number.")
                    elif (
                        not re.fullmatch(r"[0-9+() .-]{7,20}", reg_guardian_contact.strip())
                        or not 7 <= len(re.sub(r"\D", "", reg_guardian_contact)) <= 15
                    ):
                        st.warning("Enter a valid parent / guardian contact number.")
                    elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", reg_email.strip()):
                        st.warning("Enter a valid email address.")
                    elif reg_dob > date.today():
                        st.warning("Date of birth cannot be in the future.")
                    elif reg_competition_type == "team" and (
                        not reg_team_name.strip() or not reg_team_members.strip()
                    ):
                        st.warning("Enter a team name and team members' details.")
                    elif not all(
                        (
                            student_id_card,
                            photograph,
                            bonafide_certificate,
                            date_of_birth_proof,
                        )
                    ):
                        st.warning("Upload the student ID card, photograph, bonafide certificate, and date of birth proof.")
                    elif medical_certificate_required and not medical_certificate:
                        st.warning("Upload the required medical fitness certificate.")
                    elif cursor.execute(
                        """SELECT 1 FROM registrations
                           WHERE lower(trim(emis_number))=lower(trim(?))
                             AND lower(trim(event))=lower(trim(?))
                           LIMIT 1""",
                        (reg_emis_number, reg_sport),
                    ).fetchone():
                        st.error("This EMIS number already has a registration for this sport.")
                    else:
                        doc_type = (
                            "Student ID Card, Passport-size Photograph, "
                            "Bonafide Certificate, Date of Birth Proof"
                        )
                        uploaded_documents = [
                            student_id_card,
                            photograph,
                            bonafide_certificate,
                            date_of_birth_proof,
                            medical_certificate,
                        ]
                        document_names = [
                            uploaded_file.name
                            for uploaded_file in uploaded_documents
                            if uploaded_file is not None
                        ]
                        cursor.execute(
                            """
                            INSERT INTO registrations
                            (name, "class", date_of_birth, emis_number, event, document_type,
                             document_name, email, competition_type, team_name,
                             gender, mobile_number, address, guardian_contact_number,
                             institution_name, department, year_of_study, class_section,
                             playing_position, team_members_details, previous_sports_experience,
                             medical_certificate_required)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                reg_name.strip(),
                                reg_class_section.strip(),
                                reg_dob.strftime("%d-%m-%Y"),
                                reg_emis_number.strip(),
                                reg_sport.strip(),
                                doc_type,
                                ", ".join(document_names),
                                reg_email.strip(),
                                reg_competition_type,
                                reg_team_name.strip(),
                                reg_gender,
                                reg_mobile.strip(),
                                reg_address.strip(),
                                reg_guardian_contact.strip(),
                                reg_institution.strip(),
                                reg_department.strip(),
                                reg_year.strip(),
                                reg_class_section.strip(),
                                reg_playing_position.strip(),
                                reg_team_members.strip(),
                                reg_experience.strip(),
                                int(medical_certificate_required),
                            ),
                        )
                        registration_id = cursor.lastrowid
                        conn.commit()
                        add_to_organizer_inbox(
                            reg_name.strip(),
                            reg_class_section.strip(),
                            reg_dob.strftime("%d-%m-%Y"),
                            reg_emis_number.strip(),
                            reg_sport.strip(),
                            doc_type,
                            None,
                            None,
                            None,
                            registration_id,
                            reg_competition_type,
                            reg_team_name.strip(),
                            student_id_card,
                            photograph,
                            bonafide_certificate,
                            date_of_birth_proof,
                            medical_certificate,
                        )
                        st.success(
                            "Student registration and documents have been sent to the organizer."
                        )
            else:
                st.error("QR code could not be detected. Please upload a clear image.")
        except Exception as exc:
            st.error(f"Unable to read QR code: {exc}")


# =================================================
# 2. ORGANIZER INBOX
# =================================================

elif menu == "Organizer Inbox":
    st.header("📬 Organizer Inbox")
    st.warning(
        "Manually compare each player's submitted identity document with the player and school record. "
        "This app does not contact UIDAI or validate Aadhaar numbers; never enter or store an Aadhaar number here."
    )
    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    cursor.execute(
        """
         SELECT i.id, i.student_name, i.student_class, i.date_of_birth, i.emis_number,
             i.event, i.document_type, i.status, i.submitted_at,
             i.birth_certificate_name, i.birth_certificate_data, i.aadhar_card_name,
             i.aadhar_card_data, i.tenth_marksheet_name, i.tenth_marksheet_data,
             i.competition_type, i.team_name, i.identity_verified, i.identity_verified_at,
             i.student_id_card_name, i.student_id_card_data, i.photograph_name,
             i.photograph_data, i.bonafide_certificate_name, i.bonafide_certificate_data,
             i.date_of_birth_proof_name, i.date_of_birth_proof_data,
             i.medical_certificate_name, i.medical_certificate_data,
             r.emis_number, r.gender, r.mobile_number, r.email, r.address,
             r.guardian_contact_number, r.institution_name, r.department, r.year_of_study,
             r.playing_position, r.team_members_details, r.previous_sports_experience,
             r.medical_certificate_required, i.review_reason, i.reviewed_at
        FROM organizer_inbox i
        LEFT JOIN registrations r ON r.id=i.registration_id
        ORDER BY i.id DESC
        """
    )
    rows = cursor.fetchall()

    normalized_statuses = [
        "Pending" if (row[7] or "").strip().lower() in {"new", "pending"}
        else (row[7] or "Pending").title()
        for row in rows
    ]
    status_counts = {
        status: normalized_statuses.count(status)
        for status in ("Pending", "Approved", "Rejected")
    }
    metric_columns = st.columns(3)
    for column, status in zip(metric_columns, status_counts):
        column.metric(status, status_counts[status])

    filter_columns = st.columns([2, 1, 1])
    with filter_columns[0]:
        inbox_search = st.text_input(
            "Search name, EMIS, sport, team, or institution",
            key="organizer_inbox_search",
        ).strip().casefold()
    with filter_columns[1]:
        status_filter = st.selectbox(
            "Status",
            ["All", "Pending", "Approved", "Rejected"],
            key="organizer_inbox_status_filter",
        )
    with filter_columns[2]:
        event_filter = st.selectbox(
            "Sport",
            ["All"] + sorted({str(row[5]) for row in rows if row[5]}),
            key="organizer_inbox_event_filter",
        )

    filtered_rows = []
    for row, normalized_status in zip(rows, normalized_statuses):
        searchable_text = " ".join(
            str(value or "")
            for value in (row[1], row[4], row[5], row[16], row[35])
        ).casefold()
        if inbox_search and inbox_search not in searchable_text:
            continue
        if status_filter != "All" and normalized_status != status_filter:
            continue
        if event_filter != "All" and row[5] != event_filter:
            continue
        filtered_rows.append((row, normalized_status))

    csv_buffer = StringIO()
    csv_writer = csv.writer(csv_buffer)
    csv_writer.writerow(
        [
            "Registration ID",
            "Student Name",
            "EMIS Number",
            "Class / Section",
            "Date of Birth",
            "Sport",
            "Match Category",
            "Team Name",
            "Status",
            "Review Reason",
            "Submitted At",
            "Mobile Number",
            "Email",
            "Institution",
            "Department",
            "Year of Study",
        ]
    )
    for row, normalized_status in filtered_rows:
        csv_writer.writerow(
            [
                row[0], row[1], row[29] or row[4], row[2], row[3], row[5],
                row[15], row[16], normalized_status, row[42], row[8],
                row[31], row[32], row[35], row[36], row[37],
            ]
        )
    st.download_button(
        "Export filtered registrations (CSV)",
        data=csv_buffer.getvalue().encode("utf-8-sig"),
        file_name="sports_registrations.csv",
        mime="text/csv",
        disabled=not filtered_rows,
        key="export_organizer_registrations_csv",
    )

    if rows:
        for row, normalized_status in filtered_rows:
            st.markdown(f"### Registration #{row[0]}")
            st.write(f"Student: **{row[1]}**")
            st.write(f"Class: **{row[2]}** | DOB: **{row[3]}** | EMIS: **{row[4]}**")
            st.write(
                f"Event: **{row[5]}** | Required Docs: **{row[6]}** | "
                f"Status: **{normalized_status}**"
            )
            review_columns = st.columns([1, 2, 1])
            with review_columns[0]:
                review_status = st.selectbox(
                    "Review status",
                    ["Pending", "Approved", "Rejected"],
                    index=["Pending", "Approved", "Rejected"].index(normalized_status)
                    if normalized_status in {"Pending", "Approved", "Rejected"}
                    else 0,
                    key=f"review_status_{row[0]}",
                )
            with review_columns[1]:
                review_reason = st.text_input(
                    "Reason (required for rejection)",
                    value=row[42] or "",
                    key=f"review_reason_{row[0]}",
                )
            with review_columns[2]:
                st.write("")
                st.write("")
                if st.button("Save review", key=f"save_review_{row[0]}"):
                    if review_status == "Rejected" and not review_reason.strip():
                        st.error("Enter a reason before rejecting this registration.")
                    else:
                        cursor.execute(
                            """UPDATE organizer_inbox
                               SET status=?, review_reason=?,
                                   reviewed_at=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (review_status, review_reason.strip(), row[0]),
                        )
                        conn.commit()
                        st.success("Registration review saved.")
                        st.rerun()
            if normalized_status == "Rejected" and row[42]:
                st.warning(f"Rejection reason: {row[42]}")
            elif row[43]:
                st.caption(f"Reviewed at {row[43]}")
            event_category = row[15].title()
            team_label = f" · Team: {row[16]}" if event_category == "Team" else ""
            st.write(f"Competition: **{event_category}{team_label}**")
            st.write(f"Submitted At: **{row[8]}**")
            with st.expander("Full student registration details"):
                st.write(f"EMIS Number: **{row[29] or row[4]}**")
                st.write(f"Gender: **{row[30] or 'Not provided'}**")
                st.write(f"Mobile: **{row[31] or 'Not provided'}** · Email: **{row[32] or 'Not provided'}**")
                st.write(f"Address: **{row[33] or 'Not provided'}**")
                st.write(f"Parent / Guardian Contact: **{row[34] or 'Not provided'}**")
                st.write(
                    f"College / School: **{row[35] or 'Not provided'}** · "
                    f"Department: **{row[36] or 'Not provided'}**"
                )
                st.write(
                    f"Year of Study: **{row[37] or 'Not provided'}** · "
                    f"Class / Section: **{row[2] or 'Not provided'}**"
                )
                st.write(f"Playing Position: **{row[38] or 'Not applicable'}**")
                if event_category == "Team":
                    st.write(f"Team Members: **{row[39] or 'Not provided'}**")
                st.write(f"Previous Sports Experience: **{row[40] or 'Not provided'}**")
                st.write(
                    f"Medical fitness certificate required: "
                    f"**{'Yes' if row[41] else 'No'}**"
                )
            for document_name, document_data, label in (
                (row[9], row[10], "Birth Certificate"),
                (row[11], row[12], "Aadhar Card"),
                (row[13], row[14], "10th Marksheet"),
                (row[19], row[20], "Student ID Card"),
                (row[21], row[22], "Passport-size Photograph"),
                (row[23], row[24], "Bonafide Certificate"),
                (row[25], row[26], "Date of Birth Proof"),
                (row[27], row[28], "Medical Fitness Certificate"),
            ):
                if document_name and document_data:
                    st.download_button(
                        f"Download {label}",
                        data=document_data,
                        file_name=document_name,
                        key=f"download_{row[0]}_{label.replace(' ', '_')}",
                    )
            if row[17]:
                st.success(f"Identity document checked by staff · {row[18]}")
                if st.button("Clear verification", key=f"clear_identity_{row[0]}"):
                    cursor.execute(
                        """UPDATE organizer_inbox
                           SET identity_verified=0, identity_verified_at=NULL WHERE id=?""",
                        (row[0],),
                    )
                    conn.commit()
                    st.rerun()
            elif not row[19] or not row[25]:
                st.warning(
                    "A student ID card and date of birth proof are required "
                    "before the identity review can be marked complete."
                )
            else:
                checked = st.checkbox(
                    "I compared the student ID card and date-of-birth proof with the student and school record.",
                    key=f"identity_check_{row[0]}",
                )
                if st.button(
                    "Mark identity document checked",
                    key=f"verify_identity_{row[0]}",
                    disabled=not checked,
                ):
                    cursor.execute(
                        """UPDATE organizer_inbox
                           SET identity_verified=1, identity_verified_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (row[0],),
                    )
                    conn.commit()
                    st.rerun()
            st.divider()
        if not filtered_rows:
            st.info("No registrations match the selected search and filters.")
    else:
        st.info("No registration submissions have reached the organizer yet.")

    st.markdown("</div>", unsafe_allow_html=True)


# =================================================
# 3. EVENT ALLOCATION
# =================================================

elif menu == "Event Allocation":
    st.header("🏟️ Event Allocation")
    st.markdown('<div class="card">', unsafe_allow_html=True)

    participant_count = st.number_input("Number of Participants", min_value=1, value=50)
    event_type = st.selectbox("Select Event", ["Basketball", "Football", "Cricket", "Volleyball", "Athletics"])
    competition_type = st.selectbox("Competition format", ["individual", "team"])
    venue_type = st.selectbox("Venue type", ["Indoor", "Outdoor"])
    event_date = st.date_input("Event date", min_value=date.today(), key="allocation_event_date")
    location = st.selectbox(
        "Event location",
        ["Choose a place"] + sorted(CHENNAI_AREAS),
        key="allocation_location",
    )
    availability = st.selectbox("Event Slot Available?", ["Yes", "No"])
    forecast_key = (location.strip().casefold(), event_date.isoformat())
    current_forecast = None
    current_weather_plan = None

    if venue_type == "Outdoor":
        st.subheader("Outdoor weather forecast")
        st.caption(
            "Forecasts use Open-Meteo and are available up to 15 days ahead. "
            "This is weather guidance, not a guarantee of safe playing conditions."
        )
        if st.button("Check weather for event", key="check_outdoor_weather"):
            if location == "Choose a place":
                st.error("Choose an event location before checking the forecast.")
            else:
                try:
                    st.session_state["outdoor_forecast"] = {
                        "key": forecast_key,
                        "data": get_outdoor_forecast(location, event_date),
                        "checked_at": datetime.now(),
                    }
                except (ValueError, RuntimeError) as exc:
                    st.session_state.pop("outdoor_forecast", None)
                    st.error(str(exc))

        cached_forecast = st.session_state.get("outdoor_forecast")
        forecast_checked_at = (
            cached_forecast.get("checked_at") if cached_forecast else None
        )
        forecast_is_fresh = (
            cached_forecast
            and cached_forecast["key"] == forecast_key
            and isinstance(forecast_checked_at, datetime)
            and datetime.now() - forecast_checked_at < timedelta(minutes=30)
        )
        if forecast_is_fresh:
            current_forecast = cached_forecast["data"]
            st.write(f"Forecast for **{current_forecast['location']}** on **{event_date:%d/%m/%Y}**")
            weather_columns = st.columns(4)
            weather_columns[0].metric("Conditions", current_forecast["description"])
            weather_columns[1].metric(
                "Temperature",
                f"{current_forecast['temperature_min']}–{current_forecast['temperature_max']} °C",
            )
            weather_columns[2].metric(
                "Rain chance", f"{current_forecast['precipitation_probability']}%"
            )
            weather_columns[3].metric("Max wind", f"{current_forecast['wind_speed']} km/h")
            st.info(current_forecast["advice"])
            current_weather_plan = assess_weather_readiness(current_forecast, event_type)
            st.subheader(f"{event_type} Weather Readiness")
            readiness_columns = st.columns([1, 2])
            readiness_columns[0].metric(
                "Readiness index",
                f"{current_weather_plan['readiness_score']}/100",
                delta=f"{current_weather_plan['risk_level']} risk",
                delta_color="inverse",
            )
            readiness_columns[1].progress(
                current_weather_plan["readiness_score"],
                text="Higher means fewer weather-related planning concerns",
            )
            if current_weather_plan["risk_level"] in {"High", "Severe"}:
                st.warning(
                    f"**{current_weather_plan['risk_level']} event-day impact estimate** — "
                    "review the risk drivers and contingency actions below."
                )
            elif current_weather_plan["risk_level"] == "Moderate":
                st.info(
                    "**Moderate event-day impact estimate** — prepare the listed "
                    "contingencies and monitor updates."
                )
            else:
                st.success(
                    "**Low event-day impact estimate** — standard event-day "
                    "precautions still apply."
                )
            with st.expander("Why this score? Risk drivers and action plan"):
                st.markdown("**Forecast signals**")
                for factor in current_weather_plan["risk_factors"]:
                    st.markdown(f"- {factor}")
                st.markdown("**Recommended organizer actions**")
                for recommendation in current_weather_plan["recommendations"]:
                    st.markdown(f"- {recommendation}")
            st.caption(
                f"Forecast checked {forecast_checked_at:%d %b %Y, %H:%M}. "
                "This transparent, sport-specific planning estimate is based on "
                "forecast rain, wind, temperature, and weather codes—not a safety "
                "certification or a machine-learning prediction."
            )
        else:
            st.info("Check or refresh the forecast for this location and date before allocating the outdoor event.")

    high_weather_risk = bool(
        current_forecast
        and (
            current_forecast["advice"].startswith("High weather risk")
            or (
                current_weather_plan
                and current_weather_plan["risk_level"] in {"High", "Severe"}
            )
        )
    )
    safety_confirmed = False
    if high_weather_risk:
        safety_confirmed = st.checkbox(
            "I reviewed the high-risk forecast and confirmed local safety guidance for this event.",
            key="confirm_outdoor_weather_risk",
        )

    if st.button("Allocate Event"):
        if location == "Choose a place":
            st.error("Choose a location for this event before allocating it.")
        elif venue_type == "Outdoor" and current_forecast is None:
            st.error("Check the outdoor forecast for this location and date before allocating the event.")
        elif high_weather_risk and not safety_confirmed:
            st.error("Confirm the high-risk forecast and local safety guidance before allocating.")
        else:
            available = 1 if availability == "Yes" else 0
            prediction = model.predict([[available, 1]])[0]

            if prediction == 1:
                st.success(f"{event_type} has been allocated successfully!")
                cursor.execute(
                    """
                    INSERT INTO events
                    (event_name, participants, allocated_event, event_date, location,
                     venue_type, competition_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_type,
                        participant_count,
                        "Allocated",
                        event_date.isoformat(),
                        location.strip(),
                        venue_type.lower(),
                        competition_type,
                    ),
                )
                conn.commit()
            else:
                st.error("Event cannot be allocated for the selected slot.")

    cursor.execute(
        """SELECT event_name, participants, event_date, location, venue_type,
                  competition_type, allocated_event
           FROM events ORDER BY id DESC"""
    )
    scheduled_events = cursor.fetchall()
    if scheduled_events:
        st.subheader("Allocated events")
        st.dataframe(
            [
                {
                    "Event": row[0],
                    "Participants": row[1],
                    "Date": row[2],
                    "Location": row[3] or "Not specified",
                    "Venue type": row[4].title(),
                    "Competition format": row[5].title(),
                    "Status": row[6],
                }
                for row in scheduled_events
            ],
            hide_index=True,
            use_container_width=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


elif menu == "Tournament Scheduler":
    st.header("🗓️ Conflict-Free Tournament Scheduler")
    st.caption(
        "Build round-robin fixtures or a knockout bracket, then save a venue-aware schedule."
    )
    st.markdown('<div class="card">', unsafe_allow_html=True)

    cursor.execute(
        """SELECT DISTINCT TRIM(location) FROM events
           WHERE TRIM(COALESCE(location, '')) != ''
           ORDER BY TRIM(location)"""
    )
    known_venues = [row[0] for row in cursor.fetchall()]

    with st.form("tournament_scheduler_form"):
        tournament_name = st.text_input("Sport / tournament name")
        competitor_text = st.text_area(
            "Competitors (one team or participant per line)",
            help="For team events, enter each team name. For individual events, enter each participant.",
        )
        competition_format = st.selectbox(
            "Competition format",
            ["Round-robin", "Knockout"],
        )
        event_date = st.date_input(
            "Tournament date",
            value=date.today() + timedelta(days=1),
            min_value=date.today(),
            key="tournament_scheduler_date",
        )
        venue_text = st.text_area(
            "Available venues (one per line)",
            value="\n".join(known_venues),
            help="Existing event locations are suggested; edit this list to match venues available for this tournament.",
        )
        time_columns = st.columns(2)
        with time_columns[0]:
            start_time = st.time_input(
                "First match can start at",
                value=datetime.strptime("09:00", "%H:%M").time(),
                key="tournament_scheduler_start",
            )
        with time_columns[1]:
            end_time = st.time_input(
                "Finish by",
                value=datetime.strptime("17:00", "%H:%M").time(),
                key="tournament_scheduler_end",
            )
        duration_columns = st.columns(2)
        with duration_columns[0]:
            match_duration = st.number_input(
                "Match duration (minutes)",
                min_value=5,
                max_value=240,
                value=30,
                step=5,
            )
        with duration_columns[1]:
            rest_minutes = st.number_input(
                "Minimum rest between match slots (minutes)",
                min_value=0,
                max_value=180,
                value=15,
                step=5,
            )
        generate_schedule = st.form_submit_button("Generate and save schedule")

    if generate_schedule:
        participants = [name.strip() for name in competitor_text.splitlines() if name.strip()]
        venues = [venue.strip() for venue in venue_text.splitlines() if venue.strip()]
        try:
            if not tournament_name.strip():
                raise ValueError("Enter a sport or tournament name.")
            if end_time <= start_time:
                raise ValueError("The finish time must be later than the start time.")
            if event_date == date.today() and start_time <= datetime.now().time():
                raise ValueError("The first match start time must be later than the current time.")

            matchups = build_matchups(participants, competition_format)
            scheduled, conflicts = schedule_matchups(
                matchups,
                venues,
                event_date,
                start_time,
                end_time,
                int(match_duration),
                int(rest_minutes),
            )
            cursor.execute(
                """
                INSERT INTO tournament_schedules
                (event_name, competition_format, event_date, start_time, end_time,
                 match_duration_minutes, rest_minutes, venues_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tournament_name.strip(),
                    competition_format,
                    event_date.isoformat(),
                    start_time.strftime("%H:%M"),
                    end_time.strftime("%H:%M"),
                    int(match_duration),
                    int(rest_minutes),
                    json.dumps(venues),
                ),
            )
            schedule_id = cursor.lastrowid
            for fixture in scheduled + conflicts:
                conn.execute(
                    """
                    INSERT INTO tournament_fixtures
                    (schedule_id, match_number, round_number, participant_a, participant_b,
                     venue, event_date, start_time, end_time, status, conflict_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        schedule_id,
                        fixture["match_number"],
                        fixture["round_number"],
                        fixture["participant_a"],
                        fixture["participant_b"],
                        fixture["venue"],
                        fixture["event_date"],
                        fixture["start_time"],
                        fixture["end_time"],
                        fixture["status"],
                        fixture["conflict_reason"],
                    ),
                )
            conn.commit()
            st.session_state["latest_tournament_schedule_id"] = schedule_id
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except sqlite3.Error as exc:
            conn.rollback()
            st.error(f"Could not save the tournament schedule: {exc}")

    selected_schedule_id = st.session_state.get("latest_tournament_schedule_id")
    if selected_schedule_id is None:
        cursor.execute("SELECT id FROM tournament_schedules ORDER BY id DESC LIMIT 1")
        latest_schedule = cursor.fetchone()
        selected_schedule_id = latest_schedule[0] if latest_schedule else None

    if selected_schedule_id is not None:
        cursor.execute(
            """SELECT event_name, competition_format, event_date, start_time, end_time
               FROM tournament_schedules WHERE id=?""",
            (selected_schedule_id,),
        )
        tournament = cursor.fetchone()
        cursor.execute(
            """SELECT match_number, round_number, participant_a, participant_b,
                      venue, event_date, start_time, end_time, status, conflict_reason
               FROM tournament_fixtures
               WHERE schedule_id=? ORDER BY round_number, match_number""",
            (selected_schedule_id,),
        )
        fixtures = cursor.fetchall()
        if tournament and fixtures:
            scheduled_count = sum(fixture[8] == "Scheduled" for fixture in fixtures)
            conflict_count = len(fixtures) - scheduled_count
            st.subheader(f"{tournament[0]} · {tournament[1]}")
            st.caption(
                f"{tournament[2]} · {tournament[3]}–{tournament[4]} · "
                f"{scheduled_count} scheduled match(es)"
            )
            st.info(
                "Each time slot uses each venue at most once. Matches in a slot have distinct "
                "competitors; successive slots include the selected rest interval."
            )
            if conflict_count:
                st.warning(
                    f"{conflict_count} match(es) could not fit in the selected event window. "
                    "Extend the schedule window or reduce match duration/rest time."
                )
            st.dataframe(
                [
                    {
                        "Match": f"Match {row[0]}",
                        "Round": row[1],
                        "Competitor 1": row[2],
                        "Competitor 2": row[3],
                        "Venue": row[4] or "Unassigned",
                        "Date": row[5],
                        "Start": row[6] or "—",
                        "Finish": row[7] or "—",
                        "Status": row[8],
                        "Conflict": row[9] or "",
                    }
                    for row in fixtures
                ],
                hide_index=True,
                width="stretch",
            )
            if tournament[1] == "Knockout":
                st.caption(
                    "Later knockout rounds use “Winner of Match …” placeholders until results are recorded."
                )
    else:
        st.info("Enter competitors, available venues, and the event window to create your first schedule.")

    st.markdown("</div>", unsafe_allow_html=True)


# =================================================
# 4. CERTIFICATE GENERATION
# =================================================

elif menu == "Certificate Generation":
    st.header("🏅 Certificate Generation")
    if not certificate_access_granted():
        st.stop()
    st.caption("Generate certificates for any participant name, with or without a saved registration.")
    st.markdown('<div class="card">', unsafe_allow_html=True)

    cursor.execute(
        """SELECT name, event, competition_type, team_name
           FROM registrations
           WHERE TRIM(COALESCE(name, '')) != ''
             AND TRIM(COALESCE(event, '')) != ''
           ORDER BY event, team_name, name"""
    )
    registered_players = cursor.fetchall()
    individual_players = [
        row for row in registered_players if (row[2] or "individual").lower() == "individual"
    ]
    team_players = [
        row for row in registered_players
        if (row[2] or "").lower() == "team" and row[3].strip()
    ]

    certificate_sources = ["Enter names manually"]
    if registered_players:
        certificate_sources.append("Use saved registration")
    certificate_source = st.radio(
        "Certificate details",
        certificate_sources,
        horizontal=True,
        key="certificate_source",
    )

    with st.form("certificate_form"):
        if certificate_source == "Enter names manually":
            recipient_names = st.text_area(
                "Participant name(s)",
                help="Enter one name per line. A separate certificate will be generated for each name.",
            )
            event = st.text_input("Event name")
            team_name = st.text_input("Team name (optional)")
            recipients = [
                name.strip()
                for name in recipient_names.splitlines()
                if name.strip()
            ]
        else:
            certificate_type = st.radio(
                "Certificate category",
                ["Individual", "Team"],
                horizontal=True,
                key="certificate_type",
            )
            eligible = individual_players if certificate_type == "Individual" else team_players
            if not eligible:
                st.info(f"No saved {certificate_type.lower()} registrations. Choose manual entry to add any names.")
                recipients = []
                event = ""
                team_name = None
            elif certificate_type == "Team":
                team_choices = sorted({(row[1], row[3]) for row in eligible})
                team_labels = [f"{team} · {event_name}" for event_name, team in team_choices]
                selected_team_label = st.selectbox("Registered team and event", team_labels)
                event, team_name = team_choices[team_labels.index(selected_team_label)]
                recipients = [
                    row[0] for row in eligible
                    if row[1] == event and row[3] == team_name
                ]
                st.caption(f"{len(recipients)} registered team member(s) will receive certificates.")
            else:
                player_labels = [f"{row[0]} · {row[1]}" for row in eligible]
                selected_player_label = st.selectbox(
                    "Registered participant and event",
                    player_labels,
                )
                selected_player = eligible[player_labels.index(selected_player_label)]
                event = selected_player[1]
                team_name = None
                recipients = [selected_player[0]]

        event_date = st.date_input(
            "Event conducted on",
            value=date.today(),
            help="This is the event date printed on the certificate, not the certificate issue date.",
        )
        event_time = st.time_input(
            "Event start time",
            value=time(9, 0),
            help="Enter the event's start time; it will be printed on the certificate.",
        )
        award = st.selectbox(
            "Recognition",
            [
                "Participation",
                "Winner - 1st Place",
                "Runner-up - 2nd Place",
                "Third Place",
            ],
        )
        generate = st.form_submit_button("Generate certificate(s)")

    if generate:
        if not recipients:
            st.error("Enter at least one participant name or choose a saved registration.")
        elif not event.strip():
            st.error("Enter an event name before generating certificates.")
        else:
            try:
                generated = {
                    f"{index:02d}_{re.sub(r'[^A-Za-z0-9_-]+', '_', recipient).strip('_') or 'participant'}_"
                    f"{award.split(' - ')[0].lower()}.pdf":
                    create_certificate(
                        recipient,
                        event.strip(),
                        award,
                        team_name,
                        event_date,
                        event_time,
                    )
                    for index, recipient in enumerate(recipients, start=1)
                }
                st.session_state["generated_certificates"] = generated
                st.session_state["generated_certificate_event"] = event.strip()
                st.session_state["generated_certificate_award"] = award
                st.session_state["generated_certificate_event_date"] = event_date
                st.session_state["generated_certificate_event_time"] = event_time
                st.success(f"Generated {len(generated)} certificate(s) for {award.lower()}.")
            except OSError as exc:
                st.error(f"Could not load the certificate template or font: {exc}")

    generated = st.session_state.get("generated_certificates", {})
    if generated:
        st.write(
            f"**{st.session_state['generated_certificate_award']}** · "
            f"{st.session_state['generated_certificate_event']} · "
            f"Conducted {st.session_state['generated_certificate_event_date']:%d/%m/%Y} "
            f"at {st.session_state['generated_certificate_event_time']:%I:%M %p}"
        )
        if len(generated) > 1:
            archive = BytesIO()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for filename, certificate_pdf in generated.items():
                    bundle.writestr(filename, certificate_pdf)
            st.download_button(
                "Download all certificates (ZIP)",
                data=archive.getvalue(),
                file_name="sports_certificates.zip",
                mime="application/zip",
                key="download_team_certificate_bundle",
            )
        for index, (filename, certificate_pdf) in enumerate(generated.items()):
            st.download_button(
                f"Download {filename}",
                data=certificate_pdf,
                file_name=filename,
                mime="application/pdf",
                key=f"download_certificate_{index}_{filename}",
            )

    st.markdown("</div>", unsafe_allow_html=True)


# =================================================
# 5. HELP CENTER
# =================================================

elif menu == "Help Center":
    st.header("🛟 Help Center")

    faq_items = [
        ("How do I register for an event?", "Generate a registration QR code, scan or upload it in QR Event Registration, complete the student and sports form, and submit the required documents."),
        ("Which documents are required?", "Upload a student ID card, passport-size photograph, bonafide certificate, and date-of-birth proof. A medical fitness certificate is required only when the event requires it."),
        ("Where do registrations go after submission?", "Every successful registration is stored in the organizer inbox, allowing the organizer to review and approve entries directly."),
        ("How do I generate a certificate?", "An organizer enters the certificate-only password, then adds participant names and an event or selects saved registrations before generating PDFs."),
        ("How is identity checked?", "An organizer manually compares the uploaded student ID card and date-of-birth proof with the student and school record. The app does not contact UIDAI or store Aadhaar numbers."),
        ("Why is QR code registration important?", "It ensures students are matched with their event details and makes document verification quicker and more accurate."),
    ]

    for question, answer in faq_items:
        st.markdown('<div class="faq-card">', unsafe_allow_html=True)
        st.subheader(question)
        st.write(answer)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Support contact")
    st.write("Support Team: support@sportsportal.edu")
    st.write("Phone: +91 91234 56789")
    st.write("Emergency Desk: +91 99887 66554")
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Send a message to support")
    st.caption(
        "Submit to prepare an email in your email app. This website does not send or store messages."
    )
    with st.form("help_center_support_form"):
        support_name = st.text_input("Your name", key="help_support_name")
        support_email = st.text_input("Your email", key="help_support_email")
        support_message = st.text_area(
            "Message",
            max_chars=2000,
            key="help_support_message",
        )
        prepare_support_email = st.form_submit_button("Prepare email")

    if prepare_support_email:
        if not support_message.strip():
            st.error("Enter a message for the support team.")
        else:
            email_body = (
                f"From: {support_name.strip() or 'Not provided'}\n"
                f"Reply email: {support_email.strip() or 'Not provided'}\n\n"
                f"{support_message.strip()}"
            )
            mailto_url = (
                "mailto:support@sportsportal.edu"
                f"?subject={urllib.parse.quote('Sports portal support request')}"
                f"&body={urllib.parse.quote(email_body)}"
            )
            st.link_button("Open email to send", mailto_url)


# =================================================
# 7. REGISTRATION RECORDS
# =================================================

elif menu == "Registration Records":
    st.header("📋 Registration Records")
    st.markdown('<div class="card">', unsafe_allow_html=True)

    cursor.execute(
        """
        SELECT r.id, r.name, r."class", r.date_of_birth, r.emis_number, r.event,
               r.document_type, r.competition_type, r.team_name,
               COALESCE(i.identity_verified, 0), r.emis_number, r.gender,
               r.mobile_number, r.email, r.address, r.guardian_contact_number,
               r.institution_name, r.department, r.year_of_study, r.playing_position,
               r.team_members_details, r.previous_sports_experience
        FROM registrations r
        LEFT JOIN organizer_inbox i ON i.registration_id=r.id
        ORDER BY r.id DESC
        """
    )
    records = cursor.fetchall()

    if records:
        for record in records:
            st.write(
                f"**ID:** {record[0]} | **Name:** {record[1]} | **Class:** {record[2]} | "
                f"**DOB:** {record[3]} | **EMIS Number:** {record[10] or record[4]} | **Event:** {record[5]} | "
                f"**Format:** {(record[7] or 'individual').title()} "
                f"{'· Team: ' + record[8] if record[7] == 'team' else ''} | "
                f"**Identity checked:** {'Yes' if record[9] else 'No'} | **Docs:** {record[6]}"
            )
            with st.expander(f"More details for registration #{record[0]}"):
                st.write(
                    f"Gender: **{record[11] or 'Not provided'}** · "
                    f"Mobile: **{record[12] or 'Not provided'}** · "
                    f"Email: **{record[13] or 'Not provided'}**"
                )
                st.write(f"Address: **{record[14] or 'Not provided'}**")
                st.write(f"Parent / Guardian Contact: **{record[15] or 'Not provided'}**")
                st.write(
                    f"College / School: **{record[16] or 'Not provided'}** · "
                    f"Department: **{record[17] or 'Not provided'}**"
                )
                st.write(
                    f"Year of Study: **{record[18] or 'Not provided'}** · "
                    f"Playing Position: **{record[19] or 'Not applicable'}**"
                )
                if record[7] == "team":
                    st.write(f"Team Members: **{record[20] or 'Not provided'}**")
                st.write(f"Previous Sports Experience: **{record[21] or 'Not provided'}**")
    else:
        st.info("No registrations have been submitted yet.")

    st.markdown("</div>", unsafe_allow_html=True)

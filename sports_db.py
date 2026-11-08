"""SQLite persistence and domain rules for the sports event application."""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path


DATABASE_PATH = Path(os.environ.get("SPORTS_DATABASE_PATH", Path(__file__).with_name("sports_event.db")))
PASSWORD_ITERATIONS = 310_000


@contextmanager
def connect(db_path=DATABASE_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _columns(db, table):
    return {row["name"] for row in db.execute(f'PRAGMA table_info("{table}")')}


def initialize_database(db_path=DATABASE_PATH):
    """Create new tables and safely add fields to the original SQLite schema."""
    with connect(db_path) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'organizer', 'student')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT,
                participants INTEGER,
                allocated_event TEXT,
                description TEXT NOT NULL DEFAULT '',
                event_date TEXT,
                start_time TEXT,
                end_time TEXT,
                venue_id INTEGER,
                participant_limit INTEGER NOT NULL DEFAULT 100,
                event_type TEXT NOT NULL DEFAULT 'individual',
                indoor_required INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'published'
                    CHECK (status IN ('draft', 'published', 'cancelled')),
                created_by INTEGER REFERENCES users(id)
            );
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
                email TEXT,
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS venues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                capacity INTEGER NOT NULL CHECK (capacity > 0),
                location TEXT NOT NULL DEFAULT '',
                venue_type TEXT NOT NULL CHECK (venue_type IN ('indoor', 'outdoor')),
                available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
                requirements TEXT NOT NULL DEFAULT ''
            );
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
            );
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_id INTEGER NOT NULL UNIQUE REFERENCES registrations(id),
                event_id INTEGER NOT NULL REFERENCES events(id),
                checked_in_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checked_in_by INTEGER REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id),
                participant TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                place INTEGER CHECK (place BETWEEN 1 AND 3),
                points INTEGER NOT NULL DEFAULT 0,
                recorded_by INTEGER REFERENCES users(id),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, participant)
            );
            CREATE TABLE IF NOT EXISTS scoring_rules (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                first_points INTEGER NOT NULL DEFAULT 5,
                second_points INTEGER NOT NULL DEFAULT 3,
                third_points INTEGER NOT NULL DEFAULT 1
            );
            INSERT OR IGNORE INTO scoring_rules(id) VALUES (1);
            CREATE TABLE IF NOT EXISTS certificates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                certificate_id TEXT NOT NULL UNIQUE,
                registration_id INTEGER NOT NULL UNIQUE REFERENCES registrations(id),
                issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                issued_by INTEGER REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                read_at TEXT
            );
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                created_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                event_id INTEGER NOT NULL REFERENCES events(id),
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                comments TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, event_id)
            );
            """
        )

        # Older releases created these tables before event or identity metadata existed.
        event_additions = {
            "description": "TEXT NOT NULL DEFAULT ''",
            "event_date": "TEXT",
            "start_time": "TEXT",
            "end_time": "TEXT",
            "venue_id": "INTEGER",
            "participant_limit": "INTEGER NOT NULL DEFAULT 100",
            "event_type": "TEXT NOT NULL DEFAULT 'individual'",
            "indoor_required": "INTEGER NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'published'",
            "created_by": "INTEGER",
        }
        for name, definition in event_additions.items():
            if name not in _columns(db, "events"):
                db.execute(f'ALTER TABLE events ADD COLUMN "{name}" {definition}')

        registration_additions = {
            "student_id": "INTEGER REFERENCES users(id)",
            "event_id": "INTEGER REFERENCES events(id)",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "rejection_reason": "TEXT",
            "registered_at": "TEXT",
            "qr_token": "TEXT",
        }
        for name, definition in registration_additions.items():
            if name not in _columns(db, "registrations"):
                db.execute(f'ALTER TABLE registrations ADD COLUMN "{name}" {definition}')
        inbox_additions = {
            "birth_certificate_name": "TEXT",
            "birth_certificate_data": "BLOB",
            "aadhar_card_name": "TEXT",
            "aadhar_card_data": "BLOB",
            "tenth_marksheet_name": "TEXT",
            "tenth_marksheet_data": "BLOB",
            "email": "TEXT",
            "submitted_at": "TEXT",
        }
        for name, definition in inbox_additions.items():
            if name not in _columns(db, "organizer_inbox"):
                db.execute(f'ALTER TABLE organizer_inbox ADD COLUMN "{name}" {definition}')
        inbox_columns = _columns(db, "organizer_inbox")
        if "registration_id" not in inbox_columns:
            db.execute("ALTER TABLE organizer_inbox ADD COLUMN registration_id INTEGER")
        db.execute("UPDATE registrations SET registered_at=CURRENT_TIMESTAMP WHERE registered_at IS NULL")
        db.execute("UPDATE organizer_inbox SET submitted_at=CURRENT_TIMESTAMP WHERE submitted_at IS NULL")

        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_registration_student_event "
            "ON registrations(student_id, event_id) "
            "WHERE student_id IS NOT NULL AND event_id IS NOT NULL"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_registration_qr_token "
            "ON registrations(qr_token) WHERE qr_token IS NOT NULL"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_registration_emis_event "
            "ON registrations(emis_number, event_id) "
            "WHERE emis_number IS NOT NULL AND emis_number != '' AND event_id IS NOT NULL"
        )
        db.execute("CREATE INDEX IF NOT EXISTS ix_registration_status ON registrations(status)")
        db.execute("CREATE INDEX IF NOT EXISTS ix_event_schedule ON events(event_date, venue_id)")


def _password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password, encoded):
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_user(email, name, password, role="student", db_path=DATABASE_PATH):
    email = email.strip().lower()
    name = name.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or not name or len(password) < 10:
        raise ValueError("Provide a name, valid email, and password with at least 10 characters.")
    if role not in {"admin", "organizer", "student"}:
        raise ValueError("Invalid account role.")
    with connect(db_path) as db:
        try:
            cursor = db.execute(
                "INSERT INTO users(email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                (email, name, _password_hash(password), role),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account with that email already exists.") from exc
        return dict(db.execute("SELECT id, email, name, role FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone())


def seed_admin_from_environment(db_path=DATABASE_PATH):
    email = os.environ.get("SPORTS_ADMIN_EMAIL", "").strip()
    password = os.environ.get("SPORTS_ADMIN_PASSWORD", "")
    if not email and not password:
        return
    if not email or not password:
        raise RuntimeError("Set both SPORTS_ADMIN_EMAIL and SPORTS_ADMIN_PASSWORD to bootstrap the admin.")
    with connect(db_path) as db:
        exists = db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if not exists:
        create_user(email, os.environ.get("SPORTS_ADMIN_NAME", "Sports Administrator"), password, "admin", db_path)


def authenticate(email, password, db_path=DATABASE_PATH):
    with connect(db_path) as db:
        row = db.execute(
            "SELECT id, email, name, role, password_hash FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip(),),
        ).fetchone()
    if row and _verify_password(password, row["password_hash"]):
        return {key: row[key] for key in ("id", "email", "name", "role")}
    return None


def list_events(db_path=DATABASE_PATH, include_unpublished=False):
    where = "" if include_unpublished else "WHERE e.status = 'published'"
    with connect(db_path) as db:
        return db.execute(
            f"""
            SELECT e.*, v.name AS venue_name,
                   (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registration_count
            FROM events e LEFT JOIN venues v ON v.id = e.venue_id
            {where} ORDER BY e.event_date, e.start_time, e.id
            """
        ).fetchall()


def create_event(
    event_name, event_date, start_time, end_time, venue_id, participant_limit,
    description="", event_type="individual", indoor_required=False, status="published",
    actor_role="admin", db_path=DATABASE_PATH,
):
    if actor_role != "admin":
        raise PermissionError("Only administrators can create or change events.")
    name = event_name.strip()
    if not name or participant_limit < 1:
        raise ValueError("Event name and a positive participant limit are required.")
    try:
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        scheduled = date.fromisoformat(event_date)
    except ValueError as exc:
        raise ValueError("Enter a valid event date and start/end times.") from exc
    if end <= start or scheduled < date.today():
        raise ValueError("End time must follow start time and event date cannot be in the past.")
    if event_type not in {"individual", "team"} or status not in {"draft", "published"}:
        raise ValueError("Select a valid event type and publishing status.")
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        if venue_id is not None:
            venue = db.execute("SELECT available, capacity FROM venues WHERE id = ?", (venue_id,)).fetchone()
            if not venue or not venue["available"]:
                raise ValueError("Select an available venue.")
            if venue["capacity"] < participant_limit:
                raise ValueError("Venue capacity is smaller than the event participant limit.")
            conflict = db.execute(
                """
                SELECT event_name FROM events
                WHERE venue_id = ? AND event_date = ? AND status != 'cancelled'
                  AND start_time < ? AND end_time > ?
                LIMIT 1
                """,
                (venue_id, event_date, end_time, start_time),
            ).fetchone()
            if conflict:
                raise ValueError(f"Venue time conflicts with {conflict['event_name']}.")
        db.execute(
            """
            INSERT INTO events(event_name, description, event_date, start_time, end_time,
                venue_id, participant_limit, event_type, indoor_required, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, description.strip(), event_date, start_time, end_time, venue_id,
             participant_limit, event_type, int(indoor_required), status),
        )


def save_venue(name, capacity, location, venue_type, available=True, requirements="", db_path=DATABASE_PATH):
    if not name.strip() or capacity < 1 or venue_type not in {"indoor", "outdoor"}:
        raise ValueError("Provide a name, positive capacity, and valid indoor/outdoor type.")
    with connect(db_path) as db:
        cursor = db.execute(
            """INSERT INTO venues(name, capacity, location, venue_type, available, requirements)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name.strip(), capacity, location.strip(), venue_type, int(available), requirements.strip()),
        )
        return cursor.lastrowid


def update_venue(venue_id, name, capacity, location, venue_type, available, requirements,
                 actor_role, db_path=DATABASE_PATH):
    if actor_role != "admin":
        raise PermissionError("Only administrators can edit venues.")
    if not name.strip() or capacity < 1 or venue_type not in {"indoor", "outdoor"}:
        raise ValueError("Provide a name, positive capacity, and valid indoor/outdoor type.")
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM venues WHERE id=?", (venue_id,)).fetchone():
            raise ValueError("Venue not found.")
        too_small = db.execute(
            """SELECT event_name FROM events WHERE venue_id=? AND status != 'cancelled'
               AND participant_limit > ? LIMIT 1""",
            (venue_id, capacity),
        ).fetchone()
        if too_small:
            raise ValueError(f"{too_small['event_name']} exceeds the new venue capacity.")
        indoor_conflict = db.execute(
            """SELECT event_name FROM events WHERE venue_id=? AND status != 'cancelled'
               AND indoor_required=1 AND ?='outdoor' LIMIT 1""",
            (venue_id, venue_type),
        ).fetchone()
        if indoor_conflict:
            raise ValueError(f"{indoor_conflict['event_name']} requires an indoor venue.")
        try:
            db.execute(
                """UPDATE venues SET name=?, capacity=?, location=?, venue_type=?,
                   available=?, requirements=? WHERE id=?""",
                (name.strip(), capacity, location.strip(), venue_type, int(available),
                 requirements.strip(), venue_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("A venue with that name already exists.") from exc


def recommend_venues(participant_count, event_date, start_time, end_time, indoor_required=False, db_path=DATABASE_PATH):
    if participant_count < 1:
        raise ValueError("Participant count must be positive.")
    if datetime.strptime(end_time, "%H:%M").time() <= datetime.strptime(start_time, "%H:%M").time():
        raise ValueError("End time must follow start time.")
    date.fromisoformat(event_date)
    with connect(db_path) as db:
        venues = db.execute("SELECT * FROM venues WHERE available = 1 ORDER BY capacity, name").fetchall()
        recommendations = []
        for venue in venues:
            if venue["capacity"] < participant_count:
                continue
            if indoor_required and venue["venue_type"] != "indoor":
                continue
            conflict = db.execute(
                """SELECT 1 FROM events WHERE venue_id = ? AND event_date = ?
                   AND status != 'cancelled' AND start_time < ? AND end_time > ? LIMIT 1""",
                (venue["id"], event_date, end_time, start_time),
            ).fetchone()
            if conflict:
                continue
            reason = f"Capacity {venue['capacity']} accommodates {participant_count} participants"
            if indoor_required:
                reason += "; indoor requirement is met"
            reason += "; venue is available for this time slot"
            recommendations.append((venue, reason))
        return recommendations


def create_registration(student_id, name, student_class, dob, emis, event_id, email, documents, db_path=DATABASE_PATH):
    name, emis, email = name.strip(), emis.strip(), email.strip().lower()
    if not name or not emis or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter the student's name, EMIS number, and valid email.")
    if student_class not in {str(n) for n in range(6, 13)}:
        raise ValueError("Choose a valid class from 6 to 12.")
    if date.fromisoformat(dob) >= date.today():
        raise ValueError("Date of birth must be in the past.")
    required = {"birth_certificate", "aadhar_card"} if int(student_class) <= 10 else {"tenth_marksheet"}
    if not required.issubset(documents) or any(
        not documents[key][0] or not documents[key][1] for key in required
    ):
        raise ValueError("Upload every document required for the selected class.")
    document_keys = ("birth_certificate", "aadhar_card", "tenth_marksheet")
    docs = {
        key: (documents[key][0], documents[key][1]) if documents.get(key) else (None, None)
        for key in document_keys
    }
    token = secrets.token_urlsafe(24)
    doc_label = " + ".join({
        "birth_certificate": "Birth Certificate",
        "aadhar_card": "Aadhaar Card",
        "tenth_marksheet": "10th Marksheet",
    }[key] for key in sorted(required))
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        user = db.execute("SELECT role, email FROM users WHERE id = ?", (student_id,)).fetchone()
        event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if not user or user["role"] != "student":
            raise PermissionError("Registration requires a student account.")
        if user["email"].lower() != email:
            raise ValueError("Registration email must match the signed-in student account.")
        if not event or event["status"] != "published":
            raise ValueError("This event is not open for registration.")
        count = db.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status IN ('pending', 'approved')",
            (event_id,),
        ).fetchone()[0]
        if count >= event["participant_limit"]:
            raise ValueError("This event has reached its participant limit.")
        try:
            cursor = db.execute(
                """INSERT INTO registrations(name, "class", date_of_birth, emis_number, event,
                   document_type, document_name, email, student_id, event_id, status, qr_token, registered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, CURRENT_TIMESTAMP)""",
                (name, student_class, dob, emis, event["event_name"], doc_label,
                 ", ".join(value[0] for key, value in docs.items() if key in required and value[0]),
                 email, student_id, event_id, token),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError("You have already registered for this event.") from exc
            raise
        registration_id = cursor.lastrowid
        db.execute(
            """INSERT INTO organizer_inbox(registration_id, student_name, student_class, date_of_birth,
               emis_number, event, document_type, status, birth_certificate_name, birth_certificate_data,
               aadhar_card_name, aadhar_card_data, tenth_marksheet_name, tenth_marksheet_data, email)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?, ?, ?, ?, ?)""",
            (registration_id, name, student_class, dob, emis, event["event_name"], doc_label,
             docs["birth_certificate"][0], docs["birth_certificate"][1],
             docs["aadhar_card"][0], docs["aadhar_card"][1],
             docs["tenth_marksheet"][0], docs["tenth_marksheet"][1], email),
        )
        db.execute("UPDATE registrations SET id = id WHERE id = ?", (registration_id,))
        db.execute(
            "INSERT INTO notifications(user_id, message) VALUES (?, ?)",
            (student_id, f"Your registration for {event['event_name']} is pending review."),
        )
        return registration_id, token


def review_registration(registration_id, status, reason, reviewer_id, db_path=DATABASE_PATH):
    if status not in {"approved", "rejected"}:
        raise ValueError("Choose approved or rejected.")
    if status == "rejected" and not reason.strip():
        raise ValueError("A rejection reason is required.")
    with connect(db_path) as db:
        reviewer = db.execute("SELECT role FROM users WHERE id = ?", (reviewer_id,)).fetchone()
        if not reviewer or reviewer["role"] not in {"admin", "organizer"}:
            raise PermissionError("Only staff can review registrations.")
        row = db.execute(
            "SELECT student_id, event FROM registrations WHERE id = ?", (registration_id,)
        ).fetchone()
        if not row:
            raise ValueError("Registration not found.")
        db.execute(
            "UPDATE registrations SET status = ?, rejection_reason = ? WHERE id = ?",
            (status, reason.strip() if status == "rejected" else None, registration_id),
        )
        db.execute(
            "UPDATE organizer_inbox SET status = ? WHERE registration_id = ?",
            (status.title(), registration_id),
        )
        if row["student_id"]:
            message = f"Your registration for {row['event']} was {status}."
            if status == "rejected":
                message += f" Reason: {reason.strip()}"
            db.execute("INSERT INTO notifications(user_id, message) VALUES (?, ?)", (row["student_id"], message))


def mark_attendance(qr_token, actor_id, db_path=DATABASE_PATH):
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        actor = db.execute("SELECT role FROM users WHERE id = ?", (actor_id,)).fetchone()
        if not actor or actor["role"] not in {"admin", "organizer"}:
            raise PermissionError("Only authorized staff can mark attendance.")
        registration = db.execute(
            "SELECT id, event_id, status FROM registrations WHERE qr_token = ?", (qr_token.strip(),)
        ).fetchone()
        if not registration:
            raise ValueError("No registration matches this QR ID.")
        if registration["status"] != "approved":
            raise ValueError("Attendance is available only for approved registrations.")
        try:
            db.execute(
                "INSERT INTO attendance(registration_id, event_id, checked_in_by) VALUES (?, ?, ?)",
                (registration["id"], registration["event_id"], actor_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Attendance has already been recorded.") from exc


def record_result(event_id, participant, score, place, actor_id, db_path=DATABASE_PATH):
    with connect(db_path) as db:
        actor = db.execute("SELECT role FROM users WHERE id = ?", (actor_id,)).fetchone()
        if not actor or actor["role"] not in {"admin", "organizer"}:
            raise PermissionError("Only authorized staff can enter results.")
        event = db.execute("SELECT event_type FROM events WHERE id = ?", (event_id,)).fetchone()
        if not event or not participant.strip() or score < 0 or place not in {1, 2, 3}:
            raise ValueError("Enter a valid event, participant/team, non-negative score, and place.")
        points = db.execute(
            "SELECT first_points, second_points, third_points FROM scoring_rules WHERE id = 1"
        ).fetchone()[place - 1]
        db.execute(
            """INSERT INTO results(event_id, participant, score, place, points, recorded_by)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id, participant) DO UPDATE SET score=excluded.score,
                 place=excluded.place, points=excluded.points, recorded_by=excluded.recorded_by,
                 updated_at=CURRENT_TIMESTAMP""",
            (event_id, participant.strip(), score, place, points, actor_id),
        )


def set_scoring_rules(first, second, third, actor_role, db_path=DATABASE_PATH):
    if actor_role != "admin":
        raise PermissionError("Only administrators can change scoring rules.")
    if min(first, second, third) < 0:
        raise ValueError("Points cannot be negative.")
    with connect(db_path) as db:
        db.execute(
            "UPDATE scoring_rules SET first_points=?, second_points=?, third_points=? WHERE id=1",
            (first, second, third),
        )
        db.execute(
            """UPDATE results SET points=CASE place WHEN 1 THEN ? WHEN 2 THEN ? WHEN 3 THEN ? ELSE 0 END""",
            (first, second, third),
        )


def set_event_status(event_id, status, actor_role, db_path=DATABASE_PATH):
    if actor_role != "admin":
        raise PermissionError("Only administrators can change event visibility.")
    if status not in {"draft", "published", "cancelled"}:
        raise ValueError("Choose a valid event status.")
    with connect(db_path) as db:
        event = db.execute("SELECT event_name, status FROM events WHERE id=?", (event_id,)).fetchone()
        if not event:
            raise ValueError("Event not found.")
        db.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))
        if event["status"] != status:
            students = db.execute(
                "SELECT DISTINCT student_id FROM registrations WHERE event_id=? AND student_id IS NOT NULL",
                (event_id,),
            ).fetchall()
            db.executemany(
                "INSERT INTO notifications(user_id, message) VALUES (?, ?)",
                [(row["student_id"], f"Event update: {event['event_name']} is now {status}.") for row in students],
            )


def update_event(
    event_id, event_name, event_date, start_time, end_time, venue_id,
    participant_limit, description="", event_type="individual",
    indoor_required=False, actor_role="admin", db_path=DATABASE_PATH,
):
    if actor_role != "admin":
        raise PermissionError("Only administrators can edit events.")
    if not event_name.strip() or participant_limit < 1:
        raise ValueError("Event name and a positive participant limit are required.")
    try:
        scheduled = date.fromisoformat(event_date)
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("Enter a valid event date and start/end times.") from exc
    if scheduled < date.today() or end <= start or event_type not in {"individual", "team"}:
        raise ValueError("Use a current/future date, valid time range, and event type.")
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone()
        if not existing:
            raise ValueError("Event not found.")
        current_count = db.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id=? AND status IN ('pending', 'approved')",
            (event_id,),
        ).fetchone()[0]
        if participant_limit < current_count:
            raise ValueError("Participant limit cannot be lower than existing pending/approved registrations.")
        if venue_id is not None:
            venue = db.execute("SELECT available, capacity FROM venues WHERE id=?", (venue_id,)).fetchone()
            if not venue or not venue["available"]:
                raise ValueError("Select an available venue.")
            if venue["capacity"] < participant_limit:
                raise ValueError("Venue capacity is smaller than the event participant limit.")
            conflict = db.execute(
                """SELECT event_name FROM events WHERE venue_id=? AND event_date=?
                   AND status != 'cancelled' AND id != ?
                   AND start_time < ? AND end_time > ? LIMIT 1""",
                (venue_id, event_date, event_id, end_time, start_time),
            ).fetchone()
            if conflict:
                raise ValueError(f"Venue time conflicts with {conflict['event_name']}.")
        before = db.execute(
            "SELECT event_name, event_date, start_time, end_time, venue_id FROM events WHERE id=?",
            (event_id,),
        ).fetchone()
        db.execute(
            """UPDATE events SET event_name=?, description=?, event_date=?, start_time=?, end_time=?,
               venue_id=?, participant_limit=?, event_type=?, indoor_required=? WHERE id=?""",
            (event_name.strip(), description.strip(), event_date, start_time, end_time,
             venue_id, participant_limit, event_type, int(indoor_required), event_id),
        )
        after = (event_name.strip(), event_date, start_time, end_time, venue_id)
        if tuple(before) != after:
            students = db.execute(
                "SELECT DISTINCT student_id FROM registrations WHERE event_id=? AND student_id IS NOT NULL",
                (event_id,),
            ).fetchall()
            db.executemany(
                "INSERT INTO notifications(user_id, message) VALUES (?, ?)",
                [(row["student_id"], f"Schedule update: details for {event_name.strip()} have changed.")
                 for row in students],
            )


def issue_certificate(registration_id, actor_id, db_path=DATABASE_PATH):
    with connect(db_path) as db:
        actor = db.execute("SELECT role FROM users WHERE id=?", (actor_id,)).fetchone()
        if not actor or actor["role"] not in {"admin", "organizer"}:
            raise PermissionError("Only authorized staff can issue certificates.")
        eligible = db.execute(
            """SELECT 1 FROM registrations r JOIN attendance a ON a.registration_id=r.id
               WHERE r.id=? AND r.status='approved'""",
            (registration_id,),
        ).fetchone()
        if not eligible:
            raise ValueError("Certificates require an approved registration and recorded attendance.")
        certificate_id = f"SSP-{secrets.token_hex(6).upper()}"
        try:
            db.execute(
                "INSERT INTO certificates(certificate_id, registration_id, issued_by) VALUES (?, ?, ?)",
                (certificate_id, registration_id, actor_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("A certificate has already been issued for this registration.") from exc
        return certificate_id


def public_certificate(certificate_id, db_path=DATABASE_PATH):
    with connect(db_path) as db:
        return db.execute(
            """SELECT c.certificate_id, c.issued_at, r.event
               FROM certificates c JOIN registrations r ON r.id=c.registration_id
               WHERE c.certificate_id=?""",
            (certificate_id,),
        ).fetchone()


def dashboard_data(db_path=DATABASE_PATH):
    with connect(db_path) as db:
        return {
            "events": db.execute("SELECT COUNT(*) FROM events WHERE status != 'cancelled'").fetchone()[0],
            "registrations": db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0],
            "pending": db.execute("SELECT COUNT(*) FROM registrations WHERE status='pending'").fetchone()[0],
            "approved": db.execute("SELECT COUNT(*) FROM registrations WHERE status='approved'").fetchone()[0],
            "attendance": db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0],
            "by_event": db.execute(
                """SELECT event, COUNT(*) AS registrations FROM registrations
                   GROUP BY event ORDER BY registrations DESC"""
            ).fetchall(),
        }

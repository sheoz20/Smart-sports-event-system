import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import sports_db


class SportsDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "sports_test.db"
        sports_db.initialize_database(self.path)
        self.admin = sports_db.create_user("admin@example.test", "Admin", "secure-password-1", "admin", self.path)
        self.organizer = sports_db.create_user(
            "organizer@example.test", "Organizer", "secure-password-2", "organizer", self.path
        )
        self.student = sports_db.create_user(
            "student@example.test", "Student", "secure-password-3", "student", self.path
        )
        self.venue_id = sports_db.save_venue(
            "Main Hall", 120, "School", "indoor", True, db_path=self.path
        )
        self.event_id = self.make_event()

    def tearDown(self):
        self.temporary.cleanup()

    def make_event(self, name="Track Meet", start="09:00", end="10:00", limit=20):
        next_day = (date.today() + timedelta(days=1)).isoformat()
        with sports_db.connect(self.path) as conn:
            conn.execute(
                """INSERT INTO events(event_name, event_date, start_time, end_time, venue_id,
                   participant_limit, event_type, status) VALUES (?, ?, ?, ?, ?, ?, 'individual', 'published')""",
                (name, next_day, start, end, self.venue_id, limit),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def registration(self, student=None, event_id=None, emis="EMIS-001", student_class="11", docs=None):
        student = student or self.student
        docs = docs if docs is not None else {"tenth_marksheet": ("marks.pdf", b"sample")}
        return sports_db.create_registration(
            student["id"], student["name"], student_class, "2012-01-02", emis,
            event_id or self.event_id, student["email"], docs, self.path,
        )

    def test_password_hash_and_authentication(self):
        with sports_db.connect(self.path) as conn:
            stored = conn.execute("SELECT password_hash FROM users WHERE id=?", (self.student["id"],)).fetchone()[0]
        self.assertNotIn("secure-password-3", stored)
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertEqual(self.student["id"], sports_db.authenticate(
            "STUDENT@example.test", "secure-password-3", self.path
        )["id"])
        self.assertIsNone(sports_db.authenticate("student@example.test", "wrong-password", self.path))

    def test_registration_class_documents_duplicates_and_status(self):
        with self.assertRaisesRegex(ValueError, "required for the selected class"):
            self.registration(docs={})
        registration_id, token = self.registration()
        self.assertTrue(token)
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.registration()
        second_student = sports_db.create_user(
            "other@example.test", "Other Student", "secure-password-4", "student", self.path
        )
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.registration(student=second_student)
        sports_db.review_registration(registration_id, "rejected", "Missing eligibility", self.organizer["id"], self.path)
        with sports_db.connect(self.path) as conn:
            status, reason = conn.execute(
                "SELECT status, rejection_reason FROM registrations WHERE id=?", (registration_id,)
            ).fetchone()
            notification = conn.execute(
                "SELECT message FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (self.student["id"],),
            ).fetchone()[0]
        self.assertEqual((status, reason), ("rejected", "Missing eligibility"))
        self.assertIn("Missing eligibility", notification)
        with self.assertRaisesRegex(ValueError, "required"):
            sports_db.review_registration(registration_id, "rejected", "", self.organizer["id"], self.path)
        sports_db.review_registration(registration_id, "approved", "", self.organizer["id"], self.path)
        next_day = (date.today() + timedelta(days=1)).isoformat()
        sports_db.update_event(
            self.event_id, "Track Meet Revised", next_day, "09:15", "10:15",
            self.venue_id, 20, actor_role="admin", db_path=self.path,
        )
        with sports_db.connect(self.path) as conn:
            schedule_notice = conn.execute(
                "SELECT message FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (self.student["id"],),
            ).fetchone()[0]
        self.assertIn("Schedule update", schedule_notice)

    def test_primary_school_documents_and_staff_access(self):
        with self.assertRaisesRegex(ValueError, "required"):
            self.registration(student_class="8", docs={"birth_certificate": ("birth.pdf", b"birth")})
        registration_id, _ = self.registration(
            student_class="8",
            docs={
                "birth_certificate": ("birth.pdf", b"birth"),
                "aadhar_card": ("id.pdf", b"identity"),
            },
        )
        with self.assertRaises(PermissionError):
            sports_db.review_registration(registration_id, "approved", "", self.student["id"], self.path)

    def test_schedule_conflict_venue_capacity_and_recommendations(self):
        next_day = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaises(PermissionError):
            sports_db.create_event(
                "Unauthorized", next_day, "12:00", "13:00", None, 25,
                actor_role="organizer", db_path=self.path,
            )
        with self.assertRaisesRegex(ValueError, "capacity"):
            sports_db.create_event(
                "Too large", next_day, "12:00", "13:00", self.venue_id, 200,
                actor_role="admin", db_path=self.path,
            )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            sports_db.create_event(
                "Conflicting event", next_day, "09:30", "10:30", self.venue_id, 25,
                actor_role="admin", db_path=self.path,
            )
        self.make_event("Afternoon event", "10:30", "11:30")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            sports_db.update_event(
                self.event_id, "Updated", next_day, "10:00", "11:00", self.venue_id, 20,
                actor_role="admin", db_path=self.path,
            )
        with self.assertRaisesRegex(ValueError, "positive"):
            sports_db.recommend_venues(0, next_day, "08:00", "09:00", db_path=self.path)
        suggestions = sports_db.recommend_venues(
            100, next_day, "12:00", "13:00", True, self.path
        )
        self.assertEqual(suggestions[0][0]["name"], "Main Hall")
        self.assertIn("Capacity 120", suggestions[0][1])
        sports_db.update_venue(
            self.venue_id, "Updated Hall", 200, "North Wing", "indoor", False, "",
            "admin", self.path,
        )
        self.assertEqual(
            sports_db.recommend_venues(100, next_day, "12:00", "13:00", True, self.path),
            [],
        )
        self.assertEqual(sports_db.list_events(self.path)[0]["event_name"], "Track Meet")

    def test_attendance_results_certificate_and_dashboard(self):
        registration_id, token = self.registration()
        with self.assertRaises(PermissionError):
            sports_db.mark_attendance(token, self.student["id"], self.path)
        with self.assertRaisesRegex(ValueError, "approved"):
            sports_db.mark_attendance(token, self.organizer["id"], self.path)
        sports_db.review_registration(registration_id, "approved", "", self.organizer["id"], self.path)
        sports_db.mark_attendance(token, self.organizer["id"], self.path)
        with self.assertRaisesRegex(ValueError, "already"):
            sports_db.mark_attendance(token, self.organizer["id"], self.path)
        sports_db.record_result(self.event_id, "Student", 10, 1, self.organizer["id"], self.path)
        with sports_db.connect(self.path) as conn:
            result = conn.execute("SELECT points FROM results").fetchone()[0]
        self.assertEqual(result, 5)
        sports_db.set_scoring_rules(8, 4, 2, "admin", self.path)
        with sports_db.connect(self.path) as conn:
            result = conn.execute("SELECT points FROM results").fetchone()[0]
        self.assertEqual(result, 8)
        certificate_id = sports_db.issue_certificate(registration_id, self.organizer["id"], self.path)
        public_certificate = sports_db.public_certificate(certificate_id, self.path)
        self.assertEqual(public_certificate["event"], "Track Meet")
        self.assertNotIn("name", public_certificate.keys())
        with self.assertRaisesRegex(ValueError, "already"):
            sports_db.issue_certificate(registration_id, self.organizer["id"], self.path)
        metrics = sports_db.dashboard_data(self.path)
        self.assertEqual((metrics["events"], metrics["registrations"], metrics["approved"], metrics["attendance"]),
                         (1, 1, 1, 1))

    def test_legacy_schema_migrates_without_losing_records(self):
        legacy_path = Path(self.temporary.name) / "legacy.db"
        conn = sqlite3.connect(legacy_path)
        conn.executescript(
            """
            CREATE TABLE registrations(id INTEGER PRIMARY KEY, name TEXT, "class" TEXT,
                date_of_birth TEXT, emis_number TEXT, event TEXT, document_type TEXT,
                document_name TEXT, email TEXT);
            CREATE TABLE events(id INTEGER PRIMARY KEY, event_name TEXT, participants INTEGER, allocated_event TEXT);
            CREATE TABLE organizer_inbox(id INTEGER PRIMARY KEY, student_name TEXT, student_class TEXT,
                date_of_birth TEXT, emis_number TEXT, event TEXT, document_type TEXT, status TEXT);
            INSERT INTO registrations VALUES(1, 'Legacy Student', '9', '2011-01-01',
                'EMIS-LEGACY', 'Football', 'Birth Certificate', 'birth.pdf', 'legacy@example.test');
            INSERT INTO events VALUES(1, 'Football', 20, 'Allocated');
            """
        )
        conn.commit()
        conn.close()
        sports_db.initialize_database(legacy_path)
        with sports_db.connect(legacy_path) as migrated:
            student = migrated.execute("SELECT name, event FROM registrations WHERE id=1").fetchone()
            event = migrated.execute("SELECT event_name, status FROM events WHERE id=1").fetchone()
        self.assertEqual(tuple(student), ("Legacy Student", "Football"))
        self.assertEqual(tuple(event), ("Football", "published"))


if __name__ == "__main__":
    unittest.main()

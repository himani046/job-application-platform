import tempfile
import unittest
from pathlib import Path

import backend.application_store as store
import backend.database as database
from backend.models import ApplicationRecord


class ApplicationIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.original = database.DATABASE_PATH
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.tmp.name) / "platform.db"
        database.init_db()

    def tearDown(self):
        database.DATABASE_PATH = self.original
        self.tmp.cleanup()

    def make_record(self, application_id):
        return ApplicationRecord(
            id=application_id,
            profile_id="profile-1",
            job_id="job-123",
            job_url="https://example.com/jobs/123",
            portal="custom",
            status="queued",
            created_at="2026-10-02T00:00:00+00:00",
            updated_at="2026-10-02T00:00:00+00:00",
        )

    def test_same_logical_application_returns_existing_record(self):
        first = store.create_application(self.make_record("11111111-1111-1111-1111-111111111111"))
        second = store.create_application(self.make_record("22222222-2222-2222-2222-222222222222"))

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.application_key, second.application_key)

        with database.connection() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM applications").fetchone()["n"]
        self.assertEqual(count, 1)

    def test_identity_is_distinct_across_profiles_and_portals(self):
        first = store.create_application(self.make_record("11111111-1111-1111-1111-111111111111"))
        other = self.make_record("22222222-2222-2222-2222-222222222222")
        other.profile_id = "profile-2"
        second = store.create_application(other)

        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.application_key, second.application_key)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

import backend.database as database


class DatabaseTests(unittest.TestCase):
    def test_schema_and_transaction_rollback(self):
        original = database.DATABASE_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                database.DATABASE_PATH = Path(tmp) / "platform.db"
                database.init_db()
                with database.connection() as conn:
                    conn.execute(
                        "INSERT INTO jobs (id,portal,title,url,created_at) VALUES (?,?,?,?,?)",
                        ("job-1", "custom", "ML Engineer", "https://example.com/job/1", "2026-10-02T00:00:00+00:00"),
                    )
                with self.assertRaises(RuntimeError):
                    with database.connection() as conn:
                        conn.execute(
                            "INSERT INTO jobs (id,portal,title,url,created_at) VALUES (?,?,?,?,?)",
                            ("job-2", "custom", "Data Scientist", "https://example.com/job/2", "2026-10-02T00:00:00+00:00"),
                        )
                        raise RuntimeError("rollback")
                with database.connection() as conn:
                    rows = conn.execute("SELECT id FROM jobs ORDER BY id").fetchall()
                self.assertEqual([row["id"] for row in rows], ["job-1"])
        finally:
            database.DATABASE_PATH = original


if __name__ == "__main__":
    unittest.main()

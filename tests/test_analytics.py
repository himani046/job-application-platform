import unittest

from backend.analytics import summarize_applications
from backend.models import ApplicationRecord


class AnalyticsTests(unittest.TestCase):
    def test_empty_summary(self):
        result = summarize_applications([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["submission_rate"], 0)

    def test_status_and_submission_metrics(self):
        records = [
            ApplicationRecord(
                id="00000000-0000-0000-0000-000000000001",
                profile_id="profile", job_id="job1", job_url="https://example.com/1",
                portal="greenhouse", status="submitted",
                created_at="2026-10-02T00:00:00+00:00",
                updated_at="2026-10-02T00:10:00+00:00",
            ),
            ApplicationRecord(
                id="00000000-0000-0000-0000-000000000002",
                profile_id="profile", job_id="job2", job_url="https://example.com/2",
                portal="lever", status="failed",
                created_at="2026-10-02T00:00:00+00:00",
                updated_at="2026-10-02T00:05:00+00:00",
            ),
        ]
        result = summarize_applications(records)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["submitted"], 1)
        self.assertEqual(result["submission_rate"], 0.5)
        self.assertEqual(result["by_portal"]["greenhouse"], 1)
        self.assertEqual(result["average_lifecycle_seconds"], 450)


if __name__ == "__main__":
    unittest.main()

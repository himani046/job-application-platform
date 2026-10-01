import unittest

from backend.jobs import canonical_job_url, job_fingerprint, normalize_job


class JobTests(unittest.TestCase):
    def test_tracking_parameters_are_removed(self):
        first = "https://Example.com/jobs/123/?utm_source=x&refId=abc&foo=bar"
        second = "https://example.com/jobs/123?foo=bar"
        self.assertEqual(canonical_job_url(first), canonical_job_url(second))

    def test_fingerprint_is_stable(self):
        self.assertEqual(
            job_fingerprint("https://example.com/job/1", "ML Engineer"),
            job_fingerprint("https://EXAMPLE.com/job/1/", "  ML   Engineer "),
        )

    def test_normalize_preserves_metadata(self):
        job = normalize_job(
            {
                "url": "https://example.com/job/1",
                "title": "ML Engineer",
                "company": "Example",
                "location": "India",
                "description": "Python and machine learning",
            },
            "custom",
        )
        self.assertEqual(job.company, "Example")
        self.assertEqual(job.location, "India")
        self.assertIn("machine learning", job.description)


if __name__ == "__main__":
    unittest.main()

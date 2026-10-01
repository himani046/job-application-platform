import unittest

from backend.models import RunRequest
from backend.portals import get_adapter


class PortalAdapterTests(unittest.TestCase):
    def test_linkedin_builds_location_search(self):
        request = RunRequest(
            mode="discover",
            portal="linkedin",
            keywords="Machine Learning",
            search_location="India",
            workplace_type="remote",
        )
        adapter = get_adapter("linkedin", request)
        url = adapter.build_discovery_url(request)

        self.assertIn("linkedin.com/jobs/search", url)
        self.assertIn("location=India", url)
        self.assertIn("f_WT=2", url)
        self.assertTrue(adapter.accepts_url(url))

    def test_naukri_builds_keyword_search(self):
        request = RunRequest(
            mode="discover",
            portal="naukri",
            keywords="Python Developer",
            search_location="India",
        )
        adapter = get_adapter("naukri", request)
        url = adapter.build_discovery_url(request)

        self.assertEqual(url, "https://www.naukri.com/python-developer-jobs")
        self.assertTrue(adapter.accepts_url(url))

    def test_ats_rejects_wrong_host(self):
        adapter = get_adapter("greenhouse")
        self.assertFalse(
            adapter.accepts_url("https://example.com/jobs/123")
        )

    def test_greenhouse_form_rules(self):
        adapter = get_adapter("greenhouse")
        rules = adapter.form_rules()

        self.assertIn('input[name="job_application[email]"]', rules.field_selectors["email"])
        self.assertIn(r"\bresume\b", rules.field_patterns["resume"])
        self.assertIn("submit application", rules.submit_button_patterns)
        self.assertTrue(
            adapter.accepts_url("https://boards.greenhouse.io/example/jobs/123")
        )

    def test_lever_form_rules(self):
        adapter = get_adapter("lever")
        rules = adapter.form_rules()

        self.assertIn('input[name="email"]', rules.field_selectors["email"])
        self.assertIn(r"\bphone\b", rules.field_patterns["phone"])
        self.assertIn("submit application", rules.submit_button_patterns)
        self.assertTrue(
            adapter.accepts_url("https://jobs.lever.co/example/123")
        )

    def test_workday_keeps_generic_form_fallback(self):
        adapter = get_adapter("workday")
        self.assertEqual(adapter.form_rules().field_selectors, {})


if __name__ == "__main__":
    unittest.main()

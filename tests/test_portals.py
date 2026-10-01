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


if __name__ == "__main__":
    unittest.main()

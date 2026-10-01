import unittest

from backend.matcher import match_job
from backend.models import JobRecord, Profile


class MatcherTests(unittest.TestCase):
    def test_skill_overlap_raises_score(self):
        profile = Profile(skills=["Python", "FastAPI", "Machine Learning"])
        job = JobRecord(
            id="1",
            portal="custom",
            title="Python ML Engineer",
            url="https://example.com/jobs/1",
            description="Build FastAPI services for machine learning systems.",
        )
        result = match_job(profile, job)
        self.assertGreater(result.score, 0.5)
        self.assertIn("python", result.matched_skills)

    def test_missing_experience_is_explained(self):
        profile = Profile(years_of_experience=1, skills=["Python"])
        job = JobRecord(
            id="2",
            portal="custom",
            title="Python Engineer",
            url="https://example.com/jobs/2",
            description="Requires 3+ years of experience.",
        )
        result = match_job(profile, job)
        self.assertEqual(result.missing_required_years, 2.0)
        self.assertTrue(any("below" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()

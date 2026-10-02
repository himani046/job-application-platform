import unittest

from backend.application_planner import extract_job_requirements, plan_application
from backend.models import PersonalDetails, OnlineProfiles, Profile


class PlannerTests(unittest.TestCase):
    def profile(self):
        return Profile(
            personal=PersonalDetails(first_name="A", last_name="B", full_name="A B", email="a@example.com"),
            online_profiles=OnlineProfiles(),
            skills=["Python", "SQL"],
            years_of_experience=2,
        )

    def test_plans_safe_and_review_fields(self):
        result = plan_application([
            {"key": "1", "kind": "text", "label": "First Name", "required": True, "filled": False, "options": [], "meta": ""},
            {"key": "2", "kind": "radio", "label": "Will you require visa sponsorship?", "required": True, "filled": False, "options": [], "meta": ""},
        ], self.profile())
        self.assertEqual(result["fields"][0]["action"], "auto_fill")
        self.assertEqual(result["fields"][1]["action"], "review")
        self.assertTrue(result["requires_human_review"])

    def test_requirement_extraction(self):
        result = extract_job_requirements("At least 2 years of experience with Python and SQL. Remote role.")
        self.assertEqual(result["required_years"], 2.0)
        self.assertIn("python", result["skills"])
        self.assertTrue(result["remote"])


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.models import Education, PersonalDetails, OnlineProfiles, Profile
from backend.universal_form import build_field_spec, plan_fields


class UniversalFormTests(unittest.TestCase):
    def make_profile(self):
        return Profile(
            personal=PersonalDetails(
                first_name="TestFirst",
                last_name="TestLast",
                full_name="TestFirst TestLast",
                email="test@example.invalid",
                phone="+00 0000000000",
                city="Test City",
                state="Test State",
                country="Test Country",
            ),
            online_profiles=OnlineProfiles(
                linkedin="https://example.invalid/in/test",
                github="https://example.invalid/test",
                portfolio="https://example.invalid",
            ),
            education=[Education(institution="Test University", degree="B.Tech")],
            years_of_experience=2,
            skills=["Python", "Machine Learning", "PyTorch", "SQL"],
        )

    def test_semantic_classification(self):
        spec = build_field_spec({
            "key": "x",
            "kind": "text",
            "label": "How many years have you worked with Python?",
            "meta": "",
            "required": True,
            "filled": False,
            "options": [],
        })
        self.assertEqual(spec.semantic, "years_experience")

    def test_profile_answer_plan(self):
        plan = plan_fields([
            {"key": "1", "kind": "text", "label": "First Name", "required": True, "filled": False, "options": [], "meta": ""},
            {"key": "2", "kind": "text", "label": "Email Address", "required": True, "filled": False, "options": [], "meta": ""},
        ], self.make_profile())
        self.assertEqual(plan[0]["answer"], "TestFirst")
        self.assertEqual(plan[1]["answer"], "test@example.invalid")
        self.assertEqual(plan[0]["action"], "fill")

    def test_skill_set_uses_resume_profile_skills(self):
        plan = plan_fields([
            {
                "key": "skills",
                "kind": "text",
                "label": "Skill Set",
                "required": True,
                "filled": False,
                "options": [],
                "meta": "",
            },
        ], self.make_profile())
        self.assertEqual(
            plan[0]["answer"],
            "Python, Machine Learning, PyTorch, SQL",
        )
        self.assertEqual(plan[0]["action"], "fill")

    def test_sensitive_fields_require_review(self):
        plan = plan_fields([
            {"key": "1", "kind": "radio", "label": "Will you require visa sponsorship?", "required": True, "filled": False,
             "options": [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}], "meta": ""},
        ], self.make_profile())
        self.assertTrue(plan[0]["sensitive"])
        self.assertEqual(plan[0]["action"], "review")
        self.assertIsNone(plan[0]["answer"])


if __name__ == "__main__":
    unittest.main()

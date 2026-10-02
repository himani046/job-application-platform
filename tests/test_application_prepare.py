import unittest

from backend.application_prepare import classify_field, review_field, submission_blockers


class ApplicationPreparationTests(unittest.TestCase):
    def test_salary_requires_review(self):
        result = classify_field("Expected salary")
        self.assertTrue(result.sensitive)
        self.assertEqual(result.category, "salary")

    def test_work_authorization_requires_review(self):
        result = classify_field("Are you legally authorized to work in the country?")
        self.assertTrue(result.sensitive)
        self.assertEqual(result.category, "work_authorization")

    def test_demographic_question_requires_review(self):
        result = classify_field("Gender identity")
        self.assertTrue(result.sensitive)
        self.assertEqual(result.category, "demographic")

    def test_normal_profile_field_is_not_sensitive(self):
        result = classify_field("Email address")
        self.assertFalse(result.sensitive)
        self.assertEqual(result.category, "standard")

    def test_required_unfilled_field_is_review_required(self):
        result = review_field({
            "key": "abc",
            "label": "Phone",
            "kind": "text",
            "required": True,
            "filled": False,
        })
        self.assertTrue(result["review_required"])
        self.assertFalse(result["sensitive"])

    def test_submission_guard_blocks_without_human_approval(self):
        blockers = submission_blockers([], [], human_approved=False)
        self.assertIn("Explicit human approval has not been granted.", blockers)

    def test_submission_guard_blocks_missing_required_fields(self):
        blockers = submission_blockers([
            {"label": "Phone", "required": True, "filled": False, "kind": "text"},
        ], [], human_approved=True)
        self.assertTrue(any("Missing required fields" in item for item in blockers))


if __name__ == "__main__":
    unittest.main()

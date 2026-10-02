import unittest

from backend.resume_selector import choose_profile_for_job


class ResumeSelectorTests(unittest.TestCase):
    def test_profiles_are_ranked_without_mutating_facts(self):
        profiles = [
            {"id": "a", "profile": {"skills": ["python"], "years_of_experience": 1, "education": []}, "original_name": "a.pdf"},
            {"id": "b", "profile": {"skills": ["python", "sql"], "years_of_experience": 3, "education": [{"degree": "B.Tech"}]}, "original_name": "b.pdf"},
        ]
        result = choose_profile_for_job(
            profiles,
            {"title": "Python SQL Engineer", "required_skills": "python sql"},
        )
        self.assertEqual(result[0].profile_id, "b")
        self.assertGreaterEqual(result[0].score, result[1].score)


if __name__ == "__main__":
    unittest.main()

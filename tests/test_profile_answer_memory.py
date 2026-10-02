import tempfile
import unittest
from pathlib import Path

import backend.storage as storage
from backend.models import Profile


class ProfileAnswerMemoryTests(unittest.TestCase):
    def test_manual_answer_is_saved_to_the_selected_profile(self):
        original_profile_dir = storage.PROFILE_DIR
        original_resume_dir = storage.RESUME_DIR

        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                storage.PROFILE_DIR = root / "profiles"
                storage.RESUME_DIR = root / "resumes"
                storage.PROFILE_DIR.mkdir()
                storage.RESUME_DIR.mkdir()

                profile = Profile()
                record = storage.create_profile(
                    profile,
                    b"resume",
                    ".pdf",
                    "resume.pdf",
                )

                storage.remember_answer(
                    record["id"],
                    "What is your preferred work location?",
                    "Remote",
                )

                saved = storage.get_profile(record["id"])
                self.assertEqual(
                    saved.custom_answers[
                        "what is your preferred work location"
                    ],
                    "Remote",
                )
        finally:
            storage.PROFILE_DIR = original_profile_dir
            storage.RESUME_DIR = original_resume_dir

    def test_answer_memory_is_profile_specific(self):
        original_profile_dir = storage.PROFILE_DIR
        original_resume_dir = storage.RESUME_DIR

        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                storage.PROFILE_DIR = root / "profiles"
                storage.RESUME_DIR = root / "resumes"
                storage.PROFILE_DIR.mkdir()
                storage.RESUME_DIR.mkdir()

                first = storage.create_profile(
                    Profile(),
                    b"resume-a",
                    ".pdf",
                    "a.pdf",
                )
                second = storage.create_profile(
                    Profile(),
                    b"resume-b",
                    ".pdf",
                    "b.pdf",
                )

                storage.remember_answer(
                    first["id"],
                    "Preferred work location",
                    "Remote",
                )

                first_saved = storage.get_profile(first["id"])
                second_saved = storage.get_profile(second["id"])

                self.assertEqual(
                    first_saved.custom_answers["preferred work location"],
                    "Remote",
                )
                self.assertNotIn(
                    "preferred work location",
                    second_saved.custom_answers,
                )
        finally:
            storage.PROFILE_DIR = original_profile_dir
            storage.RESUME_DIR = original_resume_dir


if __name__ == "__main__":
    unittest.main()

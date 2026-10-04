import unittest

from backend.common_answers import (
    COMMON_QUESTIONS,
    common_answer_for_key,
    common_answer_for_question,
    normalize_common_question,
    save_common_answer,
)


class CommonAnswerTests(unittest.TestCase):
    def test_current_ctc_variations_share_one_answer(self):
        answers = {"current ctc": "15.26 LPA"}

        self.assertEqual(
            common_answer_for_question(
                "What is your current compensation?",
                answers,
            ),
            "15.26 LPA",
        )
        self.assertEqual(
            common_answer_for_question(
                "CURRENT CTC",
                answers,
            ),
            "15.26 LPA",
        )

    def test_notice_period_variations_share_one_answer(self):
        answers = {"notice period": "90 days"}

        self.assertEqual(
            common_answer_for_question(
                "What is your notice duration?",
                answers,
            ),
            "90 days",
        )

    def test_last_working_day_variations_share_one_answer(self):
        answers = {
            "last working day / available date": "26/02/2027",
        }

        self.assertEqual(
            common_answer_for_question(
                "What is your available date to join?",
                answers,
            ),
            "26/02/2027",
        )

    def test_office_location_yes_no_variation(self):
        answers = {
            "comfortable working from the specified office?": "Yes",
        }

        self.assertEqual(
            common_answer_for_question(
                "Are you comfortable working from the Bengaluru office?",
                answers,
            ),
            "Yes",
        )

    def test_save_common_answer_uses_canonical_question_key(self):
        answers = {}
        save_common_answer(answers, "expected_ctc", "25 LPA")

        self.assertEqual(answers["expected ctc"], "25 LPA")
        self.assertEqual(
            common_answer_for_key("expected_ctc", answers),
            "25 LPA",
        )

    def test_common_question_catalog_is_grouped(self):
        categories = {item.category for item in COMMON_QUESTIONS}
        self.assertIn("Compensation", categories)
        self.assertIn("Availability", categories)
        self.assertIn("Work arrangement", categories)

    def test_normalization(self):
        self.assertEqual(
            normalize_common_question(" Current CTC:* "),
            "current ctc",
        )


if __name__ == "__main__":
    unittest.main()

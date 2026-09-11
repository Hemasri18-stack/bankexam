"""
Unit tests for the analytics engine (section 35 of the spec).
Run with:  python3 -m unittest test_analytics.py -v
No external test framework required - uses the standard library's unittest.
"""
import unittest
import datetime
import analytics as an


def q(attempted=1, correct=1, difficulty="Medium", time_taken=45, topic_id=1, test_id=1, marks=1, neg=0):
    return {
        "attempted": attempted, "correct": correct, "difficulty": difficulty,
        "time_taken_seconds": time_taken, "topic_id": topic_id, "test_id": test_id,
        "marks": marks, "negative_marks": neg,
    }


class TestScoreAndAccuracy(unittest.TestCase):
    def test_basic_accuracy_and_score(self):
        questions = [
            q(1, 1, marks=1, neg=0),
            q(1, 0, marks=0, neg=0.25),
            q(1, 1, marks=1, neg=0),
            q(0, 0, marks=0, neg=0),  # unattempted
        ]
        result = an.analyze_test(questions)
        self.assertEqual(result["total_questions"], 4)
        self.assertEqual(result["attempted"], 3)
        self.assertEqual(result["unattempted"], 1)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["incorrect"], 1)
        self.assertAlmostEqual(result["accuracy"], 66.7, places=1)
        self.assertAlmostEqual(result["attempt_rate"], 75.0, places=1)
        self.assertAlmostEqual(result["score"], 1.75, places=2)
        self.assertAlmostEqual(result["negative_marks"], 0.25, places=2)

    def test_negative_marking(self):
        questions = [q(1, 0, marks=0, neg=0.25) for _ in range(4)] + [q(1, 1, marks=1, neg=0)]
        result = an.analyze_test(questions)
        self.assertAlmostEqual(result["score"], 1 - 4 * 0.25, places=2)

    def test_difficulty_accuracy(self):
        questions = [
            q(1, 1, difficulty="Easy"), q(1, 1, difficulty="Easy"),
            q(1, 0, difficulty="Hard"), q(1, 1, difficulty="Hard"),
        ]
        result = an.analyze_test(questions)
        self.assertEqual(result["easy_accuracy"], 100.0)
        self.assertEqual(result["hard_accuracy"], 50.0)

    def test_empty_test(self):
        result = an.analyze_test([])
        self.assertEqual(result["total_questions"], 0)
        self.assertEqual(result["accuracy"], 0.0)


class TestTopicAggregation(unittest.TestCase):
    def test_group_by_topic(self):
        questions = [q(topic_id=1, correct=1) for _ in range(6)] + [q(topic_id=1, correct=0) for _ in range(2)]
        questions += [q(topic_id=2, correct=1) for _ in range(3)] + [q(topic_id=2, correct=0) for _ in range(4)]
        result = an.analyze_by_topic(questions, {1: "Percentage", 2: "Profit & Loss"})
        by_name = {r["topic_name"]: r for r in result}
        self.assertEqual(by_name["Percentage"]["accuracy"], 75.0)
        self.assertAlmostEqual(by_name["Profit & Loss"]["accuracy"], 42.9, places=1)
        # sorted ascending by accuracy -> weakest first
        self.assertEqual(result[0]["topic_name"], "Profit & Loss")


class TestWeakTopicDetection(unittest.TestCase):
    def test_insufficient_data_flagged(self):
        # only 1 test, 5 questions -> below MIN_QUESTIONS(10) and MIN_TESTS(2)
        questions = [q(test_id=1, correct=1) for _ in range(3)] + [q(test_id=1, correct=0) for _ in range(2)]
        result = an.compute_topic_weakness(1, "Percentage", questions, [])
        self.assertTrue(result["insufficient_data"])

    def test_sufficient_via_question_count(self):
        # 1 test but 12 questions -> passes via MIN_QUESTIONS
        questions = [q(test_id=1, correct=1) for _ in range(6)] + [q(test_id=1, correct=0) for _ in range(6)]
        result = an.compute_topic_weakness(1, "Percentage", questions, [])
        self.assertFalse(result["insufficient_data"])

    def test_sufficient_via_test_count(self):
        questions = [q(test_id=1, correct=1) for _ in range(3)] + [q(test_id=2, correct=0) for _ in range(3)]
        result = an.compute_topic_weakness(1, "Percentage", questions, [])
        self.assertFalse(result["insufficient_data"])

    def test_low_accuracy_classified_weak_or_critical(self):
        questions = [q(test_id=1, correct=0, time_taken=100) for _ in range(10)]
        questions += [q(test_id=1, correct=1) for _ in range(2)]
        mistakes = [{"mistake_type": "Concept Mistake"} for _ in range(8)]
        result = an.compute_topic_weakness(1, "Profit & Loss", questions, mistakes)
        self.assertIn(result["classification"], ("Weak", "Critical Weakness"))

    def test_high_accuracy_classified_strong(self):
        questions = [q(test_id=1, correct=1, time_taken=30) for _ in range(20)]
        result = an.compute_topic_weakness(1, "Time & Work", questions, [])
        self.assertIn(result["classification"], ("Strong", "Excellent"))

    def test_classify_weakness_bands(self):
        self.assertEqual(an.classify_weakness(10), "Excellent")
        self.assertEqual(an.classify_weakness(30), "Strong")
        self.assertEqual(an.classify_weakness(50), "Average")
        self.assertEqual(an.classify_weakness(70), "Weak")
        self.assertEqual(an.classify_weakness(90), "Critical Weakness")

    def test_speed_vs_accuracy_distinction(self):
        """Two students with 100% accuracy but different speed should not both look identical -
        the faster one should have a materially lower (or equal) weakness score."""
        fast = [q(test_id=1, correct=1, time_taken=24) for _ in range(10)] + [q(test_id=2, correct=1, time_taken=24) for _ in range(2)]
        slow = [q(test_id=1, correct=1, time_taken=110) for _ in range(10)] + [q(test_id=2, correct=1, time_taken=110) for _ in range(2)]
        fast_result = an.compute_topic_weakness(1, "Topic", fast, [])
        slow_result = an.compute_topic_weakness(2, "Topic", slow, [])
        self.assertLessEqual(fast_result["weakness_score"], slow_result["weakness_score"])


class TestMistakeAnalysis(unittest.TestCase):
    def test_dominant_mistake_type(self):
        mistakes = [{"mistake_type": "Concept Mistake"}] * 6 + [{"mistake_type": "Silly Mistake"}] * 2
        result = an.analyze_mistakes(mistakes)
        self.assertEqual(result["top_type"], "Concept Mistake")
        self.assertIn("Concept Mistakes", result["interpretation"])

    def test_no_mistakes(self):
        result = an.analyze_mistakes([])
        self.assertEqual(result["counts"], {})


class TestRevisionScheduling(unittest.TestCase):
    def test_stage_dates(self):
        dates = an.build_revision_dates("2026-01-01")
        stages = dict(dates)
        self.assertEqual(stages["Day 1"], "2026-01-02")
        self.assertEqual(stages["Day 3"], "2026-01-04")
        self.assertEqual(stages["Day 7"], "2026-01-08")
        self.assertEqual(stages["Day 14"], "2026-01-15")
        self.assertEqual(stages["Day 30"], "2026-01-31")
        self.assertEqual(stages["Day 60"], "2026-03-02")


class TestStudyStreak(unittest.TestCase):
    def test_consecutive_days(self):
        today = datetime.date.today()
        dates = [(today - datetime.timedelta(days=i)).isoformat() for i in range(5)]
        current, longest = an.compute_streak(dates)
        self.assertEqual(current, 5)
        self.assertEqual(longest, 5)

    def test_broken_streak(self):
        today = datetime.date.today()
        dates = [(today - datetime.timedelta(days=i)).isoformat() for i in [0, 1, 2, 5, 6, 7, 8]]
        current, longest = an.compute_streak(dates)
        self.assertEqual(current, 3)
        self.assertEqual(longest, 4)

    def test_no_sessions(self):
        current, longest = an.compute_streak([])
        self.assertEqual((current, longest), (0, 0))


class TestSyllabusCompletion(unittest.TestCase):
    def test_status_weights(self):
        self.assertEqual(an.topic_completion_fraction("Not Started"), 0.0)
        self.assertEqual(an.topic_completion_fraction("Completed"), 1.0)
        self.assertEqual(an.topic_completion_fraction("Strong"), 1.0)
        self.assertGreater(an.topic_completion_fraction("Practicing"), an.topic_completion_fraction("Learning"))


class TestRecommendationGeneration(unittest.TestCase):
    def test_weak_topics_prioritized_high(self):
        weak_list = [
            {"insufficient_data": False, "topic_name": "Profit & Loss", "classification": "Critical Weakness",
             "weakness_score": 90, "accuracy": 40, "avg_time_seconds": 80, "top_mistake_type": "Concept Mistake", "trend": "Declining"},
            {"insufficient_data": False, "topic_name": "Time & Work", "classification": "Strong",
             "weakness_score": 15, "accuracy": 92, "avg_time_seconds": 40, "top_mistake_type": None, "trend": "Stable"},
        ]
        recs = an.generate_recommendations(weak_list, [])
        self.assertEqual(recs[0]["topic_name"], "Profit & Loss")
        self.assertEqual(recs[0]["priority"], "High")

    def test_revision_due_included(self):
        recs = an.generate_recommendations([], [{"topic_name": "Syllogism", "days_overdue": 2}])
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["type"], "revision")
        self.assertEqual(recs[0]["priority"], "High")


if __name__ == "__main__":
    unittest.main()

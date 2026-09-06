"""Wave 3 纯函数单测：客观题判分与每题正确率统计（无 DB）。"""
from types import SimpleNamespace

from app.api.v1.routes.ta._shared import _grade_quiz_attempt
from app.api.v1.routes.ta.quizzes import _quiz_stats_by_question


def _q(qid: str, answer: str, score: float = 10, question_type: str = "single_choice") -> SimpleNamespace:
    return SimpleNamespace(id=qid, prompt=f"题{qid}", answer=answer, score=score, question_type=question_type)


def test_grade_all_correct() -> None:
    questions = [_q("q1", "A"), _q("q2", "T")]
    total, details = _grade_quiz_attempt({"q1": "A", "q2": "T"}, questions)
    assert total == 20.0
    assert details["q1"]["correct"] is True
    assert details["q2"]["score"] == 10.0


def test_grade_partial() -> None:
    questions = [_q("q1", "A", 10), _q("q2", "F", 20)]
    total, details = _grade_quiz_attempt({"q1": "B", "q2": "F"}, questions)
    assert total == 20.0
    assert details["q1"]["correct"] is False
    assert details["q2"]["correct"] is True


def test_grade_missing_answer_scores_zero() -> None:
    questions = [_q("q1", "A"), _q("q2", "T")]
    total, details = _grade_quiz_attempt({"q1": "A"}, questions)
    assert total == 10.0
    assert details["q2"]["correct"] is False


def test_stats_basic() -> None:
    questions = [_q("q1", "A"), _q("q2", "T")]
    attempts = [
        SimpleNamespace(answers={"q1": "A", "q2": "T"}),
        SimpleNamespace(answers={"q1": "A", "q2": "F"}),
    ]
    stats = _quiz_stats_by_question(attempts, questions)
    s1, s2 = stats[0], stats[1]
    assert s1["correct_count"] == 2 and s1["accuracy"] == 1.0
    assert s2["correct_count"] == 1 and s2["accuracy"] == 0.5


def test_stats_no_attempts_accuracy_none() -> None:
    questions = [_q("q1", "A")]
    stats = _quiz_stats_by_question([], questions)
    assert stats[0]["total_count"] == 0
    assert stats[0]["accuracy"] is None

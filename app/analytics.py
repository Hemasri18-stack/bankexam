"""
Analytics engine for Bank Exam Prep Manager.
Pure functions operating on data pulled from the DB layer - kept separate
from routing/db code so the logic is easy to test and reason about.
"""
import datetime
import statistics

REVISION_STAGES = [1, 3, 7, 14, 30, 60]  # days after completion


def safe_div(a, b):
    return (a / b) if b else 0.0


def pct(a, b, digits=1):
    return round(safe_div(a, b) * 100, digits)


# ---------------------------------------------------------------------------
# Test-level analysis  (section 11)
# ---------------------------------------------------------------------------
def analyze_test(questions):
    """questions: list of sqlite3.Row / dict from test_questions for one test."""
    total = len(questions)
    attempted = sum(1 for q in questions if q["attempted"])
    unattempted = total - attempted
    correct = sum(1 for q in questions if q["correct"])
    incorrect = attempted - correct
    score = sum((q["marks"] or 0) - (q["negative_marks"] or 0) for q in questions)
    negative = sum(q["negative_marks"] or 0 for q in questions)
    times = [q["time_taken_seconds"] for q in questions if q["time_taken_seconds"]]
    avg_time = round(statistics.mean(times), 1) if times else 0

    def diff_accuracy(level):
        subset = [q for q in questions if q["difficulty"] == level and q["attempted"]]
        c = sum(1 for q in subset if q["correct"])
        return pct(c, len(subset))

    return {
        "total_questions": total,
        "attempted": attempted,
        "unattempted": unattempted,
        "correct": correct,
        "incorrect": incorrect,
        "accuracy": pct(correct, attempted),
        "attempt_rate": pct(attempted, total),
        "score": round(score, 2),
        "negative_marks": round(negative, 2),
        "avg_time_seconds": avg_time,
        "easy_accuracy": diff_accuracy("Easy"),
        "medium_accuracy": diff_accuracy("Medium"),
        "hard_accuracy": diff_accuracy("Hard"),
    }


# ---------------------------------------------------------------------------
# Topic-wise analysis for a single test  (section 12)
# ---------------------------------------------------------------------------
def analyze_by_topic(questions, topic_names):
    """topic_names: dict topic_id -> name. Returns list sorted by accuracy asc."""
    by_topic = {}
    for q in questions:
        tid = q["topic_id"]
        if tid is None:
            continue
        by_topic.setdefault(tid, []).append(q)

    result = []
    for tid, qs in by_topic.items():
        attempted = sum(1 for q in qs if q["attempted"])
        correct = sum(1 for q in qs if q["correct"])
        result.append({
            "topic_id": tid,
            "topic_name": topic_names.get(tid, f"Topic {tid}"),
            "total_questions": len(qs),
            "attempted": attempted,
            "correct": correct,
            "incorrect": attempted - correct,
            "accuracy": pct(correct, attempted),
        })
    result.sort(key=lambda r: r["accuracy"])
    return result


# ---------------------------------------------------------------------------
# Weak topic detection across ALL tests  (section 13)
# ---------------------------------------------------------------------------
MIN_TESTS = 2
MIN_QUESTIONS = 10


def classify_weakness(score):
    if score <= 20:
        return "Excellent"
    if score <= 40:
        return "Strong"
    if score <= 60:
        return "Average"
    if score <= 80:
        return "Weak"
    return "Critical Weakness"


def compute_topic_weakness(topic_id, topic_name, question_rows, mistake_rows):
    """
    question_rows: all test_questions across all tests for this topic, ordered by test date asc.
    mistake_rows: mistakes tied to this topic.
    Returns None if insufficient data (fewer than MIN_QUESTIONS questions AND fewer than MIN_TESTS tests).
    """
    total_q = len(question_rows)
    test_ids = set(q["test_id"] for q in question_rows)
    num_tests = len(test_ids)

    if total_q < MIN_QUESTIONS and num_tests < MIN_TESTS:
        return {
            "topic_id": topic_id, "topic_name": topic_name,
            "insufficient_data": True,
            "questions_seen": total_q, "tests_seen": num_tests,
        }

    attempted = [q for q in question_rows if q["attempted"]]
    correct = [q for q in attempted if q["correct"]]
    accuracy = pct(len(correct), len(attempted))

    times = [q["time_taken_seconds"] for q in attempted if q["time_taken_seconds"]]
    avg_time = statistics.mean(times) if times else 60
    # Normalize speed: assume 60s/question is "par". Slower -> higher weakness contribution.
    speed_penalty = max(0.0, min(1.0, (avg_time - 40) / 80))  # 40s=ideal..120s=worst

    # Recent vs historical (split chronologically in half)
    half = max(1, len(question_rows) // 2)
    historical = question_rows[:half]
    recent = question_rows[half:] if len(question_rows) > half else question_rows
    hist_att = [q for q in historical if q["attempted"]]
    hist_corr = [q for q in hist_att if q["correct"]]
    rec_att = [q for q in recent if q["attempted"]]
    rec_corr = [q for q in rec_att if q["correct"]]
    hist_acc = pct(len(hist_corr), len(hist_att))
    recent_acc = pct(len(rec_corr), len(rec_att))
    improvement_rate = round(recent_acc - hist_acc, 1)

    mistakes_count = len(mistake_rows)
    mistake_freq = pct(mistakes_count, len(attempted)) if attempted else 0

    # Weighted weakness score (0-100, higher = weaker)
    accuracy_component = (100 - accuracy) * 0.50
    speed_component = (speed_penalty * 100) * 0.20
    mistake_component = min(100, mistake_freq) * 0.20
    # Recent performance component: if recent accuracy is low, that's bad (weak); scaled to 0-100
    recent_component = (100 - recent_acc) * 0.10

    weakness_score = round(accuracy_component + speed_component + mistake_component + recent_component, 1)
    weakness_score = max(0, min(100, weakness_score))

    if improvement_rate > 8:
        trend = "Improving"
    elif improvement_rate < -8:
        trend = "Declining"
    else:
        trend = "Stable"

    mistake_type_counts = {}
    for m in mistake_rows:
        mt = m["mistake_type"] or "Unknown"
        mistake_type_counts[mt] = mistake_type_counts.get(mt, 0) + 1
    top_mistake_type = max(mistake_type_counts, key=mistake_type_counts.get) if mistake_type_counts else None

    return {
        "topic_id": topic_id,
        "topic_name": topic_name,
        "insufficient_data": False,
        "questions_seen": total_q,
        "tests_seen": num_tests,
        "accuracy": accuracy,
        "avg_time_seconds": round(avg_time, 1),
        "historical_accuracy": hist_acc,
        "recent_accuracy": recent_acc,
        "improvement_rate": improvement_rate,
        "trend": trend,
        "mistake_count": mistakes_count,
        "top_mistake_type": top_mistake_type,
        "weakness_score": weakness_score,
        "classification": classify_weakness(weakness_score),
    }


# ---------------------------------------------------------------------------
# Mistake analysis  (section 14)
# ---------------------------------------------------------------------------
def analyze_mistakes(mistake_rows):
    counts = {}
    for m in mistake_rows:
        mt = m["mistake_type"] or "Unknown"
        counts[mt] = counts.get(mt, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {"counts": {}, "interpretation": "Not enough mistake data yet - keep logging tests."}

    top_type, top_count = max(counts.items(), key=lambda kv: kv[1])
    share = pct(top_count, total)

    interpretations = {
        "Concept Mistake": f"Your main problem is Concept Mistakes ({share}% of errors). Revisit fundamentals before more practice.",
        "Calculation Mistake": f"You are losing marks mainly to Calculation Mistakes ({share}%). Slow down slightly and double-check arithmetic.",
        "Silly Mistake": f"A large share of errors ({share}%) are Silly Mistakes - focus on careful reading and double-checking answers.",
        "Time Pressure": f"Your accuracy is good on relaxed practice, but {share}% of mistakes come from Time Pressure - work on speed drills.",
        "Guess": f"{share}% of mistakes come from Guessing - build confidence with more targeted practice instead of guessing.",
        "Didn't Know": f"{share}% of mistakes are because you Didn't Know the concept - prioritize learning these topics first.",
        "Forgot Formula": f"{share}% of mistakes are due to Forgetting Formulas - keep a formula sheet and revise it daily.",
        "Misread Question": f"{share}% of mistakes come from Misreading Questions - practice reading the question twice before answering.",
        "Logical Error": f"{share}% of mistakes are Logical Errors - slow down on reasoning steps and verify each inference.",
    }
    interpretation = interpretations.get(top_type, f"Your most frequent mistake type is {top_type} ({share}% of errors).")

    return {"counts": counts, "top_type": top_type, "top_share": share, "interpretation": interpretation}


# ---------------------------------------------------------------------------
# Recommendation engine  (section 16)
# ---------------------------------------------------------------------------
def generate_recommendations(weakness_list, revision_due_topics, max_items=5):
    """
    weakness_list: output of compute_topic_weakness for many topics (insufficient_data ones excluded/handled).
    revision_due_topics: list of {topic_name, days_overdue}
    Returns ordered list of recommendation dicts with priority labels.
    """
    recs = []
    usable = [w for w in weakness_list if not w.get("insufficient_data")]
    usable.sort(key=lambda w: w["weakness_score"], reverse=True)

    for w in usable[:max_items]:
        if w["classification"] in ("Weak", "Critical Weakness"):
            reason_parts = [f"Current accuracy: {w['accuracy']}%"]
            if w["avg_time_seconds"] > 75:
                reason_parts.append(f"average time {int(w['avg_time_seconds'])}s/question is high")
            if w["top_mistake_type"]:
                reason_parts.append(f"most common issue: {w['top_mistake_type']}")
            recs.append({
                "priority": "High" if w["classification"] == "Critical Weakness" else "Medium",
                "topic_name": w["topic_name"],
                "action": f"Revise {w['topic_name']} and attempt 20-30 targeted practice questions.",
                "reason": "; ".join(reason_parts),
                "type": "weakness",
            })
        elif w["classification"] == "Average" and w["trend"] != "Improving":
            recs.append({
                "priority": "Medium",
                "topic_name": w["topic_name"],
                "action": f"Practice {w['topic_name']} - accuracy is average and not yet improving.",
                "reason": f"Accuracy {w['accuracy']}%, trend: {w['trend']}",
                "type": "average",
            })
        elif w["classification"] in ("Strong", "Excellent"):
            recs.append({
                "priority": "Low",
                "topic_name": w["topic_name"],
                "action": f"Light revision only for {w['topic_name']}.",
                "reason": f"Accuracy {w['accuracy']}%, already strong.",
                "type": "maintain",
            })

    for r in revision_due_topics:
        recs.append({
            "priority": "High" if r["days_overdue"] > 0 else "Medium",
            "topic_name": r["topic_name"],
            "action": f"Complete scheduled revision for {r['topic_name']}.",
            "reason": f"{'Overdue by ' + str(r['days_overdue']) + ' day(s)' if r['days_overdue'] > 0 else 'Due today'}.",
            "type": "revision",
        })

    order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: order.get(r["priority"], 3))
    return recs


# ---------------------------------------------------------------------------
# Revision scheduling  (section 17)
# ---------------------------------------------------------------------------
def build_revision_dates(completion_date_str):
    base = datetime.date.fromisoformat(completion_date_str)
    return [(f"Day {d}", (base + datetime.timedelta(days=d)).isoformat()) for d in REVISION_STAGES]


# ---------------------------------------------------------------------------
# Study streak (section 8 / 18)
# ---------------------------------------------------------------------------
def compute_streak(session_dates):
    """session_dates: sorted set of ISO date strings with at least one session."""
    if not session_dates:
        return 0, 0
    dates = sorted(set(datetime.date.fromisoformat(d) for d in session_dates))
    longest = current = 1
    streaks = [1]
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            streaks[-1] += 1
        else:
            streaks.append(1)
    longest = max(streaks)

    today = datetime.date.today()
    date_set = set(dates)
    current = 0
    d = today
    if d not in date_set:
        d = d - datetime.timedelta(days=1)  # allow "today not logged yet"
    while d in date_set:
        current += 1
        d -= datetime.timedelta(days=1)
    return current, longest


# ---------------------------------------------------------------------------
# Syllabus completion (section 5)
# ---------------------------------------------------------------------------
STATUS_WEIGHTS = {
    "Not Started": 0.0, "Learning": 0.25, "Practicing": 0.5,
    "Completed": 1.0, "Needs Revision": 0.85, "Strong": 1.0,
}


def topic_completion_fraction(status):
    return STATUS_WEIGHTS.get(status, 0.0)

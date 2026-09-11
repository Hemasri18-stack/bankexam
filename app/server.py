"""
Bank Exam Prep Manager - application server.
Pure Python standard library (http.server + sqlite3). No external dependencies.
Run:  python3 server.py   then open http://localhost:8000
"""
import json
import re
import os
import sys
import datetime
import mimetypes
import posixpath
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
import db
import analytics as an

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


def json_response(handler, payload, status=200):
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler, message, status=400):
    json_response(handler, {"error": message}, status)


ROUTES = []  # list of (method, regex, func)


def route(method, pattern):
    regex = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((method, regex, fn))
        return fn
    return deco


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
@route("GET", r"/api/dashboard")
def get_dashboard(handler, m, body):
    conn = db.get_conn()
    today = db.today()

    subjects = rows_to_list(conn.execute("SELECT * FROM subjects ORDER BY sort_order").fetchall())
    subj_completion = {}
    overall_num = overall_den = 0
    for s in subjects:
        topics = conn.execute("SELECT status FROM topics WHERE subject_id=?", (s["id"],)).fetchall()
        num = sum(an.topic_completion_fraction(t["status"]) for t in topics)
        den = len(topics)
        subj_completion[s["name"]] = an.pct(num, den)
        overall_num += num
        overall_den += den
    overall_completion = an.pct(overall_num, overall_den)

    # today's tasks
    today_tasks = rows_to_list(conn.execute(
        "SELECT * FROM tasks WHERE due_date=? ORDER BY priority", (today,)).fetchall())
    completed_today = sum(1 for t in today_tasks if t["status"] == "Completed")

    # streak
    dates = [r["date"] for r in conn.execute("SELECT DISTINCT date FROM study_sessions").fetchall()]
    current_streak, longest_streak = an.compute_streak(dates)

    # total study hours
    total_minutes = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions").fetchone()["m"]

    # tests
    tests = rows_to_list(conn.execute("SELECT * FROM tests ORDER BY date").fetchall())
    scores = [t["obtained_marks"] for t in tests]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    best_score = max(scores) if scores else 0

    # accuracy across all test_questions
    all_q = conn.execute("SELECT * FROM test_questions").fetchall()
    attempted = [q for q in all_q if q["attempted"]]
    correct = [q for q in attempted if q["correct"]]
    avg_accuracy = an.pct(len(correct), len(attempted))
    times = [q["time_taken_seconds"] for q in attempted if q["time_taken_seconds"]]
    avg_speed = round(sum(times) / len(times), 1) if times else 0

    # weakest / strongest topic (needs enough data)
    topic_names = {t["id"]: t["name"] for t in conn.execute("SELECT id,name FROM topics").fetchall()}
    weak_list = _compute_all_weakness(conn)
    usable = [w for w in weak_list if not w.get("insufficient_data")]
    weakest_topic = max(usable, key=lambda w: w["weakness_score"])["topic_name"] if usable else "Not enough data yet"
    strongest_topic = min(usable, key=lambda w: w["weakness_score"])["topic_name"] if usable else "Not enough data yet"

    # weakest subject (by avg accuracy of its topics' recent tests)
    subj_acc = {}
    for s in subjects:
        qs = [q for q in all_q if q["subject_id"] == s["id"] and q["attempted"]]
        c = [q for q in qs if q["correct"]]
        if qs:
            subj_acc[s["name"]] = an.pct(len(c), len(qs))
    weakest_subject = min(subj_acc, key=subj_acc.get) if subj_acc else "Not enough data yet"

    # topics needing revision (due today or overdue)
    due = rows_to_list(conn.execute(
        "SELECT rs.*, t.name topic_name FROM revision_schedule rs JOIN topics t ON t.id=rs.topic_id "
        "WHERE rs.status='Pending' AND rs.revision_date<=? ORDER BY rs.revision_date", (today,)).fetchall())

    upcoming_tasks = rows_to_list(conn.execute(
        "SELECT * FROM tasks WHERE status IN ('Pending','In Progress') AND due_date>=? ORDER BY due_date LIMIT 8",
        (today,)).fetchall())

    conn.close()
    return {
        "date": today,
        "today_target_minutes": int(_get_setting("daily_study_minutes", "90")),
        "today_tasks_total": len(today_tasks),
        "today_tasks_completed": completed_today,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_study_hours": round(total_minutes / 60, 1),
        "syllabus_completion": overall_completion,
        "subject_completion": subj_completion,
        "tests_attempted": len(tests),
        "average_test_score": avg_score,
        "best_test_score": best_score,
        "average_accuracy": avg_accuracy,
        "average_speed_seconds": avg_speed,
        "weakest_subject": weakest_subject,
        "weakest_topic": weakest_topic,
        "strongest_topic": strongest_topic,
        "topics_needing_revision": due,
        "upcoming_tasks": upcoming_tasks,
    }


def _get_setting(key, default=None):
    conn = db.get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


@route("GET", r"/api/charts/weekly-hours")
def chart_weekly_hours(handler, m, body):
    conn = db.get_conn()
    since = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    rows = conn.execute(
        "SELECT date, SUM(duration_minutes) m FROM study_sessions WHERE date>=? GROUP BY date ORDER BY date",
        (since,)).fetchall()
    conn.close()
    data = {r["date"]: round(r["m"] / 60, 2) for r in rows}
    labels = [(datetime.date.today() - datetime.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    return {"labels": labels, "values": [data.get(l, 0) for l in labels]}


@route("GET", r"/api/charts/monthly-hours")
def chart_monthly_hours(handler, m, body):
    conn = db.get_conn()
    since = (datetime.date.today() - datetime.timedelta(days=29)).isoformat()
    rows = conn.execute(
        "SELECT date, SUM(duration_minutes) m FROM study_sessions WHERE date>=? GROUP BY date ORDER BY date",
        (since,)).fetchall()
    conn.close()
    data = {r["date"]: round(r["m"] / 60, 2) for r in rows}
    labels = [(datetime.date.today() - datetime.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    return {"labels": labels, "values": [data.get(l, 0) for l in labels]}


@route("GET", r"/api/charts/score-trend")
def chart_score_trend(handler, m, body):
    conn = db.get_conn()
    rows = conn.execute("SELECT name, date, obtained_marks FROM tests ORDER BY date").fetchall()
    conn.close()
    return {"labels": [r["name"] for r in rows], "dates": [r["date"] for r in rows],
            "values": [r["obtained_marks"] for r in rows]}


@route("GET", r"/api/charts/accuracy-trend")
def chart_accuracy_trend(handler, m, body):
    conn = db.get_conn()
    tests = conn.execute("SELECT id, name, date FROM tests ORDER BY date").fetchall()
    values, labels = [], []
    for t in tests:
        qs = conn.execute("SELECT attempted, correct FROM test_questions WHERE test_id=?", (t["id"],)).fetchall()
        attempted = sum(1 for q in qs if q["attempted"])
        correct = sum(1 for q in qs if q["correct"])
        values.append(an.pct(correct, attempted))
        labels.append(t["name"])
    conn.close()
    return {"labels": labels, "values": values}


@route("GET", r"/api/charts/streak-calendar")
def chart_streak_calendar(handler, m, body):
    conn = db.get_conn()
    since = (datetime.date.today() - datetime.timedelta(days=41)).isoformat()
    rows = conn.execute(
        "SELECT date, SUM(duration_minutes) m FROM study_sessions WHERE date>=? GROUP BY date", (since,)).fetchall()
    conn.close()
    data = {r["date"]: r["m"] for r in rows}
    labels = [(datetime.date.today() - datetime.timedelta(days=i)).isoformat() for i in range(41, -1, -1)]
    return {"labels": labels, "values": [data.get(l, 0) for l in labels]}


# ---------------------------------------------------------------------------
# SUBJECTS / TOPICS / SUBTOPICS  (Syllabus tracker)
# ---------------------------------------------------------------------------
@route("GET", r"/api/subjects")
def list_subjects(handler, m, body):
    conn = db.get_conn()
    subs = rows_to_list(conn.execute("SELECT * FROM subjects ORDER BY sort_order").fetchall())
    for s in subs:
        topics = conn.execute("SELECT status FROM topics WHERE subject_id=?", (s["id"],)).fetchall()
        num = sum(an.topic_completion_fraction(t["status"]) for t in topics)
        s["completion_pct"] = an.pct(num, len(topics))
        s["topic_count"] = len(topics)
    conn.close()
    return subs


@route("GET", r"/api/subjects/(?P<sid>\d+)/topics")
def list_topics(handler, m, body):
    conn = db.get_conn()
    topics = rows_to_list(conn.execute(
        "SELECT * FROM topics WHERE subject_id=? ORDER BY sort_order", (m["sid"],)).fetchall())
    for t in topics:
        t["subtopics"] = rows_to_list(conn.execute(
            "SELECT * FROM subtopics WHERE topic_id=? ORDER BY sort_order", (t["id"],)).fetchall())
    conn.close()
    return topics


@route("GET", r"/api/topics")
def list_all_topics(handler, m, body):
    conn = db.get_conn()
    topics = rows_to_list(conn.execute(
        "SELECT t.*, s.name subject_name FROM topics t JOIN subjects s ON s.id=t.subject_id ORDER BY s.sort_order, t.sort_order").fetchall())
    conn.close()
    return topics


@route("GET", r"/api/topics/(?P<tid>\d+)")
def get_topic(handler, m, body):
    conn = db.get_conn()
    t = row_to_dict(conn.execute("SELECT * FROM topics WHERE id=?", (m["tid"],)).fetchone())
    if t:
        t["subtopics"] = rows_to_list(conn.execute(
            "SELECT * FROM subtopics WHERE topic_id=? ORDER BY sort_order", (m["tid"],)).fetchall())
    conn.close()
    if not t:
        raise ApiError("Topic not found", 404)
    return t


@route("PUT", r"/api/topics/(?P<tid>\d+)")
def update_topic(handler, m, body):
    fields = ["status", "start_date", "completion_date", "confidence_level", "questions_solved",
              "questions_correct", "questions_incorrect", "num_revisions", "last_revised_date",
              "next_revision_date", "importance"]
    updates = {k: body[k] for k in fields if k in body}
    if not updates:
        raise ApiError("No valid fields to update")
    conn = db.get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE topics SET {set_clause} WHERE id=?", (*updates.values(), m["tid"]))
    conn.commit()

    # If just marked Completed, auto-generate a revision schedule (section 17)
    if updates.get("status") == "Completed":
        comp_date = updates.get("completion_date") or db.today()
        conn.execute("DELETE FROM revision_schedule WHERE topic_id=? AND status='Pending'", (m["tid"],))
        for stage, rdate in an.build_revision_dates(comp_date):
            conn.execute(
                "INSERT INTO revision_schedule(topic_id, revision_date, status, stage, created_at) VALUES (?,?,?,?,?)",
                (m["tid"], rdate, "Pending", stage, db.now()))
        conn.commit()
    t = row_to_dict(conn.execute("SELECT * FROM topics WHERE id=?", (m["tid"],)).fetchone())
    conn.close()
    return t


# ---------------------------------------------------------------------------
# NOTES
# ---------------------------------------------------------------------------
@route("GET", r"/api/notes")
def list_notes(handler, m, body):
    conn = db.get_conn()
    q = handler.query.get("q", [""])[0]
    subject_id = handler.query.get("subject_id", [""])[0]
    topic_id = handler.query.get("topic_id", [""])[0]
    favorite = handler.query.get("favorite", [""])[0]

    sql = """SELECT n.*, s.name subject_name, t.name topic_name FROM notes n
              LEFT JOIN subjects s ON s.id=n.subject_id LEFT JOIN topics t ON t.id=n.topic_id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (n.title LIKE ? OR n.content LIKE ? OR n.tags LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if subject_id:
        sql += " AND n.subject_id=?"
        params.append(subject_id)
    if topic_id:
        sql += " AND n.topic_id=?"
        params.append(topic_id)
    if favorite == "1":
        sql += " AND n.is_favorite=1"
    sql += " ORDER BY n.is_pinned DESC, n.updated_at DESC"
    notes = rows_to_list(conn.execute(sql, params).fetchall())
    conn.close()
    return notes


@route("POST", r"/api/notes")
def create_note(handler, m, body):
    required_ok = body.get("title")
    if not required_ok:
        raise ApiError("Title is required")
    conn = db.get_conn()
    cur = conn.execute(
        """INSERT INTO notes(subject_id, topic_id, subtopic_id, title, content, formula, shortcut, example,
           important_points, common_mistakes, tags, is_favorite, is_pinned, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.get("subject_id"), body.get("topic_id"), body.get("subtopic_id"), body["title"],
         body.get("content", ""), body.get("formula", ""), body.get("shortcut", ""), body.get("example", ""),
         body.get("important_points", ""), body.get("common_mistakes", ""), body.get("tags", ""),
         int(bool(body.get("is_favorite"))), int(bool(body.get("is_pinned"))), db.now(), db.now())
    )
    conn.commit()
    note = row_to_dict(conn.execute("SELECT * FROM notes WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return note


@route("PUT", r"/api/notes/(?P<nid>\d+)")
def update_note(handler, m, body):
    fields = ["subject_id", "topic_id", "subtopic_id", "title", "content", "formula", "shortcut", "example",
              "important_points", "common_mistakes", "tags", "is_favorite", "is_pinned"]
    updates = {k: body[k] for k in fields if k in body}
    if not updates:
        raise ApiError("No valid fields to update")
    updates["updated_at"] = db.now()
    conn = db.get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE notes SET {set_clause} WHERE id=?", (*updates.values(), m["nid"]))
    conn.commit()
    note = row_to_dict(conn.execute("SELECT * FROM notes WHERE id=?", (m["nid"],)).fetchone())
    conn.close()
    return note


@route("DELETE", r"/api/notes/(?P<nid>\d+)")
def delete_note(handler, m, body):
    conn = db.get_conn()
    conn.execute("DELETE FROM notes WHERE id=?", (m["nid"],))
    conn.commit()
    conn.close()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# TASKS
# ---------------------------------------------------------------------------
@route("GET", r"/api/tasks")
def list_tasks(handler, m, body):
    conn = db.get_conn()
    filt = handler.query.get("filter", [""])[0]
    today = db.today()
    sql = """SELECT tk.*, s.name subject_name, t.name topic_name FROM tasks tk
             LEFT JOIN subjects s ON s.id=tk.subject_id LEFT JOIN topics t ON t.id=tk.topic_id WHERE 1=1"""
    params = []
    if filt == "today":
        sql += " AND tk.due_date=?"
        params.append(today)
    elif filt == "week":
        week_end = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        sql += " AND tk.due_date BETWEEN ? AND ?"
        params += [today, week_end]
    elif filt == "overdue":
        sql += " AND tk.due_date<? AND tk.status NOT IN ('Completed','Skipped')"
        params.append(today)
    elif filt == "completed":
        sql += " AND tk.status='Completed'"
    sql += " ORDER BY CASE tk.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, tk.due_date"
    tasks = rows_to_list(conn.execute(sql, params).fetchall())
    conn.close()
    return tasks


@route("POST", r"/api/tasks")
def create_task(handler, m, body):
    if not body.get("title"):
        raise ApiError("Title is required")
    conn = db.get_conn()
    cur = conn.execute(
        """INSERT INTO tasks(title, subject_id, topic_id, priority, due_date, estimated_minutes, status,
           recurring, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (body["title"], body.get("subject_id"), body.get("topic_id"), body.get("priority", "Medium"),
         body.get("due_date", db.today()), body.get("estimated_minutes"), body.get("status", "Pending"),
         body.get("recurring", "None"), db.now())
    )
    conn.commit()
    task = row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return task


@route("PUT", r"/api/tasks/(?P<tid>\d+)")
def update_task(handler, m, body):
    fields = ["title", "subject_id", "topic_id", "priority", "due_date", "estimated_minutes", "status",
              "completion_date", "recurring"]
    updates = {k: body[k] for k in fields if k in body}
    if not updates:
        raise ApiError("No valid fields to update")
    if updates.get("status") == "Completed" and "completion_date" not in updates:
        updates["completion_date"] = db.today()
    conn = db.get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id=?", (*updates.values(), m["tid"]))
    conn.commit()
    task = row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (m["tid"],)).fetchone())
    conn.close()
    return task


@route("DELETE", r"/api/tasks/(?P<tid>\d+)")
def delete_task(handler, m, body):
    conn = db.get_conn()
    conn.execute("DELETE FROM tasks WHERE id=?", (m["tid"],))
    conn.commit()
    conn.close()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# STUDY SESSIONS (Daily Study Tracker)
# ---------------------------------------------------------------------------
@route("GET", r"/api/study-sessions")
def list_sessions(handler, m, body):
    conn = db.get_conn()
    limit = handler.query.get("limit", ["100"])[0]
    sessions = rows_to_list(conn.execute(
        """SELECT ss.*, s.name subject_name, t.name topic_name FROM study_sessions ss
           LEFT JOIN subjects s ON s.id=ss.subject_id LEFT JOIN topics t ON t.id=ss.topic_id
           ORDER BY ss.date DESC, ss.id DESC LIMIT ?""", (limit,)).fetchall())
    conn.close()
    return sessions


@route("POST", r"/api/study-sessions")
def create_session(handler, m, body):
    if not body.get("date"):
        raise ApiError("Date is required")
    conn = db.get_conn()
    cur = conn.execute(
        """INSERT INTO study_sessions(date, start_time, end_time, subject_id, topic_id, study_type,
           duration_minutes, questions_solved, questions_correct, questions_incorrect, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (body["date"], body.get("start_time"), body.get("end_time"), body.get("subject_id"),
         body.get("topic_id"), body.get("study_type", "Practice"), body.get("duration_minutes", 0),
         body.get("questions_solved", 0), body.get("questions_correct", 0),
         body.get("questions_incorrect", 0), body.get("notes", ""))
    )
    # roll up into topic question counts
    if body.get("topic_id"):
        conn.execute(
            """UPDATE topics SET questions_solved = questions_solved + ?, questions_correct = questions_correct + ?,
               questions_incorrect = questions_incorrect + ? WHERE id=?""",
            (body.get("questions_solved", 0), body.get("questions_correct", 0),
             body.get("questions_incorrect", 0), body["topic_id"])
        )
    conn.commit()
    sess = row_to_dict(conn.execute("SELECT * FROM study_sessions WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return sess


@route("GET", r"/api/study-sessions/summary")
def session_summary(handler, m, body):
    conn = db.get_conn()
    today = db.today()
    week_start = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    month_start = (datetime.date.today() - datetime.timedelta(days=29)).isoformat()

    def sum_minutes(since=None, exact=None):
        if exact:
            row = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions WHERE date=?", (exact,)).fetchone()
        else:
            row = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions WHERE date>=?", (since,)).fetchone()
        return row["m"]

    today_min = sum_minutes(exact=today)
    week_min = sum_minutes(since=week_start)
    month_min = sum_minutes(since=month_start)
    all_dates = [r["date"] for r in conn.execute("SELECT DISTINCT date FROM study_sessions").fetchall()]
    current_streak, longest_streak = an.compute_streak(all_dates)
    total_days = len(all_dates)
    total_min = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions").fetchone()["m"]
    avg_daily = round(total_min / total_days, 1) if total_days else 0
    conn.close()
    return {
        "today_minutes": today_min, "week_minutes": week_min, "month_minutes": month_min,
        "average_daily_minutes": avg_daily, "current_streak": current_streak, "longest_streak": longest_streak,
    }


# ---------------------------------------------------------------------------
# TESTS + QUESTION-LEVEL ENTRY
# ---------------------------------------------------------------------------
@route("GET", r"/api/tests")
def list_tests(handler, m, body):
    conn = db.get_conn()
    tests = rows_to_list(conn.execute("SELECT * FROM tests ORDER BY date DESC, id DESC").fetchall())
    conn.close()
    return tests


@route("POST", r"/api/tests")
def create_test(handler, m, body):
    if not body.get("name"):
        raise ApiError("Test name is required")
    conn = db.get_conn()
    cur = conn.execute(
        """INSERT INTO tests(name, exam, test_type, date, duration_minutes, total_questions, max_marks,
           obtained_marks, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (body["name"], body.get("exam"), body.get("test_type", "Custom Test"), body.get("date", db.today()),
         body.get("duration_minutes"), body.get("total_questions", 0), body.get("max_marks", 0),
         body.get("obtained_marks", 0), db.now())
    )
    conn.commit()
    test = row_to_dict(conn.execute("SELECT * FROM tests WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return test


@route("DELETE", r"/api/tests/(?P<test_id>\d+)")
def delete_test(handler, m, body):
    conn = db.get_conn()
    conn.execute("DELETE FROM tests WHERE id=?", (m["test_id"],))
    conn.commit()
    conn.close()
    return {"deleted": True}


@route("POST", r"/api/tests/(?P<test_id>\d+)/questions")
def add_questions(handler, m, body):
    """Bulk add question-level rows. body: {questions: [ {...}, ... ]}"""
    questions = body.get("questions", [])
    if not questions:
        raise ApiError("No questions provided")
    conn = db.get_conn()
    total_marks = 0.0
    for q in questions:
        marks = float(q.get("marks", 0) or 0)
        neg = float(q.get("negative_marks", 0) or 0)
        total_marks += marks - neg
        cur = conn.execute(
            """INSERT INTO test_questions(test_id, question_number, subject_id, topic_id, subtopic_id,
               question_type, attempted, correct, time_taken_seconds, marks, negative_marks, difficulty, mistake_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m["test_id"], q.get("question_number"), q.get("subject_id"), q.get("topic_id"), q.get("subtopic_id"),
             q.get("question_type", "MCQ"), int(bool(q.get("attempted"))), int(bool(q.get("correct"))),
             q.get("time_taken_seconds", 0), marks, neg, q.get("difficulty", "Medium"), q.get("mistake_type"))
        )
        # auto-create a mistake row if wrong
        if q.get("attempted") and not q.get("correct"):
            tq_id = cur.lastrowid
            conn.execute(
                """INSERT INTO mistakes(test_question_id, subject_id, topic_id, mistake_type, user_answer,
                   correct_answer, explanation, resolved, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (tq_id, q.get("subject_id"), q.get("topic_id"), q.get("mistake_type"),
                 q.get("user_answer", ""), q.get("correct_answer", ""), q.get("explanation", ""), 0, db.now())
            )
    conn.execute("UPDATE tests SET obtained_marks = obtained_marks + ? WHERE id=?", (round(total_marks, 2), m["test_id"]))
    conn.commit()
    conn.close()
    return {"inserted": len(questions)}


@route("GET", r"/api/tests/(?P<test_id>\d+)/analysis")
def test_analysis(handler, m, body):
    conn = db.get_conn()
    test = row_to_dict(conn.execute("SELECT * FROM tests WHERE id=?", (m["test_id"],)).fetchone())
    if not test:
        raise ApiError("Test not found", 404)
    questions = conn.execute("SELECT * FROM test_questions WHERE test_id=?", (m["test_id"],)).fetchall()
    topic_names = {t["id"]: t["name"] for t in conn.execute("SELECT id,name FROM topics").fetchall()}
    overall = an.analyze_test(questions)
    by_topic = an.analyze_by_topic(questions, topic_names)
    mistakes = conn.execute(
        "SELECT * FROM mistakes WHERE test_question_id IN (SELECT id FROM test_questions WHERE test_id=?)",
        (m["test_id"],)).fetchall()
    mistake_analysis = an.analyze_mistakes(mistakes)
    conn.close()
    return {
        "test": test, "overall": overall,
        "by_topic": by_topic,
        "weakest_topics": by_topic[:3],
        "strongest_topics": sorted(by_topic, key=lambda r: -r["accuracy"])[:3],
        "mistake_analysis": mistake_analysis,
    }


# ---------------------------------------------------------------------------
# WEAK TOPIC ANALYZER  (across all tests)
# ---------------------------------------------------------------------------
def _compute_all_weakness(conn):
    topics = conn.execute("SELECT id, name FROM topics").fetchall()
    results = []
    for t in topics:
        qs = conn.execute(
            """SELECT tq.* FROM test_questions tq JOIN tests te ON te.id=tq.test_id
               WHERE tq.topic_id=? ORDER BY te.date ASC""", (t["id"],)).fetchall()
        if not qs:
            continue
        mistakes = conn.execute(
            "SELECT * FROM mistakes WHERE topic_id=?", (t["id"],)).fetchall()
        result = an.compute_topic_weakness(t["id"], t["name"], qs, mistakes)
        results.append(result)
    return results


@route("GET", r"/api/weak-topics")
def weak_topics(handler, m, body):
    conn = db.get_conn()
    results = _compute_all_weakness(conn)
    conn.close()
    usable = [r for r in results if not r.get("insufficient_data")]
    insufficient = [r for r in results if r.get("insufficient_data")]
    usable.sort(key=lambda r: -r["weakness_score"])
    return {
        "topics": usable,
        "insufficient_data_topics": insufficient,
        "weakest": [r for r in usable if r["classification"] in ("Weak", "Critical Weakness")][:10],
        "strongest": sorted(usable, key=lambda r: r["weakness_score"])[:10],
    }


@route("GET", r"/api/recommendations")
def recommendations(handler, m, body):
    conn = db.get_conn()
    weak = _compute_all_weakness(conn)
    today = db.today()
    due_rows = conn.execute(
        "SELECT rs.*, t.name topic_name FROM revision_schedule rs JOIN topics t ON t.id=rs.topic_id "
        "WHERE rs.status='Pending' AND rs.revision_date<=?", (today,)).fetchall()
    due_topics = []
    for r in due_rows:
        days_overdue = (datetime.date.today() - datetime.date.fromisoformat(r["revision_date"])).days
        due_topics.append({"topic_name": r["topic_name"], "days_overdue": days_overdue})
    recs = an.generate_recommendations(weak, due_topics)
    conn.close()
    return {"recommendations": recs}


@route("GET", r"/api/smart-daily-plan")
def smart_daily_plan(handler, m, body):
    """Section 20: generate a slotted plan for the available study window."""
    conn = db.get_conn()
    available_minutes = int(_get_setting("daily_study_minutes", "90"))
    start_time_str = _get_setting("study_start_time", "18:00")

    weak = _compute_all_weakness(conn)
    weak_sorted = sorted([w for w in weak if not w.get("insufficient_data")], key=lambda w: -w["weakness_score"])
    today = db.today()
    due_rows = conn.execute(
        "SELECT rs.*, t.name topic_name FROM revision_schedule rs JOIN topics t ON t.id=rs.topic_id "
        "WHERE rs.status='Pending' AND rs.revision_date<=?", (today,)).fetchall()
    pending_tasks = conn.execute(
        "SELECT * FROM tasks WHERE status IN ('Pending','In Progress') AND due_date<=? ORDER BY priority LIMIT 5",
        (today,)).fetchall()
    conn.close()

    slots = []
    remaining = available_minutes
    t = datetime.datetime.strptime(start_time_str, "%H:%M")

    def add_slot(minutes, label):
        nonlocal remaining, t
        if remaining <= 0 or minutes <= 0:
            return
        minutes = min(minutes, remaining)
        end = t + datetime.timedelta(minutes=minutes)
        slots.append({"start": t.strftime("%H:%M"), "end": end.strftime("%H:%M"), "activity": label})
        t = end
        remaining -= minutes

    if due_rows:
        add_slot(10, f"Revision: {due_rows[0]['topic_name']}")
    if weak_sorted:
        add_slot(30, f"Practice: {weak_sorted[0]['topic_name']} - 20 questions")
    if len(weak_sorted) > 1:
        add_slot(25, f"Practice: {weak_sorted[1]['topic_name']}")
    if pending_tasks:
        add_slot(15, f"Task: {pending_tasks[0]['title']}")
    add_slot(remaining, "Error-log revision & quick recap")

    conn.close() if False else None
    return {"date": today, "total_minutes": available_minutes, "slots": slots}


# ---------------------------------------------------------------------------
# ERROR BOOK
# ---------------------------------------------------------------------------
@route("GET", r"/api/mistakes")
def list_mistakes(handler, m, body):
    conn = db.get_conn()
    topic_id = handler.query.get("topic_id", [""])[0]
    mistake_type = handler.query.get("mistake_type", [""])[0]
    resolved = handler.query.get("resolved", [""])[0]
    sql = """SELECT mk.*, s.name subject_name, t.name topic_name, tq.question_number, te.name test_name
             FROM mistakes mk LEFT JOIN subjects s ON s.id=mk.subject_id LEFT JOIN topics t ON t.id=mk.topic_id
             LEFT JOIN test_questions tq ON tq.id=mk.test_question_id LEFT JOIN tests te ON te.id=tq.test_id
             WHERE 1=1"""
    params = []
    if topic_id:
        sql += " AND mk.topic_id=?"
        params.append(topic_id)
    if mistake_type:
        sql += " AND mk.mistake_type=?"
        params.append(mistake_type)
    if resolved:
        sql += " AND mk.resolved=?"
        params.append(resolved)
    sql += " ORDER BY mk.created_at DESC"
    mistakes = rows_to_list(conn.execute(sql, params).fetchall())
    conn.close()
    return mistakes


@route("PUT", r"/api/mistakes/(?P<mid>\d+)")
def update_mistake(handler, m, body):
    fields = ["explanation", "personal_note", "resolved"]
    updates = {k: body[k] for k in fields if k in body}
    if not updates:
        raise ApiError("No valid fields to update")
    conn = db.get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE mistakes SET {set_clause} WHERE id=?", (*updates.values(), m["mid"]))
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM mistakes WHERE id=?", (m["mid"],)).fetchone())
    conn.close()
    return row


@route("GET", r"/api/mistakes/frequent")
def frequent_mistakes(handler, m, body):
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT mistake_type, COUNT(*) c FROM mistakes GROUP BY mistake_type ORDER BY c DESC").fetchall()
    conn.close()
    return rows_to_list(rows)


# ---------------------------------------------------------------------------
# REVISION MANAGER
# ---------------------------------------------------------------------------
@route("GET", r"/api/revision")
def list_revision(handler, m, body):
    conn = db.get_conn()
    today = db.today()
    rows = rows_to_list(conn.execute(
        "SELECT rs.*, t.name topic_name FROM revision_schedule rs JOIN topics t ON t.id=rs.topic_id "
        "ORDER BY rs.revision_date").fetchall())
    conn.close()
    due_today, overdue, upcoming, done = [], [], [], []
    for r in rows:
        if r["status"] == "Done":
            done.append(r)
        elif r["revision_date"] < today:
            overdue.append(r)
        elif r["revision_date"] == today:
            due_today.append(r)
        else:
            upcoming.append(r)
    return {"due_today": due_today, "overdue": overdue, "upcoming": upcoming[:15], "done": done[-15:]}


@route("PUT", r"/api/revision/(?P<rid>\d+)")
def update_revision(handler, m, body):
    fields = ["status", "revision_date"]
    updates = {k: body[k] for k in fields if k in body}
    if not updates:
        raise ApiError("No valid fields to update")
    conn = db.get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE revision_schedule SET {set_clause} WHERE id=?", (*updates.values(), m["rid"]))
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM revision_schedule WHERE id=?", (m["rid"],)).fetchone())
    conn.close()
    return row


# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------
@route("GET", r"/api/statistics")
def statistics_page(handler, m, body):
    conn = db.get_conn()
    total_minutes = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions").fetchone()["m"]
    dates = [r["date"] for r in conn.execute("SELECT DISTINCT date FROM study_sessions").fetchall()]
    current_streak, longest_streak = an.compute_streak(dates)
    week_start = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    month_start = (datetime.date.today() - datetime.timedelta(days=29)).isoformat()
    week_min = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions WHERE date>=?", (week_start,)).fetchone()["m"]
    month_min = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions WHERE date>=?", (month_start,)).fetchone()["m"]

    tests = rows_to_list(conn.execute("SELECT * FROM tests ORDER BY date").fetchall())
    scores = [t["obtained_marks"] for t in tests]
    prelims = [t["obtained_marks"] for t in tests if "Prelim" in (t["test_type"] or "")]
    mains = [t["obtained_marks"] for t in tests if "Mains" in (t["test_type"] or "")]

    all_q = conn.execute("SELECT * FROM test_questions").fetchall()
    attempted = [q for q in all_q if q["attempted"]]
    correct = [q for q in attempted if q["correct"]]
    times = [q["time_taken_seconds"] for q in attempted if q["time_taken_seconds"]]

    subjects = rows_to_list(conn.execute("SELECT * FROM subjects ORDER BY sort_order").fetchall())
    subject_stats = []
    for s in subjects:
        qs = [q for q in all_q if q["subject_id"] == s["id"]]
        att = [q for q in qs if q["attempted"]]
        corr = [q for q in att if q["correct"]]
        tms = [q["time_taken_seconds"] for q in att if q["time_taken_seconds"]]
        score = sum((q["marks"] or 0) - (q["negative_marks"] or 0) for q in qs)
        subject_stats.append({
            "subject": s["name"],
            "accuracy": an.pct(len(corr), len(att)),
            "score": round(score, 2),
            "attempted": len(att),
            "correct": len(corr),
            "incorrect": len(att) - len(corr),
            "average_time_seconds": round(sum(tms) / len(tms), 1) if tms else 0,
        })
    conn.close()

    return {
        "study": {
            "total_hours": round(total_minutes / 60, 1),
            "weekly_average_hours": round((week_min / 60) / 7, 2),
            "monthly_average_hours": round((month_min / 60) / 30, 2),
            "current_streak": current_streak,
            "longest_streak": longest_streak,
        },
        "tests": {
            "attempted": len(tests),
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "best_score": max(scores) if scores else 0,
            "average_accuracy": an.pct(len(correct), len(attempted)),
            "highest_accuracy": max([an.pct(1 if q["correct"] else 0, 1) for q in attempted], default=0),
            "average_speed_seconds": round(sum(times) / len(times), 1) if times else 0,
            "prelims_average": round(sum(prelims) / len(prelims), 2) if prelims else 0,
            "mains_average": round(sum(mains) / len(mains), 2) if mains else 0,
        },
        "subjects": subject_stats,
    }


# ---------------------------------------------------------------------------
# SEARCH
# ---------------------------------------------------------------------------
@route("GET", r"/api/search")
def global_search(handler, m, body):
    q = handler.query.get("q", [""])[0].strip()
    if not q:
        return {"notes": [], "topics": [], "tasks": [], "tests": [], "mistakes": []}
    like = f"%{q}%"
    conn = db.get_conn()
    notes = rows_to_list(conn.execute("SELECT id,title FROM notes WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? LIMIT 10", (like, like, like)).fetchall())
    topics = rows_to_list(conn.execute("SELECT id,name FROM topics WHERE name LIKE ? LIMIT 10", (like,)).fetchall())
    tasks = rows_to_list(conn.execute("SELECT id,title FROM tasks WHERE title LIKE ? LIMIT 10", (like,)).fetchall())
    tests = rows_to_list(conn.execute("SELECT id,name FROM tests WHERE name LIKE ? LIMIT 10", (like,)).fetchall())
    mistakes = rows_to_list(conn.execute(
        "SELECT mk.id, mk.mistake_type, t.name topic_name FROM mistakes mk LEFT JOIN topics t ON t.id=mk.topic_id "
        "WHERE t.name LIKE ? LIMIT 10", (like,)).fetchall())
    conn.close()
    return {"notes": notes, "topics": topics, "tasks": tasks, "tests": tests, "mistakes": mistakes}


# ---------------------------------------------------------------------------
# CURRENT AFFAIRS
# ---------------------------------------------------------------------------
@route("GET", r"/api/current-affairs")
def list_current_affairs(handler, m, body):
    conn = db.get_conn()
    category = handler.query.get("category", [""])[0]
    sql = "SELECT * FROM current_affairs WHERE 1=1"
    params = []
    if category:
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY date DESC, id DESC"
    rows = rows_to_list(conn.execute(sql, params).fetchall())
    conn.close()
    return rows


@route("POST", r"/api/current-affairs")
def create_current_affairs(handler, m, body):
    if not body.get("title"):
        raise ApiError("Title is required")
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO current_affairs(category, title, content, date, tags, created_at) VALUES (?,?,?,?,?,?)",
        (body.get("category", "National"), body["title"], body.get("content", ""),
         body.get("date", db.today()), body.get("tags", ""), db.now())
    )
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM current_affairs WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


@route("DELETE", r"/api/current-affairs/(?P<cid>\d+)")
def delete_current_affairs(handler, m, body):
    conn = db.get_conn()
    conn.execute("DELETE FROM current_affairs WHERE id=?", (m["cid"],))
    conn.commit()
    conn.close()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# SETTINGS / DATA MANAGEMENT
# ---------------------------------------------------------------------------
@route("GET", r"/api/settings")
def get_settings(handler, m, body):
    conn = db.get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


@route("PUT", r"/api/settings")
def update_settings(handler, m, body):
    conn = db.get_conn()
    for k, v in body.items():
        conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)", (k, str(v)))
    conn.commit()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


@route("GET", r"/api/exams")
def list_exams(handler, m, body):
    conn = db.get_conn()
    rows = rows_to_list(conn.execute("SELECT * FROM exams").fetchall())
    conn.close()
    return rows


@route("POST", r"/api/data/reset-demo")
def reset_demo(handler, m, body):
    """Wipe and reseed with fresh demo data (used from Settings > Data Management)."""
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.init_db(seed_demo=True)
    return {"reset": True}


@route("POST", r"/api/data/wipe")
def wipe_data(handler, m, body):
    """Wipe all data but keep syllabus structure - fresh start for a real user."""
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.init_db(seed_demo=False)
    return {"wiped": True}


@route("GET", r"/api/export/(?P<table>\w+)")
def export_csv(handler, m, body):
    table = m["table"]
    allowed = {"notes", "tasks", "study_sessions", "tests", "test_questions", "mistakes", "topics", "revision_schedule"}
    if table not in allowed:
        raise ApiError("Unknown export table", 404)
    conn = db.get_conn()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()
    if not rows:
        csv_text = ""
    else:
        headers = rows[0].keys()
        lines = [",".join(headers)]
        for r in rows:
            vals = []
            for h in headers:
                v = r[h]
                v = "" if v is None else str(v).replace(",", ";").replace("\n", " ")
                vals.append(v)
            lines.append(",".join(vals))
        csv_text = "\n".join(lines)
    body_bytes = csv_text.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/csv")
    handler.send_header("Content-Disposition", f"attachment; filename={table}.csv")
    handler.send_header("Content-Length", str(len(body_bytes)))
    handler.end_headers()
    handler.wfile.write(body_bytes)
    return "__RAW_HANDLED__"


@route("GET", r"/api/backup")
def backup_db(handler, m, body):
    if not os.path.exists(db.DB_PATH):
        raise ApiError("No database found", 404)
    with open(db.DB_PATH, "rb") as f:
        data = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.send_header("Content-Disposition", "attachment; filename=bankprep_backup.db")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
    return "__RAW_HANDLED__"


# ---------------------------------------------------------------------------
# REPORTS  (section 30)
# ---------------------------------------------------------------------------
@route("GET", r"/api/reports/weekly")
def weekly_report(handler, m, body):
    conn = db.get_conn()
    since = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    minutes = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions WHERE date>=?", (since,)).fetchone()["m"]
    solved = conn.execute("SELECT COALESCE(SUM(questions_solved),0) q FROM study_sessions WHERE date>=?", (since,)).fetchone()["q"]
    tests = conn.execute("SELECT * FROM tests WHERE date>=?", (since,)).fetchall()

    all_q_ids = [t["id"] for t in tests]
    accuracy = 0
    if all_q_ids:
        placeholders = ",".join("?" * len(all_q_ids))
        qs = conn.execute(f"SELECT * FROM test_questions WHERE test_id IN ({placeholders})", all_q_ids).fetchall()
        att = [q for q in qs if q["attempted"]]
        corr = [q for q in att if q["correct"]]
        accuracy = an.pct(len(corr), len(att))

    subjects = conn.execute("SELECT * FROM subjects").fetchall()
    subj_acc = {}
    for s in subjects:
        qs = conn.execute(
            """SELECT tq.* FROM test_questions tq JOIN tests te ON te.id=tq.test_id
               WHERE tq.subject_id=? AND te.date>=?""", (s["id"], since)).fetchall()
        att = [q for q in qs if q["attempted"]]
        corr = [q for q in att if q["correct"]]
        if att:
            subj_acc[s["name"]] = an.pct(len(corr), len(att))
    best_subject = max(subj_acc, key=subj_acc.get) if subj_acc else "N/A"
    worst_subject = min(subj_acc, key=subj_acc.get) if subj_acc else "N/A"

    weak = _compute_all_weakness(conn)
    weak_usable = sorted([w for w in weak if not w.get("insufficient_data")], key=lambda w: -w["weakness_score"])[:3]

    mistakes = conn.execute(
        "SELECT mk.* FROM mistakes mk JOIN test_questions tq ON tq.id=mk.test_question_id JOIN tests te ON te.id=tq.test_id WHERE te.date>=?",
        (since,)).fetchall()
    mistake_analysis = an.analyze_mistakes(mistakes)
    conn.close()

    return {
        "period": "weekly", "since": since,
        "study_hours": round(minutes / 60, 1),
        "questions_solved": solved,
        "tests_taken": len(tests),
        "average_accuracy": accuracy,
        "best_subject": best_subject,
        "weakest_subject": worst_subject,
        "top_weak_topics": [w["topic_name"] for w in weak_usable],
        "most_common_mistake": mistake_analysis.get("top_type", "N/A"),
        "recommendation": f"Focus on {weak_usable[0]['topic_name']} for the next few study sessions." if weak_usable else "Keep up consistent practice across all subjects.",
    }


@route("GET", r"/api/reports/monthly")
def monthly_report(handler, m, body):
    conn = db.get_conn()
    since = (datetime.date.today() - datetime.timedelta(days=29)).isoformat()
    minutes = conn.execute("SELECT COALESCE(SUM(duration_minutes),0) m FROM study_sessions WHERE date>=?", (since,)).fetchone()["m"]
    solved = conn.execute("SELECT COALESCE(SUM(questions_solved),0) q FROM study_sessions WHERE date>=?", (since,)).fetchone()["q"]
    tests = conn.execute("SELECT * FROM tests WHERE date>=?", (since,)).fetchall()
    conn.close()
    return {
        "period": "monthly", "since": since,
        "study_hours": round(minutes / 60, 1),
        "questions_solved": solved,
        "tests_taken": len(tests),
    }


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "BankPrepServer/1.0"

    def log_message(self, fmt, *args):
        pass  # keep console quiet

    def _dispatch(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        self.query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or not path.startswith("/api/"):
            return self._serve_static(path)

        body = {}
        length = int(self.headers.get("Content-Length", 0))
        if length:
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                return error_response(self, "Invalid JSON body", 400)

        for rmethod, regex, fn in ROUTES:
            if rmethod != method:
                continue
            match = regex.match(path)
            if match:
                try:
                    result = fn(self, match.groupdict(), body)
                except ApiError as e:
                    return error_response(self, e.message, e.status)
                except Exception as e:
                    return error_response(self, f"Server error: {e}", 500)
                if result == "__RAW_HANDLED__":
                    return
                return json_response(self, result)
        error_response(self, f"No route for {method} {path}", 404)

    def _serve_static(self, path):
        if path == "/":
            path = "/index.html"
        # URL paths always use forward slashes. Normalize with posixpath (not
        # os.path.normpath) so this works correctly on Windows, where
        # os.path.normpath would turn "/js/app.js" into "\js\app.js" and then
        # os.path.join would silently discard STATIC_DIR because a leading
        # backslash looks "drive-relative" to Windows' path joiner.
        normalized = posixpath.normpath(path)
        parts = [p for p in normalized.split("/") if p not in ("", ".", "..")]
        full_path = os.path.join(STATIC_DIR, *parts) if parts else STATIC_DIR
        if not os.path.abspath(full_path).startswith(os.path.abspath(STATIC_DIR)):
            self.send_response(403)
            self.end_headers()
            return
        if not os.path.isfile(full_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        ctype, _ = mimetypes.guess_type(full_path)
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    os.makedirs(os.path.dirname(db.DB_PATH), exist_ok=True)
    fresh = db.init_db(seed_demo=True)
    port = 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Bank Exam Prep Manager running at http://localhost:{port}")
    print("Database:", db.DB_PATH, "(fresh)" if fresh else "(existing)")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()


if __name__ == "__main__":
    main()
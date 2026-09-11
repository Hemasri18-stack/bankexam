"""
Database layer for Bank Exam Prep Manager.
SQLite persistence. Schema + seed data (syllabus + demo data) live here.
"""
import sqlite3
import os
import datetime
import random

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bankprep.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    importance TEXT DEFAULT 'Medium',      -- High / Medium / Low
    status TEXT DEFAULT 'Not Started',      -- Not Started / Learning / Practicing / Completed / Needs Revision / Strong
    start_date TEXT,
    completion_date TEXT,
    confidence_level INTEGER DEFAULT 0,     -- 0-100
    questions_solved INTEGER DEFAULT 0,
    questions_correct INTEGER DEFAULT 0,
    questions_incorrect INTEGER DEFAULT 0,
    num_revisions INTEGER DEFAULT 0,
    last_revised_date TEXT,
    next_revision_date TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subtopics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    subtopic_id INTEGER REFERENCES subtopics(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT,
    formula TEXT,
    shortcut TEXT,
    example TEXT,
    important_points TEXT,
    common_mistakes TEXT,
    tags TEXT,
    is_favorite INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    priority TEXT DEFAULT 'Medium',     -- High / Medium / Low
    due_date TEXT,
    estimated_minutes INTEGER,
    status TEXT DEFAULT 'Pending',      -- Pending / In Progress / Completed / Skipped
    completion_date TEXT,
    recurring TEXT DEFAULT 'None',      -- None / Daily / Weekly
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    study_type TEXT DEFAULT 'Practice', -- Concept Learning / Practice / Revision / Test / Analysis
    duration_minutes INTEGER DEFAULT 0,
    questions_solved INTEGER DEFAULT 0,
    questions_correct INTEGER DEFAULT 0,
    questions_incorrect INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    exam TEXT,
    test_type TEXT,           -- Topic Test / Sectional Test / Prelims Mock / Mains Mock / Previous Year Paper / Custom Test
    date TEXT,
    duration_minutes INTEGER,
    total_questions INTEGER DEFAULT 0,
    max_marks REAL DEFAULT 0,
    obtained_marks REAL DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS test_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    question_number INTEGER,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    subtopic_id INTEGER REFERENCES subtopics(id) ON DELETE SET NULL,
    question_type TEXT,
    attempted INTEGER DEFAULT 0,
    correct INTEGER DEFAULT 0,
    time_taken_seconds INTEGER DEFAULT 0,
    marks REAL DEFAULT 0,
    negative_marks REAL DEFAULT 0,
    difficulty TEXT DEFAULT 'Medium',   -- Easy / Medium / Hard
    mistake_type TEXT                   -- see MISTAKE_TYPES
);

CREATE TABLE IF NOT EXISTS mistakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_question_id INTEGER REFERENCES test_questions(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    mistake_type TEXT,
    user_answer TEXT,
    correct_answer TEXT,
    explanation TEXT,
    personal_note TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS revision_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    revision_date TEXT NOT NULL,
    status TEXT DEFAULT 'Pending',    -- Pending / Done / Skipped
    stage TEXT,                        -- Day 1 / Day 3 / Day 7 ...
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS current_affairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    title TEXT,
    content TEXT,
    date TEXT,
    tags TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

MISTAKE_TYPES = [
    "Concept Mistake", "Calculation Mistake", "Silly Mistake", "Misread Question",
    "Time Pressure", "Guess", "Didn't Know", "Forgot Formula", "Logical Error"
]

SYLLABUS = {
    "Quantitative Aptitude": {
        "Number System": ["Natural numbers", "Whole numbers", "Integers", "Prime numbers", "Factors", "Multiples", "Divisibility", "HCF", "LCM"],
        "Simplification": ["BODMAS", "Fractions", "Decimals", "Surds", "Indices"],
        "Approximation": [],
        "Percentage": [],
        "Ratio & Proportion": [],
        "Average": [],
        "Profit & Loss": [],
        "Discount": [],
        "Simple Interest": [],
        "Compound Interest": [],
        "Partnership": [],
        "Mixture & Allegation": [],
        "Problems on Ages": [],
        "Time & Work": [],
        "Pipes & Cisterns": [],
        "Time, Speed & Distance": [],
        "Trains": [],
        "Boats & Streams": [],
        "Number Series": ["Missing series", "Wrong series"],
        "Quadratic Equations": [],
        "Probability": [],
        "Permutation & Combination": [],
        "Data Sufficiency": [],
        "Data Interpretation": ["Table", "Bar graph", "Line graph", "Pie chart", "Caselet", "Missing DI", "Mixed DI", "Arithmetic DI"],
    },
    "Reasoning": {
        "Alphabet Test": [], "Alphanumeric Series": [], "Coding-Decoding": [], "Direction Sense": [],
        "Blood Relations": [], "Ranking": [], "Order & Sequence": [], "Analogy": [], "Classification": [],
        "Inequality": [], "Syllogism": [], "Linear Seating Arrangement": [], "Circular Seating Arrangement": [],
        "Square Arrangement": [], "Rectangle Arrangement": [], "Parallel Rows": [], "Floor Puzzle": [],
        "Box Puzzle": [], "Month-Based Puzzle": [], "Day-Based Puzzle": [], "Scheduling Puzzle": [],
        "Age Puzzle": [], "Comparison Puzzle": [], "Selection Puzzle": [], "Distribution Puzzle": [],
        "Input-Output": [], "Data Sufficiency": [], "Statement & Conclusion": [], "Statement & Assumption": [],
        "Statement & Argument": [], "Cause & Effect": [], "Course of Action": [], "Critical Reasoning": [],
        "Logical Reasoning": [], "Analytical Reasoning": [],
    },
    "English": {
        "Parts of Speech": [], "Noun": [], "Pronoun": [], "Adjective": [], "Adverb": [], "Verb": [],
        "Articles": [], "Prepositions": [], "Conjunctions": [], "Subject-Verb Agreement": [], "Tenses": [],
        "Modals": [], "Active/Passive Voice": [], "Direct/Indirect Speech": [], "Conditionals": [],
        "Degrees of Comparison": [],
        "Synonyms": [], "Antonyms": [], "One Word Substitution": [], "Idioms": [], "Phrasal Verbs": [],
        "Confusing Words": [], "Contextual Vocabulary": [],
        "Error Detection": [], "Sentence Correction": [], "Fillers": [], "Double Fillers": [], "Cloze Test": [],
        "Para Jumbles": [], "Sentence Rearrangement": [], "Connectors": [], "Odd Sentence": [],
        "Word Replacement": [], "Reading Comprehension": [], "Inference": [], "Main Idea": [], "Tone": [],
    },
    "Banking Awareness": {
        "Banking Basics": [], "Types of Banks": [], "Commercial Banks": [], "Cooperative Banks": [],
        "Regional Rural Banks": [], "Small Finance Banks": [], "Payments Banks": [], "NBFCs": [], "RBI": [],
        "Monetary Policy": [], "Repo Rate": [], "Reverse Repo": [], "CRR": [], "SLR": [], "MSF": [], "SDF": [],
        "Bank Rate": [], "Open Market Operations": [], "Inflation": [], "NPA": [], "CASA": [], "KYC": [],
        "AML": [], "Basel Norms": [], "Capital Adequacy": [], "Priority Sector Lending": [],
        "Financial Inclusion": [], "Digital Banking": [], "UPI": [], "NEFT": [], "RTGS": [], "IMPS": [],
        "AEPS": [], "BBPS": [], "RuPay": [], "CBDC": [], "SEBI": [], "NABARD": [], "SIDBI": [], "IRDAI": [],
        "PFRDA": [], "IMF": [], "World Bank": [], "ADB": [], "Budget": [], "Economic Survey": [], "GDP": [],
        "Fiscal Deficit": [], "Balance of Payments": [],
    },
    "Computer": {
        "Computer Fundamentals": [], "Hardware": [], "Software": [], "CPU": [], "Memory": [], "Storage": [],
        "Operating Systems": [], "Windows": [], "Linux": [], "Internet": [], "Intranet": [], "WWW": [],
        "Browser": [], "URL": [], "HTTP/HTTPS": [], "DNS": [], "IP Address": [], "LAN": [], "MAN": [], "WAN": [],
        "PAN": [], "Networking Devices": [], "Network Topologies": [], "Protocols": [], "Virus": [], "Worm": [],
        "Trojan": [], "Malware": [], "Phishing": [], "Firewall": [], "Encryption": [], "Authentication": [],
        "MS Word": [], "MS Excel": [], "MS PowerPoint": [], "DBMS": [], "Cloud Computing": [],
        "Artificial Intelligence": [], "Machine Learning": [], "IoT": [], "Digital Payments": [],
    },
    "Current Affairs": {
        "National": [], "International": [], "Banking": [], "Economy": [], "Government Schemes": [],
        "Appointments": [], "Awards": [], "Sports": [], "Science & Technology": [], "Defence": [],
        "Space": [], "Environment": [], "Important Days": [], "Books & Authors": [], "Reports & Indexes": [],
        "Summits": [], "Important Organizations": [],
    },
}

EXAMS = [
    ("SBI PO", "State Bank of India Probationary Officer"),
    ("SBI Clerk", "State Bank of India Junior Associate / Clerk"),
    ("IBPS PO", "IBPS Probationary Officer (Common Recruitment Process)"),
    ("IBPS Clerk", "IBPS Clerk (Common Recruitment Process)"),
    ("IBPS RRB PO", "IBPS Regional Rural Bank Officer Scale I"),
    ("IBPS RRB Clerk", "IBPS Regional Rural Bank Office Assistant"),
]


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def today():
    return datetime.date.today().isoformat()


def init_db(seed_demo=True):
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()

    cur = conn.execute("SELECT COUNT(*) c FROM subjects")
    already_seeded = cur.fetchone()["c"] > 0

    if not already_seeded:
        _seed_exams(conn)
        _seed_syllabus(conn)
        conn.commit()
        if seed_demo:
            _seed_demo_data(conn)
            conn.commit()
    conn.close()
    return fresh


def _seed_exams(conn):
    for name, desc in EXAMS:
        conn.execute("INSERT OR IGNORE INTO exams(name, description) VALUES (?,?)", (name, desc))


def _seed_syllabus(conn):
    for s_idx, (subject, topics) in enumerate(SYLLABUS.items()):
        cur = conn.execute("INSERT INTO subjects(name, sort_order) VALUES (?,?)", (subject, s_idx))
        subject_id = cur.lastrowid
        for t_idx, (topic, subtopics) in enumerate(topics.items()):
            importance = "High" if subject in ("Quantitative Aptitude", "Reasoning", "English") else "Medium"
            cur2 = conn.execute(
                "INSERT INTO topics(subject_id, name, importance, sort_order) VALUES (?,?,?,?)",
                (subject_id, topic, importance, t_idx)
            )
            topic_id = cur2.lastrowid
            for st_idx, st in enumerate(subtopics):
                conn.execute(
                    "INSERT INTO subtopics(topic_id, name, sort_order) VALUES (?,?,?)",
                    (topic_id, st, st_idx)
                )


def _seed_demo_data(conn):
    """Populate realistic demo data so the dashboard/analytics are non-empty on first launch."""
    random.seed(42)

    def topic_id(subject, topic):
        row = conn.execute(
            "SELECT t.id FROM topics t JOIN subjects s ON s.id=t.subject_id WHERE s.name=? AND t.name=?",
            (subject, topic)
        ).fetchone()
        return row["id"] if row else None

    def subject_id(subject):
        row = conn.execute("SELECT id FROM subjects WHERE name=?", (subject,)).fetchone()
        return row["id"] if row else None

    # --- Study sessions across the last 35 days ---
    subjects_cycle = ["Quantitative Aptitude", "Reasoning", "English", "Banking Awareness", "Computer"]
    topics_by_subject = {
        "Quantitative Aptitude": ["Percentage", "Profit & Loss", "Time & Work", "Simple Interest", "Data Interpretation", "Number Series"],
        "Reasoning": ["Syllogism", "Circular Seating Arrangement", "Puzzle", "Inequality", "Coding-Decoding"],
        "English": ["Reading Comprehension", "Cloze Test", "Para Jumbles", "Error Detection"],
        "Banking Awareness": ["RBI", "Repo Rate", "NPA", "Digital Banking"],
        "Computer": ["MS Excel", "Networking Devices", "Internet"],
    }
    # fix names that don't exactly match seeded topics (Puzzle isn't a topic; use Floor Puzzle)
    topics_by_subject["Reasoning"][2] = "Floor Puzzle"

    start = datetime.date.today() - datetime.timedelta(days=34)
    streak_break_day = 30  # simulate one missed day for realism
    for i in range(35):
        d = start + datetime.timedelta(days=i)
        if i == streak_break_day:
            continue  # skip a day
        subj = subjects_cycle[i % len(subjects_cycle)]
        topic = topics_by_subject[subj][i % len(topics_by_subject[subj])]
        tid = topic_id(subj, topic)
        sid = subject_id(subj)
        duration = random.choice([60, 75, 90, 90, 90, 45])
        solved = random.randint(10, 35)
        correct = int(solved * random.uniform(0.5, 0.95))
        conn.execute(
            """INSERT INTO study_sessions(date, start_time, end_time, subject_id, topic_id, study_type,
               duration_minutes, questions_solved, questions_correct, questions_incorrect, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (d.isoformat(), "18:00", "19:30", sid, tid, random.choice(
                ["Concept Learning", "Practice", "Revision", "Practice"]),
             duration, solved, correct, solved - correct, "Auto-generated demo session")
        )

    # --- Update topic progress stats from sessions (rough aggregation) + statuses ---
    topic_status_plan = {
        "Quantitative Aptitude": {
            "Percentage": ("Completed", 80), "Profit & Loss": ("Needs Revision", 40),
            "Time & Work": ("Strong", 90), "Simple Interest": ("Practicing", 55),
            "Compound Interest": ("Learning", 30), "Data Interpretation": ("Practicing", 45),
            "Number Series": ("Completed", 70), "Ratio & Proportion": ("Completed", 75),
            "Average": ("Completed", 72), "Quadratic Equations": ("Learning", 35),
        },
        "Reasoning": {
            "Syllogism": ("Strong", 88), "Circular Seating Arrangement": ("Practicing", 50),
            "Floor Puzzle": ("Needs Revision", 38), "Inequality": ("Completed", 80),
            "Coding-Decoding": ("Completed", 78), "Blood Relations": ("Strong", 85),
            "Direction Sense": ("Completed", 74),
        },
        "English": {
            "Reading Comprehension": ("Practicing", 55), "Cloze Test": ("Learning", 40),
            "Para Jumbles": ("Needs Revision", 35), "Error Detection": ("Practicing", 48),
            "Idioms": ("Completed", 70),
        },
        "Banking Awareness": {
            "RBI": ("Completed", 82), "Repo Rate": ("Completed", 85), "NPA": ("Practicing", 50),
            "Digital Banking": ("Completed", 76),
        },
        "Computer": {
            "MS Excel": ("Completed", 80), "Networking Devices": ("Practicing", 52), "Internet": ("Completed", 78),
        },
    }
    for subj, tmap in topic_status_plan.items():
        for topic, (status, confidence) in tmap.items():
            tid = topic_id(subj, topic)
            if not tid:
                continue
            solved = random.randint(20, 60)
            correct = int(solved * (confidence / 100.0))
            start_date = (datetime.date.today() - datetime.timedelta(days=random.randint(10, 60))).isoformat()
            completion_date = None
            if status in ("Completed", "Strong", "Needs Revision"):
                completion_date = (datetime.date.today() - datetime.timedelta(days=random.randint(1, 20))).isoformat()
            conn.execute(
                """UPDATE topics SET status=?, confidence_level=?, questions_solved=?, questions_correct=?,
                   questions_incorrect=?, start_date=?, completion_date=?, num_revisions=?, last_revised_date=?
                   WHERE id=?""",
                (status, confidence, solved, correct, solved - correct, start_date, completion_date,
                 random.randint(0, 4), (datetime.date.today() - datetime.timedelta(days=random.randint(0, 10))).isoformat(),
                 tid)
            )

    # --- Tests + question-level results (simulate improving Percentage, weak Profit & Loss, strong Time & Work) ---
    test_defs = [
        ("Quant Sectional Test 1", "IBPS PO", "Sectional Test", 20),
        ("Quant Sectional Test 2", "IBPS PO", "Sectional Test", 17),
        ("Quant Sectional Test 3", "IBPS PO", "Sectional Test", 10),
        ("Full Prelims Mock 1", "SBI PO", "Prelims Mock", 25),
    ]
    quant_topics_for_tests = ["Percentage", "Profit & Loss", "Time & Work", "Simple Interest", "Data Interpretation"]
    # accuracy plan per test index (0..3) per topic, to show trends
    accuracy_plan = {
        "Percentage": [0.50, 0.60, 0.75, 0.80],
        "Profit & Loss": [0.40, 0.45, 0.42, 0.44],
        "Time & Work": [0.70, 0.80, 0.85, 0.88],
        "Simple Interest": [0.55, 0.55, 0.60, 0.65],
        "Data Interpretation": [0.45, 0.48, 0.50, 0.55],
    }
    mistake_pool = MISTAKE_TYPES
    day_offset = 28
    for t_idx, (name, exam, ttype, days_ago) in enumerate(test_defs):
        test_date = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()
        total_q = 50 if "Prelims" in ttype else 25
        cur = conn.execute(
            """INSERT INTO tests(name, exam, test_type, date, duration_minutes, total_questions, max_marks,
               obtained_marks, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (name, exam, ttype, test_date, 20 if ttype == "Sectional Test" else 60, total_q, total_q, 0, now())
        )
        test_id = cur.lastrowid
        qnum = 1
        total_marks = 0.0
        per_topic_q = total_q // len(quant_topics_for_tests)
        for topic in quant_topics_for_tests:
            tid = topic_id("Quantitative Aptitude", topic)
            sid = subject_id("Quantitative Aptitude")
            acc = accuracy_plan[topic][min(t_idx, 3)]
            for _ in range(per_topic_q):
                attempted = 1 if random.random() < 0.9 else 0
                correct = 1 if (attempted and random.random() < acc) else 0
                difficulty = random.choice(["Easy", "Medium", "Medium", "Hard"])
                mtype = None
                marks = 0
                neg = 0
                if attempted and correct:
                    marks = 1
                elif attempted and not correct:
                    neg = 0.25
                    mtype = random.choice(mistake_pool)
                total_marks += marks - neg
                conn.execute(
                    """INSERT INTO test_questions(test_id, question_number, subject_id, topic_id, question_type,
                       attempted, correct, time_taken_seconds, marks, negative_marks, difficulty, mistake_type)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (test_id, qnum, sid, tid, "MCQ", attempted, correct,
                     random.randint(25, 110), marks, neg, difficulty, mtype)
                )
                if attempted and not correct:
                    tq_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
                    conn.execute(
                        """INSERT INTO mistakes(test_question_id, subject_id, topic_id, mistake_type,
                           user_answer, correct_answer, explanation, resolved, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (tq_id, sid, tid, mtype, "Option B", "Option D",
                         "Review the concept and redo similar questions.", 0, now())
                    )
                qnum += 1
        conn.execute("UPDATE tests SET obtained_marks=? WHERE id=?", (round(total_marks, 2), test_id))

    # --- Notes ---
    sample_notes = [
        ("Quantitative Aptitude", "Percentage", "Percentage increase/decrease shortcut",
         "% change = (New - Old)/Old * 100", "If A is x% more than B, B is [x/(100+x)]*100% less than A.",
         "20% of 150 = 30", "Always convert fractions to percentages you know by heart (1/8=12.5% etc.)",
         "Confusing 'of' with 'more than'"),
        ("Quantitative Aptitude", "Profit & Loss", "Profit & Loss basics",
         "Profit% = (SP-CP)/CP * 100", "If profit and loss % are equal on two articles at same SP, there is always a net loss.",
         "CP=100, SP=120 -> Profit% = 20%", "Learn successive discount formula for combined discounts.",
         "Mixing up CP-based and SP-based percentage."),
        ("Reasoning", "Syllogism", "Syllogism - basic rules",
         "Some + Some = No conclusion (in most cases)", "Use Venn diagrams for possibility cases.",
         "All cats are dogs. All dogs are birds. -> All cats are birds.", "Practice possibility-based syllogisms separately.",
         "Assuming 'some' means 'some not'."),
    ]
    for subj, topic, title, formula, shortcut, example, points, mistakes in sample_notes:
        sid = subject_id(subj)
        tid = topic_id(subj, topic)
        conn.execute(
            """INSERT INTO notes(subject_id, topic_id, title, content, formula, shortcut, example,
               important_points, common_mistakes, tags, is_favorite, is_pinned, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, tid, title, f"Notes on {topic}.", formula, shortcut, example, points, mistakes,
             topic.lower().replace(" ", ","), 1 if topic == "Percentage" else 0, 1 if topic == "Syllogism" else 0,
             now(), now())
        )

    # --- Tasks ---
    task_defs = [
        ("Practice 30 Percentage questions", "Quantitative Aptitude", "Percentage", "High", 0, 45),
        ("Revise Syllogism rules", "Reasoning", "Syllogism", "Medium", 1, 20),
        ("Take Quant sectional test", "Quantitative Aptitude", "Profit & Loss", "High", 2, 20),
        ("Read Banking Awareness - RBI functions", "Banking Awareness", "RBI", "Medium", 0, 30),
        ("Revise yesterday's error log", "Quantitative Aptitude", "Profit & Loss", "High", 0, 15),
        ("Attempt 1 Reading Comprehension passage", "English", "Reading Comprehension", "Medium", 3, 20),
    ]
    for title, subj, topic, priority, due_offset, est in task_defs:
        sid = subject_id(subj)
        tid = topic_id(subj, topic)
        due = (datetime.date.today() + datetime.timedelta(days=due_offset)).isoformat()
        conn.execute(
            """INSERT INTO tasks(title, subject_id, topic_id, priority, due_date, estimated_minutes, status,
               recurring, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (title, sid, tid, priority, due, est, "Pending", "None", now())
        )
    # Mark one completed for realism
    conn.execute("UPDATE tasks SET status='Completed', completion_date=? WHERE title LIKE 'Read Banking%'", (today(),))

    # --- Revision schedule (for a couple of completed topics) ---
    stages = [1, 3, 7, 14, 30, 60]
    for subj, topic in [("Quantitative Aptitude", "Percentage"), ("Reasoning", "Inequality")]:
        tid = topic_id(subj, topic)
        base = datetime.date.today() - datetime.timedelta(days=5)
        for s in stages:
            rdate = base + datetime.timedelta(days=s)
            status = "Done" if rdate < datetime.date.today() else "Pending"
            conn.execute(
                """INSERT INTO revision_schedule(topic_id, revision_date, status, stage, created_at)
                   VALUES (?,?,?,?,?)""",
                (tid, rdate.isoformat(), status, f"Day {s}", now())
            )

    # --- Current affairs sample entries ---
    ca_samples = [
        ("Banking", "RBI keeps repo rate unchanged", "RBI's MPC kept the repo rate steady in its latest policy review.", today()),
        ("Government Schemes", "PM Vishwakarma Yojana", "Scheme supporting traditional artisans and craftspeople.", today()),
        ("Appointments", "New MD & CEO appointed at a PSU bank", "Track appointments relevant to banking sector.", today()),
    ]
    for cat, title, content, d in ca_samples:
        conn.execute(
            "INSERT INTO current_affairs(category, title, content, date, tags, created_at) VALUES (?,?,?,?,?,?)",
            (cat, title, content, d, cat.lower(), now())
        )

    # --- Settings defaults ---
    defaults = {
        "daily_study_minutes": "90",
        "study_start_time": "18:00",
        "study_end_time": "19:30",
        "target_exam": "IBPS PO",
        "prep_start_date": (datetime.date.today() - datetime.timedelta(days=35)).isoformat(),
        "prep_end_date": (datetime.date.today() + datetime.timedelta(days=690)).isoformat(),
        "mode": "Preparation",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)", (k, v))

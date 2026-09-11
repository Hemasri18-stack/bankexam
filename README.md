# Bank Exam Prep Manager

A complete, self-contained personal study-management and performance-analytics
application for a 2-year Bank PO/Clerk preparation journey (SBI PO, SBI Clerk,
IBPS PO, IBPS Clerk, IBPS RRB PO, IBPS RRB Clerk).

It runs entirely on your own machine, stores all data in a local SQLite file,
and needs **no internet connection and no installation** beyond Python itself
(Chart.js is loaded from a CDN for charts only - everything else works offline).

---

## 1. How to run the application

**Requirement:** Python 3.8+ (already installed on most machines; check with
`python3 --version`). No pip packages, no Node, no build step.

```bash
cd bankprep/app
python3 server.py
```

You'll see:

```
Bank Exam Prep Manager running at http://localhost:8000
Database: .../bankprep/data/bankprep.db (fresh)
Press Ctrl+C to stop.
```

Open **http://localhost:8000** in your browser. That's it.

- On **Windows**, double-click `run_windows.bat` (or run `python server.py` from
  the `app` folder in Command Prompt).
- On **Mac/Linux**, run `./run_mac_linux.sh` or `python3 server.py`.

To stop the server, press `Ctrl+C` in the terminal. Your data is saved
automatically to `bankprep/data/bankprep.db` - closing the app (or your
computer) never loses anything, because every action writes straight to disk.

The first time you run it, the app seeds itself with **realistic demo data**
(sample notes, tasks, study sessions, tests with question-level results, weak
topics, a revision schedule) so the dashboard and analytics aren't empty. You
can wipe this at any time from **Settings > Danger Zone > Wipe All My Data**,
which clears everything but keeps the full syllabus structure intact so you
can start tracking your real progress immediately.

---

## 2. Project structure

```
bankprep/
├── README.md
├── run_windows.bat
├── run_mac_linux.sh
├── data/
│   └── bankprep.db              <- created automatically on first run (SQLite)
└── app/
    ├── server.py                 <- HTTP server + all REST API routes
    ├── db.py                     <- schema, seed syllabus, seed demo data
    ├── analytics.py               <- the analytics/recommendation engine (pure functions)
    ├── test_analytics.py          <- unit tests for the analytics engine
    └── static/                    <- the whole frontend (served by server.py)
        ├── index.html
        ├── css/style.css
        └── js/app.js
```

This is a **clean-architecture split**, matching what the spec asked for:

| Layer | File | Responsibility |
|---|---|---|
| UI | `static/*` | Rendering, forms, charts - talks to the backend only via `fetch()` |
| Routing / API | `server.py` | Turns HTTP requests into calls against `db.py` / `analytics.py`, returns JSON |
| Business logic / analytics engine | `analytics.py` | Score, accuracy, weak-topic scoring, recommendations, streaks - no DB or HTTP code at all, so it's independently testable |
| Data layer | `db.py` | SQLite schema, connection helper, syllabus + demo data seeding |

Nothing is a single monolithic file of mixed concerns - the analytics engine in
particular has zero knowledge of HTTP or SQL, which is why `test_analytics.py`
can test it directly with plain Python lists/dicts.

**Why this stack?** Python's standard library (`http.server` + `sqlite3`) has
zero external dependencies, so the app is guaranteed to run on any machine with
Python installed - no `pip install`, no version conflicts, no build tools. The
frontend is plain HTML/CSS/JS so there's no bundler and no `node_modules`.

---

## 3. Database schema

SQLite, single file at `data/bankprep.db`. Tables (see `db.py` for full DDL):

- **exams** - the 6 target exams
- **subjects** → **topics** → **subtopics** - the 3-level syllabus hierarchy
  - `topics` also carries status, confidence, question counts, and revision dates
- **notes** - linked to subject/topic/subtopic
- **tasks** - the to-do list, with priority/status/recurring
- **study_sessions** - the daily study log (date, subject, topic, duration, questions)
- **tests** → **test_questions** - one test has many question-level rows
- **mistakes** - auto-created from any incorrect `test_questions` row
- **revision_schedule** - auto-generated Day 1/3/7/14/30/60 rows per completed topic
- **current_affairs** - manually created entries by category
- **settings** - key/value store (daily study minutes, mode, target exam, etc.)

Relationships match the spec exactly: a test has many test_questions; a topic
has many notes and many test_questions; a test_question can generate a mistake.
Foreign keys use `ON DELETE CASCADE`/`SET NULL` so deleting a test cleans up
its questions and mistakes automatically.

---

## 4. How the analytics engine works (`app/analytics.py`)

All analytics are **pure functions** - given the same rows, they always return
the same result, which is what makes them testable without spinning up the
whole app.

- **`analyze_test(questions)`** - per-test totals: accuracy, attempt rate,
  score, negative marks, average time, and accuracy split by Easy/Medium/Hard.
- **`analyze_by_topic(questions, topic_names)`** - groups one test's questions
  by topic and ranks them by accuracy (weakest first).
- **`compute_topic_weakness(...)`** - the core weak-topic engine, see below.
- **`analyze_mistakes(mistakes)`** - counts mistake types and returns a
  plain-English interpretation of the dominant one (e.g. "Your main problem is
  Concept Mistakes...").
- **`generate_recommendations(...)`** - turns weakness scores + due revisions
  into a prioritized action list.
- **`compute_streak(dates)`** - current and longest study streak from a list
  of session dates.
- **`build_revision_dates(completion_date)`** - the Day 1/3/7/14/30/60 schedule.

---

## 5. How weak topics are calculated

For every topic, the app pulls **every question ever answered** for that topic
across **all tests**, in chronological order, plus every mistake tied to it.

**Minimum data guard (spec section 13):** a topic isn't classified until it has
at least **2 tests OR 10 questions** of history. Below that, it's shown
separately as "Awaiting More Data" instead of being falsely labeled weak from
a single unlucky question.

Once there's enough data, four signals are combined into a **weakness score
(0-100, higher = weaker)**:

```
weakness_score =
    (100 - accuracy)        * 0.50   <- how often you get it wrong
  + (speed_penalty * 100)   * 0.20   <- are you slower than ~40-120s/question?
  + mistake_frequency       * 0.20   <- how often a wrong answer happens per attempt
  + (100 - recent_accuracy) * 0.10   <- is your LATEST performance still weak?
```

This directly implements the spec's requirement to track **accuracy AND speed
separately** (section 29): a student who gets 10/10 in 8 minutes scores lower
weakness (better) than one who gets 10/10 in 20 minutes, even though both have
100% accuracy, because the speed component penalizes the slower one.

The score is then classified:

| Score | Label |
|---|---|
| 0-20 | Excellent |
| 21-40 | Strong |
| 41-60 | Average |
| 61-80 | Weak |
| 81-100 | Critical Weakness |

Recent vs. historical accuracy is computed by splitting the topic's question
history in half chronologically - if recent accuracy is meaningfully higher
than historical, the topic is marked **Improving**; meaningfully lower is
**Declining**; otherwise **Stable**.

---

## 6. How recommendations are generated

`generate_recommendations()` (spec section 16) takes:
1. Every topic's weakness result (skipping ones still "Awaiting More Data"),
2. Every topic with a revision due today or overdue,

...and produces an ordered list, **High → Medium → Low priority**:

- **Critical Weakness / Weak** topics → "Revise X and attempt 20-30 targeted
  practice questions," with the reason citing accuracy, average time (if
  slow), and the most common mistake type for that topic.
- **Average** topics that aren't improving → a medium-priority practice nudge.
- **Strong/Excellent** topics → a low-priority "light revision only" note, so
  strong topics are never ignored entirely, just deprioritized.
- **Overdue/due revisions** → always included, with overdue ones ranked High.

The same weakness + revision data also feeds the **Smart Daily Plan**
(`/api/smart-daily-plan`), which slots your actual 90-minute (configurable)
study window into revision → weakest-topic practice → second-weakest topic →
a pending task → error-log review, using whatever time is left after each
slot.

---

## 7. Running the application

See section 1 above. In short: `python3 server.py` from the `app/` folder,
then open `http://localhost:8000`.

---

## 8. How to add new subjects/topics

Open `app/db.py` and edit the `SYLLABUS` dictionary near the top:

```python
SYLLABUS = {
    "Quantitative Aptitude": {
        "Number System": ["Natural numbers", "Whole numbers", ...],
        "Percentage": [],
        ...
    },
    "Your New Subject": {
        "Your New Topic": ["Subtopic A", "Subtopic B"],
    },
}
```

Then either:
- **Delete `data/bankprep.db`** and restart the app (it will reseed from
  scratch - you'll lose existing data), **or**
- Add the new rows directly via SQL (or a small one-off Python script using
  `db.get_conn()`) if you want to keep your existing notes/tests/progress.

---

## 9. How to add new exams

Add an entry to the `EXAMS` list in `app/db.py`:

```python
EXAMS = [
    ("SBI PO", "State Bank of India Probationary Officer"),
    ...
    ("Your New Exam", "Description"),
]
```

Exam names are also used as free-text options in the "New Test" form
(`app/static/js/app.js`, search for `SBI PO` in `openTestModal`) - add your
exam name to that list too so it appears in the dropdown.

---

## 10. How to backup data

Go to **Settings → Backup & Restore → Download Full Backup**. This downloads
the entire `bankprep.db` SQLite file. To restore, stop the server and replace
`bankprep/data/bankprep.db` with your saved copy, then restart.

You can also export any individual table as CSV from **Settings → Data
Export** (notes, tasks, study sessions, tests, question-level results,
mistakes, topics, revision schedule) - useful for opening in Excel/Google
Sheets or for a lightweight backup of just one part of your data.

**Nothing is ever deleted without confirmation.** The "Wipe All My Data" and
"Reset to Demo Data" buttons in Settings both require you to confirm twice
before anything happens.

---

## 11. How to extend the application in the future

Some natural next steps, given the current architecture:

- **New analytics:** add a pure function to `analytics.py`, write a unit test
  for it in `test_analytics.py`, then expose it via a new route in
  `server.py`. The frontend just needs a `fetch()` call and some HTML.
- **Multi-user support:** add a `user_id` column to the tables that need it
  and a simple login screen; the DAO-style queries in `server.py` would need
  a `WHERE user_id=?` added, but the schema/analytics logic stays the same.
- **Mobile app / native UI:** the backend is a plain JSON REST API
  (`/api/...`), so any frontend (mobile app, different web framework) could
  be swapped in without touching `server.py` or `analytics.py`.
- **Smarter recommendations:** `generate_recommendations()` is a single,
  well-isolated function - swapping in a more sophisticated scoring model
  (e.g. weighting by exam-specific topic importance) only requires editing
  that function and its tests.
- **Rich text / Markdown notes:** the `notes.content` field is plain text
  today; rendering it through a Markdown parser in the frontend (e.g. adding
  a small JS Markdown renderer) would be a frontend-only change.

---

## 12. Testing

Run the analytics engine's unit test suite (accuracy, negative marking, topic
aggregation, weak-topic detection, mistake classification, revision
scheduling, study streaks, syllabus completion, and recommendation
generation) with:

```bash
cd bankprep/app
python3 -m unittest test_analytics.py -v
```

All 21 tests should pass.

---

## 13. Notes on the demo data

On first launch the app seeds ~35 days of study sessions, several completed
and in-progress topics across all subjects, 4 mock tests with full
question-level results (deliberately modeled so Percentage improves over
time, Profit & Loss stays weak, and Time & Work stays strong - so you can see
the trend/weak-topic engine working immediately), sample notes, tasks, a
revision schedule, and a few current-affairs entries. This is purely to make
the dashboard meaningful on day one; delete it any time from **Settings →
Wipe All My Data** and start tracking your real preparation.

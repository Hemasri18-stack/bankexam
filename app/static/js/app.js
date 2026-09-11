/* ============================================================
   Bank Exam Prep Manager - Frontend Application (vanilla JS)
   ============================================================ */

const API = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    return res.json();
  },
  async post(path, body) {
    const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    return res.json();
  },
  async put(path, body) {
    const res = await fetch(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    return res.json();
  },
  async del(path) {
    const res = await fetch(path, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    return res.json();
  }
};

function toast(msg, isError) {
  const el = document.createElement("div");
  el.className = "toast";
  if (isError) el.style.background = "#b91c1c";
  el.textContent = msg;
  document.getElementById("toastRoot").appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtDate(d) {
  if (!d) return "-";
  const dt = new Date(d + "T00:00:00");
  if (isNaN(dt)) return d;
  return dt.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function badgeClass(status) {
  return "status-" + String(status || "").replace(/\s+/g, "");
}

function openModal(title, formHtml, onSubmit, submitLabel) {
  const root = document.getElementById("modalRoot");
  root.innerHTML = `
    <div class="modal-overlay" id="modalOverlay">
      <div class="modal-box">
        <h3>${esc(title)}</h3>
        <form id="modalForm">${formHtml}</form>
        <div class="modal-actions">
          <button class="btn ghost" id="modalCancel" type="button">Cancel</button>
          <button class="btn" id="modalSubmit" type="submit" form="modalForm">${submitLabel || "Save"}</button>
        </div>
      </div>
    </div>`;
  document.getElementById("modalCancel").onclick = closeModal;
  document.getElementById("modalOverlay").onclick = (e) => { if (e.target.id === "modalOverlay") closeModal(); };
  document.getElementById("modalForm").onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    try {
      await onSubmit(data);
      closeModal();
    } catch (err) {
      toast(err.message, true);
    }
  };
}
function closeModal() { document.getElementById("modalRoot").innerHTML = ""; }

/* ------------------------------------------------------------------ */
/* Navigation                                                          */
/* ------------------------------------------------------------------ */
const VIEWS = {
  dashboard: renderDashboard,
  studyplan: renderStudyPlan,
  syllabus: renderSyllabus,
  notes: renderNotes,
  tasks: renderTasks,
  studytracker: renderStudyTracker,
  tests: renderTests,
  weaktopics: renderWeakTopics,
  errorbook: renderErrorBook,
  revision: renderRevision,
  statistics: renderStatistics,
  currentaffairs: renderCurrentAffairs,
  reports: renderReports,
  settings: renderSettings,
};

let SUBJECTS_CACHE = null;
async function getSubjects() {
  if (!SUBJECTS_CACHE) SUBJECTS_CACHE = await API.get("/api/subjects");
  return SUBJECTS_CACHE;
}
let TOPICS_CACHE = null;
async function getAllTopics() {
  if (!TOPICS_CACHE) TOPICS_CACHE = await API.get("/api/topics");
  return TOPICS_CACHE;
}

async function navigate(view) {
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  const el = document.getElementById("view-" + view);
  el.classList.add("active");
  el.innerHTML = `<div class="empty-state">Loading...</div>`;
  try {
    await VIEWS[view](el);
  } catch (err) {
    el.innerHTML = `<div class="empty-state">Error loading view: ${esc(err.message)}</div>`;
  }
}

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => navigate(btn.dataset.view));
});

document.getElementById("topbarDate").textContent = new Date().toLocaleDateString(undefined, {
  weekday: "long", year: "numeric", month: "long", day: "numeric"
});

/* ------------------------------------------------------------------ */
/* Global search                                                       */
/* ------------------------------------------------------------------ */
const searchInput = document.getElementById("globalSearch");
const searchResults = document.getElementById("searchResults");
let searchTimer = null;
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = searchInput.value.trim();
  if (!q) { searchResults.classList.add("hidden"); return; }
  searchTimer = setTimeout(async () => {
    const r = await API.get("/api/search?q=" + encodeURIComponent(q));
    const groups = [
      ["Notes", r.notes, n => n.title],
      ["Topics", r.topics, n => n.name],
      ["Tasks", r.tasks, n => n.title],
      ["Tests", r.tests, n => n.name],
      ["Mistakes", r.mistakes, n => `${n.mistake_type || "Mistake"} - ${n.topic_name || ""}`],
    ];
    let html = "";
    groups.forEach(([label, items]) => {
      if (items && items.length) {
        html += `<div class="search-group-title">${label}</div>`;
        items.forEach(i => html += `<div class="search-result-item">${esc(i.title || i.name)}</div>`);
      }
    });
    searchResults.innerHTML = html || `<div class="empty-state">No results</div>`;
    searchResults.classList.remove("hidden");
  }, 250);
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".search-box")) searchResults.classList.add("hidden");
});

/* ------------------------------------------------------------------ */
/* Chart helpers                                                       */
/* ------------------------------------------------------------------ */
const CHART_REGISTRY = {};
function makeChart(canvasId, config) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  if (typeof Chart === "undefined") {
    const msg = document.createElement("div");
    msg.className = "empty-state";
    msg.style.fontSize = "12px";
    msg.textContent = "Chart unavailable - Chart.js couldn't load.";
    ctx.replaceWith(msg);
    return;
  }

  try {
    if (CHART_REGISTRY[canvasId]) CHART_REGISTRY[canvasId].destroy();
    CHART_REGISTRY[canvasId] = new Chart(ctx, config);
  } catch (err) {
    console.error("Chart render failed for", canvasId, err);
  }
}

/* ==================================================================
   DASHBOARD
   ================================================================== */
async function renderDashboard(el) {
  const d = await API.get("/api/dashboard");
  const subjEntries = Object.entries(d.subject_completion || {});

  el.innerHTML = `
    <h1 class="page-title">Dashboard</h1>
    <p class="page-sub">${d.date} &middot; Today's target: ${d.today_target_minutes} minutes</p>

    <div class="grid grid-4">
      ${statCard("Today's Tasks", `${d.today_tasks_completed}/${d.today_tasks_total}`, "completed today")}
      ${statCard("Study Streak", `${d.current_streak} 🔥`, `longest: ${d.longest_streak} days`)}
      ${statCard("Total Study Hours", `${d.total_study_hours}h`, "all time")}
      ${statCard("Syllabus Completion", `${d.syllabus_completion}%`, "overall")}
    </div>

    <div class="grid grid-4" style="margin-top:16px;">
      ${statCard("Tests Attempted", d.tests_attempted, "")}
      ${statCard("Average Score", d.average_test_score, `best: ${d.best_test_score}`)}
      ${statCard("Average Accuracy", `${d.average_accuracy}%`, `speed: ${d.average_speed_seconds}s/q`)}
      ${statCard("Weakest Subject", d.weakest_subject, `weak topic: ${d.weakest_topic}`)}
    </div>

    <div class="section-title">Subject-wise Syllabus Completion</div>
    <div class="card">
      ${subjEntries.map(([name, pct]) => progressRow(name, pct)).join("") || `<div class="empty-state">No subjects yet</div>`}
    </div>

    <div class="grid grid-2" style="margin-top:20px;">
      <div class="card"><div class="section-title" style="margin-top:0;">Weekly Study Hours</div><div class="chart-wrap"><canvas id="chartWeekly"></canvas></div></div>
      <div class="card"><div class="section-title" style="margin-top:0;">Test Score Trend</div><div class="chart-wrap"><canvas id="chartScore"></canvas></div></div>
    </div>
    <div class="grid grid-2" style="margin-top:16px;">
      <div class="card"><div class="section-title" style="margin-top:0;">Accuracy Trend</div><div class="chart-wrap"><canvas id="chartAccuracy"></canvas></div></div>
      <div class="card"><div class="section-title" style="margin-top:0;">Study Streak (last 6 weeks)</div><div class="chart-wrap"><canvas id="chartStreak"></canvas></div></div>
    </div>

    <div class="grid grid-2" style="margin-top:20px;">
      <div class="card">
        <div class="section-title" style="margin-top:0;">Topics Needing Revision</div>
        ${(d.topics_needing_revision || []).map(t => `<div class="list-item"><span>${esc(t.topic_name)}</span><span class="pill">${esc(t.revision_date)}</span></div>`).join("") || `<div class="empty-state">Nothing due - great job!</div>`}
      </div>
      <div class="card">
        <div class="section-title" style="margin-top:0;">Upcoming Tasks</div>
        ${(d.upcoming_tasks || []).map(t => `<div class="list-item"><span>${esc(t.title)}</span><span class="badge ${t.priority}">${esc(t.priority)}</span></div>`).join("") || `<div class="empty-state">No upcoming tasks</div>`}
      </div>
    </div>
  `;

  const weekly = await API.get("/api/charts/weekly-hours");
  makeChart("chartWeekly", { type: "bar", data: { labels: weekly.labels.map(shortDate), datasets: [{ label: "Hours", data: weekly.values, backgroundColor: "#3b5bfd" }] }, options: baseChartOpts() });

  const score = await API.get("/api/charts/score-trend");
  makeChart("chartScore", { type: "line", data: { labels: score.labels, datasets: [{ label: "Score", data: score.values, borderColor: "#3b5bfd", tension: 0.3, fill: false }] }, options: baseChartOpts() });

  const acc = await API.get("/api/charts/accuracy-trend");
  makeChart("chartAccuracy", { type: "line", data: { labels: acc.labels, datasets: [{ label: "Accuracy %", data: acc.values, borderColor: "#16a34a", tension: 0.3, fill: false }] }, options: baseChartOpts() });

  const streak = await API.get("/api/charts/streak-calendar");
  makeChart("chartStreak", { type: "bar", data: { labels: streak.labels.map(shortDate), datasets: [{ label: "Minutes", data: streak.values, backgroundColor: streak.values.map(v => v > 0 ? "#16a34a" : "#e6e9f2") }] }, options: { ...baseChartOpts(), scales: { x: { display: false }, y: { display: false } } } });
}

function shortDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
function baseChartOpts() {
  return { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } };
}
function statCard(label, value, sub) {
  return `<div class="card stat-card"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-sub">${esc(sub)}</div></div>`;
}
function progressRow(label, pct) {
  return `<div class="progress-row"><div class="progress-label"><span>${esc(label)}</span><span>${pct}%</span></div><div class="progress-bar-bg"><div class="progress-bar-fill" style="width:${pct}%"></div></div></div>`;
}

/* ==================================================================
   STUDY PLAN  (Smart Daily Plan)
   ================================================================== */
async function renderStudyPlan(el) {
  const plan = await API.get("/api/smart-daily-plan");
  el.innerHTML = `
    <h1 class="page-title">Today's Smart Study Plan</h1>
    <p class="page-sub">Generated from weak topics, revision due, and pending tasks - ${plan.total_minutes} minutes available.</p>
    <div class="card">
      ${plan.slots.map(s => `
        <div class="list-item">
          <span><b>${s.start}-${s.end}</b> &nbsp; ${esc(s.activity)}</span>
        </div>`).join("") || `<div class="empty-state">No plan could be generated - add some topics or tasks first.</div>`}
    </div>
    <p class="muted" style="margin-top:10px;font-size:12px;">This plan refreshes automatically based on your latest test results, revision schedule, and pending to-dos. Edit tasks or topic status to change tomorrow's plan.</p>
  `;
}

/* ==================================================================
   SYLLABUS TRACKER
   ================================================================== */
async function renderSyllabus(el) {
  const subjects = await getSubjects();
  el.innerHTML = `
    <h1 class="page-title">Syllabus Tracker</h1>
    <p class="page-sub">Track status, confidence and revision for every topic across all subjects.</p>
    <div class="tabs" id="subjTabs"></div>
    <div id="topicList"></div>
  `;
  const tabsEl = document.getElementById("subjTabs");
  tabsEl.innerHTML = subjects.map((s, i) => `<button class="tab-btn ${i === 0 ? "active" : ""}" data-sid="${s.id}">${esc(s.name)} (${s.completion_pct}%)</button>`).join("");
  tabsEl.querySelectorAll(".tab-btn").forEach(btn => {
    btn.onclick = async () => {
      tabsEl.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      await loadTopicsForSubject(btn.dataset.sid);
    };
  });
  if (subjects.length) await loadTopicsForSubject(subjects[0].id);
}

async function loadTopicsForSubject(sid) {
  const topics = await API.get(`/api/subjects/${sid}/topics`);
  const el = document.getElementById("topicList");
  el.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Topic</th><th>Status</th><th>Confidence</th><th>Q Solved</th><th>Accuracy</th><th>Next Revision</th><th></th></tr></thead>
      <tbody>
        ${topics.map(t => {
          const acc = t.questions_solved ? Math.round((t.questions_correct / t.questions_solved) * 100) : 0;
          return `<tr>
            <td>${esc(t.name)}${t.subtopics.length ? `<div class="muted" style="font-size:11px;">${t.subtopics.map(s => esc(s.name)).join(", ")}</div>` : ""}</td>
            <td><span class="badge ${badgeClass(t.status)}">${esc(t.status)}</span></td>
            <td>${t.confidence_level}%</td>
            <td>${t.questions_solved}</td>
            <td>${acc}%</td>
            <td>${fmtDate(t.next_revision_date)}</td>
            <td><button class="btn small secondary" data-tid="${t.id}">Update</button></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>
  `;
  el.querySelectorAll("button[data-tid]").forEach(btn => {
    btn.onclick = () => openTopicUpdateModal(btn.dataset.tid, sid);
  });
}

function openTopicUpdateModal(tid, sid) {
  API.get(`/api/topics/${tid}`).then(t => {
    openModal(`Update: ${t.name}`, `
      <div class="form-grid">
        <div><label>Status</label><select name="status">
          ${["Not Started", "Learning", "Practicing", "Completed", "Needs Revision", "Strong"].map(s => `<option ${s === t.status ? "selected" : ""}>${s}</option>`).join("")}
        </select></div>
        <div><label>Confidence Level (0-100)</label><input type="number" name="confidence_level" min="0" max="100" value="${t.confidence_level}"></div>
        <div><label>Start Date</label><input type="date" name="start_date" value="${t.start_date || ""}"></div>
        <div><label>Completion Date</label><input type="date" name="completion_date" value="${t.completion_date || ""}"></div>
        <div><label>Questions Solved</label><input type="number" name="questions_solved" value="${t.questions_solved}"></div>
        <div><label>Questions Correct</label><input type="number" name="questions_correct" value="${t.questions_correct}"></div>
      </div>
    `, async (data) => {
      data.confidence_level = Number(data.confidence_level);
      data.questions_solved = Number(data.questions_solved);
      data.questions_correct = Number(data.questions_correct);
      data.questions_incorrect = Math.max(0, data.questions_solved - data.questions_correct);
      await API.put(`/api/topics/${tid}`, data);
      TOPICS_CACHE = null;
      toast("Topic updated");
      await loadTopicsForSubject(sid);
    });
  });
}

/* ==================================================================
   NOTES
   ================================================================== */
async function renderNotes(el) {
  el.innerHTML = `
    <div class="section-title" style="margin-top:0;">
      <h1 class="page-title" style="margin:0;">Notes</h1>
      <button class="btn" id="addNoteBtn">+ New Note</button>
    </div>
    <div class="flex" style="margin-bottom:14px;">
      <input type="text" id="noteSearch" placeholder="Search notes..." style="max-width:260px;">
      <select id="noteFavoriteFilter" style="max-width:160px;"><option value="">All notes</option><option value="1">Favorites only</option></select>
    </div>
    <div id="notesGrid" class="grid grid-3"></div>
  `;
  document.getElementById("addNoteBtn").onclick = () => openNoteModal();
  document.getElementById("noteSearch").oninput = debounce(loadNotes, 300);
  document.getElementById("noteFavoriteFilter").onchange = loadNotes;
  await loadNotes();
}

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

async function loadNotes() {
  const q = document.getElementById("noteSearch").value;
  const fav = document.getElementById("noteFavoriteFilter").value;
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (fav) params.set("favorite", fav);
  const notes = await API.get("/api/notes?" + params.toString());
  const grid = document.getElementById("notesGrid");
  grid.innerHTML = notes.map(n => `
    <div class="card note-card ${n.is_pinned ? "pinned" : ""}">
      <div class="flex-between">
        <b>${esc(n.title)}</b>
        <span>${n.is_pinned ? "📌" : ""}${n.is_favorite ? "⭐" : ""}</span>
      </div>
      <div class="muted" style="font-size:11.5px;margin:4px 0 8px;">${esc(n.subject_name || "")} ${n.topic_name ? "› " + esc(n.topic_name) : ""}</div>
      <div style="font-size:13px; max-height:70px; overflow:hidden;">${esc(n.content || "").slice(0, 150)}</div>
      ${n.formula ? `<div style="font-size:12px;margin-top:6px;"><b>Formula:</b> ${esc(n.formula)}</div>` : ""}
      <div class="flex" style="margin-top:10px;">
        <button class="btn small secondary" data-edit="${n.id}">Edit</button>
        <button class="btn small ghost" data-fav="${n.id}">${n.is_favorite ? "Unfavorite" : "Favorite"}</button>
        <button class="btn small danger" data-del="${n.id}">Delete</button>
      </div>
    </div>
  `).join("") || `<div class="empty-state">No notes yet - click "New Note" to add your first one.</div>`;

  grid.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => openNoteModal(notes.find(n => n.id == b.dataset.edit)));
  grid.querySelectorAll("[data-fav]").forEach(b => b.onclick = async () => {
    const n = notes.find(x => x.id == b.dataset.fav);
    await API.put(`/api/notes/${n.id}`, { is_favorite: n.is_favorite ? 0 : 1 });
    loadNotes();
  });
  grid.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (confirm("Delete this note?")) { await API.del(`/api/notes/${b.dataset.del}`); toast("Note deleted"); loadNotes(); }
  });
}

async function openNoteModal(note) {
  const subjects = await getSubjects();
  const topics = await getAllTopics();
  const isEdit = !!note;
  note = note || {};
  openModal(isEdit ? "Edit Note" : "New Note", `
    <div class="form-grid">
      <div style="grid-column:1/-1;"><label>Title</label><input name="title" required value="${esc(note.title || "")}"></div>
      <div><label>Subject</label><select name="subject_id" id="noteSubjectSel">
        <option value="">-</option>${subjects.map(s => `<option value="${s.id}" ${s.id === note.subject_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}
      </select></div>
      <div><label>Topic</label><select name="topic_id" id="noteTopicSel">
        <option value="">-</option>${topics.map(t => `<option value="${t.id}" ${t.id === note.topic_id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}
      </select></div>
      <div style="grid-column:1/-1;"><label>Content</label><textarea name="content">${esc(note.content || "")}</textarea></div>
      <div><label>Formula</label><textarea name="formula">${esc(note.formula || "")}</textarea></div>
      <div><label>Shortcut</label><textarea name="shortcut">${esc(note.shortcut || "")}</textarea></div>
      <div><label>Example</label><textarea name="example">${esc(note.example || "")}</textarea></div>
      <div><label>Common Mistakes</label><textarea name="common_mistakes">${esc(note.common_mistakes || "")}</textarea></div>
      <div style="grid-column:1/-1;"><label>Important Points</label><textarea name="important_points">${esc(note.important_points || "")}</textarea></div>
      <div><label>Tags (comma separated)</label><input name="tags" value="${esc(note.tags || "")}"></div>
      <div class="checkbox-row"><input type="checkbox" name="is_pinned" ${note.is_pinned ? "checked" : ""} style="width:auto;"><label style="margin:0;">Pin this note</label></div>
    </div>
  `, async (data) => {
    data.is_pinned = data.is_pinned ? 1 : 0;
    if (isEdit) await API.put(`/api/notes/${note.id}`, data);
    else await API.post("/api/notes", data);
    toast("Note saved");
    loadNotes();
  }, "Save Note");
}

/* ==================================================================
   TASKS / TO-DO
   ================================================================== */
async function renderTasks(el) {
  el.innerHTML = `
    <div class="section-title" style="margin-top:0;">
      <h1 class="page-title" style="margin:0;">Tasks / To-Do</h1>
      <button class="btn" id="addTaskBtn">+ New Task</button>
    </div>
    <div class="tabs">
      <button class="tab-btn active" data-f="today">Today</button>
      <button class="tab-btn" data-f="week">This Week</button>
      <button class="tab-btn" data-f="overdue">Overdue</button>
      <button class="tab-btn" data-f="completed">Completed</button>
      <button class="tab-btn" data-f="">All</button>
    </div>
    <div id="taskList" class="card"></div>
  `;
  document.getElementById("addTaskBtn").onclick = () => openTaskModal();
  el.querySelectorAll(".tab-btn").forEach(btn => {
    btn.onclick = () => {
      el.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      loadTasks(btn.dataset.f);
    };
  });
  await loadTasks("today");
}

async function loadTasks(filter) {
  const tasks = await API.get("/api/tasks" + (filter ? `?filter=${filter}` : ""));
  const el = document.getElementById("taskList");
  el.innerHTML = tasks.map(t => `
    <div class="list-item">
      <span class="checkbox-row">
        <input type="checkbox" data-toggle="${t.id}" ${t.status === "Completed" ? "checked" : ""} style="width:auto;">
        <span style="${t.status === "Completed" ? "text-decoration:line-through;color:#9aa1b5;" : ""}">${esc(t.title)}</span>
        <span class="muted" style="font-size:11px;">${esc(t.subject_name || "")}</span>
      </span>
      <span class="flex">
        <span class="badge ${t.priority}">${esc(t.priority)}</span>
        <span class="pill">${fmtDate(t.due_date)}</span>
        <button class="btn small ghost" data-del="${t.id}">🗑</button>
      </span>
    </div>
  `).join("") || `<div class="empty-state">No tasks in this view.</div>`;

  el.querySelectorAll("[data-toggle]").forEach(cb => cb.onchange = async () => {
    await API.put(`/api/tasks/${cb.dataset.toggle}`, { status: cb.checked ? "Completed" : "Pending" });
    loadTasks(document.querySelector(".tab-btn.active").dataset.f);
  });
  el.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    await API.del(`/api/tasks/${b.dataset.del}`);
    loadTasks(document.querySelector(".tab-btn.active").dataset.f);
  });
}

async function openTaskModal() {
  const subjects = await getSubjects();
  const topics = await getAllTopics();
  openModal("New Task", `
    <div class="form-grid">
      <div style="grid-column:1/-1;"><label>Title</label><input name="title" required placeholder="e.g. Practice 30 Percentage questions"></div>
      <div><label>Subject</label><select name="subject_id"><option value="">-</option>${subjects.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select></div>
      <div><label>Topic</label><select name="topic_id"><option value="">-</option>${topics.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select></div>
      <div><label>Priority</label><select name="priority"><option>High</option><option selected>Medium</option><option>Low</option></select></div>
      <div><label>Due Date</label><input type="date" name="due_date" value="${new Date().toISOString().slice(0, 10)}"></div>
      <div><label>Estimated Minutes</label><input type="number" name="estimated_minutes" value="30"></div>
      <div><label>Recurring</label><select name="recurring"><option>None</option><option>Daily</option><option>Weekly</option></select></div>
    </div>
  `, async (data) => {
    await API.post("/api/tasks", data);
    toast("Task added");
    loadTasks(document.querySelector(".tab-btn.active")?.dataset.f || "today");
  }, "Add Task");
}

/* ==================================================================
   DAILY STUDY TRACKER
   ================================================================== */
async function renderStudyTracker(el) {
  const summary = await API.get("/api/study-sessions/summary");
  el.innerHTML = `
    <div class="section-title" style="margin-top:0;">
      <h1 class="page-title" style="margin:0;">Daily Study Tracker</h1>
      <button class="btn" id="logSessionBtn">+ Log Study Session</button>
    </div>
    <div class="grid grid-4">
      ${statCard("Today", (summary.today_minutes / 60).toFixed(1) + "h", "")}
      ${statCard("This Week", (summary.week_minutes / 60).toFixed(1) + "h", "")}
      ${statCard("This Month", (summary.month_minutes / 60).toFixed(1) + "h", "")}
      ${statCard("Streak", `${summary.current_streak} days`, `longest: ${summary.longest_streak}`)}
    </div>
    <div class="section-title">Recent Sessions</div>
    <div id="sessionList" class="card"></div>
  `;
  document.getElementById("logSessionBtn").onclick = () => openSessionModal();
  const sessions = await API.get("/api/study-sessions?limit=30");
  document.getElementById("sessionList").innerHTML = `
    <table class="data-table"><thead><tr><th>Date</th><th>Subject</th><th>Topic</th><th>Type</th><th>Duration</th><th>Solved</th><th>Correct</th></tr></thead>
    <tbody>${sessions.map(s => `<tr><td>${fmtDate(s.date)}</td><td>${esc(s.subject_name || "")}</td><td>${esc(s.topic_name || "")}</td><td>${esc(s.study_type)}</td><td>${s.duration_minutes}m</td><td>${s.questions_solved}</td><td>${s.questions_correct}</td></tr>`).join("")}</tbody></table>
  ` + (sessions.length ? "" : `<div class="empty-state">No sessions logged yet.</div>`);
}

async function openSessionModal() {
  const subjects = await getSubjects();
  const topics = await getAllTopics();
  openModal("Log Study Session", `
    <div class="form-grid">
      <div><label>Date</label><input type="date" name="date" value="${new Date().toISOString().slice(0, 10)}" required></div>
      <div><label>Study Type</label><select name="study_type">
        <option>Concept Learning</option><option selected>Practice</option><option>Revision</option><option>Test</option><option>Analysis</option>
      </select></div>
      <div><label>Start Time</label><input type="time" name="start_time" value="18:00"></div>
      <div><label>End Time</label><input type="time" name="end_time" value="19:30"></div>
      <div><label>Subject</label><select name="subject_id">${subjects.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select></div>
      <div><label>Topic</label><select name="topic_id"><option value="">-</option>${topics.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select></div>
      <div><label>Duration (minutes)</label><input type="number" name="duration_minutes" value="90"></div>
      <div><label>Questions Solved</label><input type="number" name="questions_solved" value="0"></div>
      <div><label>Questions Correct</label><input type="number" name="questions_correct" value="0"></div>
      <div style="grid-column:1/-1;"><label>Notes</label><textarea name="notes"></textarea></div>
    </div>
  `, async (data) => {
    ["duration_minutes", "questions_solved", "questions_correct"].forEach(k => data[k] = Number(data[k] || 0));
    data.questions_incorrect = Math.max(0, data.questions_solved - data.questions_correct);
    await API.post("/api/study-sessions", data);
    toast("Session logged");
    navigate("studytracker");
  }, "Log Session");
}

/* ==================================================================
   TESTS
   ================================================================== */
async function renderTests(el) {
  el.innerHTML = `
    <div class="section-title" style="margin-top:0;">
      <h1 class="page-title" style="margin:0;">Test & Mock Test Tracker</h1>
      <button class="btn" id="addTestBtn">+ New Test</button>
    </div>
    <div id="testList" class="card"></div>
  `;
  document.getElementById("addTestBtn").onclick = () => openTestModal();
  await loadTests();
}

async function loadTests() {
  const tests = await API.get("/api/tests");
  const el = document.getElementById("testList");
  el.innerHTML = `
    <table class="data-table"><thead><tr><th>Test</th><th>Exam</th><th>Type</th><th>Date</th><th>Score</th><th></th></tr></thead>
    <tbody>${tests.map(t => `<tr>
      <td>${esc(t.name)}</td><td>${esc(t.exam || "")}</td><td>${esc(t.test_type)}</td><td>${fmtDate(t.date)}</td>
      <td>${t.obtained_marks}/${t.max_marks}</td>
      <td>
        <button class="btn small secondary" data-analyze="${t.id}">Analyze</button>
        <button class="btn small ghost" data-addq="${t.id}">Add Questions</button>
        <button class="btn small danger" data-del="${t.id}">Delete</button>
      </td>
    </tr>`).join("")}</tbody></table>
  ` + (tests.length ? "" : `<div class="empty-state">No tests recorded yet.</div>`);

  el.querySelectorAll("[data-analyze]").forEach(b => b.onclick = () => showTestAnalysis(b.dataset.analyze));
  el.querySelectorAll("[data-addq]").forEach(b => b.onclick = () => openAddQuestionsModal(b.dataset.addq));
  el.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (confirm("Delete this test and all its question data?")) { await API.del(`/api/tests/${b.dataset.del}`); loadTests(); }
  });
}

async function openTestModal() {
  openModal("New Test", `
    <div class="form-grid">
      <div style="grid-column:1/-1;"><label>Test Name</label><input name="name" required placeholder="e.g. Quant Sectional Test 4"></div>
      <div><label>Exam</label><select name="exam">
        <option>SBI PO</option><option>SBI Clerk</option><option>IBPS PO</option><option>IBPS Clerk</option><option>IBPS RRB PO</option><option>IBPS RRB Clerk</option>
      </select></div>
      <div><label>Test Type</label><select name="test_type">
        <option>Topic Test</option><option>Sectional Test</option><option>Prelims Mock</option><option>Mains Mock</option><option>Previous Year Paper</option><option>Custom Test</option>
      </select></div>
      <div><label>Date</label><input type="date" name="date" value="${new Date().toISOString().slice(0, 10)}"></div>
      <div><label>Duration (minutes)</label><input type="number" name="duration_minutes" value="20"></div>
      <div><label>Total Questions</label><input type="number" name="total_questions" value="25"></div>
      <div><label>Max Marks</label><input type="number" name="max_marks" value="25"></div>
    </div>
  `, async (data) => {
    ["duration_minutes", "total_questions", "max_marks"].forEach(k => data[k] = Number(data[k] || 0));
    const test = await API.post("/api/tests", data);
    toast("Test created - now add question-level results");
    loadTests();
    openAddQuestionsModal(test.id, data.total_questions);
  }, "Create Test");
}

async function openAddQuestionsModal(testId, totalHint) {
  const subjects = await getSubjects();
  const topics = await getAllTopics();
  const n = totalHint || prompt("How many questions to enter results for?", "10");
  const count = Math.max(1, Math.min(100, Number(n) || 10));
  let rows = "";
  for (let i = 1; i <= count; i++) {
    rows += `
      <tr>
        <td>${i}</td>
        <td><select name="subject_${i}" style="min-width:110px;">${subjects.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select></td>
        <td><select name="topic_${i}" style="min-width:130px;"><option value="">-</option>${topics.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select></td>
        <td><select name="difficulty_${i}"><option>Easy</option><option selected>Medium</option><option>Hard</option></select></td>
        <td><input type="checkbox" name="attempted_${i}" checked style="width:auto;"></td>
        <td><input type="checkbox" name="correct_${i}" style="width:auto;"></td>
        <td><input type="number" name="time_${i}" value="45" style="width:60px;"></td>
        <td><select name="mistake_${i}"><option value="">-</option>${["Concept Mistake","Calculation Mistake","Silly Mistake","Misread Question","Time Pressure","Guess","Didn't Know","Forgot Formula","Logical Error"].map(m => `<option>${m}</option>`).join("")}</select></td>
      </tr>`;
  }
  openModal(`Add Question Results (${count} questions)`, `
    <div style="overflow-x:auto;">
    <table class="data-table" style="font-size:11.5px;">
      <thead><tr><th>#</th><th>Subject</th><th>Topic</th><th>Diff.</th><th>Att.</th><th>Correct</th><th>Time(s)</th><th>Mistake</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>
  `, async (data) => {
    const questions = [];
    for (let i = 1; i <= count; i++) {
      const attempted = !!data[`attempted_${i}`];
      const correct = !!data[`correct_${i}`];
      questions.push({
        question_number: i,
        subject_id: Number(data[`subject_${i}`]) || null,
        topic_id: Number(data[`topic_${i}`]) || null,
        difficulty: data[`difficulty_${i}`],
        attempted, correct,
        time_taken_seconds: Number(data[`time_${i}`] || 0),
        marks: attempted && correct ? 1 : 0,
        negative_marks: attempted && !correct ? 0.25 : 0,
        mistake_type: attempted && !correct ? (data[`mistake_${i}`] || "Didn't Know") : null,
      });
    }
    await API.post(`/api/tests/${testId}/questions`, { questions });
    toast("Question results saved - analysis updated");
    loadTests();
  }, "Save Results");
}

async function showTestAnalysis(testId) {
  const a = await API.get(`/api/tests/${testId}/analysis`);
  const rows = a.by_topic.map(t => `<tr><td>${esc(t.topic_name)}</td><td>${t.total_questions}</td><td>${t.attempted}</td><td>${t.correct}</td><td>${t.accuracy}%</td></tr>`).join("");
  openModal(`Analysis: ${a.test.name}`, `
    <div class="grid grid-3" style="margin-bottom:14px;">
      ${statCard("Accuracy", a.overall.accuracy + "%", "")}
      ${statCard("Score", a.overall.score, "")}
      ${statCard("Avg Time", a.overall.avg_time_seconds + "s", "per question")}
    </div>
    <p><b>Attempted:</b> ${a.overall.attempted}/${a.overall.total_questions} &nbsp; <b>Correct:</b> ${a.overall.correct} &nbsp; <b>Incorrect:</b> ${a.overall.incorrect}</p>
    <p><b>Difficulty accuracy:</b> Easy ${a.overall.easy_accuracy}% / Medium ${a.overall.medium_accuracy}% / Hard ${a.overall.hard_accuracy}%</p>
    <table class="data-table"><thead><tr><th>Topic</th><th>Qs</th><th>Attempted</th><th>Correct</th><th>Accuracy</th></tr></thead><tbody>${rows}</tbody></table>
    <p style="margin-top:12px;"><b>Interpretation:</b> ${esc(a.mistake_analysis.interpretation)}</p>
  `, async () => {}, "Close");
  document.getElementById("modalSubmit").textContent = "Close";
}

/* ==================================================================
   WEAK TOPIC ANALYZER
   ================================================================== */
async function renderWeakTopics(el) {
  const data = await API.get("/api/weak-topics");
  el.innerHTML = `
    <h1 class="page-title">Weak Topic Analyzer</h1>
    <p class="page-sub">Weakness score combines accuracy (50%), speed (20%), mistake frequency (20%) and recent trend (10%). Topics need at least 2 tests or 10 questions before being classified.</p>
    <div class="grid grid-2">
      <div class="card">
        <div class="section-title" style="margin-top:0;">Weakest Topics</div>
        ${data.weakest.map(w => weaknessRow(w)).join("") || `<div class="empty-state">No critical weaknesses detected yet.</div>`}
      </div>
      <div class="card">
        <div class="section-title" style="margin-top:0;">Strongest Topics</div>
        ${data.strongest.map(w => weaknessRow(w)).join("") || `<div class="empty-state">Not enough data yet.</div>`}
      </div>
    </div>
    <div class="section-title">All Analyzed Topics</div>
    <div class="card">
      <table class="data-table">
        <thead><tr><th>Topic</th><th>Accuracy</th><th>Trend</th><th>Avg Time</th><th>Weakness Score</th><th>Classification</th></tr></thead>
        <tbody>${data.topics.map(w => `<tr><td>${esc(w.topic_name)}</td><td>${w.accuracy}%</td><td>${w.trend}</td><td>${w.avg_time_seconds}s</td><td>${w.weakness_score}</td><td><span class="badge ${w.classification.replace(/\s+/g, "")}">${w.classification}</span></td></tr>`).join("")}</tbody>
      </table>
    </div>
    ${data.insufficient_data_topics.length ? `
    <div class="section-title">Awaiting More Data</div>
    <div class="card"><p class="muted">These topics need more attempts (at least 2 tests or 10 questions) before a reliable weakness classification: ${data.insufficient_data_topics.map(t => esc(t.topic_name)).join(", ")}.</p></div>` : ""}
  `;
}
function weaknessRow(w) {
  return `<div class="list-item"><span>${esc(w.topic_name)}</span><span class="flex"><span class="muted">${w.accuracy}%</span><span class="badge ${w.classification.replace(/\s+/g, "")}">${w.classification}</span></span></div>`;
}

/* ==================================================================
   ERROR BOOK
   ================================================================== */
async function renderErrorBook(el) {
  const freq = await API.get("/api/mistakes/frequent");
  el.innerHTML = `
    <h1 class="page-title">Error Book</h1>
    <p class="page-sub">Every incorrect attempt from your tests, automatically collected here.</p>
    <div class="card" style="margin-bottom:18px;">
      <div class="section-title" style="margin-top:0;">Most Frequent Mistake Types</div>
      <div class="chart-wrap small"><canvas id="mistakeChart"></canvas></div>
    </div>
    <div class="flex" style="margin-bottom:12px;">
      <select id="resolvedFilter"><option value="">All</option><option value="0">Unresolved</option><option value="1">Understood</option></select>
    </div>
    <div id="mistakeList" class="card"></div>
  `;
  makeChart("mistakeChart", {
    type: "bar",
    data: { labels: freq.map(f => f.mistake_type || "Unknown"), datasets: [{ data: freq.map(f => f.c), backgroundColor: "#e11d48" }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
  });
  document.getElementById("resolvedFilter").onchange = loadMistakes;
  await loadMistakes();
}

async function loadMistakes() {
  const resolved = document.getElementById("resolvedFilter").value;
  const mistakes = await API.get("/api/mistakes" + (resolved ? `?resolved=${resolved}` : ""));
  const el = document.getElementById("mistakeList");
  el.innerHTML = mistakes.slice(0, 60).map(m => `
    <div class="list-item">
      <span>
        <b>${esc(m.topic_name || "Unknown topic")}</b> - ${esc(m.mistake_type || "")}
        <div class="muted" style="font-size:11px;">${esc(m.test_name || "")} · Q${m.question_number || "-"}</div>
      </span>
      <span class="flex">
        <span class="badge ${m.resolved ? "Strong" : "High"}">${m.resolved ? "Understood" : "Unresolved"}</span>
        <button class="btn small secondary" data-resolve="${m.id}">${m.resolved ? "Mark Unresolved" : "Mark Understood"}</button>
      </span>
    </div>
  `).join("") || `<div class="empty-state">No mistakes logged - keep it up!</div>`;

  el.querySelectorAll("[data-resolve]").forEach(b => b.onclick = async () => {
    const m = mistakes.find(x => x.id == b.dataset.resolve);
    await API.put(`/api/mistakes/${m.id}`, { resolved: m.resolved ? 0 : 1 });
    loadMistakes();
  });
}

/* ==================================================================
   REVISION MANAGER
   ================================================================== */
async function renderRevision(el) {
  const r = await API.get("/api/revision");
  el.innerHTML = `
    <h1 class="page-title">Revision Manager</h1>
    <p class="page-sub">Automatic spaced-revision schedule: Day 1, 3, 7, 14, 30, 60 after completing a topic.</p>
    <div class="grid grid-2">
      <div class="card">
        <div class="section-title" style="margin-top:0;">Overdue</div>
        ${r.overdue.map(x => revisionRow(x)).join("") || `<div class="empty-state">Nothing overdue.</div>`}
      </div>
      <div class="card">
        <div class="section-title" style="margin-top:0;">Due Today</div>
        ${r.due_today.map(x => revisionRow(x)).join("") || `<div class="empty-state">Nothing due today.</div>`}
      </div>
    </div>
    <div class="section-title">Upcoming</div>
    <div class="card">${r.upcoming.map(x => revisionRow(x, true)).join("") || `<div class="empty-state">No upcoming revisions scheduled.</div>`}</div>
  `;
  el.querySelectorAll("[data-done]").forEach(b => b.onclick = async () => {
    await API.put(`/api/revision/${b.dataset.done}`, { status: "Done" });
    toast("Marked done");
    renderRevision(el);
  });
}
function revisionRow(x, hideAction) {
  return `<div class="list-item"><span>${esc(x.topic_name)} <span class="muted" style="font-size:11px;">(${x.stage})</span></span><span class="flex"><span class="pill">${fmtDate(x.revision_date)}</span>${hideAction ? "" : `<button class="btn small secondary" data-done="${x.id}">Mark Done</button>`}</span></div>`;
}

/* ==================================================================
   STATISTICS
   ================================================================== */
async function renderStatistics(el) {
  const s = await API.get("/api/statistics");
  el.innerHTML = `
    <h1 class="page-title">Progress Statistics</h1>
    <div class="section-title" style="margin-top:0;">Study Statistics</div>
    <div class="grid grid-4">
      ${statCard("Total Hours", s.study.total_hours, "")}
      ${statCard("Weekly Avg", s.study.weekly_average_hours + "h/day", "")}
      ${statCard("Current Streak", s.study.current_streak + " days", "longest: " + s.study.longest_streak)}
      ${statCard("Monthly Avg", s.study.monthly_average_hours + "h/day", "")}
    </div>
    <div class="section-title">Test Statistics</div>
    <div class="grid grid-4">
      ${statCard("Tests Attempted", s.tests.attempted, "")}
      ${statCard("Average Score", s.tests.average_score, "best: " + s.tests.best_score)}
      ${statCard("Average Accuracy", s.tests.average_accuracy + "%", "")}
      ${statCard("Average Speed", s.tests.average_speed_seconds + "s", "per question")}
    </div>
    <div class="grid grid-2" style="margin-top:16px;">
      ${statCard("Prelims Average", s.tests.prelims_average, "")}
      ${statCard("Mains Average", s.tests.mains_average, "")}
    </div>
    <div class="section-title">Subject-wise Statistics</div>
    <div class="card">
      <table class="data-table">
        <thead><tr><th>Subject</th><th>Accuracy</th><th>Score</th><th>Attempted</th><th>Correct</th><th>Incorrect</th><th>Avg Time</th></tr></thead>
        <tbody>${s.subjects.map(x => `<tr><td>${esc(x.subject)}</td><td>${x.accuracy}%</td><td>${x.score}</td><td>${x.attempted}</td><td>${x.correct}</td><td>${x.incorrect}</td><td>${x.average_time_seconds}s</td></tr>`).join("")}</tbody>
      </table>
    </div>
  `;
}

/* ==================================================================
   CURRENT AFFAIRS
   ================================================================== */
const CA_CATEGORIES = ["National","International","Banking","Economy","Government Schemes","Appointments","Awards","Sports","Science & Technology","Defence","Space","Environment","Important Days","Books & Authors","Reports & Indexes","Summits","Important Organizations"];

async function renderCurrentAffairs(el) {
  el.innerHTML = `
    <div class="section-title" style="margin-top:0;">
      <h1 class="page-title" style="margin:0;">Current Affairs</h1>
      <button class="btn" id="addCaBtn">+ New Entry</button>
    </div>
    <select id="caCategoryFilter" style="max-width:220px;margin-bottom:14px;"><option value="">All categories</option>${CA_CATEGORIES.map(c => `<option>${c}</option>`).join("")}</select>
    <div id="caList" class="card"></div>
  `;
  document.getElementById("addCaBtn").onclick = () => openCaModal();
  document.getElementById("caCategoryFilter").onchange = loadCa;
  await loadCa();
}
async function loadCa() {
  const cat = document.getElementById("caCategoryFilter").value;
  const rows = await API.get("/api/current-affairs" + (cat ? `?category=${encodeURIComponent(cat)}` : ""));
  document.getElementById("caList").innerHTML = rows.map(r => `
    <div class="list-item">
      <span><b>${esc(r.title)}</b><div class="muted" style="font-size:11px;">${esc(r.category)} · ${fmtDate(r.date)}</div></span>
      <button class="btn small danger" data-del="${r.id}">Delete</button>
    </div>
  `).join("") || `<div class="empty-state">No current affairs entries yet.</div>`;
  document.querySelectorAll("#caList [data-del]").forEach(b => b.onclick = async () => { await API.del(`/api/current-affairs/${b.dataset.del}`); loadCa(); });
}
function openCaModal() {
  openModal("New Current Affairs Entry", `
    <div class="form-grid">
      <div style="grid-column:1/-1;"><label>Title</label><input name="title" required></div>
      <div><label>Category</label><select name="category">${CA_CATEGORIES.map(c => `<option>${c}</option>`).join("")}</select></div>
      <div><label>Date</label><input type="date" name="date" value="${new Date().toISOString().slice(0, 10)}"></div>
      <div style="grid-column:1/-1;"><label>Content</label><textarea name="content"></textarea></div>
      <div><label>Tags</label><input name="tags"></div>
    </div>
  `, async (data) => { await API.post("/api/current-affairs", data); toast("Saved"); loadCa(); }, "Save");
}

/* ==================================================================
   REPORTS
   ================================================================== */
async function renderReports(el) {
  el.innerHTML = `
    <h1 class="page-title">Reports</h1>
    <div class="tabs"><button class="tab-btn active" data-r="weekly">Weekly Report</button><button class="tab-btn" data-r="monthly">Monthly Report</button></div>
    <div id="reportBody" class="card"></div>
  `;
  el.querySelectorAll(".tab-btn").forEach(b => b.onclick = () => { el.querySelectorAll(".tab-btn").forEach(x => x.classList.remove("active")); b.classList.add("active"); loadReport(b.dataset.r); });
  await loadReport("weekly");
}
async function loadReport(period) {
  const r = await API.get(`/api/reports/${period}`);
  const body = document.getElementById("reportBody");
  if (period === "weekly") {
    body.innerHTML = `
      <p><b>Study Hours:</b> ${r.study_hours}</p>
      <p><b>Questions Solved:</b> ${r.questions_solved}</p>
      <p><b>Tests Taken:</b> ${r.tests_taken}</p>
      <p><b>Average Accuracy:</b> ${r.average_accuracy}%</p>
      <p><b>Best Subject:</b> ${esc(r.best_subject)}</p>
      <p><b>Weakest Subject:</b> ${esc(r.weakest_subject)}</p>
      <p><b>Top Weak Topics:</b> ${(r.top_weak_topics || []).map(esc).join(", ") || "N/A"}</p>
      <p><b>Most Common Mistake:</b> ${esc(r.most_common_mistake)}</p>
      <p><b>Recommendation:</b> ${esc(r.recommendation)}</p>
    `;
  } else {
    body.innerHTML = `<p><b>Study Hours:</b> ${r.study_hours}</p><p><b>Questions Solved:</b> ${r.questions_solved}</p><p><b>Tests Taken:</b> ${r.tests_taken}</p>`;
  }
}

/* ==================================================================
   SETTINGS / DATA MANAGEMENT
   ================================================================== */
async function renderSettings(el) {
  const settings = await API.get("/api/settings");
  el.innerHTML = `
    <h1 class="page-title">Settings & Data Management</h1>
    <div class="section-title" style="margin-top:0;">Study Preferences</div>
    <div class="card">
      <div class="form-grid">
        <div><label>Daily Study Minutes</label><input id="setMinutes" type="number" value="${settings.daily_study_minutes || 90}"></div>
        <div><label>Study Start Time</label><input id="setStart" type="time" value="${settings.study_start_time || "18:00"}"></div>
        <div><label>Target Exam</label><select id="setExam">
          ${["SBI PO","SBI Clerk","IBPS PO","IBPS Clerk","IBPS RRB PO","IBPS RRB Clerk"].map(e => `<option ${e === settings.target_exam ? "selected" : ""}>${e}</option>`).join("")}
        </select></div>
      </div>
      <button class="btn" id="saveSettingsBtn" style="margin-top:12px;">Save Preferences</button>
    </div>

    <div class="section-title">Data Export</div>
    <div class="card">
      <p class="muted">Download any table as CSV for backup or analysis in Excel/Sheets.</p>
      <div class="flex" style="flex-wrap:wrap;">
        ${["notes","tasks","study_sessions","tests","test_questions","mistakes","topics","revision_schedule"].map(t => `<a class="btn small secondary" href="/api/export/${t}" download>${t}.csv</a>`).join("")}
      </div>
    </div>

    <div class="section-title">Backup & Restore</div>
    <div class="card">
      <p class="muted">Download a full database backup file (.db). Keep it safe - you can replace <code>data/bankprep.db</code> with it to restore.</p>
      <a class="btn secondary" href="/api/backup" download>Download Full Backup</a>
    </div>

    <div class="section-title">Danger Zone</div>
    <div class="card">
      <p class="muted">These actions cannot be undone. A confirmation is required.</p>
      <button class="btn danger" id="wipeBtn">Wipe All My Data (keep syllabus)</button>
      <button class="btn ghost" id="reseedBtn">Reset to Demo Data</button>
    </div>
  `;
  document.getElementById("saveSettingsBtn").onclick = async () => {
    await API.put("/api/settings", {
      daily_study_minutes: document.getElementById("setMinutes").value,
      study_start_time: document.getElementById("setStart").value,
      target_exam: document.getElementById("setExam").value,
    });
    toast("Settings saved");
  };
  document.getElementById("wipeBtn").onclick = async () => {
    if (confirm("This will permanently delete ALL your notes, tasks, tests, and progress. Continue?")) {
      if (confirm("Are you absolutely sure? This cannot be undone.")) {
        await API.post("/api/data/wipe");
        toast("All data wiped");
        location.reload();
      }
    }
  };
  document.getElementById("reseedBtn").onclick = async () => {
    if (confirm("This will replace all data with fresh demo data. Continue?")) {
      await API.post("/api/data/reset-demo");
      toast("Demo data restored");
      location.reload();
    }
  };
}

/* ------------------------------------------------------------------ */
/* Init                                                                 */
/* ------------------------------------------------------------------ */
(async function init() {
  try {
    const settings = await API.get("/api/settings");
    document.getElementById("modeSelect").value = settings.mode || "Preparation";
  } catch (e) {}
  document.getElementById("modeSelect").onchange = async (e) => {
    await API.put("/api/settings", { mode: e.target.value });
    toast(`Switched to ${e.target.value} Mode`);
  };
  navigate("dashboard");
})();
// Shared helpers for pages after login

// Create an element with safe text (textContent prevents XSS)
function make(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined && text !== null) el.textContent = text;
  if (className) el.className = className;
  return el;
}

// Handles common errors. Redirects to login if the student is not logged in.
function handleError(err, box) {
  if (err.status === 401) { window.location.href = "/login.html"; return; }
  if (box) showError(box, err);
}

var DIFFICULTY_NAMES = { 1: "Easy", 2: "Medium", 3: "Hard" };
var STATUS_LABELS = { "new": "Not started", weak: "Weak", average: "Average", strong: "Strong" };
var ACTION_LABELS = { revise: "Revise", learn: "Learn", quiz: "Quiz" };

// Coloured label such as "Weak" or "Strong"
function statusBadge(status) {
  return make("span", STATUS_LABELS[status] || status, "badge badge-" + status);
}

// Colour class for a percentage bar
function pctClass(percent) {
  if (percent < 50) return "low";
  if (percent < 80) return "mid";
  return "high";
}

// One horizontal bar: label, coloured bar, percentage
function barRow(label, percent) {
  const row = make("div", null, "bar-row");
  row.appendChild(make("div", label, "bar-label"));
  const track = make("div", null, "bar-track");
  const fill = make("div", null, "bar-fill " + pctClass(percent));
  fill.style.width = percent + "%";
  track.appendChild(fill);
  row.appendChild(track);
  row.appendChild(make("div", percent + "%", "bar-value"));
  return row;
}

// Fills a <ul> with recommendation items (each links to the topic page)
function renderRecommendations(listEl, recs) {
  recs.forEach(function (r) {
    const li = make("li", null, "rec-item");
    li.appendChild(make("span", ACTION_LABELS[r.action_type] || r.action_type, "badge badge-action"));
    const link = make("a", r.message);
    link.href = "/topic.html?id=" + r.topic_id;
    li.appendChild(link);
    listEl.appendChild(li);
  });
}

// Build the navigation bar on every page that has a .nav-links container
document.addEventListener("DOMContentLoaded", function () {
  const nav = document.querySelector(".nav-links");
  if (!nav) return;
  nav.innerHTML = "";
  [["Dashboard", "/dashboard.html"], ["Subjects", "/subjects.html"],
   ["AI Tutor", "/tutor.html"], ["Progress", "/progress.html"], ["Recommendations", "/recommendations.html"]
  ].forEach(function (item) {
    const a = make("a", item[0]);
    a.href = item[1];
    nav.appendChild(a);
  });
  const btn = make("button", "Logout", "btn btn-outline");
  btn.id = "logout-btn";
  btn.addEventListener("click", async function () {
    try { await api("/auth/logout", { method: "POST" }); } catch (e) {}
    window.location.href = "/";
  });
  nav.appendChild(btn);
});
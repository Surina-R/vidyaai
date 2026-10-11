function statBox(number, label) {
  const box = make("div", null, "stat");
  box.appendChild(make("div", number, "num"));
  box.appendChild(make("div", label, "muted"));
  return box;
}

function fillTopicList(listId, emptyId, topics) {
  const list = document.getElementById(listId);
  if (topics.length === 0) { document.getElementById(emptyId).classList.remove("hidden"); return; }
  topics.forEach(function (t) {
    const li = make("li");
    const link = make("a", t.name);
    link.href = "/topic.html?id=" + t.id;
    li.appendChild(link);
    li.appendChild(make("span", "  recent accuracy " + t.accuracy + "%", "muted"));
    list.appendChild(li);
  });
}

async function init() {
  const errorBox = document.getElementById("error");
  let me;
  try {
    me = await api("/auth/me");
  } catch (err) {
    if (err.status === 401) { window.location.href = "/login.html"; return; }
    document.getElementById("welcome").textContent = err.message;
    return;
  }

  document.getElementById("welcome").textContent = "Welcome, " + me.user.name;

  if (me.user.role === "teacher") {
    document.getElementById("teacher-note").classList.remove("hidden");
    return;
  }

  document.getElementById("student-area").classList.remove("hidden");
  document.getElementById("profile-line").textContent =
    "Class: " + me.profile.grade + "  •  School: " + (me.profile.school || "-");

  try {
    const d = await api("/student/dashboard");
    const s = d.stats;

    const stats = document.getElementById("stats");
    stats.appendChild(statBox(s.quizzes, "Quizzes taken"));
    stats.appendChild(statBox(s.questions, "Questions answered"));
    stats.appendChild(statBox(s.accuracy + "%", "Overall accuracy"));
    stats.appendChild(statBox(s.topics_strong + " / " + s.topics_total, "Topics mastered"));
    document.getElementById("mastery-text").textContent =
      "Mastery: " + s.mastery_percent + "% of your topics are strong";
    document.getElementById("mastery-bar").style.width = s.mastery_percent + "%";

    if (d.recommendations.length === 0) document.getElementById("rec-empty").classList.remove("hidden");
    renderRecommendations(document.getElementById("rec-list"), d.recommendations);

    fillTopicList("weak-list", "weak-empty", d.weak);
    fillTopicList("strong-list", "strong-empty", d.strong);
  } catch (err) {
    handleError(err, errorBox);
  }

  // Recent quiz activity
  try {
    const data = await api("/quiz/history");
    const list = document.getElementById("recent");
    if (data.attempts.length === 0) document.getElementById("recent-empty").classList.remove("hidden");
    data.attempts.forEach(function (a) {
      const li = make("li");
      const link = make("a", a.topic_name);
      link.href = "/results.html?attempt=" + a.id;
      li.appendChild(link);
      li.appendChild(make("span",
        "  —  " + a.score + "/" + a.total_questions + " (" + DIFFICULTY_NAMES[a.difficulty] + ")  •  " + a.completed_at,
        "muted"));
      list.appendChild(li);
    });
  } catch (err) { /* the dashboard still works without history */ }
}

init();
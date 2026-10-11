const errorBox = document.getElementById("error");

function addCell(row, text) {
  row.appendChild(make("td", String(text)));
}

async function init() {
  try {
    const me = await api("/auth/me");
    if (me.user.role !== "student") {
      errorBox.textContent = "This page is for students.";
      errorBox.classList.remove("hidden");
      return;
    }
    const data = await api("/student/progress");

    // Topic table
    const tbody = document.getElementById("topic-rows");
    data.topics.forEach(function (t) {
      const tr = document.createElement("tr");
      const nameCell = document.createElement("td");
      const link = make("a", t.name);
      link.href = "/topic.html?id=" + t.id;
      nameCell.appendChild(link);
      tr.appendChild(nameCell);
      addCell(tr, t.subject_name);
      const statusCell = document.createElement("td");
      statusCell.appendChild(statusBadge(t.status));
      tr.appendChild(statusCell);
      addCell(tr, t.attempts);
      addCell(tr, t.attempts ? t.correct_answers + " / " + t.questions_answered : "-");
      addCell(tr, t.attempts ? t.accuracy + "%" : "-");
      addCell(tr, DIFFICULTY_NAMES[t.difficulty]);
      tbody.appendChild(tr);
    });

    // Improvement per topic
    const list = document.getElementById("improvement");
    if (data.improvement.length === 0) document.getElementById("improvement-empty").classList.remove("hidden");
    data.improvement.forEach(function (i) {
      const li = make("li");
      li.appendChild(make("strong", i.topic_name));
      const sign = i.change > 0 ? "+" : "";
      li.appendChild(make("span", "   " + i.first + "% → " + i.latest + "%   (" + sign + i.change + " points, " + i.attempts + " quizzes)",
        i.change > 0 ? "ok-text" : (i.change < 0 ? "bad-text" : "muted")));
      list.appendChild(li);
    });

    // Score history as bars
    const timeline = document.getElementById("timeline");
    if (data.timeline.length === 0) document.getElementById("timeline-empty").classList.remove("hidden");
    data.timeline.forEach(function (a) {
      timeline.appendChild(barRow(a.topic_name + " (" + DIFFICULTY_NAMES[a.difficulty] + ")", a.percent));
    });
  } catch (err) {
    handleError(err, errorBox);
  }
}

init();
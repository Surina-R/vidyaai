const topicId = new URLSearchParams(window.location.search).get("id");
const errorBox = document.getElementById("error");

async function init() {
  if (!topicId) { window.location.href = "/subjects.html"; return; }
  try {
    const data = await api("/quiz/topic/" + encodeURIComponent(topicId));
    const perf = data.performance;

    document.getElementById("topic-name").textContent = data.topic.name;
    document.getElementById("subject-name").textContent = data.topic.subject_name;
    document.getElementById("content").classList.remove("hidden");

    if (data.prerequisite) {
      const box = document.getElementById("prereq");
      box.textContent = "Tip: this topic is easier if you know \"" + data.prerequisite.name + "\" first.";
      box.classList.remove("hidden");
    }

    // Student's current level in this topic (comes from their quiz history)
    const statusLine = make("p");
    statusLine.appendChild(document.createTextNode("Your level in this topic: "));
    statusLine.appendChild(statusBadge(perf.status));
    if (perf.attempts > 0) {
      statusLine.appendChild(make("span", "  recent accuracy " + perf.accuracy + "%", "muted"));
    }
    const info = document.getElementById("quiz-info");
    info.parentNode.insertBefore(statusLine, info);
    info.textContent = "Each quiz has up to " + data.questions_per_quiz + " questions. Choose a difficulty:";

    // Difficulty options. "auto" is the adaptive one and is selected by default.
    const box = document.getElementById("difficulty-options");
    const choices = [["auto", "Recommended for you: " + DIFFICULTY_NAMES[perf.recommended_difficulty] +
                              " (adapts to your performance)"]];
    [1, 2, 3].forEach(function (d) {
      choices.push([String(d), DIFFICULTY_NAMES[d] + "  (" + data.question_counts[String(d)] + " questions available)"]);
    });
    choices.forEach(function (c, index) {
      const label = make("label", null, "option");
      const radio = document.createElement("input");
      radio.type = "radio"; radio.name = "difficulty"; radio.value = c[0];
      if (index === 0) radio.checked = true;
      label.appendChild(radio);
      label.appendChild(make("span", c[1]));
      box.appendChild(label);
    });

    // Previous attempts
    const list = document.getElementById("attempts");
    if (data.attempts.length === 0) document.getElementById("no-attempts").classList.remove("hidden");
    data.attempts.forEach(function (a) {
      const li = make("li");
      const link = make("a", a.score + "/" + a.total_questions + " (" + DIFFICULTY_NAMES[a.difficulty] + ")");
      link.href = "/results.html?attempt=" + a.id;
      li.appendChild(link);
      li.appendChild(make("span", "  •  " + a.completed_at, "muted"));
      list.appendChild(li);
    });
  } catch (err) {
    handleError(err, errorBox);
  }
}

document.getElementById("start-btn").addEventListener("click", async function () {
  const button = this;
  errorBox.classList.add("hidden");
  const chosen = document.querySelector("input[name=difficulty]:checked");
  if (!chosen) return;
  button.disabled = true;
  button.textContent = "Preparing your quiz...";      // for weak topics the AI may create new questions
  try {
    const data = await api("/quiz/start", {
      method: "POST",
      body: {
        topic_id: Number(topicId),
        difficulty: chosen.value === "auto" ? "auto" : Number(chosen.value)
      }
    });
    window.location.href = "/quiz.html?attempt=" + data.attempt_id + (data.ai_added ? "&ai=" + data.ai_added : "");
  } catch (err) {
    handleError(err, errorBox);
    button.disabled = false;
    button.textContent = "Start quiz";
  }
});

init();
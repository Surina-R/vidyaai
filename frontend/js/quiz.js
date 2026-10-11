const attemptId = new URLSearchParams(window.location.search).get("attempt");
const errorBox = document.getElementById("error");
let QUESTIONS = [];

function updateProgress() {
  const answered = document.querySelectorAll("input[type=radio]:checked").length;
  document.getElementById("answered-text").textContent = "Answered " + answered + " of " + QUESTIONS.length;
  document.getElementById("bar").style.width = (QUESTIONS.length ? (answered / QUESTIONS.length) * 100 : 0) + "%";
}

function renderQuestions() {
  const box = document.getElementById("questions");
  QUESTIONS.forEach(function (q, index) {
    const card = make("div", null, "card");
    card.appendChild(make("h3", "Q" + (index + 1) + ". " + q.text));
    ["A", "B", "C", "D"].forEach(function (letter) {
      const label = make("label", null, "option");
      const radio = document.createElement("input");
      radio.type = "radio"; radio.name = "q" + q.id; radio.value = letter;
      radio.addEventListener("change", updateProgress);
      label.appendChild(radio);
      label.appendChild(make("span", letter + ")  " + q.options[letter]));
      card.appendChild(label);
    });
    box.appendChild(card);
  });
  updateProgress();
}

async function init() {
  if (!attemptId) { window.location.href = "/subjects.html"; return; }
  try {
    const data = await api("/quiz/" + encodeURIComponent(attemptId));
    if (data.completed) {                  // already submitted, so show the results instead
      window.location.href = "/results.html?attempt=" + attemptId;
      return;
    }
    document.getElementById("quiz-title").textContent = data.topic_name + " Quiz";
    document.getElementById("quiz-sub").textContent = "Difficulty: " + DIFFICULTY_NAMES[data.difficulty];
        const aiCount = Number(new URLSearchParams(window.location.search).get("ai")) || 0;
    if (aiCount > 0) {
      document.getElementById("quiz-sub").textContent +=
        "  •  " + aiCount + " new question(s) created by AI for your weak areas";
    }
    QUESTIONS = data.questions;
    renderQuestions();
    document.getElementById("quiz-area").classList.remove("hidden");
  } catch (err) {
    handleError(err, errorBox);
  }
}

document.getElementById("submit-btn").addEventListener("click", async function () {
  const button = this;
  errorBox.classList.add("hidden");

  // Collect the chosen options: { "questionId": "B", ... }
  const answers = {};
  QUESTIONS.forEach(function (q) {
    const chosen = document.querySelector("input[name=q" + q.id + "]:checked");
    if (chosen) answers[q.id] = chosen.value;
  });

  const answered = Object.keys(answers).length;
  if (answered < QUESTIONS.length && !confirm("You have not answered all questions. Submit anyway?")) return;

  button.disabled = true;
  try {
    await api("/quiz/" + encodeURIComponent(attemptId) + "/submit", { method: "POST", body: { answers: answers } });
    window.location.href = "/results.html?attempt=" + attemptId;
  } catch (err) {
    handleError(err, errorBox);
    button.disabled = false;
  }
});

init();
const attemptId = new URLSearchParams(window.location.search).get("attempt");
const errorBox = document.getElementById("error");

function messageFor(percent) {
  if (percent >= 80) return "Great work! You understand this topic well.";
  if (percent >= 50) return "Good effort. Read the explanations below and try again.";
  return "This topic needs more practice. Read the explanations carefully.";
}

async function init() {
  if (!attemptId) { window.location.href = "/subjects.html"; return; }
  try {
    const r = await api("/quiz/" + encodeURIComponent(attemptId) + "/result");
    const percent = r.total ? Math.round((r.score / r.total) * 100) : 0;

    document.getElementById("result-topic").textContent = r.topic_name + " (" + DIFFICULTY_NAMES[r.difficulty] + ")";
    document.getElementById("result-score").textContent = r.score + " / " + r.total + "  (" + percent + "%)";
    document.getElementById("result-message").textContent = messageFor(percent);
    document.getElementById("retry-btn").href = "/topic.html?id=" + r.topic_id;
        // Link to the AI tutor, opened on this topic and asking it to explain the student's mistakes
    const retry = document.getElementById("retry-btn");
    const tutorLink = make("a", "Explain my mistakes with AI", "btn btn-outline");
    tutorLink.href = "/tutor.html?topic=" + r.topic_id + "&mistakes=1";
    retry.parentNode.insertBefore(tutorLink, retry.nextSibling);

    // ---- Answer review ----
    const box = document.getElementById("answers");
    r.answers.forEach(function (a, index) {
      const card = make("div", null, "card answer " + (a.is_correct ? "correct" : "wrong"));
      card.appendChild(make("h3", "Q" + (index + 1) + ". " + a.text));

      if (a.is_correct) {
        card.appendChild(make("p", "Correct: " + a.correct + ")  " + a.options[a.correct], "ok-text"));
      } else {
        const yours = a.selected ? a.selected + ")  " + a.options[a.selected] : "(not answered)";
        card.appendChild(make("p", "Your answer: " + yours, "bad-text"));
        card.appendChild(make("p", "Correct answer: " + a.correct + ")  " + a.options[a.correct], "ok-text"));
        if (a.explanation) {
          const ex = make("div", null, "explain");
          ex.appendChild(make("strong", "Why? "));
          ex.appendChild(document.createTextNode(a.explanation));
          card.appendChild(ex);
        }
      }
      box.appendChild(card);
    });

    // ---- Feedback-loop cards, placed above the answer review ----
    const heading = box.previousElementSibling;       // the "Review your answers" heading

    const progressCard = make("div", null, "card");
    progressCard.appendChild(make("h2", "Your progress on this topic"));
    const levelLine = make("p");
    levelLine.appendChild(document.createTextNode("Current level: "));
    levelLine.appendChild(statusBadge(r.performance.status));
    levelLine.appendChild(make("span",
      "  recent accuracy " + r.performance.accuracy + "%  •  next quiz level: " +
      DIFFICULTY_NAMES[r.performance.recommended_difficulty], "muted"));
    progressCard.appendChild(levelLine);

    if (r.previous) {
      const prevPercent = r.previous.total ? Math.round((r.previous.score / r.previous.total) * 100) : 0;
      const diff = percent - prevPercent;
      let text, cls;
      if (diff > 0) {
        text = "Improved! " + prevPercent + "% → " + percent + "% (+" + diff + " points compared with your previous quiz)";
        cls = "ok-text";
      } else if (diff < 0) {
        text = "Lower than your previous quiz (" + prevPercent + "% → " + percent + "%). Read the explanations and try again.";
        cls = "bad-text";
      } else {
        text = "Same as your previous quiz (" + percent + "%).";
        cls = "muted";
      }
      progressCard.appendChild(make("p", text, cls));
    } else {
      progressCard.appendChild(make("p", "This is your first quiz on this topic.", "muted"));
    }
    box.parentNode.insertBefore(progressCard, heading);

    const nextCard = make("div", null, "card");
    nextCard.appendChild(make("h2", "What to do next"));
    const nextList = make("ul", null, "list");
    renderRecommendations(nextList, r.recommendations.slice(0, 4));
    nextCard.appendChild(nextList);
    box.parentNode.insertBefore(nextCard, heading);

    document.getElementById("result-area").classList.remove("hidden");
  } catch (err) {
    handleError(err, errorBox);
  }
}

init();
const errorBox = document.getElementById("error");
const chat = document.getElementById("chat");
const select = document.getElementById("topic-select");
const sendBtn = document.getElementById("send-btn");
const mistakesBtn = document.getElementById("mistakes-btn");
const input = document.getElementById("message");

let HISTORY = [];      // earlier messages, so the AI can answer follow-up questions
let BUSY = false;

function selectedTopic() { return select.value ? Number(select.value) : null; }

function refreshButtons() {
  sendBtn.disabled = BUSY;
  mistakesBtn.disabled = BUSY || !selectedTopic();
}

function addMessage(role, text, note) {
  const box = make("div", null, "msg " + (role === "user" ? "user" : "bot"));
  box.appendChild(make("div", text));
  if (note) box.appendChild(make("div", note, "msg-note muted"));
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
  return box;
}

function noteFor(data) {
  return data.source === "ai" ? "Answered by AI (needs internet)" : data.note;
}

// Sends a request to the backend and shows the answer
async function talk(shownText, path, body) {
  if (BUSY) return;
  errorBox.classList.add("hidden");
  addMessage("user", shownText);
  const waiting = addMessage("bot", "Thinking...");
  BUSY = true; refreshButtons();
  try {
    const data = await api(path, { method: "POST", body: body });
    waiting.remove();
    addMessage("bot", data.reply, noteFor(data));
    if (data.source === "ai") {
      HISTORY.push({ role: "user", text: shownText }, { role: "assistant", text: data.reply });
    }
  } catch (err) {
    waiting.remove();
    handleError(err, errorBox);
  }
  BUSY = false; refreshButtons();
}

function sendQuestion() {
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  talk(message, "/ai/tutor", { topic_id: selectedTopic(), message: message, history: HISTORY.slice(-6) });
}

function explainMistakes() {
  talk("Explain my mistakes in this topic.", "/ai/explain-mistakes", { topic_id: selectedTopic() });
}

// Shows the student's level for the chosen topic (this data comes from their quiz history)
async function showLevel() {
  const line = document.getElementById("level-line");
  line.textContent = "";
  refreshButtons();
  const id = selectedTopic();
  if (!id) return;
  try {
    const d = await api("/quiz/topic/" + id);
    line.appendChild(document.createTextNode("Your level in this topic: "));
    line.appendChild(statusBadge(d.performance.status));
    if (d.performance.attempts > 0) {
      line.appendChild(make("span", "  recent accuracy " + d.performance.accuracy + "%"));
    }
  } catch (e) { /* the tutor still works without this line */ }
}

async function init() {
  try {
    const me = await api("/auth/me");
    if (me.user.role !== "student") {
      errorBox.textContent = "This page is for students.";
      errorBox.classList.remove("hidden");
      return;
    }
    const meta = await api("/meta");
    const status = await api("/ai/status");

    document.getElementById("ai-status").textContent = status.configured
      ? "AI tutor is online (needs internet). If it cannot be reached, built-in notes are shown instead."
      : "AI key not set: showing built-in notes only. Add GEMINI_API_KEY in backend/.env to turn the AI on.";

    // Topic dropdown, grouped by subject
    meta.subjects
      .filter(function (s) { return me.subject_ids.indexOf(s.id) !== -1; })
      .forEach(function (s) {
        const group = document.createElement("optgroup");
        group.label = s.name;
        s.topics.filter(function (tp) { return tp.grade_min <= me.profile.grade; }).forEach(function (tp) {
          const o = document.createElement("option");
          o.value = tp.id; o.textContent = tp.name;
          group.appendChild(o);
        });
        select.appendChild(group);
      });

    const params = new URLSearchParams(window.location.search);
    if (params.get("topic")) select.value = params.get("topic");

    addMessage("bot", "Hi! Choose a topic and ask me anything about it. I can also explain the mistakes you made in your quizzes.");
    await showLevel();
    if (params.get("mistakes") && selectedTopic()) explainMistakes();
  } catch (err) {
    handleError(err, errorBox);
  }
}

select.addEventListener("change", showLevel);
sendBtn.addEventListener("click", sendQuestion);
mistakesBtn.addEventListener("click", explainMistakes);
input.addEventListener("keydown", function (e) { if (e.key === "Enter") sendQuestion(); });

init();
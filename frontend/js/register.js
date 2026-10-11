function byId(id) { return document.getElementById(id); }

async function init() {
  // Load grades and subjects from the backend
  let meta;
  try {
    meta = await api("/meta");
  } catch (err) {
    showError(byId("form-error"), err);
    return;
  }

  meta.grades.forEach(function (g) {
    const o = document.createElement("option");
    o.value = g; o.textContent = g;
    byId("grade").appendChild(o);
  });

  const box = byId("subjects");
  meta.subjects.forEach(function (s) {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.name = "subject"; cb.value = s.id;
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + s.name));
    box.appendChild(label);
  });
}

byId("register-form").addEventListener("submit", async function (e) {
  e.preventDefault();
  const errorBox = byId("form-error");
  const button = byId("submit-btn");
  errorBox.classList.add("hidden");

  const subjects = Array.from(document.querySelectorAll("input[name=subject]:checked"))
    .map(function (cb) { return Number(cb.value); });

  button.disabled = true;
  try {
    await api("/auth/register", {
      method: "POST",
      body: {
        name: byId("name").value,
        email: byId("email").value,
        password: byId("password").value,
        grade: Number(byId("grade").value),
        school: byId("school").value,
        subjects: subjects
      }
    });
    window.location.href = "/dashboard.html";   // registration also logs the student in
  } catch (err) {
    showError(errorBox, err);
    button.disabled = false;
  }
});

init();
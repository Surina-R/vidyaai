async function init() {
  const errorBox = document.getElementById("error");
  try {
    const me = await api("/auth/me");
    if (me.user.role !== "student") {
      errorBox.textContent = "This page is for students.";
      errorBox.classList.remove("hidden");
      return;
    }
    const meta = await api("/meta");

    const container = document.getElementById("subjects");
    meta.subjects
      .filter(function (s) { return me.subject_ids.indexOf(s.id) !== -1; })
      .forEach(function (s) {
        const card = make("div", null, "card");
        card.appendChild(make("h2", s.name));
        const list = make("div", null, "topic-list");
        s.topics
          .filter(function (tp) { return tp.grade_min <= me.profile.grade; })
          .forEach(function (tp) {
            const link = make("a", tp.name, "tag");
            link.href = "/topic.html?id=" + tp.id;
            list.appendChild(link);
          });
        card.appendChild(list);
        container.appendChild(card);
      });
  } catch (err) {
    handleError(err, errorBox);
  }
}

init();
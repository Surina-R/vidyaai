async function init() {
  const errorBox = document.getElementById("error");
  try {
    const me = await api("/auth/me");
    if (me.user.role !== "student") {
      errorBox.textContent = "This page is for students.";
      errorBox.classList.remove("hidden");
      return;
    }
    const data = await api("/student/recommendations");
    if (data.recommendations.length === 0) document.getElementById("rec-empty").classList.remove("hidden");
    renderRecommendations(document.getElementById("rec-list"), data.recommendations);
  } catch (err) {
    handleError(err, errorBox);
  }
}

init();
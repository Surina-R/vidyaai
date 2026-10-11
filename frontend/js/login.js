document.getElementById("login-form").addEventListener("submit", async function (e) {
  e.preventDefault();
  const errorBox = document.getElementById("form-error");
  const button = document.getElementById("submit-btn");
  errorBox.classList.add("hidden");
  button.disabled = true;

  try {
    await api("/auth/login", {
      method: "POST",
      body: {
        email: document.getElementById("email").value,
        password: document.getElementById("password").value
      }
    });
    window.location.href = "/dashboard.html";
  } catch (err) {
    showError(errorBox, err);
    button.disabled = false;
  }
});
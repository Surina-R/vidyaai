// One helper for talking to the backend. Every page uses it.
async function api(path, options) {
  options = options || {};
  const settings = {
    method: options.method || "GET",
    headers: {},
    credentials: "same-origin"          // send the login cookie
  };
  if (options.body) {
    settings.headers["Content-Type"] = "application/json";
    settings.body = JSON.stringify(options.body);
  }

  let response;
  try {
    response = await fetch("/api" + path, settings);
  } catch (e) {
    throw { code: "NETWORK", message: "Cannot reach the server. Check your connection.", status: 0 };
  }

  let data = {};
  try { data = await response.json(); } catch (e) { /* empty body */ }

  if (!response.ok) {
    throw { code: data.code || "ERROR", message: data.error || "Something went wrong.", status: response.status };
  }
  return data;
}

// Shows an error message in a box
function showError(box, err) {
  box.textContent = err.message;
  box.classList.remove("hidden");
}
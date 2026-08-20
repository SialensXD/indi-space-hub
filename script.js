const screens = {
  welcome: document.querySelector("#welcome-screen"),
  application: document.querySelector("#application-screen"),
  pending: document.querySelector("#pending-screen"),
  rejected: document.querySelector("#rejected-screen"),
  info: document.querySelector("#info-screen"),
};
const applicationKey = "indie-site-application-token";
const apiUrl = (document.querySelector('meta[name="site-api-url"]')?.content || "").replace(/\/$/, "");
let pollTimer;

function apiPath(path) {
  return `${apiUrl}${path}`;
}

async function readJson(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("API сайта не подключен к этой странице.");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Сервер не принял запрос.");
  return data;
}

function showScreen(name) {
  Object.values(screens).forEach((screen) => screen.classList.add("is-hidden"));
  screens[name].classList.remove("is-hidden");
}

function showFormMessage(message, isError = false) {
  const element = document.querySelector("#form-message");
  element.textContent = message;
  element.classList.toggle("error", isError);
}

async function checkStatus(token) {
  try {
    const response = await fetch(apiPath(`/api/applications/${encodeURIComponent(token)}`));
    if (response.status === 404) {
      localStorage.removeItem(applicationKey);
      showScreen("application");
      return;
    }
    const application = await readJson(response);
    if (application.status === "approved") {
      clearInterval(pollTimer);
      showScreen("info");
      loadStats();
    } else if (application.status === "rejected") {
      clearInterval(pollTimer);
      showScreen("rejected");
    } else {
      showScreen("pending");
    }
  } catch (error) {
    console.error("Не удалось проверить заявку", error);
  }
}

async function loadStats() {
  const table = document.querySelector("#top-table");
  try {
    const response = await fetch(apiPath("/api/stats"));
    const data = await readJson(response);
    table.innerHTML = data.top.length
      ? data.top.map((player, index) => `<tr><td>${index + 1}</td><td>@${player.username}</td><td>${player.messages}</td><td>${player.xp}</td><td>${player.wins}</td></tr>`).join("")
      : '<tr><td colspan="5">Пока нет статистики.</td></tr>';
  } catch (error) {
    table.innerHTML = `<tr><td colspan="5">${error.message}</td></tr>`;
  }
}

document.querySelector("#begin-button").addEventListener("click", () => showScreen("application"));
document.querySelector("#retry-button").addEventListener("click", () => showScreen("application"));
document.querySelector("#application-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  const username = document.querySelector("#username").value.trim().replace(/^@/, "");
  button.disabled = true;
  showFormMessage("Отправляем заявку...");
  try {
    const response = await fetch(apiPath("/api/apply"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await readJson(response);
    localStorage.setItem(applicationKey, data.token);
    checkStatus(data.token);
    pollTimer = setInterval(() => checkStatus(data.token), 5000);
  } catch (error) {
    showFormMessage(
      error.message === "Failed to fetch"
        ? "Не удалось связаться с сервером. Проверь URL backend и CORS."
        : error.message,
      true,
    );
    button.disabled = false;
  }
});

const savedToken = localStorage.getItem(applicationKey);
if (savedToken) checkStatus(savedToken);
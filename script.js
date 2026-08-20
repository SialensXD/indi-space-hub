const screens = {
  welcome: document.querySelector("#welcome-screen"),
  application: document.querySelector("#application-screen"),
  pending: document.querySelector("#pending-screen"),
  rejected: document.querySelector("#rejected-screen"),
  info: document.querySelector("#info-screen"),
};
const applicationKey = "indie-site-application-token";
let pollTimer;

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
    const response = await fetch(`/api/applications/${encodeURIComponent(token)}`);
    if (!response.ok) {
      localStorage.removeItem(applicationKey);
      showScreen("application");
      return;
    }
    const application = await response.json();
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
    const response = await fetch("/api/stats");
    const data = await response.json();
    table.innerHTML = data.top.length
      ? data.top.map((player, index) => `<tr><td>${index + 1}</td><td>@${player.username}</td><td>${player.messages}</td><td>${player.xp}</td><td>${player.wins}</td></tr>`).join("")
      : '<tr><td colspan="5">Пока нет статистики.</td></tr>';
  } catch (error) {
    table.innerHTML = '<tr><td colspan="5">Статистика временно недоступна.</td></tr>';
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
    const response = await fetch("/api/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Не удалось отправить заявку");
    localStorage.setItem(applicationKey, data.token);
    checkStatus(data.token);
    pollTimer = setInterval(() => checkStatus(data.token), 5000);
  } catch (error) {
    showFormMessage(error.message, true);
    button.disabled = false;
  }
});

const savedToken = localStorage.getItem(applicationKey);
if (savedToken) checkStatus(savedToken);
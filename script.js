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
      loadChangelog();
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
    if (data.top.length) {
      const medals = ["🥇", "🥈", "🥉"];
      table.innerHTML = data.top.map((player, index) => {
        const medal = medals[index] || `${index + 1}.`;
        const rank = index < 3 ? `data-rank="${index + 1}"` : "";
        return `<tr ${rank}><td class="rank-cell">${medal}</td><td class="player-cell">@${player.username}</td><td class="stat-cell">${player.messages}</td><td class="stat-cell">${player.xp}</td><td class="stat-cell">${player.wins}</td></tr>`;
      }).join("");
    } else {
      table.innerHTML = '<tr><td colspan="5">Пока нет статистики.</td></tr>';
    }
  } catch (error) {
    table.innerHTML = `<tr><td colspan="5">${error.message}</td></tr>`;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderChangelog(entries) {
  const feed = document.querySelector("#changelog-feed");
  if (!entries.length) {
    feed.innerHTML = '<p class="muted">Пока новостей нет.</p>';
    return;
  }

  const cards = entries.map((entry) => {
    const date = new Date(entry.published_at).toLocaleDateString("ru-RU");
    return `<article class="news-item"><time datetime="${escapeHtml(entry.published_at)}">${escapeHtml(date)}</time><div><h4>${escapeHtml(entry.title)}</h4><p>${escapeHtml(entry.body).replaceAll("\n", "<br>")}</p></div></article>`;
  }).join("");
  feed.innerHTML = `<div class="news-track">${cards}${cards}</div>`;
  feed.addEventListener("click", () => feed.classList.toggle("is-paused"), { once: false });
}

async function loadChangelog() {
  const feed = document.querySelector("#changelog-feed");
  try {
    const response = await fetch(apiPath("/api/changelog"));
    const data = await readJson(response);
    renderChangelog(data.entries);
  } catch (error) {
    feed.innerHTML = `<p class="muted">Не удалось загрузить чейнджлог: ${escapeHtml(error.message)}</p>`;
  }
}

function activateInfoTab(tab) {
  const tabs = document.querySelectorAll('[role="tab"]');
  const panels = document.querySelectorAll('[role="tabpanel"]');
  const panel = document.querySelector(`#${tab.getAttribute("aria-controls")}`);
  tabs.forEach((item) => {
    const isActive = item === tab;
    item.classList.toggle("is-active", isActive);
    item.setAttribute("aria-selected", isActive);
    item.tabIndex = isActive ? 0 : -1;
  });
  panels.forEach((item) => {
    item.hidden = item !== panel;
    item.classList.toggle("is-active", item === panel);
  });
}

document.querySelectorAll('[role="tab"]').forEach((tab, index, tabs) => {
  tab.addEventListener("click", () => activateInfoTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextTab = tabs[(index + direction + tabs.length) % tabs.length];
    activateInfoTab(nextTab);
    nextTab.focus();
  });
});

const rolesGrid = document.querySelector("#roles-grid");
const rolesBackdrop = document.querySelector("#roles-backdrop");

function closeRoleCard() {
  const openCard = rolesGrid?.querySelector(".role-card.is-open");
  if (!openCard) return;
  openCard.classList.remove("is-open");
  rolesGrid.classList.remove("has-open-card");
  rolesBackdrop.classList.remove("is-visible");
  rolesBackdrop.setAttribute("aria-hidden", "true");
}

function openRoleCard(card) {
  const currentCard = rolesGrid.querySelector(".role-card.is-open");
  if (currentCard === card) return;
  currentCard?.classList.remove("is-open");
  card.classList.add("is-open");
  rolesGrid.classList.add("has-open-card");
  rolesBackdrop.classList.add("is-visible");
  rolesBackdrop.setAttribute("aria-hidden", "false");
  card.querySelector(".role-close")?.focus();
}

rolesGrid?.addEventListener("click", (event) => {
  const closeButton = event.target.closest(".role-close");
  if (closeButton) {
    event.stopPropagation();
    closeRoleCard();
    return;
  }
  const card = event.target.closest(".role-card");
  if (card) openRoleCard(card);
});

rolesGrid?.addEventListener("keydown", (event) => {
  const card = event.target.closest(".role-card");
  if (!card || event.target.closest(".role-close")) return;
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openRoleCard(card);
  }
});

rolesBackdrop?.addEventListener("click", closeRoleCard);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeRoleCard();
});

document.querySelector("#begin-button").addEventListener("click", () => showScreen("application"));
document.querySelector("#retry-button").addEventListener("click", () => showScreen("application"));
document.querySelector("#application-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  const username = document.querySelector("#username").value.trim().replace(/^@/, "");
  const role = document.querySelector("#role").value.trim();
  button.disabled = true;
  showFormMessage("Отправляем заявку...");
  try {
    const response = await fetch(apiPath("/api/apply"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, role }),
    });
    const data = await readJson(response);
    localStorage.setItem(applicationKey, data.token);
    checkStatus(data.token);
    pollTimer = setInterval(() => checkStatus(data.token), 5000);
  } catch (error) {
    showFormMessage(
      error.message === "Failed to fetch"
        ? "Не удалось связаться с сервером. Проверь URL backend и CORS и попробуй снова!"
        : error.message,
      true,
    );
    button.disabled = false;
  }
});

const savedToken = localStorage.getItem(applicationKey);
if (savedToken) checkStatus(savedToken);
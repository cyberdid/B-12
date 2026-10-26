"use strict";
// B-12 Web UI. Uses only the real API; every model/tool text goes through textContent.
// The owner token is kept in sessionStorage for this tab and sent only as a header.

const TOKEN_KEY = "b12.token";
const SESSION_KEY = "b12.session";
const $ = (id) => document.getElementById(id);

const state = { token: null, session: null, turnId: null, controller: null, busy: false };
// Tool cards by call ID survive approval/resume streams of the same turn.
const cards = new Map();

function storage(kind) {
  try {
    return window[kind];
  } catch {
    return null;
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const headers = { Authorization: `Bearer ${state.token}` };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: options.method || "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });
  if (response.status === 401) {
    logout("Токен не прийнято.");
    throw new Error("unauthorized");
  }
  return response;
}

async function json(path, options) {
  const response = await api(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  return data;
}

function setStatus(text) {
  $("status").textContent = text || "";
}

function scrollDown() {
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
}

function addMessage(kind, text) {
  $("empty").hidden = true;
  const node = el("div", `msg ${kind}`, text);
  $("messages").append(node);
  scrollDown();
  return node;
}

function toolCard(event) {
  const card = el("div", "msg tool");
  const title = el("div");
  title.append(el("span", "badge", "⚙ "), document.createTextNode(event.name));
  card.append(title);
  if (event.arguments) {
    const details = el("details");
    details.append(el("summary", null, "Аргументи"));
    details.append(el("pre", null, JSON.stringify(event.arguments, null, 2)));
    card.append(details);
  }
  $("messages").append(card);
  scrollDown();
  return card;
}

function setBusy(busy) {
  state.busy = busy;
  $("send").disabled = busy;
  $("cancel").hidden = !busy;
}

async function readStream(response, assistant) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (!line) continue;
      const event = JSON.parse(line);
      if (event.type === "turn_started") state.turnId = event.turn_id;
      else if (event.type === "text_delta") {
        assistant.textContent += event.text;
        scrollDown();
      } else if (event.type === "tool_started") cards.set(event.call_id, toolCard(event));
      else if (event.type === "tool_result") {
        const card = cards.get(event.call_id) || toolCard(event);
        const badge = el("span", `badge ${event.status}`, ` → ${event.status}`);
        if (event.error_code) badge.textContent += ` (${event.error_code})`;
        if (event.outcome_unknown) badge.textContent += " — результат невідомий";
        card.firstChild.append(badge);
      } else if (event.type === "approval_pending") {
        addMessage("state", `Очікує підтвердження: ${event.name}`);
      } else if (event.type === "result" || event.type === "error") result = event;
    }
  }
  return result;
}

async function runTurn(start) {
  setBusy(true);
  const assistant = addMessage("assistant", "");
  state.controller = new AbortController();
  try {
    const response = await start(state.controller.signal);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    }
    const result = await readStream(response, assistant);
    if (!result) addMessage("state", "З’єднання завершилося без результату.");
    else if (result.type === "error") addMessage("state", `Помилка: ${result.error}`);
    else {
      if (result.content && !assistant.textContent) assistant.textContent = result.content;
      if (result.state !== "completed") {
        const reason = result.error_code ? ` (${result.error_code})` : "";
        addMessage("state", `Стан: ${result.state}${reason}`);
      }
    }
    if (!assistant.textContent) assistant.remove();
  } catch (error) {
    if (!assistant.textContent) assistant.remove();
    addMessage("state", error.name === "AbortError" ? "Скасовано." : `Помилка: ${error.message}`);
  } finally {
    state.controller = null;
    state.turnId = null;
    setBusy(false);
    refreshApprovals();
  }
}

async function send(text) {
  addMessage("user", text);
  await runTurn((signal) =>
    api("/api/chat", { method: "POST", body: { session_id: state.session, text }, signal }),
  );
}

async function cancelTurn() {
  const turn = state.turnId;
  if (turn) {
    await api(`/api/turns/${turn}/cancel`, { method: "POST", body: {} }).catch(() => {});
  }
  if (state.controller) state.controller.abort();
}

async function loadHistory() {
  cards.clear();
  $("messages").replaceChildren();
  const history = await json(`/api/sessions/${state.session}/history`);
  for (const message of history) {
    if (message.role === "user") addMessage("user", message.content);
    else if (message.role === "assistant" && message.content) addMessage("assistant", message.content);
    else if (message.role === "tool") addMessage("tool", `⚙ ${message.tool_name}`);
  }
  $("empty").hidden = history.length > 0;
}

async function loadSessions(preferred) {
  let sessions = await json("/api/sessions");
  if (!sessions.length) sessions = [(await json("/api/sessions", { method: "POST", body: {} })).session_id];
  const select = $("session-select");
  select.replaceChildren(
    ...sessions.map((id, i) => {
      const option = el("option", null, `Сесія ${i + 1}`);
      option.value = id;
      return option;
    }),
  );
  state.session = sessions.includes(preferred) ? preferred : sessions[sessions.length - 1];
  select.value = state.session;
  storage("localStorage")?.setItem(SESSION_KEY, state.session);
  await loadHistory();
}

async function refreshApprovals() {
  const list = $("approvals");
  try {
    const items = await json("/api/approvals");
    $("approval-count").textContent = items.length ? `(${items.length})` : "";
    list.replaceChildren(
      ...items.map((item) => {
        const li = el("li");
        li.append(el("strong", null, item.name));
        li.append(el("span", "meta", `операція ${item.operation_id.slice(0, 8)}…`));
        const actions = el("div", "actions");
        const yes = el("button", null, "Дозволити");
        const no = el("button", "ghost", "Відхилити");
        yes.type = no.type = "button";
        yes.addEventListener("click", () => decide(item, true));
        no.addEventListener("click", () => decide(item, false));
        actions.append(yes, no);
        li.append(actions);
        return li;
      }),
    );
    if (!items.length) list.replaceChildren(el("li", "meta", "Немає дій, що очікують."));
  } catch (error) {
    list.replaceChildren(el("li", "meta", `Недоступно: ${error.message}`));
  }
}

async function decide(item, approve) {
  try {
    await json(`/api/approvals/${item.operation_id}`, { method: "POST", body: { approve } });
    addMessage("state", approve ? `Дозволено: ${item.name}` : `Відхилено: ${item.name}`);
    await runTurn((signal) =>
      api(`/api/turns/${item.turn_id}/resume`, { method: "POST", body: {}, signal }),
    );
  } catch (error) {
    setStatus(`Не вдалося: ${error.message}`);
  }
}

function memoryItem(record) {
  const li = el("li");
  li.append(el("span", null, record.text));
  li.append(el("span", "meta", `${record.kind} · ${record.created_at.slice(0, 16).replace("T", " ")}`));
  const forget = el("button", "ghost", "Забути");
  forget.type = "button";
  forget.addEventListener("click", async () => {
    const response = await api(`/api/memory/${record.id}`, { method: "DELETE" });
    const receipt = await response.json().catch(() => ({}));
    if (response.status === 200) li.replaceChildren(el("span", "meta", "Забуто повністю."));
    else if (response.status === 202) {
      li.replaceChildren(el("span", "meta", `Очікує: ${(receipt.pending_stores || []).join(", ")}`));
    } else li.append(el("span", "error", "Не вдалося забути."));
  });
  li.append(forget);
  return li;
}

async function searchMemory(query) {
  const list = $("memories");
  try {
    const records = await json(`/api/memory?q=${encodeURIComponent(query)}`);
    list.replaceChildren(...records.map(memoryItem));
    if (!records.length) list.replaceChildren(el("li", "meta", "Нічого не знайдено."));
  } catch (error) {
    list.replaceChildren(el("li", "meta", `Недоступно: ${error.message}`));
  }
}

async function loadTools() {
  const tools = await json("/api/tools");
  $("tools").replaceChildren(
    ...tools.map((tool) => {
      const li = el("li");
      li.append(el("strong", null, tool.name));
      li.append(el("span", null, tool.description));
      li.append(el("span", "meta", `${tool.capability} · ${tool.risk}`));
      return li;
    }),
  );
}

async function checkHealth() {
  const dot = $("health");
  try {
    const response = await fetch("/api/health");
    dot.className = response.ok ? "dot ok" : "dot bad";
  } catch {
    dot.className = "dot bad";
  }
}

function logout(message) {
  storage("sessionStorage")?.removeItem(TOKEN_KEY);
  state.token = null;
  $("app").hidden = true;
  $("login").hidden = false;
  $("login-error").textContent = message || "";
}

async function enter() {
  const me = await json("/api/me");
  $("login").hidden = true;
  $("app").hidden = false;
  $("consent").checked = me.consent;
  $("consent").disabled = !me.owner && !me.consent;
  await loadSessions(storage("localStorage")?.getItem(SESSION_KEY));
  await Promise.all([refreshApprovals(), loadTools(), checkHealth()]);
}

function bind() {
  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.token = $("token-input").value.trim();
    $("token-input").value = "";
    try {
      await enter();
      storage("sessionStorage")?.setItem(TOKEN_KEY, state.token);
    } catch (error) {
      if (error.message !== "unauthorized") logout(`Помилка: ${error.message}`);
    }
  });
  $("logout").addEventListener("click", () => logout());
  $("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = $("input").value.trim();
    if (!text || state.busy) return;
    $("input").value = "";
    send(text);
  });
  $("input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $("composer").requestSubmit();
    }
  });
  $("cancel").addEventListener("click", cancelTurn);
  $("new-session").addEventListener("click", async () => {
    const created = await json("/api/sessions", { method: "POST", body: {} });
    await loadSessions(created.session_id);
  });
  $("session-select").addEventListener("change", (event) => loadSessions(event.target.value));
  $("consent").addEventListener("change", async (event) => {
    try {
      await json("/api/control/consent", { method: "POST", body: { consent: event.target.checked } });
      setStatus(event.target.checked ? "Пам’ять увімкнено." : "Пам’ять вимкнено: нові записи не зберігаються.");
    } catch (error) {
      event.target.checked = !event.target.checked;
      setStatus(`Не вдалося змінити згоду: ${error.message}`);
    }
  });
  $("memory-search").addEventListener("submit", (event) => {
    event.preventDefault();
    searchMemory($("memory-query").value.trim());
  });
  $("memory-add").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = $("memory-text").value.trim();
    try {
      const record = await json("/api/memory", { method: "POST", body: { text } });
      $("memory-text").value = "";
      $("memories").prepend(memoryItem(record));
    } catch (error) {
      setStatus(`Не збережено: ${error.message}`);
    }
  });
  for (const tab of document.querySelectorAll("[data-tab]")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll("[data-tab]")) {
        other.setAttribute("aria-selected", String(other === tab));
        $(`tab-${other.dataset.tab}`).hidden = other !== tab;
      }
    });
  }
  window.addEventListener("online", checkHealth);
  window.addEventListener("offline", () => ($("health").className = "dot bad"));
  setInterval(checkHealth, 15000);
}

bind();
state.token = storage("sessionStorage")?.getItem(TOKEN_KEY) || null;
if (state.token) enter().catch(() => logout());
else logout();

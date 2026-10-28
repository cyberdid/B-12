"use strict";
// B-12 Web UI. Uses only the real API; every model/tool text goes through textContent.
// The owner token is kept in sessionStorage for this tab and sent only as a header.

const TOKEN_KEY = "b12.token";
const SESSION_KEY = "b12.session";
const DRAFT_KEY = "b12.draft";
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

function messageActions(node, text, when) {
  const bar = el("div", "msg-actions");
  const copy = el("button", "ghost", "Копіювати");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      copy.textContent = "Скопійовано";
      setTimeout(() => (copy.textContent = "Копіювати"), 1500);
    } catch {
      copy.textContent = "Не вдалося";
    }
  });
  bar.append(copy);
  if (when) bar.append(el("span", "meta", when.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })));
  node.append(bar);
}

function addMessage(kind, text, when) {
  $("empty").hidden = true;
  if (kind !== "tool") closeToolGroup();
  const node = el("div", `msg ${kind}`);
  if (kind === "assistant") node.append(renderMarkdown(text));
  else node.textContent = text;
  if (text && (kind === "assistant" || kind === "user")) messageActions(node, text, when);
  $("messages").append(node);
  scrollDown();
  return node;
}

const SUMMARY_KEYS = ["path", "command", "executable", "query", "url", "memory_id", "text"];

function toolSummary(args) {
  if (!args || typeof args !== "object") return "";
  for (const key of SUMMARY_KEYS) {
    if (typeof args[key] === "string" && args[key]) {
      const value = args[key].replace(/\s+/g, " ").trim();
      return value.length > 70 ? `${value.slice(0, 69)}…` : value;
    }
  }
  return "";
}

// All tool calls of one reply go into one collapsible group ("Інструменти: N").
let toolGroup = null;

function currentToolGroup() {
  if (!toolGroup) {
    toolGroup = el("details", "tool-group");
    toolGroup.open = true;
    toolGroup.append(el("summary", null, "Інструменти: 0"));
    $("messages").append(toolGroup);
  }
  const count = toolGroup.querySelectorAll(":scope > .msg.tool").length + 1;
  toolGroup.querySelector("summary").textContent = `Інструменти: ${count}`;
  return toolGroup;
}

function closeToolGroup() {
  if (toolGroup) toolGroup.open = false;
  toolGroup = null;
}

function toolCard(event) {
  const card = el("div", "msg tool");
  card.dataset.started = String(performance.now());
  const title = el("div", "tool-title");
  title.append(el("span", "tool-name", `⚙ ${event.name}`));
  const summary = toolSummary(event.arguments);
  if (summary) title.append(el("span", "tool-summary", summary));
  title.append(el("span", "badge running", " … виконується"));
  card.append(title);
  if (event.arguments && Object.keys(event.arguments).length) {
    const details = el("details", "tool-args");
    details.append(el("summary", null, "аргументи"));
    details.append(el("pre", null, JSON.stringify(event.arguments, null, 2)));
    card.append(details);
  }
  const resultBox = el("details", "tool-result");
  resultBox.hidden = true;
  resultBox.append(el("summary", null, "результат"), el("pre", null, ""));
  card.append(resultBox);
  currentToolGroup().append(card);
  scrollDown();
  return card;
}

// Show what a tool returned. Clipped by the server to the model's budget; the full
// outcome is what the model saw, so the owner sees exactly that.
function showResult(card, content) {
  const box = card.querySelector(".tool-result");
  if (!box) return;
  const text = typeof content?.text === "string" ? content.text : JSON.stringify(content ?? {}, null, 2);
  box.querySelector("pre").textContent = text;
  box.hidden = false;
}

function setBusy(busy) {
  state.busy = busy;
  $("send").disabled = busy;
  $("cancel").hidden = !busy;
}

async function readStream(response, view) {
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
        if (!view.node) {
          view.node = addMessage("assistant", "");
          view.raw = "";
        }
        view.raw += event.text;
        view.node.replaceChildren(renderMarkdown(view.raw));
        view.shown = true;
        scrollDown();
      } else if (event.type === "tool_started") {
        view.node = null; // text after a tool call starts a new bubble below its card
        cards.set(event.call_id, toolCard(event));
      } else if (event.type === "tool_result") {
        const card = cards.get(event.call_id) || toolCard(event);
        card.querySelector(".badge.running")?.remove();
        const badge = el("span", `badge ${event.status}`, ` → ${event.status}`);
        if (event.error_code) badge.textContent += ` (${event.error_code})`;
        const started = Number(card.dataset.started);
        if (started) badge.textContent += ` · ${Math.max(1, Math.round(performance.now() - started))} мс`;
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
  const view = { node: null, shown: false };
  state.controller = new AbortController();
  try {
    const response = await start(state.controller.signal);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    }
    const result = await readStream(response, view);
    if (!result) addMessage("state", "З’єднання завершилося без результату.");
    else if (result.type === "error") addMessage("state", `Помилка: ${result.error}`);
    else {
      if (result.content && !view.shown) addMessage("assistant", result.content, new Date());
      else if (view.node && view.raw) messageActions(view.node, view.raw, new Date());
      if (result.state !== "completed") {
        const reason = result.error_code ? ` (${result.error_code})` : "";
        addMessage("state", `Стан: ${result.state}${reason}`);
      }
    }
    for (const outcome of result?.tool_results || []) {
      const card = cards.get(outcome.call_id);
      if (card) showResult(card, outcome.content);
    }
  } catch (error) {
    addMessage("state", error.name === "AbortError" ? "Скасовано." : `Помилка: ${error.message}`);
  } finally {
    closeToolGroup();
    state.controller = null;
    state.turnId = null;
    setBusy(false);
    refreshApprovals();
  }
}

async function send(text) {
  addMessage("user", text);
  await runTurn((signal) =>
    api("/api/chat", { method: "POST", body: { session_id: state.session, text, persist: $("persist").checked }, signal }),
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
  closeToolGroup();
  $("messages").replaceChildren();
  const history = await json(`/api/sessions/${state.session}/history`);
  // Arguments live on the assistant's tool_calls; results live on the tool messages.
  const argsById = new Map();
  for (const message of history) {
    for (const call of message.tool_calls || []) {
      const fn = call.function || call;
      argsById.set(call.id, fn.arguments);
    }
  }
  for (const message of history) {
    if (message.role === "user") addMessage("user", message.content, null);
    else if (message.role === "assistant" && message.content) addMessage("assistant", message.content, null);
    else if (message.role === "tool") {
      let outcome = {};
      try {
        outcome = JSON.parse(message.content || "{}");
      } catch {
        /* unparsable stored result: show the name only */
      }
      const card = toolCard({ name: message.tool_name, arguments: argsById.get(message.tool_call_id) });
      card.querySelector(".badge.running")?.remove();
      if (outcome.content !== undefined) showResult(card, outcome.content);
      const status = outcome.status || "completed";
      const badge = el("span", `badge ${status}`, ` → ${status}`);
      if (outcome.error_code) badge.textContent += ` (${outcome.error_code})`;
      card.firstChild.append(badge);
      card.dataset.started = "";
    }
  }
  $("empty").hidden = history.length > 0;
}

async function loadSessions(preferred) {
  let sessions = await json("/api/sessions");
  if (!sessions.length) sessions = [(await json("/api/sessions", { method: "POST", body: {} })).session_id];
  state.session = sessions.includes(preferred) ? preferred : sessions[sessions.length - 1];
  // Newest conversations first, numbered by creation order.
  $("session-list").replaceChildren(
    ...sessions
      .map((id, i) => {
        const item = el("button", "session-item", `Розмова ${i + 1}`);
        item.type = "button";
        item.setAttribute("aria-current", String(id === state.session));
        item.addEventListener("click", () => {
          loadSessions(id);
          $("sidebar").classList.remove("open");
        });
        return item;
      })
      .reverse(),
  );
  storage("localStorage")?.setItem(SESSION_KEY, state.session);
  await loadHistory();
}

async function refreshApprovals() {
  const list = $("approvals");
  try {
    const items = await json("/api/approvals");
    const count = items.length ? `(${items.length})` : "";
    $("approval-count").textContent = count;
    $("approval-count-tab").textContent = count;
    $("toggle-panel").classList.toggle("alert", items.length > 0);
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
  const li = el("li", "memory-card");
  li.append(el("span", "memory-text", record.text));
  li.append(el("span", "meta", `${record.kind} · ${record.created_at.slice(0, 16).replace("T", " ")}`));
  const actions = el("div", "actions");
  const edit = el("button", "ghost", "Редагувати");
  edit.type = "button";
  edit.addEventListener("click", () => {
    $("memory-text").value = record.text;
    $("memory-text").dataset.replaces = record.id;
    $("memory-text").focus();
    $("memory-save").textContent = "Зберегти зміну";
  });
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
  actions.append(edit, forget);
  li.append(actions);
  return li;
}

async function loadAllMemories() {
  const list = $("memories-all");
  try {
    const records = await json("/api/memory/records?limit=1000");
    $("memories-count").textContent = `${records.length} записів`;
    list.replaceChildren(...records.map(memoryItem));
    if (!records.length) list.replaceChildren(el("li", "meta", "Пам’ять порожня."));
  } catch (error) {
    list.replaceChildren(el("li", "meta", `Недоступно: ${error.message}`));
  }
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
    storage("localStorage")?.removeItem(DRAFT_KEY);
    send(text);
  });
  $("input").value = storage("localStorage")?.getItem(DRAFT_KEY) || "";
  $("input").addEventListener("input", (event) => {
    try {
      storage("localStorage")?.setItem(DRAFT_KEY, event.target.value);
    } catch {
      /* storage unavailable: draft is not kept */
    }
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
  $("toggle-panel").addEventListener("click", () => {
    const open = $("panel").hidden;
    $("panel").hidden = !open;
    document.querySelector(".layout").classList.toggle("panel-open", open);
  });
  $("toggle-sidebar").addEventListener("click", () => $("sidebar").classList.toggle("open"));
  $("consent").addEventListener("change", async (event) => {
    try {
      await json("/api/control/consent", { method: "POST", body: { consent: event.target.checked } });
      setStatus(event.target.checked ? "Пам’ять увімкнено." : "Пам’ять вимкнено: нові записи не зберігаються.");
    } catch (error) {
      event.target.checked = !event.target.checked;
      setStatus(`Не вдалося змінити згоду: ${error.message}`);
    }
  });
  $("memories-reload").addEventListener("click", loadAllMemories);
  $("memory-search").addEventListener("submit", (event) => {
    event.preventDefault();
    searchMemory($("memory-query").value.trim());
  });
  $("memory-add").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = $("memory-text").value.trim();
    const replaces = $("memory-text").dataset.replaces;
    try {
      const record = await json("/api/memory", { method: "POST", body: { text } });
      if (replaces) {
        await api(`/api/memory/${replaces}`, { method: "DELETE" });
        delete $("memory-text").dataset.replaces;
        $("memory-save").textContent = "Зберегти";
      }
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
      if (tab.dataset.tab === "memory") loadAllMemories();
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

// Headless Chrome acceptance of the B-12 Web UI over CDP. Usage: node web_accept.mjs URL TOKEN_FILE OUT_DIR SANDBOX
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, tokenFile, out, sandbox] = process.argv.slice(2);
const profile = mkdtempSync(join(tmpdir(), "b12-chrome-"));
const port = 9333;
const chrome = spawn("google-chrome", [
  "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--window-size=1280,860", "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const report = [];
const check = (name, ok, detail = "") => { report.push({ name, ok: !!ok, detail }); console.log(ok ? "PASS" : "FAIL", name, detail); };

let ws, id = 0; const pending = new Map(); const consoleErrors = [];
async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      const page = tabs.find((t) => t.type === "page");
      ws = new WebSocket(page.webSocketDebuggerUrl);
      await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
        if (msg.method === "Runtime.exceptionThrown") consoleErrors.push(msg.params.exceptionDetails.text);
        if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") consoleErrors.push(JSON.stringify(msg.params.args.map((a) => a.value)));
      };
      return;
    } catch { await sleep(200); }
  }
  throw new Error("chrome not reachable");
}
const cdp = (method, params = {}) => new Promise((res) => { const n = ++id; pending.set(n, res); ws.send(JSON.stringify({ id: n, method, params })); });
const evaluate = async (expr) => (await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const waitFor = async (expr, ms = 60000) => { const end = Date.now() + ms; while (Date.now() < end) { if (await evaluate(expr)) return true; await sleep(200); } return false; };
async function shot(name) { const r = await cdp("Page.captureScreenshot", { format: "png" }); writeFileSync(join(out, name), Buffer.from(r.result.data, "base64")); }
async function typeInto(selector, text, enter = true) {
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
  await cdp("Input.insertText", { text });
  if (enter) {
    await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" });
    await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
  }
}
const click = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
const busyDone = () => waitFor(`document.getElementById("send").disabled === false`, 120000);
const lastState = () => evaluate(`[...document.querySelectorAll(".msg.state")].map(n=>n.textContent).slice(-1)[0] || ""`);

try {
  await connect();
  await cdp("Runtime.enable"); await cdp("Page.enable");
  await cdp("Page.navigate", { url });
  await waitFor(`document.readyState === "complete"`);
  check("login form shown without token", await waitFor(`!document.getElementById("login").hidden`));
  await shot("01-login.png");

  await typeInto("#token-input", "wrong-token", false);
  await click("#login-form button");
  check("wrong token rejected", await waitFor(`document.getElementById("login-error").textContent.length > 0`));

  await typeInto("#token-input", readFileSync(tokenFile, "utf8").trim(), false);
  await click("#login-form button");
  check("app opens with valid token", await waitFor(`!document.getElementById("app").hidden`));
  check("token not in URL", !(await evaluate("location.href")).includes("token"));
  check("tools listed", await waitFor(`document.querySelectorAll("#tools li").length === 13`), String(await evaluate(`document.querySelectorAll("#tools li").length`)));
  check("health ok", await waitFor(`document.getElementById("health").className === "dot ok"`));
  await shot("02-app-empty.png");

  // Real tool turn: file write + read; verify bytes independently.
  const target = join(sandbox, "web-ui.txt");
  await typeInto("#input", `Створи файл ${target} з текстом 'Вебтест 55', потім прочитай його і скажи вміст.`);
  await waitFor(`document.getElementById("send").disabled === true`, 5000);
  await busyDone();
  const cards = await evaluate(`[...document.querySelectorAll(".msg.tool")].filter(n=>n.querySelector("details")).map(n=>n.textContent)`);
  check("tool cards show completed results", cards.length >= 2 && cards.every((c) => c.includes("completed")), JSON.stringify(cards));
  check("file written by real tool", existsSync(target) && readFileSync(target, "utf8") === "Вебтест 55");
  const reply = await evaluate(`[...document.querySelectorAll(".msg.assistant")].map(n=>n.textContent).slice(-1)[0] || ""`);
  check("assistant reply streamed", reply.includes("Вебтест 55"), reply.slice(0, 160));
  await shot("03-tool-turn.png");

  // History survives reload of the page (server persisted the turn).
  await cdp("Page.reload"); await waitFor(`!document.getElementById("app").hidden`);
  check("history reloads after page refresh", await waitFor(`document.querySelectorAll(".msg.user").length >= 1`));

  // Memory: remember, search, forget through the panel.
  await click('[data-tab="memory"]');
  await typeInto("#memory-text", "Улюблений колір тестувальника — бірюзовий", false);
  await click("#memory-add button");
  check("memory stored", await waitFor(`[...document.querySelectorAll("#memories li")].some(n=>n.textContent.includes("бірюзовий"))`));
  await typeInto("#memory-query", "бірюзовий", false);
  await click("#memory-search button");
  check("memory searchable", await waitFor(`[...document.querySelectorAll("#memories li")].some(n=>n.textContent.includes("бірюзовий"))`));
  await shot("04-memory.png");
  await evaluate(`[...document.querySelectorAll("#memories li button")].find((b) => b.textContent === "Забути").click()`);
  check("memory forget reports full purge", await waitFor(`document.querySelector("#memories li").textContent.includes("Забуто повністю")`, 30000), await evaluate(`document.querySelector("#memories li").textContent`));

  // Approval flow: model searches memory and asks to forget; owner approves in UI.
  await typeInto("#memory-text", "Тестовий пароль від шафки 8642", false);
  await click("#memory-add button");
  await sleep(500);
  await typeInto("#input", "Знайди в пам'яті запис про пароль від шафки і забудь його назавжди.");
  await busyDone();
  await click('[data-tab="approvals"]');
  const hasApproval = await waitFor(`document.querySelectorAll("#approvals li button").length > 0`, 5000);
  check("approval appears in queue", hasApproval, await lastState());
  await shot("05-approval.png");
  if (hasApproval) {
    await click("#approvals li button");
    await waitFor(`document.getElementById("send").disabled === true`, 5000);
    await busyDone();
    const remaining = await evaluate(`fetch("/api/memory?q=8642",{headers:{Authorization:"Bearer "+sessionStorage.getItem("b12.token")}}).then(r=>r.json())`);
    check("approved forget removed memory", Array.isArray(remaining) && remaining.length === 0, JSON.stringify(remaining));
    check("resumed result attaches to original tool card", await evaluate(`[...document.querySelectorAll(".msg.tool")].filter(n=>n.textContent.includes("memory_forget")).length === 1 && [...document.querySelectorAll(".msg.tool")].some(n=>n.textContent.includes("memory_forget") && n.textContent.includes("completed"))`));
    await shot("06-after-approval.png");
  }

  // Cancel a long generation.
  await typeInto("#input", "Напиши дуже довге оповідання українською, щонайменше на 1500 слів, про маяк.");
  await waitFor(`document.getElementById("cancel").hidden === false`, 5000);
  await waitFor(`[...document.querySelectorAll(".msg.assistant")].slice(-1)[0]?.textContent.length > 40`, 30000);
  await click("#cancel");
  await busyDone();
  check("cancel ends turn", (await evaluate(`[...document.querySelectorAll(".msg.state")].map(n=>n.textContent).join("|")`)).match(/cancelled|Скасовано/) !== null, await lastState());

  // Consent toggle round-trip through control API.
  await click("#consent");
  const off = await waitFor(`fetch("/api/me",{headers:{Authorization:"Bearer "+sessionStorage.getItem("b12.token")}}).then(r=>r.json()).then(m=>m.consent===false)`, 5000);
  await click("#consent");
  const on = await waitFor(`fetch("/api/me",{headers:{Authorization:"Bearer "+sessionStorage.getItem("b12.token")}}).then(r=>r.json()).then(m=>m.consent===true)`, 5000);
  check("consent toggle changes server state", off && on);

  // Visual: dark mode and phone width.
  await cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "dark" }] });
  await shot("07-dark.png");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await sleep(300);
  check("no horizontal overflow at 390px", await evaluate(`document.documentElement.scrollWidth <= 390`), String(await evaluate("document.documentElement.scrollWidth")));
  await shot("08-mobile-dark.png");
  check("no console errors", consoleErrors.length === 0, JSON.stringify(consoleErrors).slice(0, 400));
} catch (error) {
  check("script completed", false, String(error));
} finally {
  writeFileSync(join(out, "report.json"), JSON.stringify(report, null, 2));
  ws?.close(); chrome.kill();
  process.exit(report.every((r) => r.ok) ? 0 : 1);
}

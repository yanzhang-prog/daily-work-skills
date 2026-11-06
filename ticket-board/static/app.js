// DOM, fetch and WebSockets. All decisions live in board.js.
// SECURITY: nothing from the server or the user is ever put in the page as HTML. Every piece of
// text goes through textContent (the `el` helper below), so markup in a title or chat message
// is shown literally instead of being run. Chat is plain text (white-space: pre-wrap in CSS).
import {
  STATUS_LABELS, PHASES, MAX_TITLE, MAX_REQUEST, phaseTracker, applyEvent, emptyChat,
  countNeedsYou, validateNewTicket, nextBackoffMs,
} from "/static/board.js";

const NEAR_BOTTOM_PX = 80;
const CLOSE_NOT_FOUND = 4404;
const $ = (id) => document.getElementById(id);

/** Create an element; `text` is assigned via textContent, never parsed as HTML. */
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}

function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}

// ---------- fetch helpers ----------
async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}
const listColumns = (closed) => api(`/api/columns?include_closed=${closed}`);
const createColumn = (title, request) => api("/api/columns", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, request }),
});
const closeColumn = (id) => api(`/api/columns/${encodeURIComponent(id)}`, { method: "DELETE" });
const reopenColumn = (id) => api(`/api/columns/${encodeURIComponent(id)}/reopen`, { method: "POST" });

// ---------- reconnecting socket ----------
// The server replays history after `after=<seq>`, and de-duplication by seq (board.js) makes
// overlap harmless. So reconnecting is just: wait, reopen from the last seq we saw. The wait
// doubles each failed attempt (1s, 2s, 4s ... capped at 15s) so a down server is not hammered;
// the counter resets once a connection actually opens.
function connectSocket({ path, onMessage, onState, stopCodes = [] }) {
  let ws = null, attempt = 0, timer = null, stopped = false;
  const open = () => {
    ws = new WebSocket(wsUrl(path()));
    ws.onopen = () => { attempt = 0; onState(true); };
    ws.onmessage = (m) => {
      let data;
      try { data = JSON.parse(m.data); } catch { return; }
      onMessage(data);
    };
    ws.onclose = (e) => {
      onState(false);
      if (stopped || stopCodes.includes(e.code)) return;
      timer = setTimeout(open, nextBackoffMs(attempt++));
    };
  };
  open();
  return {
    send: (obj) => { if (ws && ws.readyState === WebSocket.OPEN) { ws.send(JSON.stringify(obj)); return true; } return false; },
    close: () => { stopped = true; clearTimeout(timer); if (ws) ws.close(); },
  };
}

// ---------- column view ----------
const views = new Map(); // column id -> view

function renderHead(v) {
  const c = v.column;
  v.title.textContent = c.title;
  v.badge.className = `badge ${c.status}`;
  const label = c.label || STATUS_LABELS[c.status] || c.status;
  v.badge.textContent = `● ${label}${c.note ? ": " + c.note : ""}`;
  v.root.className = `column ${c.status}`;
  v.phases.replaceChildren();
  const steps = phaseTracker(PHASES, c.completed, c.phase, c.status);
  steps.forEach((s, i) => {
    if (i) v.phases.append(" → ");
    const mark = s.state === "done" ? " ✓" : "";
    v.phases.append(el("span", s.state, s.name + mark));
  });
  v.repos.textContent = (c.repos_read || []).join(" · ");
  v.repos.hidden = !(c.repos_read || []).length;
}

function permissionBlock(v, e) {
  const box = el("div", "perm");
  box.append(el("div", "perm-title", `Permission needed: ${e.tool}`), el("div", "perm-summary", e.summary));
  const row = el("div", "row");
  const answered = e.request_id in v.chat.answered ? v.chat.answered[e.request_id]
    : e.request_id in v.localAnswers ? v.localAnswers[e.request_id] : undefined;
  if (answered === undefined) {
    const allow = el("button", "allow", "Allow"), deny = el("button", "deny", "Deny");
    for (const [btn, ok] of [[allow, true], [deny, false]]) {
      btn.type = "button";
      btn.disabled = !v.connected;
      btn.addEventListener("click", () => answerPermission(v, e.request_id, ok));
      row.append(btn);
    }
  } else {
    row.append(el("span", "result", answered ? "Allowed" : "Denied"));
  }
  box.append(row);
  return box;
}

function answerPermission(v, requestId, allow) {
  if (v.socket.send({ type: "permission", request_id: requestId, allow })) {
    v.localAnswers[requestId] = allow;
    scheduleChat(v);
  }
}

function eventNode(v, e) {
  switch (e.type) {
    case "user_message": return el("div", "msg user", e.text ?? e.message);
    case "assistant_text": return el("div", "msg assistant", e.text);
    case "tool_activity": return el("div", "tool", `${e.tool}: ${e.summary}`);
    case "session_error": return el("div", "err", e.message);
    case "permission_request": return permissionBlock(v, e);
    default: return null; // turn_finished, permission_answer: state only
  }
}

function renderChat(v) {
  v.chatQueued = false;
  const box = v.chatBox;
  const near = box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_BOTTOM_PX;
  const nodes = v.chat.events.map((e) => eventNode(v, e)).filter(Boolean);
  if (v.transientError) nodes.push(el("div", "err small", v.transientError));
  box.replaceChildren(...nodes);
  if (near || v.firstRender) box.scrollTop = box.scrollHeight;
  v.firstRender = false;
}

// Batch re-renders: a history replay delivers hundreds of events in one tick.
function scheduleChat(v) {
  if (v.chatQueued) return;
  v.chatQueued = true;
  requestAnimationFrame(() => renderChat(v));
}

function sendReply(v) {
  const text = v.input.value;
  if (!text.trim()) return;
  if (v.socket.send({ type: "message", text })) { v.input.value = ""; v.transientError = null; }
}

function setConnected(v, up) {
  v.connected = up;
  v.reconnecting.hidden = up;
  v.input.disabled = !up;
  v.sendBtn.disabled = !up;
  scheduleChat(v); // permission buttons follow the connection
}

function onColumnMessage(v, data) {
  if (data.kind === "event") {
    v.chat = applyEvent(v.chat, data.event);
    v.transientError = null;
    scheduleChat(v);
  } else if (data.kind === "status") {
    v.column = { ...v.column, ...data.status };
    renderHead(v);
  } else if (data.kind === "error") {
    v.transientError = String(data.error); // not history: cleared by the next event
    scheduleChat(v);
  }
}

function buildView(column) {
  const v = { column, chat: emptyChat(), localAnswers: {}, connected: false, firstRender: true,
    chatQueued: false, transientError: null };
  v.root = el("section");
  v.title = el("span");
  const closeBtn = el("button", "close-btn", "✕");
  closeBtn.type = "button"; closeBtn.title = "Close this ticket"; closeBtn.setAttribute("aria-label", "Close ticket");
  closeBtn.addEventListener("click", () => onClose(v));
  v.badge = el("div");
  v.phases = el("div", "phases");
  v.repos = el("div", "repos");
  v.reconnecting = el("div", "reconnecting", "reconnecting…");
  const head = el("div", "col-head");
  const titleRow = el("div", "col-title");
  titleRow.append(v.title, closeBtn);
  head.append(titleRow, v.badge, v.phases, v.repos, v.reconnecting);
  v.chatBox = el("div", "chat");
  v.input = el("textarea");
  v.input.placeholder = "Reply…"; v.input.disabled = true;
  v.input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); sendReply(v); }
  });
  v.sendBtn = el("button", "primary", "Send");
  v.sendBtn.type = "button"; v.sendBtn.disabled = true;
  v.sendBtn.addEventListener("click", () => sendReply(v));
  const reply = el("div", "reply");
  reply.append(v.input, v.sendBtn);
  v.root.append(head, v.chatBox, reply);
  renderHead(v);
  v.socket = connectSocket({
    path: () => `/ws/columns/${encodeURIComponent(column.id)}?after=${v.chat.lastSeq}`,
    onMessage: (d) => onColumnMessage(v, d),
    onState: (up) => setConnected(v, up),
    stopCodes: [CLOSE_NOT_FOUND],
  });
  return v;
}

async function onClose(v) {
  if (v.column.status === "working" && !confirm(`"${v.column.title}" is still working. Close it anyway?`)) return;
  try { await closeColumn(v.column.id); } catch (e) { alert(`Could not close: ${e.message}`); }
}

// ---------- board ----------
function syncColumns(columns) {
  const board = $("board");
  const ids = new Set(columns.map((c) => c.id));
  for (const [id, v] of views) {
    if (!ids.has(id)) { v.socket.close(); v.root.remove(); views.delete(id); }
  }
  for (const c of columns) {
    let v = views.get(c.id);
    if (!v) { v = buildView(c); views.set(c.id, v); board.append(v.root); }
    else { v.column = { ...v.column, ...c }; renderHead(v); }
  }
  $("empty").hidden = columns.length > 0;
  $("open-count").textContent = `${columns.length} open`;
  const needs = countNeedsYou(columns);
  $("needs-count").textContent = `${needs} need${needs === 1 ? "s" : ""} you`;
  $("needs-count").className = needs ? "count hot" : "count";
  refreshClosed();
}

async function refreshClosed() {
  try {
    const closed = (await listColumns(true)).filter((c) => c.closed);
    const btn = $("closed-btn");
    btn.textContent = `Closed (${closed.length})`;
    btn.hidden = closed.length === 0 && !$("closed-dialog").open;
    renderClosedList(closed);
  } catch { /* the board socket will bring us back */ }
}

function renderClosedList(closed) {
  const list = $("closed-list");
  list.replaceChildren(...closed.map((c) => {
    const li = el("li");
    const b = el("button", "ghost", "Reopen");
    b.type = "button";
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await reopenColumn(c.id); } catch (e) { alert(`Could not reopen: ${e.message}`); }
      refreshClosed();
    });
    li.append(el("span", null, c.title), b);
    return li;
  }));
}

function setupDialogs() {
  const dlg = $("new-dialog"), form = $("new-form");
  $("new-btn").addEventListener("click", () => { $("new-error").textContent = ""; dlg.showModal(); $("new-title").focus(); });
  $("new-cancel").addEventListener("click", () => dlg.close());
  $("new-title").maxLength = MAX_TITLE;
  $("new-request").maxLength = MAX_REQUEST;
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const title = $("new-title").value.trim(), request = $("new-request").value.trim();
    const check = validateNewTicket({ title, request });
    if (!check.ok) { $("new-error").textContent = check.error; return; }
    $("new-submit").disabled = true;
    try {
      await createColumn(title, request);
      form.reset(); dlg.close();
      // The board socket pushes the new column; fetch too in case it is momentarily down.
      syncColumns(await listColumns(false));
    } catch (e) { $("new-error").textContent = `Could not create: ${e.message}`; }
    finally { $("new-submit").disabled = false; }
  });
  $("closed-btn").addEventListener("click", () => { refreshClosed(); $("closed-dialog").showModal(); });
  $("closed-close").addEventListener("click", () => $("closed-dialog").close());
}

connectSocket({
  path: () => "/ws/board",
  onMessage: (d) => { if (d.kind === "columns") syncColumns(d.columns); },
  onState: () => {},
});
setupDialogs();
syncColumns([]);

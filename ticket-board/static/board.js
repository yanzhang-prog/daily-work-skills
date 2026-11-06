// Pure board logic: no DOM, no network. app.js wires this to the page; node tests import it directly.

export const STATUS_LABELS = {
  working: "Working", needs_you: "Needs you", done: "Done", stuck: "Stuck",
};
export const PHASES = ["Investigate", "Decide", "Shape", "Draft", "Create"];
export const MAX_TITLE = 120;     // mirrors config.MAX_TITLE_CHARS on the server
export const MAX_REQUEST = 20000; // mirrors config.MAX_TEXT_CHARS
const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 15000;

/** One entry per phase: done (ticked), current (bold) or todo. A finished ticket ticks all. */
export function phaseTracker(phases, completed, current, status) {
  const doneSet = new Set(completed || []);
  return phases.map((name) => {
    if (status === "done" || doneSet.has(name)) return { name, state: "done" };
    return { name, state: name === current ? "current" : "todo" };
  });
}

const hasOwn = (obj, key) => obj != null && Object.prototype.hasOwnProperty.call(obj, key);

/** Status name safe to use in a class attribute; anything unexpected becomes "unknown". */
export function safeStatus(status) {
  return typeof status === "string" && hasOwn(STATUS_LABELS, status) ? status : "unknown";
}

export function emptyChat() {
  return { events: [], lastSeq: 0, answered: {} };
}

export function isAnswered(chat, requestId) {
  return hasOwn(chat.answered, requestId);
}

/**
 * How to draw one permission_request. Only a permission_answer EVENT from the server makes it
 * "allowed"/"denied" (never the click itself). `pending` is the server's list of still-open
 * request ids as of chat seq `pendingAsOfSeq`; a request at or before that seq that is not in
 * the list can no longer be answered ("expired", e.g. replayed after a restart). A newer
 * request, or no list yet, is "open". "sending" = clicked, answer not back yet.
 */
export function permissionView(chat, request, { pending, pendingAsOfSeq, clicked }) {
  const id = request.request_id;
  if (isAnswered(chat, id)) return chat.answered[id] ? "allowed" : "denied";
  if (Array.isArray(pending) && request.seq <= pendingAsOfSeq && !pending.includes(id)) return "expired";
  if (hasOwn(clicked, id)) return "sending";
  return "open";
}

/** Double-click guard: the first click for a request wins; later clicks are ignored. */
export function claimClick(clicked, requestId) {
  if (hasOwn(clicked, requestId)) return { ok: false, clicked };
  return { ok: true, clicked: { ...clicked, [requestId]: true } };
}

/**
 * Fold one server event into the chat state, returning a NEW state.
 * - de-duplicates by seq (reconnect replays overlap live events)
 * - keeps events sorted by seq even if they arrive out of order
 * - `answered` maps request_id -> allow, filled from permission_answer events, so a request
 *   is shown as answered whatever order the two events arrive in.
 */
export function applyEvent(state, event) {
  if (!event || typeof event.seq !== "number") return state;
  if (state.events.some((e) => e.seq === event.seq)) return state;
  const events = [...state.events, event].sort((a, b) => a.seq - b.seq);
  const answered = { ...state.answered };
  if (event.type === "permission_answer" && typeof event.request_id === "string") {
    Object.defineProperty(answered, event.request_id, {
      value: event.allow === true, enumerable: true, writable: true, configurable: true,
    }); // defineProperty: a "__proto__" id stays a plain key
  }
  return { events, lastSeq: Math.max(state.lastSeq, event.seq), answered };
}

export function countNeedsYou(columns) {
  return columns.filter((c) => c.status === "needs_you").length;
}

export function validateNewTicket({ title, request } = {}) {
  const t = typeof title === "string" ? title.trim() : "";
  const r = typeof request === "string" ? request.trim() : "";
  if (!t) return { ok: false, error: "Give the ticket a title." };
  if (t.length > MAX_TITLE) return { ok: false, error: `Title is too long (max ${MAX_TITLE} characters).` };
  if (!r) return { ok: false, error: "Describe the request." };
  if (r.length > MAX_REQUEST) return { ok: false, error: `Request is too long (max ${MAX_REQUEST} characters).` };
  return { ok: true, error: null };
}

/** Reconnect delay: 1s, 2s, 4s, 8s, then 15s forever. attempt starts at 0. */
export function nextBackoffMs(attempt) {
  return Math.min(BACKOFF_BASE_MS * 2 ** Math.min(attempt, 10), BACKOFF_MAX_MS);
}

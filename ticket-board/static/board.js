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

export function emptyChat() {
  return { events: [], lastSeq: 0, answered: {} };
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
    answered[event.request_id] = event.allow === true;
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

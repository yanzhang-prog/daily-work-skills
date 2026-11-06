import { test } from "node:test";
import assert from "node:assert/strict";
import {
  STATUS_LABELS, phaseTracker, applyEvent, emptyChat, countNeedsYou, validateNewTicket, nextBackoffMs,
} from "../../static/board.js";

const PHASES = ["Investigate", "Decide", "Shape", "Draft", "Create"];
const states = (t) => t.map((p) => p.state);

test("status labels", () => {
  assert.equal(STATUS_LABELS.needs_you, "Needs you");
  assert.equal(STATUS_LABELS.stuck, "Stuck");
});

test("phaseTracker: working at Investigate", () => {
  const t = phaseTracker(PHASES, [], "Investigate", "working");
  assert.deepEqual(states(t), ["current", "todo", "todo", "todo", "todo"]);
  assert.equal(t[0].name, "Investigate");
});

test("phaseTracker: needs_you at Draft, earlier ones completed", () => {
  const t = phaseTracker(PHASES, ["Investigate", "Decide", "Shape"], "Draft", "needs_you");
  assert.deepEqual(states(t), ["done", "done", "done", "current", "todo"]);
});

test("phaseTracker: stuck keeps the current phase", () => {
  const t = phaseTracker(PHASES, ["Investigate"], "Decide", "stuck");
  assert.deepEqual(states(t), ["done", "current", "todo", "todo", "todo"]);
});

test("phaseTracker: done ticks everything", () => {
  const t = phaseTracker(PHASES, ["Investigate"], "Create", "done");
  assert.deepEqual(states(t), ["done", "done", "done", "done", "done"]);
});

test("phaseTracker: unknown current phase and missing lists do not throw", () => {
  const t = phaseTracker(PHASES, undefined, "Nonsense", "working");
  assert.deepEqual(states(t), ["todo", "todo", "todo", "todo", "todo"]);
});

const ev = (seq, type = "assistant_text", extra = {}) => ({ seq, type, at: "t", text: `m${seq}`, ...extra });
const seqs = (s) => s.events.map((e) => e.seq);

test("applyEvent: appends and tracks lastSeq", () => {
  let s = emptyChat();
  s = applyEvent(s, ev(1));
  s = applyEvent(s, ev(2));
  assert.deepEqual(seqs(s), [1, 2]);
  assert.equal(s.lastSeq, 2);
});

test("applyEvent: is immutable", () => {
  const s0 = emptyChat();
  const s1 = applyEvent(s0, ev(1));
  assert.equal(s0.events.length, 0);
  assert.notEqual(s0, s1);
});

test("applyEvent: duplicate seq is ignored", () => {
  let s = applyEvent(emptyChat(), ev(1));
  const s2 = applyEvent(s, ev(1));
  assert.deepEqual(seqs(s2), [1]);
});

test("applyEvent: out-of-order arrivals are kept in seq order, lastSeq is the max", () => {
  let s = emptyChat();
  for (const n of [3, 1, 2]) s = applyEvent(s, ev(n));
  assert.deepEqual(seqs(s), [1, 2, 3]);
  assert.equal(s.lastSeq, 3);
});

test("applyEvent: replaying the same history twice changes nothing", () => {
  const hist = [ev(1), ev(2), ev(3, "tool_activity", { tool: "Read", summary: "x" })];
  let s = emptyChat();
  for (const e of hist) s = applyEvent(s, e);
  const once = JSON.stringify(s);
  for (const e of hist) s = applyEvent(s, e);
  assert.equal(JSON.stringify(s), once);
});

test("applyEvent: later permission_answer marks the request answered", () => {
  let s = applyEvent(emptyChat(), ev(1, "permission_request", { request_id: "r1", tool: "Bash", summary: "x" }));
  assert.equal(s.answered.r1, undefined);
  s = applyEvent(s, ev(2, "permission_answer", { request_id: "r1", allow: true }));
  assert.equal(s.answered.r1, true);
});

test("applyEvent: denial is recorded as false", () => {
  let s = applyEvent(emptyChat(), ev(2, "permission_answer", { request_id: "r1", allow: false }));
  assert.equal(s.answered.r1, false);
});

test("applyEvent: answer arriving before its request still marks it answered", () => {
  let s = applyEvent(emptyChat(), ev(2, "permission_answer", { request_id: "r1", allow: true }));
  s = applyEvent(s, ev(1, "permission_request", { request_id: "r1", tool: "Bash", summary: "x" }));
  assert.equal(s.answered.r1, true);
  assert.deepEqual(seqs(s), [1, 2]);
});

test("applyEvent: ignores events without a numeric seq", () => {
  const s = applyEvent(emptyChat(), { type: "assistant_text", text: "x" });
  assert.equal(s.events.length, 0);
});

test("countNeedsYou", () => {
  assert.equal(countNeedsYou([]), 0);
  assert.equal(countNeedsYou([{ status: "needs_you" }, { status: "working" }, { status: "needs_you" }]), 2);
});

test("validateNewTicket: ok", () => {
  assert.equal(validateNewTicket({ title: "A", request: "do it" }).ok, true);
});

test("validateNewTicket: whitespace-only is rejected", () => {
  assert.equal(validateNewTicket({ title: "   ", request: "x" }).ok, false);
  assert.equal(validateNewTicket({ title: "x", request: " \n\t" }).ok, false);
  assert.match(validateNewTicket({ title: "", request: "x" }).error, /title/i);
});

test("validateNewTicket: limits 120 and 20000 (after trimming)", () => {
  assert.equal(validateNewTicket({ title: "a".repeat(120), request: "x" }).ok, true);
  assert.equal(validateNewTicket({ title: "a".repeat(121), request: "x" }).ok, false);
  assert.equal(validateNewTicket({ title: "x", request: "a".repeat(20000) }).ok, true);
  assert.equal(validateNewTicket({ title: "x", request: "a".repeat(20001) }).ok, false);
  assert.equal(validateNewTicket({ title: " " + "a".repeat(120) + " ", request: "x" }).ok, true);
});

test("validateNewTicket: non-strings are rejected", () => {
  assert.equal(validateNewTicket({}).ok, false);
});

test("nextBackoffMs: 1s, 2s, 4s, 8s then capped at 15s", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 50].map(nextBackoffMs), [1000, 2000, 4000, 8000, 15000, 15000, 15000]);
});

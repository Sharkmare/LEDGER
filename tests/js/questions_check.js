"use strict";

const assert = require("assert");
const path = require("path");
const { questionBadgeHtml, questionsHtml } = require(path.join(__dirname, "..", "..", "ledger", "static", "questions.js"));

const checks = [];
const check = (name, body) => checks.push([name, body]);

const helpers = {
  escapeHtml: (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
  formatTime: (stamp) => `t${stamp}`,
};
const open = { id: 1, text: "Which provider?", asker: "ann", created: 10, answer: "", answerer: "", answered: null };
const answered = { id: 2, text: "Ship it?", asker: "bob", created: 20, answer: "Yes", answerer: "cy", answered: 30 };

check("no badge when nothing is open, a count with the right plural otherwise", () => {
  assert.strictEqual(questionBadgeHtml(0), "");
  assert.strictEqual(questionBadgeHtml(undefined), "");
  assert.ok(questionBadgeHtml(1).includes("? 1") && questionBadgeHtml(1).includes("1 open question\""));
  assert.ok(questionBadgeHtml(3).includes("? 3") && questionBadgeHtml(3).includes("3 open questions"));
});

check("an open question gets an answer box and an answer button bound to its id", () => {
  const html = questionsHtml([open], helpers);
  assert.ok(html.includes('data-for="1"'));
  assert.ok(html.includes('data-answer="1"'));
  assert.ok(html.includes("Questions (1 open)"));
  assert.ok(!html.includes("data-question-reopen"));
});

check("an answered question shows its answer and offers reopen, with no answer box", () => {
  const html = questionsHtml([answered], helpers);
  assert.ok(html.includes("Yes") && html.includes("cy answered, t30"));
  assert.ok(html.includes('data-question-reopen="2"'));
  assert.ok(!html.includes("answer-box"));
  assert.ok(html.includes("<h4>Questions</h4>"));
});

check("open questions come before answered ones whatever the input order", () => {
  const html = questionsHtml([answered, open], helpers);
  assert.ok(html.indexOf("Which provider?") < html.indexOf("Ship it?"));
});

check("the ask form is always present", () => {
  assert.ok(questionsHtml([], helpers).includes('id="questionAsk"'));
  assert.ok(questionsHtml([open, answered], helpers).includes('id="questionBox"'));
});

check("question text, names and answers are escaped", () => {
  const hostile = { ...open, text: "<img onerror=x>", asker: "<b>a</b>" };
  const html = questionsHtml([hostile, { ...answered, answer: "<script>" }], helpers);
  assert.ok(!html.includes("<img onerror") && !html.includes("<script>") && !html.includes("<b>a</b>"));
  assert.ok(html.includes("&lt;img onerror=x&gt;"));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); } catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
console.log(`${checks.length - failed} of ${checks.length} question view checks passed`);
process.exit(failed ? 1 : 0);

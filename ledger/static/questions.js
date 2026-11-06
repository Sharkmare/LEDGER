"use strict";

function questionBadgeHtml(count) {
  if (!count) return "";
  return `<span class="chip question-chip" title="${count} open question${count === 1 ? "" : "s"}">? ${count}</span>`;
}

function openQuestionHtml(question, { escapeHtml, formatTime }) {
  return `<div class="question open" data-question="${question.id}">
    <div class="who">${escapeHtml(question.asker)} asked, ${formatTime(question.created)}</div>
    <div class="text">${escapeHtml(question.text)}</div>
    <textarea class="answer-box" rows="2" data-for="${question.id}" placeholder="Answer  (Ctrl+Enter to post)" aria-label="Answer to: ${escapeHtml(question.text)}"></textarea>
    <div class="inline"><button type="button" class="primary" data-answer="${question.id}">Answer</button><button type="button" class="ghost" data-question-remove="${question.id}">Remove</button></div></div>`;
}

function answeredQuestionHtml(question, { escapeHtml, formatTime }) {
  return `<div class="question answered" data-question="${question.id}">
    <div class="who">${escapeHtml(question.asker)} asked, ${formatTime(question.created)}</div>
    <div class="text">${escapeHtml(question.text)}</div>
    <div class="answer"><div class="who">${escapeHtml(question.answerer)} answered, ${formatTime(question.answered)}</div>${escapeHtml(question.answer)}</div>
    <div class="inline"><button type="button" class="ghost" data-question-reopen="${question.id}">Reopen</button><button type="button" class="ghost" data-question-remove="${question.id}">Remove</button></div></div>`;
}

function questionsHtml(questions, helpers) {
  const open = questions.filter((question) => question.answered === null);
  const answered = questions.filter((question) => question.answered !== null);
  const heading = open.length ? `Questions (${open.length} open)` : "Questions";
  return `<h4>${heading}</h4>${open.map((question) => openQuestionHtml(question, helpers)).join("")}${answered.map((question) => answeredQuestionHtml(question, helpers)).join("")}
    <div class="inline"><input type="text" id="questionBox" placeholder="Ask a question" aria-label="New question"><button type="button" id="questionAsk">Ask</button></div>`;
}

if (typeof module !== "undefined") module.exports = { questionBadgeHtml, questionsHtml };

"use strict";

const assert = require("assert");
const path = require("path");
const { fieldHtml, formBodyHtml } = require(path.join(__dirname, "..", "..", "ledger", "static", "formhtml.js"));

const count = (html, pattern) => (html.match(pattern) || []).length;
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("a text field has a label tied to the input, its value and autocomplete off", () => {
  const html = fieldHtml({ name: "title", label: "Title", kind: "text" }, "Hello");
  assert.ok(html.includes('<label for="form_title">Title</label>'));
  assert.ok(html.includes('<input type="text" id="form_title" data-name="title" value="Hello" autocomplete="off">'));
});

check("nothing and null show an empty value", () => {
  for (const value of [undefined, null]) assert.ok(fieldHtml({ name: "t", label: "T", kind: "text" }, value).includes('value=""'));
  assert.ok(fieldHtml({ name: "t", label: "T", kind: "text" }, 0).includes('value="0"'));
});

check("required, disabled, placeholder and help text are shown", () => {
  const html = fieldHtml({ name: "k", label: "K", kind: "text", required: true, disabled: true, placeholder: "KEY", help: "Short" }, "");
  assert.ok(html.includes(" required"));
  assert.ok(html.includes(" disabled"));
  assert.ok(html.includes('placeholder="KEY"'));
  assert.ok(html.includes('<span class="help">Short</span>'));
});

check("a field without those options has none of them", () => {
  const html = fieldHtml({ name: "k", label: "K", kind: "text" }, "");
  for (const word of [" required", " disabled", "placeholder", "class=\"help\""]) assert.ok(!html.includes(word), word);
});

check("a number field takes any step and an optional minimum", () => {
  const html = fieldHtml({ name: "n", label: "N", kind: "number", min: 1 }, 5);
  assert.ok(html.includes('type="number"'));
  assert.ok(html.includes(' min="1"'));
  assert.ok(html.includes(' step="any"'));
  assert.ok(!fieldHtml({ name: "n", label: "N", kind: "number" }, 5).includes("min="));
  assert.ok(fieldHtml({ name: "n", label: "N", kind: "number", min: 0 }, 5).includes(' min="0"'));
});

check("a select marks the chosen option, comparing as text", () => {
  const field = { name: "s", label: "S", kind: "select", options: [{ value: 1, label: "One" }, { value: 2, label: "Two" }] };
  const html = fieldHtml(field, "2");
  assert.strictEqual(count(html, / selected/g), 1);
  assert.ok(html.includes('<option value="2" selected>Two</option>'));
  assert.strictEqual(count(fieldHtml(field, 9), / selected/g), 0);
});

check("a select with no value chosen marks the blank option", () => {
  const field = { name: "s", label: "S", kind: "select", options: [{ value: "x", label: "X" }, { value: "", label: "None" }] };
  for (const value of [undefined, null, ""]) assert.ok(fieldHtml(field, value).includes('<option value="" selected>None</option>'), String(value));
});

check("a textarea has four rows unless told otherwise and holds its text", () => {
  assert.ok(fieldHtml({ name: "b", label: "B", kind: "textarea" }, "x").includes('rows="4">x</textarea>'));
  assert.ok(fieldHtml({ name: "b", label: "B", kind: "textarea", rows: 9 }, "x").includes('rows="9"'));
});

check("a checkbox is checked when its value is true and wraps its own label", () => {
  const field = { name: "c", label: "Only open", kind: "checkbox", help: "Hides closed" };
  const on = fieldHtml(field, true);
  assert.ok(on.includes('type="checkbox"') && on.includes(" checked"));
  assert.ok(on.includes("<label><input") && on.includes("Only open</label>"));
  assert.ok(on.includes('<span class="help">Hides closed</span>'));
  assert.ok(!fieldHtml(field, false).includes(" checked"));
  assert.ok(!on.includes('for="form_c"'));
});

check("a colour field offers a picker that starts on the value, or on blue when it is not a colour", () => {
  const field = { name: "col", label: "Colour", kind: "color" };
  assert.ok(fieldHtml(field, "#aabbcc").includes('type="color" data-color-for="form_col" value="#aabbcc"'));
  assert.ok(fieldHtml(field, "red").includes('value="#4cc2ff"'));
  assert.ok(fieldHtml(field, "").includes('value="#4cc2ff"'));
  assert.ok(fieldHtml(field, "#AABBCC").includes('type="color" data-color-for="form_col" value="#AABBCC"'));
  assert.ok(fieldHtml(field, "red").includes('data-name="col" value="red" placeholder="Automatic"'));
  assert.ok(!fieldHtml(field, '"><b>').includes("<b>"));
});

check("values, labels, options and help text are escaped", () => {
  const evil = '"><script>x</script>';
  const html = fieldHtml({ name: "e", label: evil, kind: "select", help: evil, options: [{ value: evil, label: evil }] }, evil) + fieldHtml({ name: "e", label: evil, kind: "textarea" }, evil) + fieldHtml({ name: "e", label: evil, kind: "text", placeholder: evil }, evil);
  assert.ok(!html.includes("<script>"), html);
});

check("fields appear in order, a group becomes a heading, and values are looked up by name", () => {
  const html = formBodyHtml([{ name: "a", label: "A", kind: "text" }, { group: "More" }, { name: "b", label: "B", kind: "text" }], { a: "one", b: "two" });
  assert.ok(html.indexOf('value="one"') < html.indexOf('<h3 class="group-title">More</h3>'));
  assert.ok(html.indexOf('<h3 class="group-title">More</h3>') < html.indexOf('value="two"'));
});

check("neighbours with the same row name share one row", () => {
  const fields = [{ name: "a", label: "A", kind: "text", row: "x" }, { name: "b", label: "B", kind: "text", row: "x" }, { name: "c", label: "C", kind: "text", row: "y" }];
  const html = formBodyHtml(fields, { a: "first", b: "second", c: "third" });
  assert.strictEqual(count(html, /class="field-row"/g), 2);
  for (const value of ["first", "second", "third"]) assert.ok(html.includes(`value="${value}"`), value);
  const firstRow = html.slice(0, html.indexOf("</div></div>") + 12);
  assert.ok(firstRow.includes("form_a") && firstRow.includes("form_b") && !firstRow.includes("form_c"));
});

check("the same row name apart from each other starts a second row", () => {
  const fields = [{ name: "a", label: "A", kind: "text", row: "x" }, { name: "m", label: "M", kind: "text" }, { name: "b", label: "B", kind: "text", row: "x" }];
  assert.strictEqual(count(formBodyHtml(fields, {}), /class="field-row"/g), 2);
});

check("a field with no row stands alone and no fields give nothing", () => {
  assert.strictEqual(count(formBodyHtml([{ name: "a", label: "A", kind: "text" }], {}), /field-row/g), 0);
  assert.strictEqual(formBodyHtml([], {}), "");
});

check("a group title is escaped", () => {
  assert.ok(!formBodyHtml([{ group: "<b>" }], {}).includes("<b>"));
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);

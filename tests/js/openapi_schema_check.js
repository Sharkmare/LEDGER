"use strict";

const assert = require("assert");
const path = require("path");
const { schemaTools, requestTarget } = require(path.join(__dirname, "..", "..", "ledger", "static", "openapischema.js"));

const ref = (name) => ({ $ref: `#/components/schemas/${name}` });
const SPEC = {
  components: {
    schemas: {
      Status: { type: "string", enum: ["todo", "done"] },
      Ticket: { type: "object", required: ["key", "status"], properties: { key: { type: "string" }, status: ref("Status"), tags: { type: "array", items: { type: "string" } }, note: { type: "string" } } },
      Many: { type: "object", properties: { a: { type: "integer" }, b: { type: "boolean" }, c: { type: "string" }, d: { type: "number" }, e: { type: "string" } } },
      Alias: ref("Status"),
      Loop: ref("Loop"),
      Extended: { allOf: [ref("Ticket"), { type: "object", required: ["extra"], properties: { extra: { type: "integer" } } }] },
      Deep: { type: "object", required: ["a"], properties: { a: { type: "object", required: ["b"], properties: { b: { type: "object", required: ["c"], properties: { c: { type: "object", required: ["d"], properties: { d: { type: "object", required: ["e"], properties: { e: { type: "string" } } } } } } } } } } },
    },
    parameters: { Limit: { name: "limit", in: "query", schema: { type: "integer" } } },
  },
  paths: {
    "/tickets": {
      parameters: [{ $ref: "#/components/parameters/Limit" }, { in: "header" }],
      get: { tags: ["Tickets"], parameters: [{ name: "q", in: "query" }] },
      post: {},
      put: { tags: [] },
      summary: "not a method",
    },
    "/tickets/{key}": { get: { tags: ["Tickets"] }, delete: {} },
  },
};
const tools = schemaTools(SPEC);
const checks = [];
const check = (name, body) => checks.push([name, body]);

check("a schema without a reference is returned as it is and nothing becomes an empty schema", () => {
  const plain = { type: "string" };
  assert.strictEqual(tools.resolve(plain), plain);
  assert.deepStrictEqual(tools.resolve(undefined), {});
  assert.deepStrictEqual(tools.resolve(null), {});
});

check("a reference is followed, also through another reference", () => {
  assert.deepStrictEqual(tools.resolve(ref("Status")).enum, ["todo", "done"]);
  assert.deepStrictEqual(tools.resolve(ref("Alias")).enum, ["todo", "done"]);
});

check("a reference to something missing gives an empty schema", () => {
  assert.deepStrictEqual(tools.resolve(ref("Nope")), {});
  assert.deepStrictEqual(tools.resolve({ $ref: "#/a/b/c" }), {});
});

check("a reference that points at itself stops instead of looping", () => {
  const result = tools.resolve(ref("Loop"));
  assert.strictEqual(typeof result, "object");
});

check("escaped slashes and tildes in a reference are understood", () => {
  const view = schemaTools({ paths: { "/tickets": { get: { tag: 1 } } }, "a~b": { ok: true } });
  assert.deepStrictEqual(view.resolve({ $ref: "#/paths/~1tickets/get" }), { tag: 1 });
  assert.deepStrictEqual(view.resolve({ $ref: "#/a~0b" }), { ok: true });
  assert.deepStrictEqual(schemaTools({ "a~1b": { ok: 2 } }).resolve({ $ref: "#/a~01b" }), { ok: 2 });
});

check("an example prefers a given example, then the default, then the first allowed value", () => {
  assert.strictEqual(tools.exampleOf({ type: "string", example: "x", default: "d", enum: ["e"] }), "x");
  assert.strictEqual(tools.exampleOf({ type: "string", default: "d", enum: ["e"] }), "d");
  assert.strictEqual(tools.exampleOf({ type: "string", enum: ["e", "f"] }), "e");
  assert.strictEqual(tools.exampleOf({ type: "integer", example: 0 }), 0);
});

check("an object example holds only the required fields and follows references", () => {
  assert.deepStrictEqual(tools.exampleOf(ref("Ticket")), { key: "string", status: "todo" });
});

check("an object with nothing marked required shows its first four fields", () => {
  assert.deepStrictEqual(tools.exampleOf(ref("Many")), { a: 0, b: false, c: "string", d: 0 });
});

check("array, number, boolean and unknown types get a plain sample", () => {
  assert.deepStrictEqual(tools.exampleOf({ type: "array", items: { type: "integer" } }), [0]);
  assert.strictEqual(tools.exampleOf({ type: "number" }), 0);
  assert.strictEqual(tools.exampleOf({ type: "boolean" }), false);
  assert.strictEqual(tools.exampleOf({}), "string");
});

check("parts joined with allOf are merged into one example", () => {
  assert.deepStrictEqual(tools.exampleOf(ref("Extended")), { key: "string", status: "todo", extra: 0 });
});

check("very deep nesting is cut off with null", () => {
  assert.deepStrictEqual(tools.exampleOf(ref("Deep")), { a: { b: { c: { d: null } } } });
});

check("a type is named by its reference, as an array of something, or by its kind", () => {
  assert.strictEqual(tools.typeLabel(ref("Ticket")), "Ticket");
  assert.strictEqual(tools.typeLabel({ type: "array", items: ref("Ticket") }), "array of Ticket");
  assert.strictEqual(tools.typeLabel({ type: "array", items: { type: "string" } }), "array of string");
  assert.strictEqual(tools.typeLabel({ type: "integer" }), "integer");
  assert.strictEqual(tools.typeLabel({ properties: {} }), "object");
  assert.strictEqual(tools.typeLabel({}), "any");
});

check("parameters from the path and the operation are joined, resolved and need a name", () => {
  const item = SPEC.paths["/tickets"];
  assert.deepStrictEqual(tools.allParameters(item, item.get).map((p) => p.name), ["limit", "q"]);
  assert.deepStrictEqual(tools.allParameters({}, {}), []);
});

check("operations come in file order with a tag, an index and only real methods", () => {
  const operations = tools.collectOperations();
  assert.deepStrictEqual(operations.map((o) => `${o.method} ${o.path}`), ["get /tickets", "post /tickets", "put /tickets", "get /tickets/{key}", "delete /tickets/{key}"]);
  assert.deepStrictEqual(operations.map((o) => o.tag), ["Tickets", "Other", "Other", "Tickets", "Other"]);
  assert.deepStrictEqual(operations.map((o) => o.index), [0, 1, 2, 3, 4]);
});

check("a spec without paths has no operations", () => {
  assert.deepStrictEqual(schemaTools({}).collectOperations(), []);
});

const input = (where, name, value) => ({ in: where, name, value });

check("path values are put into the address, encoded", () => {
  assert.deepStrictEqual(requestTarget("/tickets/{key}", [input("path", "key", " A B/1 ")]), { target: "/tickets/A%20B%2F1", query: "", unfilled: false });
});

check("query values are added and blank ones are left out", () => {
  const request = requestTarget("/tickets", [input("query", "q", "fix it"), input("query", "limit", "  "), input("query", "status", "todo")]);
  assert.strictEqual(request.query, "q=fix+it&status=todo");
});

check("a path placeholder left empty is reported as unfilled", () => {
  assert.strictEqual(requestTarget("/tickets/{key}", [input("path", "key", "")]).unfilled, true);
  assert.strictEqual(requestTarget("/a/{x}/b/{y}", [input("path", "x", "1")]).unfilled, true);
  assert.strictEqual(requestTarget("/a", []).unfilled, false);
});

check("inputs of another kind, such as a header, are not put into the address", () => {
  assert.deepStrictEqual(requestTarget("/a", [input("header", "X-Test", "1")]), { target: "/a", query: "", unfilled: false });
});

let failed = 0;
for (const [name, body] of checks) {
  try { body(); console.log("ok   " + name); } catch (error) { failed += 1; console.log("FAIL " + name + "\n     " + String(error.message).split("\n").join("\n     ")); }
}
console.log(`${checks.length - failed} of ${checks.length} passed`);
process.exit(failed ? 1 : 0);

"use strict";

const OPENAPI_METHODS = ["get", "post", "put", "patch", "delete", "head", "options"];

function schemaTools(spec) {
  function resolve(schema, depth = 0) {
    if (schema && schema.$ref && depth < 8) {
      const parts = schema.$ref.replace(/^#\//, "").split("/");
      let node = spec;
      for (const part of parts) node = node && node[part.replace(/~1/g, "/").replace(/~0/g, "~")];
      return resolve(node || {}, depth + 1);
    }
    return schema || {};
  }

  function exampleOf(schema, depth = 0) {
    const node = resolve(schema);
    if (node.example !== undefined) return node.example;
    if (node.default !== undefined) return node.default;
    if (node.enum) return node.enum[0];
    if (depth > 3) return null;
    if (node.allOf) return Object.assign({}, ...node.allOf.map((part) => exampleOf(part, depth + 1) || {}));
    if (node.type === "object" || node.properties) {
      const properties = node.properties || {};
      const required = node.required || Object.keys(properties).slice(0, 4);
      const result = {};
      for (const name of Object.keys(properties)) if (required.includes(name)) result[name] = exampleOf(properties[name], depth + 1);
      return result;
    }
    if (node.type === "array") return [exampleOf(node.items, depth + 1)];
    if (node.type === "integer" || node.type === "number") return 0;
    if (node.type === "boolean") return false;
    return "string";
  }

  function typeLabel(schema) {
    const node = resolve(schema);
    if (schema && schema.$ref) return schema.$ref.split("/").pop();
    if (node.type === "array") return `array of ${typeLabel(node.items)}`;
    return node.type || (node.properties ? "object" : "any");
  }

  function allParameters(item, operation) {
    return [...(item.parameters || []), ...(operation.parameters || [])].map((p) => resolve(p)).filter((p) => p.name);
  }

  function collectOperations() {
    const operations = [];
    for (const [path, item] of Object.entries(spec.paths || {})) {
      for (const method of OPENAPI_METHODS.filter((m) => item && item[m])) {
        const operation = item[method];
        operations.push({ path, method, operation, item, tag: (operation.tags && operation.tags[0]) || "Other", index: operations.length });
      }
    }
    return operations;
  }

  return { resolve, exampleOf, typeLabel, allParameters, collectOperations };
}

function requestTarget(path, inputs) {
  let target = path;
  const query = new URLSearchParams();
  for (const input of inputs) {
    const value = input.value.trim();
    if (!value) continue;
    if (input.in === "path") target = target.replace(`{${input.name}}`, encodeURIComponent(value));
    else if (input.in === "query") query.set(input.name, value);
  }
  return { target, query: query.toString(), unfilled: /\{[^}]+\}/.test(target) };
}

if (typeof module !== "undefined") module.exports = { schemaTools, requestTarget, OPENAPI_METHODS };

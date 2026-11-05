"use strict";

const ACTOR_STORAGE_KEY = "ledger.actor";
const byId = (id) => document.getElementById(id);

function recall(key, fallback) {
  try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
}

async function start() {
  byId("actorInput").value = recall(ACTOR_STORAGE_KEY, "docs");
  const spec = await (await fetch("/api/openapi.json")).json();
  const view = createOpenApiView(spec, { baseUrl: location.origin, headersFor: () => ({ "X-Ledger-Actor": byId("actorInput").value.trim() || "docs" }) });
  view.render(byId("operations"));
  byId("toc").remove();
  byId("intro").remove();
  byId("models").remove();
  const hash = location.hash.slice(1);
  const target = hash && document.getElementById(hash);
  if (target) { if (target.tagName === "DETAILS") target.open = true; target.scrollIntoView(); }
}

start().catch((error) => { byId("operations").innerHTML = `<p>Could not load the specification: ${openApiEscape(error.message)}</p>`; });

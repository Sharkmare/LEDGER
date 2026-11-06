"use strict";

function pollBlocker(conditions) {
  const order = ["hidden", "typing", "dialogOpen", "editing", "dragging", "selecting"];
  return order.find((name) => conditions[name]) || null;
}

function createChangeTracker() {
  const last = new Map();
  return {
    changed(name, value) {
      const signature = JSON.stringify(value);
      if (last.get(name) === signature) return false;
      last.set(name, signature);
      return true;
    },
    forget(name) { last.delete(name); },
  };
}

if (typeof module !== "undefined") module.exports = { pollBlocker, createChangeTracker };

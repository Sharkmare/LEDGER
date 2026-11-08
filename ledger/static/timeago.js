"use strict";

function ago(stamp, nowSeconds = Date.now() / 1000) {
  if (!stamp) return "never";
  const seconds = Math.max(0, nowSeconds - stamp);
  const units = [[31536000, "year"], [2592000, "month"], [604800, "week"], [86400, "day"], [3600, "hour"], [60, "minute"]];
  for (const [size, name] of units) if (seconds >= size) { const n = Math.floor(seconds / size); return `${n} ${name}${n === 1 ? "" : "s"} ago`; }
  return "just now";
}

if (typeof module !== "undefined") module.exports = { ago };

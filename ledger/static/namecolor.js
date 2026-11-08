"use strict";

function nameColor(name) {
  let hash = 0;
  for (const character of String(name).toLowerCase()) hash = (hash * 31 + character.codePointAt(0)) % 360;
  return `hsl(${hash} 62% 62%)`;
}

if (typeof module !== "undefined") module.exports = { nameColor };

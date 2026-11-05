"use strict";

const MD_LIST_ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const MD_FENCE = /^\s*(`{3,}|~{3,})\s*([\w+#.-]*)\s*$/;
const MD_HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const MD_RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const MD_TABLE_SEPARATOR = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
const MD_CALLOUT = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/i;
const MD_CALLOUT_TITLES = { note: "Note", tip: "Tip", important: "Important", warning: "Warning", caution: "Caution" };
const MD_INLINE = new RegExp([
  "(`+)([^`]|[^`][\\s\\S]*?[^`])\\1(?!`)",
  "!\\[([^\\]]*)\\]\\(([^)\\s]+)(?:\\s+\"([^\"]*)\")?\\)",
  "\\[([^\\]]+)\\]\\(([^)\\s]+)(?:\\s+\"([^\"]*)\")?\\)",
  "\\[\\[([^\\]\\n]+)\\]\\]",
  "\\*\\*(?=\\S)(.+?)(?<=\\S)\\*\\*(?!\\*)",
  "__(?=\\S)(.+?)(?<=\\S)__(?!_)",
  "~~([^~]+?)~~",
  "\\*([^*\\s][^*]*?)\\*",
  "(?<![\\w])_([^_\\s][^_]*?)_(?![\\w])",
  "(https?:\\/\\/[^\\s<>\"']+[^\\s<>\"'.,;:!?)])",
  "\\b([A-Z][A-Z0-9]{1,9}-\\d+)\\b",
].join("|"), "g");

function mdEscape(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function mdSafeUrl(url) {
  const trimmed = String(url).trim();
  if (/^(https?:|mailto:)/i.test(trimmed)) return trimmed;
  if (/^[#/.]/.test(trimmed) || !/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) return trimmed;
  return "#";
}

function mdSafeImage(url) {
  return /^https?:/i.test(String(url).trim()) ? String(url).trim() : "";
}

function mdSlug(text) {
  const slug = String(text).toLowerCase().replace(/<[^>]*>/g, "").replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s+/g, "-");
  return slug || "section";
}

function mdInline(text, context) {
  let html = "";
  let last = 0;
  const pattern = new RegExp(MD_INLINE.source, "g");
  let match;
  while ((match = pattern.exec(text)) !== null) {
    html += mdEscape(text.slice(last, match.index));
    last = match.index + match[0].length;
    if (match[2] !== undefined) {
      html += `<code>${mdEscape(match[2].replace(/^ (.*) $/, "$1"))}</code>`;
    } else if (match[4] !== undefined) {
      const source = mdSafeImage(match[4]);
      html += source ? `<img src="${mdEscape(source)}" alt="${mdEscape(match[3])}"${match[5] ? ` title="${mdEscape(match[5])}"` : ""} loading="lazy">` : mdEscape(match[0]);
    } else if (match[7] !== undefined) {
      const href = mdSafeUrl(match[7]);
      const external = /^https?:/i.test(href);
      html += `<a href="${mdEscape(href)}"${external ? ' target="_blank" rel="noopener noreferrer"' : ""}${match[8] ? ` title="${mdEscape(match[8])}"` : ""}>${mdInline(match[6], context)}</a>`;
    } else if (match[9] !== undefined) {
      const [target, label] = match[9].split("|");
      const found = context.wiki ? context.wiki[target.trim().toLowerCase()] : undefined;
      const shown = mdEscape((label || target).trim());
      html += found
        ? `<a class="wiki" data-kb-page="${found.id}">${shown}</a>`
        : `<a class="wiki missing" data-kb-create="${mdEscape(target.trim())}" title="No page has this title yet. Click to create it.">${shown}</a>`;
    } else if (match[10] !== undefined || match[11] !== undefined) {
      html += `<strong>${mdInline(match[10] !== undefined ? match[10] : match[11], context)}</strong>`;
    } else if (match[12] !== undefined) {
      html += `<del>${mdInline(match[12], context)}</del>`;
    } else if (match[13] !== undefined || match[14] !== undefined) {
      html += `<em>${mdInline(match[13] !== undefined ? match[13] : match[14], context)}</em>`;
    } else if (match[15] !== undefined) {
      html += `<a href="${mdEscape(match[15])}" target="_blank" rel="noopener noreferrer">${mdEscape(match[15])}</a>`;
    } else if (match[16] !== undefined) {
      html += context.ticket && context.ticket(match[16])
        ? `<a class="ticket-link" data-ticket="${mdEscape(match[16])}">${mdEscape(match[16])}</a>`
        : mdEscape(match[16]);
    }
  }
  return html + mdEscape(text.slice(last));
}

function mdIndent(line) {
  return line.length - line.trimStart().length;
}

function mdStartsBlock(line, next) {
  return MD_FENCE.test(line) || MD_HEADING.test(line) || MD_RULE.test(line) || /^\s*>/.test(line) || MD_LIST_ITEM.test(line)
    || (line.includes("|") && next !== undefined && MD_TABLE_SEPARATOR.test(next));
}

function mdCells(line) {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, "|"));
}

function mdTable(lines, start, context) {
  const header = mdCells(lines[start]);
  const aligns = mdCells(lines[start + 1]).map((cell) => (cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : cell.startsWith(":") ? "left" : ""));
  let index = start + 2;
  const rows = [];
  while (index < lines.length && lines[index].trim() !== "" && lines[index].includes("|")) { rows.push(mdCells(lines[index])); index += 1; }
  const cell = (tag, text, position) => `<${tag}${aligns[position] ? ` style="text-align:${aligns[position]}"` : ""}>${mdInline(text || "", context)}</${tag}>`;
  const html = `<div class="md-table"><table><thead><tr>${header.map((text, i) => cell("th", text, i)).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${header.map((_, i) => cell("td", row[i], i)).join("")}</tr>`).join("")}</tbody></table></div>`;
  return { html, next: index };
}

function mdList(lines, start, context, headings) {
  const first = lines[start].match(MD_LIST_ITEM);
  const baseIndent = first[1].length;
  const ordered = /\d/.test(first[2]);
  const items = [];
  let index = start;
  while (index < lines.length) {
    const match = lines[index].match(MD_LIST_ITEM);
    if (!match || match[1].length !== baseIndent || /\d/.test(match[2]) !== ordered) break;
    const content = [match[3]];
    index += 1;
    const continuation = [];
    while (index < lines.length) {
      const line = lines[index];
      if (line.trim() === "") {
        let ahead = index + 1;
        while (ahead < lines.length && lines[ahead].trim() === "") ahead += 1;
        if (ahead < lines.length && mdIndent(lines[ahead]) > baseIndent) { continuation.push(""); index += 1; continue; }
        break;
      }
      if (mdIndent(line) > baseIndent) { continuation.push(line); index += 1; continue; }
      break;
    }
    const strip = Math.min(...continuation.filter((l) => l.trim() !== "").map(mdIndent), 1000);
    items.push([...content, ...continuation.map((l) => (l.trim() === "" ? "" : l.slice(strip === 1000 ? 0 : strip)))]);
  }
  const rendered = items.map((item) => {
    let task = "";
    const task_match = item[0].match(/^\[( |x|X)\]\s+(.*)$/);
    if (task_match) {
      item[0] = task_match[2];
      task = `<input type="checkbox" disabled${task_match[1] !== " " ? " checked" : ""}> `;
    }
    let inner = mdBlocks(item, context, headings);
    if ((inner.match(/<p>/g) || []).length === 1 && inner.startsWith("<p>")) inner = inner.replace(/^<p>([\s\S]*?)<\/p>/, "$1");
    return `<li${task ? ' class="task"' : ""}>${task}${inner}</li>`;
  }).join("");
  const tag = ordered ? "ol" : "ul";
  const startNumber = ordered && parseInt(first[2], 10) !== 1 ? ` start="${parseInt(first[2], 10)}"` : "";
  return { html: `<${tag}${startNumber}>${rendered}</${tag}>`, next: index };
}

function mdBlocks(lines, context, headings) {
  const out = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line.trim() === "") { index += 1; continue; }
    const fence = line.match(MD_FENCE);
    if (fence) {
      const marker = fence[1];
      const body = [];
      index += 1;
      while (index < lines.length && !(lines[index].trim().startsWith(marker[0].repeat(marker.length)) && lines[index].trim().replace(new RegExp(`^\\${marker[0]}+`), "") === "")) { body.push(lines[index]); index += 1; }
      index += 1;
      const language = fence[2] ? ` data-lang="${mdEscape(fence[2])}"` : "";
      out.push(`<div class="code-block"${language}><button type="button" class="copy-code" data-copy-code>Copy</button><pre><code>${mdEscape(body.join("\n"))}</code></pre></div>`);
      continue;
    }
    const heading = line.match(MD_HEADING);
    if (heading) {
      const text = heading[2];
      let id = mdSlug(text);
      const taken = headings.filter((h) => h.id === id || h.id.startsWith(`${id}-`)).length;
      if (taken) id = `${id}-${taken}`;
      headings.push({ level: heading[1].length, text: text.replace(/[`*_~]/g, ""), id });
      out.push(`<h${heading[1].length} id="${id}">${mdInline(text, context)}<a class="anchor" href="#${id}" data-anchor="${id}" aria-label="Link to this section">#</a></h${heading[1].length}>`);
      index += 1;
      continue;
    }
    if (MD_RULE.test(line) && !MD_LIST_ITEM.test(line)) { out.push("<hr>"); index += 1; continue; }
    if (/^\s*>/.test(line)) {
      const quoted = [];
      while (index < lines.length && /^\s*>/.test(lines[index])) { quoted.push(lines[index].replace(/^\s*> ?/, "")); index += 1; }
      const callout = quoted[0] && quoted[0].match(MD_CALLOUT);
      if (callout) {
        const kind = callout[1].toLowerCase();
        out.push(`<div class="callout callout-${kind}"><div class="callout-title">${MD_CALLOUT_TITLES[kind]}</div>${mdBlocks(quoted.slice(1), context, headings)}</div>`);
      } else {
        out.push(`<blockquote>${mdBlocks(quoted, context, headings)}</blockquote>`);
      }
      continue;
    }
    if (line.includes("|") && lines[index + 1] !== undefined && MD_TABLE_SEPARATOR.test(lines[index + 1])) {
      const table = mdTable(lines, index, context);
      out.push(table.html);
      index = table.next;
      continue;
    }
    if (MD_LIST_ITEM.test(line)) {
      const list = mdList(lines, index, context, headings);
      out.push(list.html);
      index = list.next;
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() !== "" && !mdStartsBlock(lines[index], lines[index + 1])) { paragraph.push(lines[index]); index += 1; }
    out.push(`<p>${paragraph.map((l) => mdInline(l.trim(), context)).join("<br>")}</p>`);
  }
  return out.join("\n");
}

function renderMarkdown(text, context = {}) {
  const headings = [];
  const html = mdBlocks(String(text ?? "").replace(/\r\n?/g, "\n").split("\n"), context, headings);
  return { html, headings };
}

if (typeof module !== "undefined") module.exports = { renderMarkdown, mdEscape, mdSafeUrl };

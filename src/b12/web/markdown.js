"use strict";
// Minimal, safe Markdown for model replies. Output is DOM nodes built with textContent:
// nothing from the model is ever parsed as HTML. Supports paragraphs, headings, bullet and
// numbered lists, fenced code, `inline code`, **bold** and *italic*. Links stay plain text.

function mdNode(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*)/;

function mdInline(text, parent) {
  for (const part of text.split(INLINE)) {
    if (!part) continue;
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      parent.append(mdNode("code", part.slice(1, -1)));
    } else if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      parent.append(mdNode("strong", part.slice(2, -2)));
    } else if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
      parent.append(mdNode("em", part.slice(1, -1)));
    } else {
      parent.append(document.createTextNode(part));
    }
  }
  return parent;
}

function renderMarkdown(source) {
  const root = document.createDocumentFragment();
  const lines = String(source ?? "").replace(/\r\n?/g, "\n").split("\n");
  let paragraph = [];
  let list = null;
  let listKind = null;
  let fence = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const p = mdNode("p");
    paragraph.forEach((line, i) => {
      if (i) p.append(mdNode("br"));
      mdInline(line, p);
    });
    root.append(p);
    paragraph = [];
  };
  const flushList = () => {
    if (list) root.append(list);
    list = null;
    listKind = null;
  };

  for (const line of lines) {
    if (fence !== null) {
      if (/^\s*```/.test(line)) {
        const pre = mdNode("pre");
        pre.append(mdNode("code", fence.join("\n")));
        root.append(pre);
        fence = null;
      } else fence.push(line);
      continue;
    }
    if (/^\s*```/.test(line)) {
      flushParagraph();
      flushList();
      fence = [];
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (!line.trim()) {
      flushParagraph();
      flushList();
    } else if (heading) {
      flushParagraph();
      flushList();
      const h = mdNode(heading[1].length <= 2 ? "h3" : "h4");
      mdInline(heading[2], h);
      root.append(h);
    } else if (bullet || ordered) {
      flushParagraph();
      const kind = bullet ? "ul" : "ol";
      if (listKind !== kind) {
        flushList();
        list = mdNode(kind);
        listKind = kind;
      }
      const item = mdNode("li");
      mdInline((bullet || ordered)[1], item);
      list.append(item);
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  if (fence !== null) {
    const pre = mdNode("pre");
    pre.append(mdNode("code", fence.join("\n")));
    root.append(pre);
  }
  flushParagraph();
  flushList();
  return root;
}

// The conversation as chat: your words, the agent's words, and the tool calls
// between them as cards that change state when the gate decides.

import { $, copyText, fmtShort, h, reduceMotion, restartAnimation, svgIcon, toast } from "./shell.js";
import { jsonBlock } from "./trace.js";

export class TranscriptView {
  constructor() {
    this.list = $("tx");
    this.scroller = $("tx-scroll");
    this.empty = $("tx-empty");
    this.jump = $("tx-jump");
    this.segments = new Map();
    this.chips = new Map();
    this.group = null;
    this.dots = null;
    this.dotsTimer = 0;
    this.base = null;
    this.stick = true;
    this.scroller.addEventListener("scroll", () => {
      this.stick = this.scroller.scrollHeight - this.scroller.scrollTop - this.scroller.clientHeight < 40;
      if (this.stick) this.jump.classList.remove("show");
    });
    this.jump.addEventListener("click", () => { this.stick = true; this.scrollToEnd(true); this.jump.classList.remove("show"); });
    $("tx-copy")?.addEventListener("click", () => {
      const text = this.text();
      if (!text) { toast("The transcript is empty"); return; }
      copyText(text, "Transcript copied");
    });
    $("tx-clear")?.addEventListener("click", () => this.clear());
  }

  setBase(time) { this.base = time; }

  stamp(time) {
    return this.base === null ? "" : fmtShort(time - this.base);
  }

  ensureGroup(role, time) {
    if (this.group && this.group.role === role && this.list.lastElementChild === this.group.node) return this.group;
    const node = h("li", "msg " + role);
    const avatar = h("div", "avatar " + role, role === "user" ? "YOU" : "");
    const body = h("div", "msg-body");
    const meta = h("div", "msg-meta");
    meta.append(h("b", null, role === "user" ? "You" : "Interra"), h("time", null, this.stamp(time)));
    body.append(meta);
    node.append(avatar, body);
    this.list.append(node);
    this.group = { role, node, body, meta };
    return this.group;
  }

  upsert(id, role, text, { final = false, time = Date.now() / 1000, interrupted = false } = {}) {
    let segment = this.segments.get(id);
    if (!segment) {
      if (!text) return;
      if (role === "agent") this.removeDots();
      const group = this.ensureGroup(role, time);
      const bubble = h("div", "bubble");
      group.body.append(bubble);
      segment = { id, role, bubble, group, text: "", final: false, time };
      this.segments.set(id, segment);
    }
    segment.text = text;
    segment.final = final;
    segment.bubble.textContent = text;
    segment.bubble.classList.toggle("interim", role === "user" && !final);
    segment.bubble.classList.toggle("streaming", role === "agent" && !final);
    segment.group.node.classList.toggle("streaming", role === "agent" && !final);
    if (interrupted) this.tag(segment.group, "interrupted");
    this.changed();
  }

  tag(group, label) {
    if (group.meta.querySelector(".tag[data-label='" + label + "']")) return;
    const tag = h("span", "tag warn", label);
    tag.dataset.label = label;
    group.meta.append(tag);
  }

  markInterrupted(role) {
    const segments = [...this.segments.values()].filter((segment) => segment.role === role);
    const last = segments[segments.length - 1];
    if (last) this.tag(last.group, "interrupted");
  }

  showDots(time) {
    clearTimeout(this.dotsTimer);
    if (this.dots) return;
    const group = this.ensureGroup("agent", time ?? Date.now() / 1000);
    const dots = h("div", "bubble speaking-dots");
    dots.append(h("i"), h("i"), h("i"));
    dots.setAttribute("aria-label", "The agent is speaking");
    group.body.append(dots);
    group.node.classList.add("streaming");
    this.dots = { node: dots, group };
    this.changed();
  }

  removeDots() {
    clearTimeout(this.dotsTimer);
    if (!this.dots) return;
    const { node, group } = this.dots;
    node.remove();
    group.node.classList.remove("streaming");
    if (!group.body.querySelector(".bubble")) {
      group.node.remove();
      if (this.group === group) this.group = null;
    }
    this.dots = null;
    this.changed();
  }

  removeDotsSoon() {
    clearTimeout(this.dotsTimer);
    this.dotsTimer = setTimeout(() => this.removeDots(), 1500);
  }

  /** A card for a tool call or another event; the same key updates it in place. */
  chip(key, kind, title, content, { icon = "info", time = Date.now() / 1000, details, note } = {}) {
    let chip = this.chips.get(key);
    if (!chip) {
      chip = { node: h("li", "event-chip"), time };
      this.chips.set(key, chip);
      this.list.append(chip.node);
      this.group = null;
    } else {
      restartAnimation(chip.node, "flash");
    }
    chip.kind = kind;
    chip.title = title;
    const text = h("div", "chip-text");
    if (content instanceof Node) text.append(content.cloneNode(true));
    else text.textContent = content;
    chip.text = text.textContent;
    chip.node.dataset.kind = kind;
    const head = h("div", "chip-head");
    head.append(h("b", null, title), h("time", null, this.stamp(chip.time)));
    const parts = [svgIcon(icon, "ic sm"), head, text];
    if (note) parts.push(h("div", "chip-note", note));
    if (details !== undefined && details !== null) {
      const more = h("details");
      more.append(h("summary", null, "Details"), jsonBlock(details));
      parts.push(more);
    }
    chip.node.replaceChildren(...parts);
    this.changed();
  }

  changed() {
    this.empty.hidden = this.list.children.length > 0;
    if (this.stick) this.scrollToEnd(false);
    else this.jump.classList.add("show");
  }

  scrollToEnd(smooth) {
    this.scroller.scrollTo({ top: this.scroller.scrollHeight, behavior: smooth && !reduceMotion ? "smooth" : "auto" });
  }

  clear() {
    this.segments.clear();
    this.chips.clear();
    this.group = null;
    this.dots = null;
    clearTimeout(this.dotsTimer);
    this.list.replaceChildren();
    this.stick = true;
    this.jump.classList.remove("show");
    this.changed();
  }

  text() {
    const lines = [];
    for (const node of this.list.children) {
      if (node.classList.contains("event-chip")) {
        const chip = [...this.chips.values()].find((item) => item.node === node);
        if (chip) lines.push("[" + this.stamp(chip.time) + "] · " + chip.title + " " + chip.text);
        continue;
      }
      const role = node.classList.contains("user") ? "You" : "Interra";
      for (const segment of this.segments.values()) {
        if (segment.group.node === node) lines.push("[" + this.stamp(segment.time) + "] " + role + ": " + segment.text);
      }
    }
    return lines.join("\n");
  }
}

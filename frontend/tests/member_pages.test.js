/**
 * member_pages.test.js — regression suite cho 6 trang member
 * (audit luồng thành viên 1114efd: M02/M03/M04/M06/M07/M10).
 *
 * Cách chạy:  node frontend/tests/member_pages.test.js
 *
 * Chiến lược (giống nonce.test.js): trích inline script THẬT từ HTML,
 * chèn điểm expose trong sandbox (KHÔNG sửa trang gốc), chạy với DOM stub
 * + ApiClient/Auth/Toast stub theo kịch bản. member-shell.js được nạp
 * NGUYÊN FILE (không stub) để test hành vi thật của MemberModal/MemberShell.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const MEMBER = path.join(ROOT, "member");

let pass = 0, fail = 0;
function assert(cond, name) {
  if (cond) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}`); }
}

/* ------------------------------------------------------------------ */
/* Mini-DOM stub đủ dùng cho inline script member                     */
/* ------------------------------------------------------------------ */
/* innerHTML parser tối giản: chỉ đủ cho markup modal (div/button/input/
   iframe/label/p/h3/span + data-* + class/id). KHÔNG phải DOM thật. */
function parseHTML(html) {
  const VOID = new Set(["input", "img", "br", "hr"]);
  const root = makeElTagged("__parse_root", "#root");
  const stack = [root];
  const re = /<\/?([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^<>]*?)?)\/?>/g;
  let m;
  while ((m = re.exec(String(html))) !== null) {
    const closing = m[0].startsWith("</");
    const tag = m[1].toLowerCase();
    const attrs = m[2] || "";
    if (closing) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    const e = makeElTagged("", tag);
    const cls = (attrs.match(/class="([^"]*)"/) || [])[1];
    const id = (attrs.match(/id="([^"]*)"/) || [])[1];
    if (cls) { e.className = cls; cls.split(/\s+/).forEach((c) => c && e.classList.add(c)); }
    if (id) { e.id = id; }
    for (const dm of attrs.matchAll(/data-([a-z-]+)="([^"]*)"/g)) {
      const key = dm[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      e.dataset[key] = dm[2];
    }
    const cur = stack[stack.length - 1];
    cur.children.push(e); e.parent = cur;
    if (!VOID.has(tag) && !m[0].endsWith("/>")) stack.push(e);
  }
  return root.children;
}

function makeEl(id) {
  const el = {
    id, style: {}, value: "", dataset: {}, children: [], parent: null,
    _text: "", _html: "", disabled: false, hidden: false, tabIndex: -1,
    offsetParent: null, className: "", _listeners: {},
    addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); },
    removeEventListener(type, fn) { this._listeners[type] = (this._listeners[type] || []).filter((f) => f !== fn); },
    dispatch(type, ev = {}) {
      ev.preventDefault = ev.preventDefault || (() => {});
      ev.stopPropagation = ev.stopPropagation || (() => {});
      (this._listeners[type] || []).forEach((fn) => fn(ev));
    },
    focus(opts) { el.__focused = true; el.__focusOpts = opts; },
    blur() {},
    click() { this.dispatch("click"); },
    scrollIntoView() {},
    classList: {
      _set: new Set(),
      add(...c) { c.forEach((x) => this._set.add(x)); },
      remove(...c) { c.forEach((x) => this._set.delete(x)); },
      toggle(c, on) { on ? this._set.add(c) : this._set.delete(c); },
      contains(c) { return this._set.has(c); },
    },
    setAttribute(k, v) { this[k] = v; },
    getAttribute(k) { return this[k] ?? null; },
    removeAttribute(k) { delete this[k]; },
    appendChild(c) { this.children.push(c); c.parent = this; return c; },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((x) => x !== this); },
    contains(x) { return x === this || this.children.includes(x); },
    querySelector(sel) { return miniQuery([this], sel)[0] || null; },
    querySelectorAll(sel) { return miniQuery([this], sel); },
  };
  Object.defineProperty(el, "textContent", { get: () => el._text, set: (v) => { el._text = String(v); } });
  Object.defineProperty(el, "innerHTML", { get: () => el._html, set: (v) => { el._html = String(v); el.children = parseHTML(v); el.children.forEach((c) => { c.parent = el; }); } });
  Object.defineProperty(el, "textContentAndHtml", { get: () => el._text + el._html });
  return el;
}

/* selector mini: hỗ trợ ".class", "#id", "tag", "[attr]", và TỔ HỢP hậu duệ
   (".modal-body input") — đủ cho markup modal member pages */
function miniQuery(roots, sel) {
  const out = [];
  const parts = sel.split(",").map((s) => s.trim()).filter(Boolean);
  const visit = (node) => {
    for (const c of node.children || []) { visit(c); }
    for (const part of parts) {
      if (matchCompound(node, part)) { out.push(node); break; }
    }
  };
  roots.forEach(visit);
  return out;
}
function matchCompound(node, part) {
  const segs = part.split(/\s+/); // hậu duệ: segment cuối = node, các trước = tổ tiên
  let cur = node;
  for (let i = segs.length - 1; i >= 0; i--) {
    if (!matches(cur, segs[i])) return false;
    cur = cur.parent;
    if (cur == null && i > 0) return false;
  }
  return true;
}
function matches(el, part) {
  if (part.startsWith("#")) return el.id === part.slice(1);
  if (part.startsWith(".")) {
    const cls = part.slice(1);
    if (el.classList.contains(cls)) return true;
    if ((el.className || "").split(/\s+/).includes(cls)) return true;
    return false;
  }
  if (part.startsWith("[")) {
    const m = part.slice(1, -1);
    const eq = m.indexOf("=");
    const camelize = (s) => s.replace(/^data-/, "").replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    if (eq === -1) return el.dataset && el.dataset[camelize(m)] != null;
    const key = camelize(m.slice(0, eq));
    const val = m.slice(eq + 1).replace(/"/g, "");
    return el.dataset && el.dataset[key] === val;
  }
  return el.__tag === part;
}
function makeElTagged(id, tag) { const e = makeEl(id); e.__tag = tag; return e; }

/* ------------------------------------------------------------------ */
/* Sandbox tổng: HTML thật + member-shell.js thật + stubs              */
/* ------------------------------------------------------------------ */
function extractInlineScript(htmlPath) {
  const html = fs.readFileSync(htmlPath, "utf8");
  const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  if (!blocks.length) throw new Error("Không có inline script: " + htmlPath);
  return blocks.reduce((a, b) => (b.length > a.length ? b : a));
}

function makeMemberSandbox(pageFile, { exposeCode, api } = {}) {
  api = api || { calls: [] };
  if (!api.calls) api.calls = [];
  const source = extractInlineScript(path.join(MEMBER, pageFile));
  let patched = source;
  if (exposeCode) {
    const lastIdx = patched.lastIndexOf("})();");
    if (lastIdx === -1) throw new Error("Không tìm thấy terminator IIFE");
    const hasOuterIife = /\(function \(\) \{/.test(patched);
    if (hasOuterIife) {
      // checkin/home: script bọc trong (function(){...})(); — chèn expose
      // TRƯỚC terminator NGOÀI (sau boot IIFE) để nằm trong closure có toàn bộ hàm.
      patched = patched.slice(0, lastIdx) + exposeCode + "\n" + patched.slice(lastIdx);
    } else {
      // 5 trang còn lại: script TOP-LEVEL (hàm là khai báo top-level) — chèn
      // expose SAU boot IIFE (cuối script) để chạy được (boot return sớm vì
      // requireRole reject, expose top-level vẫn chạy và nhìn thấy hàm).
      patched = patched + "\n" + exposeCode + "\n";
    }
  }

  const elements = new Map();
  const seq = { n: 0 };
  const el = (id, tag) => {
    if (!elements.has(id)) {
      const e = makeElTagged(id, tag || "div");
      e.querySelector = function (sel) { return miniQuery([this], sel)[0] || null; };
      e.querySelectorAll = function (sel) { return miniQuery([this], sel); };
      elements.set(id, e);
    }
    return elements.get(id);
  };

  const docListeners = {};
  const bodyEl = el("__body", "body");
  bodyEl.contains = (x) => x.parent === bodyEl || bodyEl.children.includes(x);
  const documentStub = {
    getElementById: (id) => el(String(id)),
    querySelector: (sel) => miniQuery([bodyEl], sel)[0] || null,
    querySelectorAll: (sel) => miniQuery([bodyEl], sel),
    createElement: (tag) => { const e = makeElTagged("anon-" + ++seq.n, tag); e.querySelector = function (sel) { return miniQuery([this], sel)[0] || null; }; e.querySelectorAll = function (sel) { return miniQuery([this], sel); }; return e; },
    addEventListener: (t, fn) => { (docListeners[t] ||= []).push(fn); },
    removeEventListener: (t, fn) => { docListeners[t] = (docListeners[t] || []).filter((f) => f !== fn); },
    body: bodyEl,
    activeElement: null,
  };

  const sb = {
    console: { error: () => {}, log: () => {}, warn: () => {} },
    document: documentStub,
    localStorage: (() => { const s = {}; return {
      getItem: (k) => (k in s ? s[k] : null), setItem: (k, v) => { s[k] = String(v); }, removeItem: (k) => { delete s[k]; },
    }; })(),
    location: { protocol: "https:", origin: "https://clbip.test", pathname: "/frontend/member/" + pageFile, search: "", href: "https://clbip.test/frontend/member/" + pageFile, replaceState: () => {} },
    history: { replaceState: () => {} },
    navigator: { geolocation: { getCurrentPosition: (ok, err) => { (api && api.geo ? api.geo(ok, err) : err && err({ message: "denied" })); } } },
    URL: { createObjectURL: () => "blob:test-" + ++seq.n, revokeObjectURL: () => {} },
    AbortController: class { constructor() { this.signal = { aborted: false, addEventListener() {} }; } abort() { this.signal.aborted = true; } },
    setTimeout: (fn) => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
    Date, Math, JSON, Number, String, Array, Object, Promise, isNaN, parseFloat, parseInt, RegExp, Error,
    confirm: () => true,
    // api.js thật — fetch stub theo kịch bản
    fetch: async (url, opts = {}) => {
      const call = { url: String(url), method: opts.method || "GET", opts };
      api.calls.push(call);
      if (api.onFetch) return api.onFetch(call);
      return { ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => ({ success: true, data: {}, message: "ok" }), blob: async () => ({ size: 1 }) };
    },
    FormData: class { append() {} },
    Blob: class {},
    btoa: (s) => Buffer.from(String(s)).toString("base64"),
    screen: { width: 1920, height: 1080 },
    __calls: api.calls,
  };
  sb.window = sb;

  vm.createContext(sb);
  // member-shell.js NGUYÊN (MemberModal + MemberShell thật)
  const shellSrc = fs.readFileSync(path.join(ROOT, "js", "member-shell.js"), "utf8");
  vm.runInContext(shellSrc, sb);
  // toast stub (member-shell không cần, nhưng trang có thể gọi)
  sb.Toast = api.Toast || { success: () => {}, error: () => {}, warning: () => {}, info: () => {} };
  // Auth stub — boot guard dừng ngay (không chạy init tự động)
  sb.Auth = api.Auth || { requireRole: () => Promise.reject(new Error("stop")), cachedUser: () => (api.cachedUser || { id: 9, email: "t@clb.vn", ho_ten: "Test", xp_points: 0, current_level: 1, streak_count: 0 }), logout: () => {} };
  // ApiClient stub theo kịch bản (nếu trang cần ngoài fetch-level)
  if (api.ApiClient) sb.ApiClient = api.ApiClient;
  else sb.ApiClient = {
    get: async (ep, params) => api.get ? api.get(ep, params) : {},
    getList: async (ep, params) => api.getList ? api.getList(ep, params) : { items: [], pagination: null },
    post: async (ep, body, opts) => api.post ? api.post(ep, body, opts) : {},
    patch: async (ep, body) => api.patch ? api.patch(ep, body) : {},
    getBlob: async (ep) => api.getBlob ? api.getBlob(ep) : { size: 1 },
    download: async () => {},
    getAccessToken: () => "tok",
    getRefreshToken: () => "r",
  };
  sb.Icons = api.Icons || { render: () => "<svg/>", has: () => true };
  sb.Utils = api.Utils || {
    escapeHtml: (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
    fmtNum: (n) => String(n), fmtDateTime: (s) => String(s || ""), fmtDate: (s) => String(s || ""), fmtTime: (s) => String(s || ""),
    timeAgo: (s) => String(s || ""), initials: (n) => String(n || "?").slice(0, 1),
    debounce: (fn) => fn, guard: (fn) => fn,
    qs: () => null, qsa: (sel, root) => [],
    skeleton: () => {}, empty: (container, opts) => { sb.__lastEmpty = opts; },
    btnLoading: () => () => {}, badge: (t, tone) => `<span class="badge">${t}</span>`,
    getQueryParam: (n) => null,
  };
  sb.Celebrate = { cheer: () => {}, at: () => {} };
  sb.QRCode = function () {};
  sb.QRCode.CorrectLevel = { M: 0 };
  sb.__clbipExpose = (obj) => { sb.__test = obj; };
  sb.__docListeners = docListeners;

  vm.runInContext(patched, sb);
  return { sb, test: sb.__test, el, elements, docListeners };
}

(async () => {
/* ================================================================== */
/* M10 — profile: computeLevelProgress theo bảng backend               */
/* ================================================================== */
{
  const { sb } = makeMemberSandbox("profile.html", {
    exposeCode: "__clbipExpose({ computeLevelProgress, paintLevel, paintRing });",
  });
  const t = sb.__test;
  const cases = [
    [0, 1, 0, 100, 0, false], [50, 1, 50, 50, 50, false], [99, 1, 99, 1, 99, false],
    [100, 2, 0, 150, 0, false], [249, 2, 149, 1, 99, false], [250, 3, 0, 250, 0, false],
    [499, 3, 249, 1, 100, false], [500, 4, 0, 400, 0, false], [1400, 6, 0, 600, 0, false],
    [4999, 9, 1199, 1, 100, false], [5000, 10, 0, null, 100, true], [6000, 10, 1000, null, 100, true],
  ];
  for (const [xp, lv, into, toNext, pct, max] of cases) {
    const p = t.computeLevelProgress(xp);
    assert(p.current_level === lv && p.xp_into_level === into && p.xp_to_next === toNext
      && p.progress_percent === pct && p.max_level === max,
      `M10 biên xp=${xp} → Lv${lv} into=${into} next=${toNext} pct=${pct} max=${max}`);
  }
  // paintLevel max level KHÔNG gợi Level 11
  t.paintLevel(5200, 10, 3, null);
  const note = sb.document.getElementById("lvl-note").textContent;
  assert(/CẤP TỐI ĐA/.test(note) && !/Level 11/.test(note), "M10 max level không gợi Level 11");
  // 50 XP phải còn đúng 50 tới Level 2 (QA ví dụ)
  t.paintLevel(50, 1, 1, null);
  assert(/Còn 50 XP nữa lên Level 2/.test(sb.document.getElementById("lvl-note").textContent), "M10 50 XP → còn 50 lên Lv2");
}

/* ================================================================== */
/* M04 — checkin: multi-session + reset khi đổi phiên + payload M05     */
/* ================================================================== */
{
  const sessions = [
    { id: 11, ten_phien: "Phiên A", vi_do: 16.4637, kinh_do: 107.5909, ban_kinh_m: 50, trang_thai: "OPEN", hieu_luc_den: new Date(Date.now() + 3600e3).toISOString(), event_ten: "EV1" },
    { id: 22, ten_phien: "Phiên B", vi_do: 16.4637, kinh_do: 107.5909, ban_kinh_m: 50, trang_thai: "OPEN", hieu_luc_den: new Date(Date.now() + 3600e3).toISOString(), event_ten: null },
  ];
  let posted = null;
  const { sb, test, el } = makeMemberSandbox("checkin.html", {
    exposeCode: "__clbipExpose({ state, loadAllOpenSessions, renderSessionPicker, selectSession, doCheckIn, updateSubmitState });",
    api: {
      calls: [],
      getList: async (ep, params) => {
        if (String(ep).includes("sessions")) return { items: sessions, pagination: { page: 1, total_pages: 1, total_items: sessions.length } };
        return { items: [], pagination: null };
      },
      post: async (ep, body) => { posted = { ep, body }; return { trang_thai: "CO_MAT", xp_gained: 50, streak_count: 2 }; },
    },
    Icons: { render: () => "<svg/>", has: () => true },
  });
  const t = test;
  // init chưa chạy (requireRole reject) — gọi thủ công
  await t.loadAllOpenSessions();
  assert(sb.__test.state.sessions.length === 2, "M04 nạp đủ 2 phiên OPEN");
  t.renderSessionPicker();
  const picker = el("session-picker").innerHTML;
  assert(/Phiên A/.test(picker) && /Phiên B/.test(picker), "M04 picker hiện cả 2 phiên");
  // chọn phiên B → reset nonce/position/submitted
  sb.__test.state.nonce = "123456";
  sb.__test.state.position = { latitude: 1, longitude: 1, accuracy: 5 };
  sb.__test.state.distance = 10;
  const nonceInput = el("nonce-input");
  nonceInput.value = "123456";
  await t.selectSession(sessions[1]);
  assert(nonceInput.value === "" && sb.__test.state.nonce === "" && sb.__test.state.position === null && sb.__test.state.submitted === false,
    "M04 đổi phiên reset nonce/position/submitted");
  // doCheckIn: payload KHÔNG is_mock, CÓ accuracy, đúng session
  sb.__test.state.session = sessions[0];
  sb.__test.state.position = { latitude: 16.46379, longitude: 107.5909, accuracy: 9 };
  sb.__test.state.distance = 5;
  sb.__test.state.nonce = "654321";
  el("btn-checkin").disabled = false;
  await t.doCheckIn();
  assert(posted && posted.ep === "/attendance/check-in/", "M04/M05 POST đúng endpoint");
  assert(posted && !("is_mock" in posted.body), "M05 payload KHÔNG hardcode is_mock");
  assert(posted && posted.body.accuracy === 9 && posted.body.session_id === 11, "M05 payload accuracy + session_id đúng");
  // accuracy không hợp lệ → KHÔNG post
  posted = null;
  sb.__test.state.position = { latitude: 1, longitude: 1, accuracy: null };
  await t.doCheckIn();
  assert(posted === null, "M05 accuracy null → chặn trước khi POST");
}

/* ================================================================== */
/* M02 — events: tab Vé của tôi độc lập pagination trang events         */
/* ================================================================== */
{
  // 25 sự kiện trang 1 (page_size 20 → sự kiện id 1..5 ở trang 2);
  // member có vé của sự kiện id=1 (ngoài trang 1)
  const eventsP1 = Array.from({ length: 20 }, (_, i) => ({
    id: 25 - i, ten_hoat_dong: "Sự kiện trang 1 #" + (25 - i), trang_thai: "OPEN_REGISTRATION",
    thoi_gian_bat_dau: new Date().toISOString(), dia_diem: "Huế", loai_hd: "WORKSHOP",
    so_luong_toi_da: 100, registered_count: 1,
  }));
  const ticketEv1 = {
    id: 900, ma_ve: "VE-E2EVE00003", trang_thai: "REGISTERED", event: 1,
    event_ten: "E2EVE00003 — Sự kiện trang 2", member_ten: "Test",
    event_thoi_gian_bat_dau: new Date(Date.now() + 86400e3).toISOString(),
    event_thoi_gian_ket_thuc: new Date(Date.now() + 2 * 86400e3).toISOString(),
    event_dia_diem: "Phòng E2E", event_trang_thai: "OPEN_REGISTRATION", event_loai_hd: "HACKATHON",
  };
  const { sb, test } = makeMemberSandbox("events.html", {
    exposeCode: "__clbipExpose({ state, loadEvents, loadTickets, switchTab, renderMineTickets, updateMineCount, visibleTickets, ticketTotalPages });",
    api: {
      calls: [],
      getList: async (ep) => String(ep).includes("/events/")
        ? { items: eventsP1, pagination: { page: 1, total_pages: 2, total_items: 25 } }
        : { items: [], pagination: null },
      get: async (ep) => String(ep).includes("my-tickets") ? [ticketEv1] : {},
    },
  });
  const t = test;
  await t.loadEvents(1);
  await t.loadTickets();
  t.switchTab("mine");
  assert(t.state.tab === "mine", "M02 chuyển tab mine");
  const shown = t.visibleTickets();
  assert(shown.length === 1 && shown[0].event === 1, "M02 vé sự kiện NGOÀI trang 1 vẫn hiện (bản cũ intersect → mất)");
  const html = sb.document.getElementById("event-list").innerHTML;
  assert(/Sự kiện trang 2/.test(html) && /VE-E2EVE00003/.test(html), "M02 card vé dựng từ metadata của vé (tên + mã)");
  assert(/Phòng E2E/.test(html), "M02 card vé có địa điểm từ metadata");
  assert(!sb.__lastEmpty, "M02 KHÔNG rơi vào empty state “Bạn chưa có vé nào”");
  // pagination vé: 25 vé → 2 trang
  t.state.tickets = Array.from({ length: 25 }, (_, i) => ({ ...ticketEv1, id: i + 1, ma_ve: "VE-" + i }));
  t.state.ticketPage = 1;
  t.renderMineTickets();
  assert(t.ticketTotalPages() === 2 && t.visibleTickets().length === 20, "M02 pagination vé riêng 20/trang");
  t.state.ticketPage = 2;
  t.renderMineTickets();
  assert(t.visibleTickets().length === 5, "M02 trang vé 2 còn 5 vé");
}

/* ================================================================== */
/* M03 — documents: preview qua /preview/ endpoint + revoke lifecycle   */
/* ================================================================== */
{
  let revoked = 0;
  const { sb, test } = makeMemberSandbox("documents.html", {
    exposeCode: "__clbipExpose({ onPreview, state });",
    api: {
      calls: [],
      getBlob: async (ep) => { sb.__previewEndpoint = ep; return { size: 1024 }; },
    },
  });
  sb.URL.revokeObjectURL = () => { revoked++; };
  const doc = { id: 7, tieu_de: "Tài liệu M03", file: "/media/docs/x.pdf", file_type: "pdf", file_size: 1024 };
  await test.onPreview(doc);
  assert(sb.__previewEndpoint === "/documents/7/preview/", "M03 gọi /documents/{id}/preview/ (endpoint có auth)");
  const fetchCalls = sb.__calls.filter((c) => String(c.url).includes("/media/") || String(c.url).includes("x.pdf"));
  assert(fetchCalls.length === 0, "M03 KHÔNG fetch doc.file trực tiếp");
  assert(sb.document.body.children.some((c) => /pdf-frame/.test(c.innerHTML || "")), "M03 mở modal iframe blob");
  const backdrop = sb.document.body.children.find((c) => /pdf-frame/.test(c.innerHTML || ""));
  const closeBtn = backdrop.querySelector(".modal-close");
  closeBtn.click();
  assert(revoked === 1, "M07/M03 đóng modal → revokeObjectURL đúng 1 lần (không rò rỉ)");
}

/* ================================================================== */
/* M06 — member-shell: refreshGamification paint + giữ số khi lỗi       */
/* ================================================================== */
{
  const sb = { console: { error: () => {}, log: () => {} }, document: null, localStorage: (() => { const s = { clbip_user_info: JSON.stringify({ id: 9, email: "t@clb.vn" }) }; return { getItem: (k) => s[k] ?? null, setItem: (k, v) => { s[k] = v; }, removeItem: (k) => { delete s[k]; } }; })(), };
  const ids = ["sb-level", "sb-xp", "me-level", "pill-streak", "pill-streak-text", "pill-xp", "pill-xp-text"];
  const els = {};
  ids.forEach((id) => { const e = { style: {}, textContent: "" }; els[id] = e; sb[id] = e; });
  const apiResponses = [
    { xp: 50, level: 2, streak_count: 3, level_progress: { current_level: 2, xp_to_next: 50, progress_percent: 33, max_level: false } },
  ];
  sb.ApiClient = {
    get: async () => { if (apiResponses.length) return apiResponses.shift(); throw new Error("network"); },
  };
  sb.document = { getElementById: (id) => sb[id] || null };
  sb.window = sb;
  sb.__clbipExpose = (o) => { sb.__shell = o; };
  const vm2 = require("vm");
  vm2.createContext(sb);
  vm2.runInContext(fs.readFileSync(path.join(ROOT, "js", "member-shell.js"), "utf8"), sb);

  await sb.MemberShell.refreshGamification();
  assert(sb["sb-level"].textContent === "Lv.2", "M06 sidebar level cập nhật");
  assert(sb["sb-xp"].textContent.includes("50") && sb["sb-xp"].textContent.includes("còn 50"), "M06 sidebar XP + còn bao nhiêu lên level sau");
  assert(sb["pill-xp-text"].textContent.includes("50") && sb["pill-streak-text"].textContent.includes("3 ngày"), "M06 topbar pill XP + streak");
  // fetch lỗi → GIỮ số cũ, không ghi 0
  const before = sb["pill-xp-text"].textContent;
  await sb.MemberShell.refreshGamification();
  assert(sb["pill-xp-text"].textContent === before, "M06 fetch lỗi giữ số cũ (không ghi 0)");
  // single-flight: 2 call song song khi đang lỗi → fetch chỉ 1 lần thêm
  let fetchCount = 0;
  sb.ApiClient.get = async () => { fetchCount++; throw new Error("x"); };
  await Promise.all([sb.MemberShell.refreshGamification(), sb.MemberShell.refreshGamification()]);
  assert(fetchCount === 1, "M06 single-flight chống double-fetch");
}

/* ================================================================== */
/* M07 — MemberModal: Escape + focus trap + trả focus + scroll lock    */
/* ================================================================== */
{
  const sb = { console: { error: () => {} } };
  const docListeners = {};
  const bodyEl = makeElTagged("__body", "body");
  bodyEl.style.overflow = ""; // DOM thật: style.overflow luôn là string
  const elements = [];
  sb.document = {
    createElement: (tag) => { const e = makeElTagged("m" + elements.length, tag); elements.push(e); return e; },
    addEventListener: (t, fn) => { (docListeners[t] ||= []).push(fn); },
    removeEventListener: (t, fn) => { docListeners[t] = (docListeners[t] || []).filter((f) => f !== fn); },
    body: bodyEl,
    contains: () => true,
    activeElement: null,
    getElementById: (id) => null,
  };
  bodyEl.contains = (x) => bodyEl.children.includes(x) || x === bodyEl;
  sb.Utils = { escapeHtml: (s) => String(s) };
  sb.Icons = { render: () => "<svg/>" };
  sb.window = sb;
  const vm2 = require("vm");
  vm2.createContext(sb);
  vm2.runInContext(fs.readFileSync(path.join(ROOT, "js", "member-shell.js"), "utf8"), sb);
  const openModal = sb.MemberModal.open;

  const opener = makeEl("opener-btn"); opener.__focused = false;
  sb.document.activeElement = opener;
  const html = `<button class="btn btn-primary primary-btn">OK</button><input id="first-input"/>`;
  const api = openModal({ title: "Test M07", bodyHTML: html, footerHTML: "" });
  const backdrop = api.el;
  assert(!!backdrop.querySelector(".modal"), "M07 modal markup parse được (.modal)");
  assert(bodyEl.children.includes(backdrop), "M07 modal gắn vào body");
  assert(backdrop.querySelectorAll(".modal-close, [data-close]").length >= 1, "M07 nút đóng được query");
  assert(sb.document.body.style.overflow === "hidden", "M07 khóa scroll nền");
  // modal focus input (target: input đầu trong modal-body)
  const targetInput = backdrop.querySelector("#first-input");
  assert(!!targetInput && targetInput.__focused === true, "M07 focus vào input trong modal");
  // Escape → đóng
  (docListeners.keydown || []).forEach((f) => f({ key: "Escape", stopPropagation: () => {}, preventDefault: () => {} }));
  assert(!bodyEl.children.includes(backdrop), "M07 Escape đóng modal (remove khỏi body)");
  assert(sb.document.body.style.overflow === "", "M07 mở khóa scroll sau đóng");
  assert(opener.__focused === true, "M07 trả focus về nút mở");
  assert((docListeners.keydown || []).length === 0, "M07 dọn listener keydown sau đóng");
  // blob revoke qua onClose
  let revoked = 0;
  const api2 = openModal({ title: "T2", bodyHTML: "<span>x</span>", footerHTML: "", onClose() { revoked++; } });
  api2.close();
  assert(revoked === 1, "M07 onClose callback chạy đúng 1 lần khi đóng");
}

/* ================================================================== */
console.log(`\n=== member_pages.test.js: ${pass} PASS / ${fail} FAIL ===`);
process.exit(fail > 0 ? 1 : 0);

})();

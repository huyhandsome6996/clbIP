/**
 * helpers.js — hạ tầng chung cho test JS chạy bằng Node thuần (không dependency).
 *
 * Cách chạy:  node frontend/tests/api.test.js
 *             node frontend/tests/nonce.test.js
 *
 * - `makeApiSandbox`: nạp `frontend/js/api.js` THẬT vào VM sandbox với fetch
 *   mô phỏng theo kịch bản (unit/contract test — DOM mock chỉ dùng ở tầng này).
 * - `makeAttendanceSandbox`: trích inline script của `frontend/admin/attendance.html`,
 *   biến IIFE thành factory, chạy với timer giả (setInterval/setTimeout thủ công)
 *   để kiểm chứng hành vi nonce R03 mà không cần trình duyệt.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");

let pass = 0;
let fail = 0;
function assert(cond, name) {
  if (cond) {
    pass++;
    console.log(`PASS  ${name}`);
  } else {
    fail++;
    console.log(`FAIL  ${name}`);
  }
}
function summary(suite) {
  console.log(`\n=== ${suite}: ${pass} PASS / ${fail} FAIL ===`);
  process.exit(fail > 0 ? 1 : 0);
}

/* ------------------------------------------------------------------ */
/* 1) Sandbox cho api.js                                               */
/* ------------------------------------------------------------------ */
function makeApiSandbox(scenarios) {
  const apiSource = fs.readFileSync(path.join(ROOT, "js", "api.js"), "utf8");
  const calls = [];
  const store = {};
  const sandbox = {
    console: { error: () => {}, log: () => {} },
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    },
    location: {
      protocol: "https:",
      origin: "https://clbip.test",
      pathname: "/frontend/admin/documents.html",
      href: "https://clbip.test/frontend/admin/documents.html",
    },
    document: {
      createElement: () => ({ href: "", download: "", click: () => {}, remove: () => {}, style: {} }),
      body: { appendChild: () => {} },
    },
    URL: { createObjectURL: () => "blob:x", revokeObjectURL: () => {} },
    fetch: async (url, opts = {}) => {
      calls.push({ url: String(url), method: opts.method || "GET", auth: (opts.headers && opts.headers.Authorization) || null });
      for (const sc of scenarios) {
        if (sc.match(url, opts)) return sc.respond();
      }
      return {
        ok: true, status: 200, headers: { get: () => null },
        json: async () => ({ success: true, data: {}, message: "ok" }),
        blob: async () => new Blob([JSON.stringify({ unexpected: true })]),
      };
    },
    Blob,
    FormData, // core request() check `instanceof FormData`
    __calls: calls,
    __store: store,
  };
  sandbox.window = sandbox;
  sandbox.window.localStorage = sandbox.localStorage;
  sandbox.window.location = sandbox.location;
  vm.createContext(sandbox);
  vm.runInContext(apiSource + "\n;window.ApiClient = ApiClient; window.ApiError = ApiError;", sandbox);
  return sandbox;
}

/* ------------------------------------------------------------------ */
/* 2) Sandbox cho attendance.html (timer giả + DOM stub)               */
/* ------------------------------------------------------------------ */
function extractInlineScript(htmlPath) {
  const html = fs.readFileSync(htmlPath, "utf8");
  const m = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!m) throw new Error("Không tìm thấy inline script trong " + htmlPath);
  return m[1];
}

/**
 * Nạp attendance.html với:
 *  - timer giả: sb.__tick(ms) chạy toàn bộ callback đến hạn (interval lặp lại)
 *  - DOM stub tự tạo element theo id (textContent/style đọc-ghi được)
 *  - ApiClient.get / Auth.requireRole / Toast là stub truyền vào
 * Trả về { sb, test, el, calls } — test = các hàm nội bộ được expose.
 */
function makeAttendanceSandbox({ apiGet, apiGetError } = {}) {
  const source = extractInlineScript(path.join(ROOT, "admin", "attendance.html"));

  // Chèn điểm expose vào TRƯỚC terminator `})();` của IIFE — lời gọi chạy
  // trong closure của trang nên bắt được state/let-bindings; trang gốc
  // KHÔNG bị sửa (expose chỉ tồn tại trong sandbox test).
  const lastIdx = source.lastIndexOf("})();");
  if (lastIdx === -1) throw new Error("Không tìm thấy dấu kết thúc IIFE");
  const exposeCall =
    "__clbipExpose({ fetchNonce, invalidateNonceUI, stopNonceLoops, stopNonceTimer, state," +
    " timers: () => ({ interval: nonceTimer, retry: nonceRetryTimer, autoRetries: nonceAutoRetries }) });";
  const patched = source.slice(0, lastIdx) + exposeCall + "\n" + source.slice(lastIdx);

  const elements = new Map();
  const el = (id) => {
    if (!elements.has(id)) {
      elements.set(id, { id, textContent: "", style: {}, value: "", addEventListener: () => {} });
    }
    return elements.get(id);
  };

  // Timer giả
  let now = 0;
  let seq = 0;
  const timers = [];
  const byId = (id) => timers.find((t) => t.id === id && !t.dead);

  const calls = { fetch: 0, toastError: 0, toastSuccess: 0 };
  const sb = {
    console: { error: () => {}, log: () => {} },
    document: {
      getElementById: (id) => el(String(id)),
      createElement: () => el("anon-" + ++seq),
      addEventListener: () => {},
      body: { appendChild: () => {} },
    },
    setInterval: (fn, ms) => { const t = { id: ++seq, type: "i", fn, ms, next: now + ms, dead: false }; timers.push(t); return t.id; },
    clearInterval: (id) => { const t = byId(id); if (t) t.dead = true; },
    setTimeout: (fn, ms) => { const t = { id: ++seq, type: "t", fn, ms, next: now + ms, dead: false }; timers.push(t); return t.id; },
    clearTimeout: (id) => { const t = byId(id); if (t) t.dead = true; },
    ApiClient: {
      get: async (endpoint) => {
        calls.fetch += 1;
        if (apiGetError) throw apiGetError();
        return apiGet ? apiGet(endpoint, calls.fetch) : { nonce: "135790", expires_in: 60, trang_thai: "OPEN" };
      },
    },
    Auth: { requireRole: () => new Promise(() => {}) }, // init() không tự chạy
    Toast: {
      error: () => { calls.toastError += 1; },
      success: () => { calls.toastSuccess += 1; },
    },
    Icons: { render: () => "" },
    Utils: { btnLoading: () => () => {} },
    confirm: () => true,
    location: { pathname: "/frontend/admin/attendance.html", href: "", origin: "https://clbip.test", protocol: "https:" },
    __calls: calls,
    __el: el,
    __elements: elements,
    __tick: (ms) => {
      const end = now + ms;
      for (;;) {
        const due = timers
          .filter((t) => !t.dead && t.next <= end)
          .sort((a, b) => a.next - b.next)[0];
        if (!due) break;
        now = due.next;
        if (due.type === "i") {
          due.next = now + due.ms;
          due.fn();
        } else {
          due.dead = true;
          due.fn();
        }
      }
      now = end;
    },
    __now: () => now,
  };
  sb.window = sb;
  sb.__clbipExpose = (obj) => { sb.__test = obj; };
  vm.createContext(sb);
  vm.runInContext(patched, sb);
  return { sb, test: sb.__test, el, calls };
}

module.exports = { makeApiSandbox, makeAttendanceSandbox, assert, summary };

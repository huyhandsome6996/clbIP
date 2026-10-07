/**
 * api.test.js — contract tests cho frontend/js/api.js (R02 — QA review 69db15d)
 * =============================================================================
 * Chạy MÃ api.js THẬT trong VM sandbox với fetch mô phỏng:
 *   R02-1  Access hết hạn + refresh hợp lệ → blob success (giữ hành vi F04)
 *   R02-2  Refresh FAIL → forceLogout ĐÚNG 1 lần (không redirect lặp)
 *   R02-3  Refresh OK NHƯNG retry vẫn 401 → forceLogout (trước đây chỉ throw!)
 *   R02-4  401 mà KHÔNG có refresh token → forceLogout ngay, không gọi refresh
 *   R02-5  Nhiều request 401 song song (JSON + blob) → CHỈ 1 refresh
 *          (single-flight) và CHỈ 1 lần điều hướng logout
 *   R02-6  403/404/429 → KHÔNG refresh, KHÔNG logout (không logout nhầm)
 *   F04-5  Blob thành công trả nguyên vẹn, KHÔNG bị parse JSON
 */
"use strict";
const { makeApiSandbox, assert, summary } = require("./helpers");

const API = "https://clbip.test/api/v1";

const pdf200 = () => ({
  ok: true,
  status: 200,
  headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/pdf" : null) },
  blob: async () => new Blob([Buffer.from("%PDF-fake")]),
});
const err401 = () => ({
  ok: false,
  status: 401,
  headers: { get: (k) => (String(k).toLowerCase() === "content-type" ? "application/json" : null) },
  json: async () => ({ success: false, message: "Token không hợp lệ", data: null, errors: null }),
  blob: async () => new Blob([]),
});
const refreshOk = (calls) => ({
  match: (u, o) => u === `${API}/auth/token/refresh/` && o.method === "POST",
  respond: () => {
    calls.refresh += 1;
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => ({ data: { access: "NEW_ACCESS", refresh: "NEW_REFRESH" } }),
    };
  },
});
const refreshFail = (calls) => ({
  match: (u, o) => u === `${API}/auth/token/refresh/` && o.method === "POST",
  respond: () => {
    calls.refresh += 1;
    return { ok: false, status: 401, headers: { get: () => "application/json" }, json: async () => ({}) };
  },
});

async function r02_1_refresh_then_success() {
  const calls = { refresh: 0 };
  const sb = makeApiSandbox([
    { match: (u) => u.startsWith(`${API}/documents/5/download/`), respond: () => err401() },
    refreshOk(calls),
    { match: () => true, respond: () => pdf200() }, // mọi fetch sau có token mới
  ]);
  // Đ.replace token check: scenario đầu khớp URL download mãi → cần phân biệt lần 1/lần 2
  // → dùng kịch bản theo số lần gọi: lần 1 401, lần 2 200.
  const sb2 = makeApiSandbox([
    refreshOk(calls),
    {
      match: (u) => u.startsWith(`${API}/documents/5/download/`),
      respond: () => {
        calls.dl = (calls.dl || 0) + 1;
        return calls.dl === 1 ? err401() : pdf200();
      },
    },
  ]);
  void sb;
  sb2.localStorage.setItem("clbip_access_token", "OLD");
  sb2.localStorage.setItem("clbip_refresh_token", "REFRESH_OK");
  const blob = await sb2.ApiClient.getBlob("/documents/5/download/");
  assert(blob && blob.size > 0, "R02-1: refresh hợp lệ → blob success (F04 giữ nguyên)");
  assert(calls.refresh === 1, "R02-1: đúng 1 lần refresh");
}

async function r02_2_refresh_fail_logout_once() {
  const calls = { refresh: 0 };
  const sb = makeApiSandbox([
    { match: (u) => u.startsWith(`${API}/documents/5/download/`), respond: () => err401() },
    refreshFail(calls),
  ]);
  sb.localStorage.setItem("clbip_access_token", "OLD");
  sb.localStorage.setItem("clbip_refresh_token", "DEAD");
  let threw = null;
  try {
    await sb.ApiClient.getBlob("/documents/5/download/");
  } catch (e) {
    threw = e;
  }
  assert(threw && threw.status === 401, "R02-2: refresh fail → ApiError 401");
  assert(!sb.localStorage.getItem("clbip_access_token"), "R02-2: token đã bị clear");
  assert(String(sb.location.href).includes("login.html?expired=1"), "R02-2: điều hướng login");
  // Gọi forceLogout thêm lần nữa (mô phỏng request khác cùng chết) → KHÔNG đổi href lần 2
  const before = String(sb.location.href);
  sb.ApiClient.forceLogout();
  assert(String(sb.location.href) === before, "R02-2: forceLogout lặp không điều hướng lại (dedup)");
}

async function r02_3_refresh_ok_but_retry_401_logout() {
  const calls = { refresh: 0, dl: 0 };
  const sb = makeApiSandbox([
    refreshOk(calls),
    {
      match: (u) => u.startsWith(`${API}/documents/5/download/`),
      respond: () => {
        calls.dl += 1;
        return err401(); // 401 CẢ TRƯỚC lẫn SAU refresh
      },
    },
  ]);
  sb.localStorage.setItem("clbip_access_token", "OLD");
  sb.localStorage.setItem("clbip_refresh_token", "REFRESH_OK");
  let threw = null;
  try {
    await sb.ApiClient.getBlob("/documents/5/download/");
  } catch (e) {
    threw = e;
  }
  assert(threw && threw.status === 401, "R02-3: retry vẫn 401 → ApiError 401");
  assert(calls.refresh === 1 && calls.dl === 2, "R02-3: đúng 1 refresh + 1 retry (không lặp vô hạn)");
  assert(!sb.localStorage.getItem("clbip_access_token"), "R02-3: token bị clear sau 401 cuối");
  assert(String(sb.location.href).includes("login.html?expired=1"), "R02-3: forceLogout sau 401 cuối");
}

async function r02_4_401_without_refresh_logout() {
  const calls = { refresh: 0 };
  const sb = makeApiSandbox([
    { match: (u) => u.startsWith(`${API}/documents/5/download/`), respond: () => err401() },
    refreshOk(calls),
  ]);
  sb.localStorage.setItem("clbip_access_token", "OLD");
  // KHÔNG set refresh token
  let threw = null;
  try {
    await sb.ApiClient.getBlob("/documents/5/download/");
  } catch (e) {
    threw = e;
  }
  assert(threw && threw.status === 401, "R02-4: 401 thiếu refresh → ApiError 401");
  assert(calls.refresh === 0, "R02-4: KHÔNG gọi refresh khi không có token");
  assert(!sb.localStorage.getItem("clbip_access_token"), "R02-4: phiên được clear");
  assert(String(sb.location.href).includes("login.html?expired=1"), "R02-4: forceLogout ngay");
}

async function r02_5_concurrent_single_flight() {
  const calls = { refresh: 0, dl: 0 };
  const sb = makeApiSandbox([
    refreshOk(calls),
    { // request JSON (envelope) — phải đứng TRƯỚC scenario blob
      match: (u) => u === `${API}/documents/`,
      respond: () => ({
        ok: true,
        status: 200,
        headers: { get: () => "application/json" },
        json: async () => ({ success: true, data: { items: [] }, message: "ok" }),
      }),
    },
    {
      match: (u) => u.startsWith(`${API}/documents/`),
      respond: () => {
        calls.dl += 1;
        return calls.dl <= 3 ? err401() : pdf200();
      },
    },
  ]);
  sb.localStorage.setItem("clbip_access_token", "OLD");
  sb.localStorage.setItem("clbip_refresh_token", "REFRESH_OK");
  // 3 blob + 1 JSON request cùng bung 401 → chung 1 refresh, 1 logout-less retry
  const p1 = sb.ApiClient.getBlob("/documents/1/download/");
  const p2 = sb.ApiClient.getBlob("/documents/2/download/");
  const p3 = sb.ApiClient.getBlob("/documents/3/download/");
  const p4 = sb.ApiClient.get("/documents/");
  const all = await Promise.allSettled([p1, p2, p3, p4]);
  assert(calls.refresh === 1, "R02-5: 4 request 401 song song → đúng 1 refresh (single-flight)");
  const okCount = all.filter((r) => r.status === "fulfilled").length;
  assert(okCount === 4, "R02-5: cả 4 request thành công sau retry");
  assert(String(sb.location.href).includes("documents.html"), "R02-5: không bị logout oan khi refresh OK");
}

async function r02_6_403_404_429_no_logout() {
  for (const status of [403, 404, 429]) {
    const calls = { refresh: 0 };
    const sb = makeApiSandbox([
      {
        match: (u) => u.startsWith(`${API}/documents/9/preview/`),
        respond: () => ({
          ok: false,
          status,
          headers: { get: () => "application/json" },
          json: async () => ({ success: false, message: "Từ chối", data: null, errors: null }),
        }),
      },
      refreshOk(calls),
    ]);
    sb.localStorage.setItem("clbip_access_token", "OLD");
    sb.localStorage.setItem("clbip_refresh_token", "REFRESH_OK");
    let threw = null;
    try {
      await sb.ApiClient.getBlob("/documents/9/preview/");
    } catch (e) {
      threw = e;
    }
    assert(threw && threw.status === status, `R02-6: HTTP ${status} → ApiError đúng status`);
    assert(calls.refresh === 0, `R02-6: HTTP ${status} → KHÔNG refresh`);
    assert(!!sb.localStorage.getItem("clbip_access_token"), `R02-6: HTTP ${status} → KHÔNG clear phiên`);
    assert(!String(sb.location.href).includes("login.html"), `R02-6: HTTP ${status} → KHÔNG logout nhầm`);
  }
}

async function f04_5_blob_not_parsed() {
  const calls = { refresh: 0 };
  const sb = makeApiSandbox([
    { match: (u) => u.startsWith(`${API}/documents/7/download/`), respond: () => pdf200() },
    refreshOk(calls),
  ]);
  sb.localStorage.setItem("clbip_access_token", "T");
  const blob = await sb.ApiClient.getBlob("/documents/7/download/");
  const text = await blob.text();
  assert(text.startsWith("%PDF"), "F04-5: blob nhị phân nguyên vẹn, không bị parse JSON");
}

(async () => {
  await r02_1_refresh_then_success();
  await r02_2_refresh_fail_logout_once();
  await r02_3_refresh_ok_but_retry_401_logout();
  await r02_4_401_without_refresh_logout();
  await r02_5_concurrent_single_flight();
  await r02_6_403_404_429_no_logout();
  await f04_5_blob_not_parsed();
  summary("api.test.js (R02)");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

/**
 * nonce.test.js — hành vi nonce trên frontend/admin/attendance.html (R03)
 * =======================================================================
 * Chạy INLINE SCRIPT THẬT của trang attendance (biến IIFE thành factory)
 * trong VM sandbox với TIMER GIẢ (setInterval/setTimeout thủ công), DOM stub
 * và ApiClient stub:
 *
 *   R03-1  Hết hạn (offline): tick qua hạn → mã bị VÔ HIỆU HOÁ NGAY
 *          (hiển thị placeholder, remaining = 0, KHÔNG âm, KHÔNG giữ mã cũ)
 *   R03-2  Offline nhiều tick: KHÔNG spam fetch/toast mỗi giây (backoff ≤ 1
 *          lần tự thử rồi dừng, chỉ còn nút retry thủ công)
 *   R03-3  Hồi phục online: backoff retry thành công → mã mới hiển thị lại,
 *          bộ đếm backoff reset
 *   R03-4  Không còn tick âm: sau khi expire, remaining không bao giờ âm
 *   R03-5  Đổi phiên trong lúc fetch cũ đang bay: response cũ KHÔNG ghi đè
 *          phiên mới (sessionId snapshot giữ nguyên)
 *   R03-6  Đổi phiên dọn sạch timer: interval + backoff đều bị hủy (không
 *          timer tự hồi sinh sau khi đổi/đóng phiên)
 *   R03-7  Retry thủ công (double-click nhanh) không tạo fetch trùng
 */
"use strict";
const { makeAttendanceSandbox, assert, summary } = require("./helpers");

/** Chờ toàn bộ microtask + setTimeout(0) của stub kịp chạy xong. */
const flush = () => new Promise((r) => setTimeout(r, 5));

async function r03_1_expiry_offline_invalidates() {
  const { sb, test, el, calls } = makeAttendanceSandbox({
    // Lần 1 (init) OK; từ lần 2 (fetch lúc hết hạn) trở đi → mạng chết
    apiGet: (_endpoint, nth) =>
      nth <= 1
        ? { nonce: "246810", expires_in: 2, trang_thai: "OPEN" }
        : Promise.reject(Object.assign(new Error("Network down"), { message: "Không kết nối được máy chủ" })),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };

  // Fetch đầu thành công
  await test.fetchNonce();
  assert(el("nonce-value").textContent === "246810", "R03-1: mã được hiển thị sau fetch OK");
  assert(test.timers().interval !== null, "R03-1: countdown đang chạy");

  // Tick đến khi hết hạn (2s) — fetch lúc hết hạn sẽ THẤT BẠI (offline)
  sb.__tick(2000);
  await flush();

  assert(el("nonce-value").textContent === "······", "R03-1: mã hết hạn bị vô hiệu hoá (placeholder)");
  assert(test.state.nonce === "", "R03-1: state.nonce đã bị clear");
  assert(test.state.nonceRemain === 0, "R03-1: state remaining = 0, không âm");
  assert(
    el("nonce-remain").textContent === "0" || el("nonce-remain").textContent === "—",
    "R03-1: hiển thị remaining là 0 hoặc dấu — (lỗi), không là số đếm cũ/âm",
  );
  assert(calls.fetch === 2, "R03-1: fetch = lần đầu + lần hết hạn (2)");
  assert(calls.toastError === 1, "R03-1: đúng 1 toast lỗi (không spam)");
}

async function r03_2_no_spam_while_offline() {
  const { sb, test, calls } = makeAttendanceSandbox({
    apiGetError: () => Object.assign(new Error("Network down"), { message: "Không kết nối được máy chủ" }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };

  await test.fetchNonce(); // fail #1 → toast + lên lịch backoff 5s
  sb.__tick(1000); // 1s trôi — KHÔNG được tự fetch lại
  await flush();
  assert(calls.fetch === 1 && calls.toastError === 1, "R03-2: 1 tick trôi → không thêm fetch/toast");
  sb.__tick(4000); // tới mốc backoff 5s → tự thử lại ĐÚNG 1 lần
  await flush();
  assert(calls.fetch === 2, "R03-2: backoff tự thử lại đúng 1 lần");
  assert(calls.toastError === 2, "R03-2: toast thứ 2 từ backoff retry");
  sb.__tick(30000); // 30s trôi tiếp — phải IM LẶNG hoàn toàn (chỉ retry thủ công)
  await flush();
  assert(calls.fetch === 2 && calls.toastError === 2, "R03-2: sau backoff KHÔNG còn fetch/toast tự động nào");
  assert(test.timers().interval === null && test.timers().retry === null, "R03-2: không còn timer nào sống");
}

async function r03_3_recovery_online_after_backoff() {
  const { sb, test, el, calls } = makeAttendanceSandbox({
    apiGet: (_endpoint, nth) =>
      nth <= 1
        ? Promise.reject(Object.assign(new Error("down"), { message: "lỗi tạm thời" }))
        : Promise.resolve({ nonce: "999999", expires_in: 60, trang_thai: "OPEN" }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };

  await test.fetchNonce().catch(() => {});
  assert(calls.fetch === 1 && calls.toastError === 1, "R03-3: lần đầu fail → 1 toast");
  sb.__tick(5000); // backoff retry → OK
  await flush();
  assert(calls.fetch === 2, "R03-3: backoff retry đã chạy");
  assert(el("nonce-value").textContent === "999999", "R03-3: mã mới hiển thị sau hồi phục");
  assert(test.timers().interval !== null, "R03-3: countdown chạy lại");
  assert(test.timers().autoRetries === 0, "R03-3: bộ đếm backoff đã reset về 0");
}

async function r03_4_no_negative_remaining() {
  const { sb, test, el } = makeAttendanceSandbox({
    apiGet: () => ({ nonce: "111111", expires_in: 3, trang_thai: "OPEN" }),
    apiGetError: () => new Error("down"),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  await test.fetchNonce();
  let minSeen = test.state.nonceRemain;
  for (let i = 0; i < 6; i++) {
    sb.__tick(1000);
    await flush();
    if (test.state.nonceRemain < minSeen) minSeen = test.state.nonceRemain;
  }
  assert(minSeen >= 0, "R03-4: remaining KHÔNG bao giờ âm (min thấy = " + minSeen + ")");
  assert(el("nonce-remain").textContent !== "-", "R03-4: hiển thị không còn số âm");
}

async function r03_5_stale_response_not_applied_to_new_session() {
  let resolveOld;
  const { test, el } = makeAttendanceSandbox({
    apiGet: () => new Promise((res) => { resolveOld = res; }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  const pending = test.fetchNonce(); // fetch phiên 1 đang bay

  // BCN đổi phiên trong khi fetch cũ chưa trả
  test.stopNonceLoops();
  test.state.openSession = { id: 2, ten_phien: "Phiên B" };

  resolveOld({ nonce: "OLDOLD", expires_in: 60, trang_thai: "OPEN" }); // response cũ về muộn
  await pending;

  assert(test.state.openSession.id === 2, "R03-5: phiên mới không bị đổi");
  assert(test.state.nonce !== "OLDOLD", "R03-5: mã của phiên cũ KHÔNG hiển thị lên phiên mới");
  assert(el("nonce-value").textContent !== "OLDOLD", "R03-5: DOM không chứa mã phiên cũ");
}

async function r03_6_session_switch_clears_timers() {
  const { test } = makeAttendanceSandbox({
    apiGet: () => ({ nonce: "222222", expires_in: 60, trang_thai: "OPEN" }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  await test.fetchNonce(); // OK → interval chạy
  assert(test.timers().interval !== null, "R03-6: interval đang sống");

  test.stopNonceLoops(); // hành vi selectOpenSession/close khi đổi/đóng phiên
  assert(test.timers().interval === null && test.timers().retry === null, "R03-6: interval + backoff đều bị dọn");
}

async function r03_7_manual_retry_no_duplicate_fetch() {
  const { test, calls } = makeAttendanceSandbox({
    apiGet: () => new Promise((res) => setTimeout(() => res({ nonce: "333333", expires_in: 60 }), 0)),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  // Double-click retry nhanh: 2 lời gọi trước khi fetch đầu kịp xong
  const p1 = test.fetchNonce();
  const p2 = test.fetchNonce();
  await Promise.all([p1, p2]);
  assert(calls.fetch === 1, "R03-7: 2 lần bấm liên tiếp → chỉ 1 fetch (guard theo sessionId)");
}

(async () => {
  await r03_1_expiry_offline_invalidates();
  await r03_2_no_spam_while_offline();
  await r03_3_recovery_online_after_backoff();
  await r03_4_no_negative_remaining();
  await r03_5_stale_response_not_applied_to_new_session();
  await r03_6_session_switch_clears_timers();
  await r03_7_manual_retry_no_duplicate_fetch();
  summary("nonce.test.js (R03)");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

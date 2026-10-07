/**
 * nonce.test.js — hành vi nonce trên frontend/admin/attendance.html (R03)
 * =======================================================================
 * Chạy INLINE SCRIPT THẬT của trang attendance (biến IIFE thành factory)
 * trong VM sandbox với TIMER GIẢ (setInterval/setTimeout thủ công), DOM stub
 * và ApiClient stub.
 *
 * N01 (review ac51233): trang attendance mới là tri-view (events/attendance/
 * documents) với engine viết lại — harness expose kiến trúc mới (startNonceLoop/
 * armNonceInterval + state.nonceInterval/nonceRetryTimer/nonceAutoRetries,
 * DOM id `live-nonce-display`/`live-nonce-countdown`). HỢP ĐỒNG HÀNH VI R03
 * GIỮ NGUYÊN:
 *
 *   R03-1  Hết hạn (offline): tick qua hạn → mã bị VÔ HIỆU HOÁ NGAY
 *          (placeholder `······`, countdown 0s, KHÔNG giữ mã cũ)
 *   R03-2  Offline nhiều tick: KHÔNG spam fetch/toast mỗi giây (backoff ≤ 1
 *          lần tự thử rồi dừng, chỉ còn retry thủ công "Lấy mã mới")
 *   R03-3  Hồi phục online: backoff retry thành công → mã mới hiển thị lại,
 *          interval chạy lại, bộ đếm backoff reset
 *   R03-4  Không còn tick/countdown âm hoặc placeholder hiển thị sai
 *   R03-5  Đổi phiên trong lúc fetch cũ đang bay: response cũ KHÔNG ghi đè
 *          phiên mới (per-session guard)
 *   R03-6  Đổi/đóng phiên dọn sạch timer: interval + backoff đều bị hủy
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
        ? { nonce: "246810", trang_thai: "OPEN" }
        : Promise.reject(Object.assign(new Error("Network down"), { message: "Không kết nối được máy chủ" })),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };

  // Khởi động vòng nonce (fetch đầu thành công + interval đếm ngược)
  test.startNonceLoop(1);
  await flush();
  assert(el("live-nonce-display").textContent === "246810", "R03-1: mã được hiển thị sau fetch OK");
  assert(test.timers().interval !== null, "R03-1: countdown đang chạy");

  // Tick qua mốc 15s — fetch lúc hết hạn sẽ THẤT BẠI (offline)
  sb.__tick(15000);
  await flush();

  assert(el("live-nonce-display").textContent === "······", "R03-1: mã hết hạn bị vô hiệu hoá NGAY (placeholder)");
  assert(el("live-nonce-countdown").textContent === "0s", "R03-1: hiển thị 0s (không giữ số đếm cũ)");
  assert(test.timers().interval === null, "R03-1: interval dừng sau khi hết hạn (fetch lỗi không tái vũ trang)");
  assert(calls.fetch === 2, "R03-1: fetch = lần đầu + lần hết hạn (2)");
  assert(calls.toastError === 1, "R03-1: đúng 1 toast lỗi (không spam)");
}

async function r03_2_no_spam_while_offline() {
  const { sb, test, calls } = makeAttendanceSandbox({
    apiGetError: () => Object.assign(new Error("Network down"), { message: "Không kết nối được máy chủ" }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };

  test.startNonceLoop(1); // fetch #1 → fail → toast + lên lịch backoff 5s
  await flush();
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
  assert(test.timers().autoRetries === 1, "R03-2: bộ đếm auto-retry chặn ở giới hạn 1 lần");
}

async function r03_3_recovery_online_after_backoff() {
  const { sb, test, el, calls } = makeAttendanceSandbox({
    apiGet: (_endpoint, nth) =>
      nth <= 1
        ? Promise.reject(Object.assign(new Error("down"), { message: "lỗi tạm thời" }))
        : Promise.resolve({ nonce: "999999", trang_thai: "OPEN" }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };

  test.startNonceLoop(1);
  await flush();
  assert(calls.fetch === 1 && calls.toastError === 1, "R03-3: lần đầu fail → 1 toast");
  sb.__tick(5000); // backoff retry → OK
  await flush();
  assert(calls.fetch === 2, "R03-3: backoff retry đã chạy");
  assert(el("live-nonce-display").textContent === "999999", "R03-3: mã mới hiển thị sau hồi phục");
  assert(test.timers().interval !== null, "R03-3: countdown chạy lại (interval tái vũ trang)");
  assert(test.timers().autoRetries === 0, "R03-3: bộ đếm backoff đã reset về 0");
}

async function r03_4_no_negative_countdown() {
  const { sb, test, el } = makeAttendanceSandbox({
    apiGet: () => ({ nonce: "111111", trang_thai: "OPEN" }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  test.startNonceLoop(1);
  await flush();
  let minSeen = test.state.nonceCountdown;
  for (let i = 0; i < 20; i++) {
    sb.__tick(1000);
    await flush();
    if (test.state.nonceCountdown < minSeen) minSeen = test.state.nonceCountdown;
    // textContent không bao giờ là số âm / "-"
    const txt = el("live-nonce-countdown").textContent;
    assert(!/^-/.test(txt), "R03-4: hiển thị không bao giờ âm");
  }
  assert(minSeen >= 0, "R03-4: countdown KHÔNG bao giờ âm (min thấy = " + minSeen + ")");
  // Sau 20s: qua ít nhất 1 chu kỳ hết hạn → mã vẫn hiển thị (fetch lại OK), không placeholder
  assert(el("live-nonce-display").textContent === "111111", "R03-4: sau hết hạn + refetch OK, mã hiển thị lại");
}

async function r03_5_stale_response_not_applied_to_new_session() {
  let resolveOld;
  const { test, el } = makeAttendanceSandbox({
    apiGet: () => new Promise((res) => { resolveOld = res; }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  const pending = test.fetchNonce(1); // fetch phiên 1 đang bay

  // BCN đổi phiên trong khi fetch cũ chưa trả
  test.stopNonceLoops();
  test.state.openSession = { id: 2, ten_phien: "Phiên B" };

  resolveOld({ nonce: "OLDOLD", trang_thai: "OPEN" }); // response cũ về muộn
  await pending;

  assert(test.state.openSession.id === 2, "R03-5: phiên mới không bị đổi");
  assert(el("live-nonce-display").textContent !== "OLDOLD", "R03-5: DOM không chứa mã phiên cũ");
}

async function r03_6_session_switch_clears_timers() {
  const { test } = makeAttendanceSandbox({
    apiGet: () => ({ nonce: "222222", trang_thai: "OPEN" }),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  test.startNonceLoop(1); // OK → interval chạy
  await flush();
  assert(test.timers().interval !== null, "R03-6: interval đang sống");

  test.stopNonceLoops(); // hành vi selectOpenSession/close khi đổi/đóng phiên
  assert(test.timers().interval === null && test.timers().retry === null, "R03-6: interval + backoff đều bị dọn");
}

async function r03_7_manual_retry_no_duplicate_fetch() {
  const { test, calls } = makeAttendanceSandbox({
    apiGet: () => new Promise((res) => setTimeout(() => res({ nonce: "333333", trang_thai: "OPEN" }), 0)),
  });
  test.state.openSession = { id: 1, ten_phien: "Phiên A" };
  // Double-click retry nhanh: 2 lời gọi trước khi fetch đầu kịp xong
  const p1 = test.fetchNonce(1);
  const p2 = test.fetchNonce(1);
  await Promise.all([p1, p2]);
  assert(calls.fetch === 1, "R03-7: 2 lần bấm liên tiếp → chỉ 1 fetch (guard theo sessionId)");
}

(async () => {
  await r03_1_expiry_offline_invalidates();
  await r03_2_no_spam_while_offline();
  await r03_3_recovery_online_after_backoff();
  await r03_4_no_negative_countdown();
  await r03_5_stale_response_not_applied_to_new_session();
  await r03_6_session_switch_clears_timers();
  await r03_7_manual_retry_no_duplicate_fetch();
  summary("nonce.test.js (R03)");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

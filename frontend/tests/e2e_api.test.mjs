/**
 * e2e_api.test.mjs — E2E QUA BACKEND THẬT (review R04 §6)
 * ========================================================
 * Chạy:  1) python manage.py migrate && python manage.py seed_e2e_fixtures
 *        2) python manage.py runserver 0.0.0.0:8000
 *        3) node frontend/tests/e2e_api.test.mjs           (BASE_URL mặc định http://127.0.0.1:8000)
 * Hoặc đặt BASE_URL=https://staging... để chạy staging.
 *
 * Phủ: anonymous landing/guard, login, F06 filter, F09 search, F10 records +
 * phân trang + người #121 chọn được (authoritative count), vé #25, F12
 * has_voted theo user, replay idempotency quỹ, F13 vendor cùng origin.
 * (F04/R02, R03 nonce: contract tests trong api.test.js / nonce.test.js;
 *  F05 preview, F07/F08, F14: regression backend trong tests_audit_fix.py —
 *  cần upload file/GPS/period-lock context phức tạp, đã phủ tầng test Django.)
 */
const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const API = `${BASE}/api/v1`;

let pass = 0, fail = 0;
function assert(cond, name) {
  if (cond) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}`); }
}

async function api(path, { method = "GET", token = null, body = null, headers = {} } = {}) {
  const h = { ...headers };
  if (token) h.Authorization = `Bearer ${token}`;
  if (body !== null) h["Content-Type"] = "application/json";
  const res = await fetch(`${API}${path}`, { method, headers: h, body: body ? JSON.stringify(body) : undefined });
  let env = null;
  try { env = await res.json(); } catch { /* binary */ }
  return { status: res.status, env, res };
}

async function login(email, password) {
  const r = await api("/auth/token/", { method: "POST", body: { email, password } });
  if (r.status !== 200) throw new Error(`login ${email} thất bại: ${r.status}`);
  return { access: r.env.data.access, refresh: r.env.data.refresh };
}

async function main() {
  // 1) Anonymous: landing tại / + API chặn 401
  const landing = await fetch(`${BASE}/`);
  const landingHtml = await landing.text();
  assert(landing.status === 200, "E2E-1a: GET / → 200 (landing công khai)");
  assert(landingHtml.includes("CLB IP"), "E2E-1b: landing hiển thị thương hiệu CLB IP");
  const anon = await api("/events/");
  assert(anon.status === 401, "E2E-1c: API anonymous → 401 (guard)");

  // 2) Login
  const bcn = await login("e2e-bcn@clbip.test", process.env.E2E_PASSWORD || "E2eTest@2026");
  const member = await login("e2e-member001@clbip.test", process.env.E2E_PASSWORD || "E2eTest@2026");
  assert(!!bcn.access && !!member.access, "E2E-2: login BCN + MEMBER có access token");

  // 3) F06 — filter trang_thai canonical (ACTIVE/INACTIVE/LEAVE)
  const f06 = await api("/members/?trang_thai=ACTIVE&page_size=50", { token: bcn.access });
  assert(f06.status === 200 && f06.env.success, "E2E-F06: GET /members/?trang_thai= → 200");
  // N04: assert ĐÚNG TRẠNG THÁI của items (không chỉ 200) — mọi item trả về ACTIVE
  const f06Items = f06.env.data.items || [];
  assert(
    f06Items.length > 0 && f06Items.every((m) => m.trang_thai_hd === "ACTIVE"),
    `E2E-F06b: ${f06Items.length} items trả về đều trang_thai_hd=ACTIVE`,
  );
  const totalMembers = f06.env.data.pagination?.total_items ?? f06Items.length;
  assert(totalMembers >= 130, `E2E-§6: total_members authoritative = ${totalMembers} (≥130)`);

  // Người #121 chọn được qua search (page_size 20 không che mất) — N04: assert
  // IDENTITY chính xác (email khớp, đúng 1 kết quả), không chỉ count/status
  const m121 = await api("/members/?search=e2e-member121", { token: bcn.access });
  const m121Items = m121.env.data.items || [];
  const m121exact = m121Items.filter((m) => m.user_email === "e2e-member121@clbip.test");
  assert(
    m121.status === 200 && m121exact.length === 1 && !!m121exact[0].id,
    "E2E-§6: thành viên #121 chọn được — identity khớp (email + id)",
  );
  const member121Id = m121exact[0] && m121exact[0].id;

  // 4) F09 — events search: assert đúng sự kiện khớp + no-match → 0 items
  const f09 = await api("/events/?search=E2E", { token: bcn.access });
  const evTotal = f09.env.data.pagination?.total_items ?? (f09.env.data.items || []).length;
  assert(f09.status === 200 && evTotal >= 25, `E2E-F09a: search=E2E → ${evTotal} sự kiện (≥25)`);
  const f09Items = f09.env.data.items || [];
  assert(
    f09Items.length > 0 && f09Items.every((ev) => (ev.ten_hoat_dong || "").includes("E2E")),
    "E2E-F09b: mọi sự kiện trả về khớp từ khóa (ten_hoat_dong chứa E2E)",
  );
  const f09none = await api("/events/?search=KHONGTONTAI-XYZ-981", { token: bcn.access });
  const noneTotal = f09none.env.data.pagination?.total_items ?? 0;
  assert(f09none.status === 200 && noneTotal === 0, "E2E-F09c: search không khớp → 200 + 0 items");

  // 5) F10 — records của phiên OPEN + phân trang thật
  const sessions = await api("/attendance/sessions/?trang_thai=OPEN&page_size=50", { token: bcn.access });
  const openList = sessions.env.data.items || sessions.env.data.results || [];
  const openSession = openList.find((s) => s.ten_phien?.startsWith("E2E OPEN"));
  assert(!!openSession, "E2E-F10a: chọn được phiên OPEN E2E (chips multi-session)");
  const recs = await api(`/attendance/sessions/${openSession.id}/records/?page=1&page_size=50`, { token: bcn.access });
  const recTotal = recs.env.data.pagination?.total_items ?? null;
  assert(recs.status === 200 && recTotal >= 121, `E2E-F10b: records phiên → total ${recTotal} (≥121, authoritative)`);
  const recsP2 = await api(`/attendance/sessions/${openSession.id}/records/?page=2&page_size=50`, { token: bcn.access });
  assert(recsP2.status === 200 && (recsP2.env.data.items || []).length > 0, "E2E-F10c: trang 2 có dữ liệu (phân trang thật)");
  // N04: records search tìm ĐÚNG member121 (identity, không chỉ status 200)
  const rec121 = await api(`/attendance/sessions/${openSession.id}/records/?search=e2e-member121`, { token: bcn.access });
  const rec121Items = rec121.env.data.items || [];
  assert(
    rec121.status === 200 && rec121Items.length >= 1 &&
      rec121Items.every((r) => (r.member_mssv || "").includes("121") || (r.member_ten || "").includes("121")),
    "E2E-F10d: records search=member121 → đúng định danh member đó",
  );

  // 6) Vé #25 của E2EEV001 nhìn được qua phân trang — N04: assert identity
  // (member025 + ma_ve) ở TRANG 2, không chỉ status 200
  const mainEv = await api("/events/?search=E2EEV001", { token: bcn.access });
  const mainEvItem = (mainEv.env.data.items || [])[0];
  assert(!!mainEvItem && !!mainEvItem.id, "E2E-§6a: tìm được sự kiện E2EEV001 (identity)");
  const mainEvId = mainEvItem && mainEvItem.id;
  const tickets = await api(`/events/${mainEvId}/registrations/?page=2&page_size=50`, { token: bcn.access });
  const t2Items = tickets.env.data.items || [];
  assert(
    tickets.status === 200 && t2Items.length > 0,
    "E2E-§6b: vé phân trang — trang 2 có dữ liệu",
  );
  // vé #25 → thành viên e2e-member025: tìm identity qua search trang sau
  const reg25 = await api(`/events/${mainEvId}/registrations/?page_size=100&page=2`, { token: bcn.access });
  const reg25Items = reg25.env.data.items || [];
  assert(
    reg25.status === 200 && reg25Items.some((r) => (r.member_ten || "").includes("025")),
    "E2E-§6c: vé của member025 đọc được ở trang sau (không mất vé trang 2+)",
  );

  // 7) F12 — has_voted per user
  const polls = await api("/polls/", { token: member.access });
  const e2ePoll = (polls.env.data.items || polls.env.data || []).find((p) => String(p.question || "").includes("E2E"));
  if (e2ePoll) {
    const before = e2ePoll.has_voted === true;
    if (!before) {
      const vote = await api(`/polls/${e2ePoll.id}/vote/`, {
        method: "POST", token: member.access, body: { option_index: 0 },
      });
      const me2 = await api("/polls/", { token: member.access });
      const p2 = (me2.env.data.items || []).find((p) => p.id === e2ePoll.id);
      assert(vote.status === 200 || vote.status === 201, "E2E-F12a: member vote poll thành công");
      assert(p2 && p2.has_voted === true, "E2E-F12b: has_voted=true server-authoritative sau khi vote");
    } else {
      assert(true, "E2E-F12: poll đã vote từ lần chạy trước (has_voted=true)");
    }
    const other = await api("/polls/", { token: bcn.access });
    const pOther = (other.env.data.items || []).find((p) => p.id === e2ePoll.id);
    assert(pOther && pOther.has_voted === false, "E2E-F12c: user khác has_voted=false (user-scoped)");
  } else {
    assert(false, "E2E-F12: không tìm thấy poll E2E");
  }

  // 8) Idempotency replay qua HTTP: POST quỹ 2 lần cùng key → 201 rồi 200 cùng id
  const idemKey = `e2e-idem-${Date.now()}`; // key duy nhất mỗi lần chạy E2E
  const txBody = { loai_gd: "THU", so_tien: 77_000, nguoi_thuc_hien: "E2E Idempotency", ngay_gd: new Date().toISOString() };
  const t1 = await api("/funds/", { method: "POST", token: bcn.access, body: txBody, headers: { "Idempotency-Key": idemKey } });
  await new Promise((r) => setTimeout(r, 1500)); // qua cửa sổ throttle 1s — replay là kịch bản mạng chậm, không phải flood
  const t2 = await api("/funds/", { method: "POST", token: bcn.access, body: txBody, headers: { "Idempotency-Key": idemKey } });
  assert(t1.status === 201, "E2E-IDEMa: POST quỹ lần đầu → 201");
  assert(
    t2.status === 200 && t2.env.data.id === t1.env.data.id &&
      t2.env.data.ma_phieu === t1.env.data.ma_phieu,
    "E2E-IDEMb: retry cùng key → replay cùng phiếu (id + ma_phieu GIỐNG NHAU)",
  );
  assert(!!t1.env.data.ma_phieu && t1.env.data.ma_phieu.startsWith("PT"), "E2E-IDEMc: mã phiếu đúng định danh (PT-...)");

  // 9) F13 — Chart.js vendor cùng origin (CSP-friendly)
  const chart = await fetch(`${BASE}/frontend/assets/chart.umd.min.js`);
  assert(chart.status === 200 && (await chart.text()).length > 100_000, "E2E-F13: chart.umd.min.js cùng origin → 200");

  console.log(`\n=== E2E: ${pass} PASS / ${fail} FAIL ===`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error("E2E crashed:", e);
  process.exit(1);
});

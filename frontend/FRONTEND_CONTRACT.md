# FRONTEND CONTRACT — CLB IP ĐHSP Huế 2.0

> Tài liệu BẮT BUỘC đọc cho mọi agent xây trang frontend. Backend chạy thật tại
> `http://127.0.0.1:8000`, đã seed dữ liệu demo. KHÔNG sửa file dùng chung
> (css/*, js/api.js, js/auth.js, js/toast.js, js/utils.js, js/icons.js,
> js/celebration.js, login.html, index.html, landing.html) — chỉ ĐỌC và DÙNG.

> **Luồng trang chủ:** `/` → phục vụ `frontend/landing.html` (landing CÔNG KHAI,
> không cần đăng nhập — giới thiệu CLB + CTA Đăng nhập; nếu browser còn phiên
> đăng nhập thì JS tự đổi CTA thành "Vào cổng sinh viên" → `/frontend/index.html`
> splash điều hướng theo vai trò). Landing dùng chung `css/landing.css`
> (Tailwind build — config NẰM TRONG REPO tại `frontend/tailwind/`):
> ```
> cd frontend/tailwind && npx tailwindcss@3.4.17 -c tailwind.config.js -i input.css -o ../css/landing.css --minify
> ```
> `content` gồm member/home.html + landing.html + design_reference.html —
> xây trang mới dùng landing.css phải thêm file vào `content` rồi build lại.

## 0. Tài khoản demo (đã seed trên MySQL)
| Vai trò | Email | Mật khẩu |
|---|---|---|
| ADMIN | admin@clbip.vn | CLBIP@2026 |
| BCN | bcn@clbip.vn | CLBIP@2026 |
| MEMBER | 22a401101@student.hueuni.edu.vn | CLBIP@2026 |

## 1. Envelope chuẩn MỌI endpoint trả về
```json
{ "success": true, "data": {...}, "message": "...", "errors": null }
```
- `ApiClient.get/post/...` đã **unwrap** → trả thẳng `data`.
- Endpoint list trả `data = { items: [...], pagination: {page, page_size, total_pages, total_items} }`.
- Dùng `ApiClient.getList(endpoint, params)` → `{items, pagination}` (pagination có thể null).
- Lỗi: `err.status` (0 = mạng), `err.message` (tiếng Việt sẵn), `err.errors` (field errors DRF).
- **Khởi tạo state sau khi guard chạy xong**: bọc trong try/catch hoặc `.then` — vì `Auth.requireRole()` redirect bằng `window.location.href` (không dừng JS ngay).
- **File/blob (audit F04)**: dùng `ApiClient.getBlob(endpoint)` (trả Blob, refresh single-flight đúng 1 lần khi 401, refresh fail → tự forceLogout) hoặc `ApiClient.download(endpoint, filename)`. KHÔNG fetch URL media/storage trực tiếp kèm Bearer (CSP + DEBUG=False đều chặn).

## 2. Auth flow (đã có sẵn — chỉ dùng lại)
```js
const user = await Auth.requireRole(["ADMIN", "BCN"]);   // admin pages
const user = await Auth.requireRole(["MEMBER"]);          // member pages (ADMIN/BCN cũng bị chặn — đúng yêu cầu phân hệ)
// user = {id, email, mssv, role, is_active, ho_ten, avatar, lop, xp_points, current_level, streak_count, trang_thai_hd, date_joined}
await Auth.logout();  // blacklist refresh + clear + về login
Auth.isBoard()        // true nếu ADMIN|BCN
```
- Header trang: hiện `ho_ten`/email + avatar (Utils.initials) + nút đăng xuất (Auth.logout()).
- Lỗi 401 khi token chết: `ApiClient` tự refresh 1 lần; nếu fail → tự redirect login. Không cần xử lý thêm.

## 3. Danh sách endpoint (đã test thật)

### 3.1 Auth — `/auth`
| Method + Path | Body/Query | Response data |
|---|---|---|
| POST `/auth/token/` | `{email, password}` | `{access, refresh, user:{id,email,role,ho_ten,avatar,mssv}}` |
| POST `/auth/token/refresh/` | `{refresh}` | `{access, refresh}` |
| GET `/auth/me/` | — | user + profile (xem trên) |

### 3.2 Members — `/members` (BCN: CRUD mọi người; MEMBER: chỉ xem)
| Method + Path | Body/Query | Response |
|---|---|---|
| GET `/members/` | `?page=&search=&lop=&trang_thai=` (⚠ audit F06: query list dùng `trang_thai` — `trang_thai_hd` CHỈ là tên trường write/response) | items: `{id, mssv, ho_ten, email, lop, sdt, gioi_tinh, avatar, xp_points, current_level, streak_count, trang_thai_hd, is_active, created_at}` |
| POST `/members/` | `{email, mssv, ho_ten, password?, lop?, sdt?, gioi_tinh? NAM|NU|KHAC, ngay_sinh?}` | profile mới; **audit F03**: để trống `password` → response data có thêm `initial_password` (hiển thị ĐÚNG 1 LẦN — mọi endpoint đọc khác không trả credential) |
| GET `/members/{id}/` | — | như list item |
| PATCH `/members/{id}/` | `{email?, mssv?, ho_ten?, lop?, sdt?, gioi_tinh?, ngay_sinh?, trang_thai_hd? ACTIVE|HOAT_DONG|BAO_LUU|... , role?}` | profile |
| GET `/members/search/?q=` | `q` (tối thiểu 1 ký tự) | `{items:[{id, mssv, ho_ten, lop, ...}]}` — Trie autocomplete (chú ý: có bọc items) |
| GET `/members/board/` | — | `{id, member, member_ho_ten, member_mssv, chuc_vu, chuc_vu_display, ban_phu_trach, ban_phu_trach_display, nhiem_ky}` |
| POST `/members/board/` | `{member, chuc_vu, ban_phu_trach, nhiem_ky?}` | như trên |
| GET `/members/{id}/profile360/` | — | `{id, user_id, mssv, email, ho_ten, lop, sdt, gioi_tinh, ngay_sinh, avatar, trang_thai_hd, is_active, board_positions[], stats:{events_registered, attendance_sessions, attendance_attended, attendance_rate_percent, xp_points, current_level, streak_count}, badges:[{ten_badge, icon, awarded_at}], recent_xp:[{reason, amount, created_at}]}` |
| GET `/members/export-excel/` | — | file xlsx → `ApiClient.download("/members/export-excel/", "thanh_vien.xlsx")` |
| POST `/members/import-excel/` | FormData `{file}` | kết quả import |

### 3.3 Funds — `/funds` (CHỈ BCN/ADMIN)
| Method + Path | Body/Query | Response |
|---|---|---|
| GET `/funds/` | `?loai_gd=THU|CHI&from_date=&to_date=&sort=-ngay_gd&page=` | items: `{id, ma_phieu, loai_gd, so_tien, nguoi_thuc_hien, hinh_thuc, ngay_gd, ghi_chu, so_du_sau, is_locked, created_by_ho_ten...}` |
| POST `/funds/` | `{loai_gd: "THU"|"CHI", so_tien: int(>0), nguoi_thuc_hien: str, hinh_thuc: "TIEN_MAT"|"CHUYEN_KHOAN", ngay_gd?, ghi_chu?}` + header `Idempotency-Key` | giao dịch + so_du_sau. **Audit F02**: cùng key + cùng payload → replay 200 (trả phiếu cũ); cùng key + payload khác → **409** `IdempotencyKeyConflictException` — client phải reset key, KHÔNG tự ghi đè |
| GET `/funds/stats/` | — | `{total_income, total_expense, balance, low_balance}` |
| POST `/funds/lock-period/` | `{ten_ky, tu_ngay, den_ngay, ghi_chu?}` | `{...}` khóa sổ |
| GET `/funds/locks/` | — | items: `{id, ten_ky, tu_ngay, den_ngay, locked_by, locked_at, ghi_chu}` |
| GET `/funds/export-excel/` | — | file xlsx |

### 3.4 Events — `/events`
| Method + Path | Body/Query | Response |
|---|---|---|
| GET `/events/` | `?trang_thai=&loai_hd=&search=&sort=&page=` (audit F09: `search` khớp tên/mã hoạt động) | items: `{id, ma_hd, ten_hoat_dong, loai_hd, thoi_gian_bat_dau, thoi_gian_ket_thuc, dia_diem, trang_thai, so_luong_toi_da, tong_kinh_phi_du_tru, poster, registered_count}` |
| POST `/events/` | `{ten_hoat_dong, mo_ta?, loai_hd, thoi_gian_bat_dau, thoi_gian_ket_thuc, dia_diem, vi_do?, kinh_do?, ban_kinh_m?, so_luong_toi_da?, tong_kinh_phi_du_tru?}` | event |
| GET `/events/{id}/` | — | detail + `vi_do, kinh_do, ban_kinh_m, mo_ta, budget_details[], created_by_email` |
| PATCH `/events/{id}/` | partial | event |
| GET `/events/{id}/tasks/` | — | **PLAN (không phải items!):** `{tasks:[{id, event, ten_task, nguoi_phu_trach, nguoi_phu_trach_ten, depends_on_detail:[{id,ten_task}], is_completed, deadline}], is_valid_dag, topological_order:[taskId], cycle:[taskId]|null, executable_now:[taskId]}` |
| POST `/events/{id}/tasks/` | `{ten_task, nguoi_phu_trach?, depends_on?: [taskIds], deadline?}` | task |
| PATCH `/events/{id}/tasks/{taskId}/` | `{is_completed: bool}` (đã thêm endpoint mới) | task — `is_completed:true` tự cộng XP người phụ trách. KHÓA checkbox khi `executable_now` không chứa task (DAG). **Audit F08**: `is_completed:false` khi còn hậu nhiệm (trực tiếp/gián tiếp) đã hoàn thành → **400** + `errors.blocking_tasks: [{id, ten_task}]` |
| GET `/events/{id}/tasks/topological-order/` | — | **DAG**: mảng id theo thứ tự topo hợp lệ (Kahn) hoặc báo deadlock (cycle) |
| GET `/events/my-tickets/` | — | **MẢNG** vé của chính tôi (member): EventRegistrationSerializer — render QR theo `ma_ve` |
| POST `/events/{id}/register/` | — (user hiện tại) | `{id, ma_ve, trang_thai, member, member_ten, event, event_ten, created_at}` — `ma_ve` dùng render QR |
| POST `/events/{id}/cancel-registration/` | — | hủy vé |
| GET `/events/{id}/registrations/` | — | items: EventRegistrationSerializer |
| GET `/events/{id}/budget/` | — | `{items:[...], tong_kinh_phi_du_tru}` |
| POST `/events/{id}/budget/` | `{ten_hang_muc, so_tien>0, ghi_chu?}` (BCN) | hạng mục mới + tổng tự tính lại |
| GET/POST `/events/{id}/communications/` | POST `{tieu_de, noi_dung?...}` (field chính là `tieu_de`) | truyền thông |

*Ghi chú: cả `POST /events/{id}/register/` lẫn hủy vé trả envelope với `data` = EventRegistrationSerializer.

### 3.5 Attendance — `/attendance`
| Method + Path | Body/Query | Response |
|---|---|---|
| GET `/attendance/sessions/` | `?trang_thai=OPEN|CLOSED&page=` | items: `{id, ten_phien, vi_do, kinh_do, ban_kinh_m, trang_thai, mo_phien_at, hieu_luc_den, event, event_ten, ...}` (không có nonce_secret) |
| POST `/attendance/sessions/` | `{ten_phien, vi_do, kinh_do, ban_kinh_m?, event?, hieu_luc_den?}` (BCN) | phiên + tự tạo VẮNG cho mọi member |
| GET `/attendance/sessions/{id}/` | — | detail |
| POST `/attendance/sessions/{id}/close/` | — (BCN) | đóng phiên |
| GET `/attendance/sessions/{id}/nonce/` | — (BCN) | `{nonce: "123456"}` mã xoay 60s — hiển thị máy chiếu |
| POST `/attendance/sessions/{id}/bulk-override/` | `{items: [{member_id, trang_thai: CO_MAT|VANG|CO_PHEP|DI_MUON}]}` (BCN) — **dùng HTTP PUT (không phải POST!)** | `{updated: n}`. **Audit F01**: atomic — validate TOÀN BỘ trước, có 1 item sai → 400 và KHÔNG ghi gì cả (all-or-nothing) |
| GET `/attendance/sessions/{id}/records/` | `?trang_thai=CO_MAT|CO_PHEP|DI_MUON|VANG&search=&page=` (BCN) — **audit F10**: bảng bản ghi theo phiên | items: `{id, member, member_ten, member_mssv, member_lop, trang_thai, khoang_cach_m, checked_in_at, device_id, is_suspicious, xp_awarded, overridden_by, overridden_by_email, created_at, updated_at}` (không có GPS thô) + pagination |
| POST `/attendance/check-in/` | `{session_id, latitude, longitude, client_time (ISO), device_id, nonce, is_mock?, accuracy?}` | record: `{id, session, session_ten, member, member_ten, trang_thai CO_MAT|DI_MUON, khoang_cach_m, ...}` + `xp_gained` + `streak_count` |
| GET `/attendance/me/` | — | items AttendanceRecordSerializer: `{id, session, session_ten, member, member_ten, trang_thai, khoang_cach_m, vi_do, kinh_do, checked_in_at, device_id, is_suspicious, xp_awarded, overridden_by, created_at}` — **`member` = profile pk, dùng lấy profile id** |

⚠️ Lỗi check-in hay gặp: `409 SessionClosedException`, `400` anti-cheat (mock/nonce sai/xa quá bán kính/teleport), `409` đã check-in — **audit F07**: trùng chặn CẢ CO_MAT lẫn DI_MUON (check-in muộn gửi lại cũng 409, không sửa metadata/XP).

### 3.6 Gamification — `/gamification` (mọi user)
| Method + Path | Response |
|---|---|
| GET `/gamification/leaderboard/` | `{top_10:[{rank, id, xp, name, avatar, extra}], my_position:{in_top_k, rank, xp_gap_to_top_k}|null, total_members}` |
| GET `/gamification/badges/` | `{items:[{id, ma_badge, ten_badge, mo_ta, icon (EMOJI như 🔥🎯 — render trực tiếp, KHÔNG qua Icons.render), unlocked}], unlocked:[ma_badge]}` |
| GET `/gamification/me/` | `{xp, level, streak_count, badges:[{badge:{...}, awarded_at}], weekly_quests: {week_start, xp_this_week, attendance_count, document_shared, task_completed} (OBJECT counter — KHÔNG phải mảng)}` |

**Mẹo lấy profile id của member** (cần cho profile360): `top_10[i].id` chính là profile pk; nếu tôi trong top 10 thì dùng được ngay. Fallback: `GET /attendance/me/` → `items[0].member`.

### 3.7 Documents — `/documents`
| Method + Path | Body/Query | Response |
|---|---|---|
| GET `/documents/` | `?nhom=&search=&sort=&page=` | items: `{id, tieu_de, nhom, tags, mo_ta, file, file_type, file_size, luot_tai, uploaded_by, uploaded_by_ho_ten, created_at}` |
| POST `/documents/` | FormData: `{file, tieu_de, nhom, tags?, mo_ta?}` (BCN; file ≤15MB: pdf/docx/pptx/xlsx/png/jpg) | doc |
| GET `/documents/search/?q=` | `q` | `{items:[...], count}` — Trie autocomplete (chú ý: có bọc items) |
| GET `/documents/{id}/` | — | doc |
| GET `/documents/{id}/download/` | — | file (dùng `ApiClient.download`/`getBlob` — audit F04: blob tự refresh single-flight đúng 1 lần khi 401) — tăng luot_tai |
| GET `/documents/{id}/preview/` | — | file **inline** xem trước (audit F05) — cùng phạm vi quyền download, KHÔNG tăng luot_tai, không cộng XP |
| DELETE `/documents/{id}/` | — (BCN đơn vị upload) | xóa |

### 3.8 Posts / Feedback / Polls — mounted trực tiếp `/api/v1/`
| Method + Path | Body/Query | Response |
|---|---|---|
| GET `/posts/` | `?page=` | items: `{id, tieu_de, noi_dung, anh_dinh_kem, is_pinned, created_by, created_at}` (pinned trước) |
| POST `/posts/` | `{tieu_de, noi_dung, anh_dinh_kem?}` (BCN) | post |
| PATCH `/posts/{id}/` | partial (BCN) | post |
| DELETE `/posts/{id}/` | — (BCN) | soft delete |
| POST `/posts/{id}/pin/` | — (BCN) | ghim/bỏ ghim |
| POST `/feedback/` | `{noi_dung}` (auth, 5/ngày) | góp ý ẩn danh |
| GET `/feedback/` | — (BCN) | items `{id, noi_dung, created_at}` — KHÔNG có sender |
| GET `/polls/` | — | items `{id, question, options:["a","b"], votes:{"0":n,...}, is_closed, total_votes, has_voted (theo user hiện tại — audit F12: khóa UI vote từ server, không dùng localStorage không user-prefix), created_at}` |
| POST `/polls/` | `{question, options:[≥2]}` (BCN) | poll |
| POST `/polls/{id}/vote/` | `{option_index: 0..n-1}` | poll sau vote (mỗi user 1 lần) |

### 3.9 Common
- GET `/api/health/` → `{status:"healthy", database:true}`

## 4. Design system (tokens + components sẵn có)

### Import (đặt theo thứ tự này)
```html
<link rel="stylesheet" href="/frontend/css/variables.css">
<link rel="stylesheet" href="/frontend/css/base.css">
<link rel="stylesheet" href="/frontend/css/components.css">
<link rel="stylesheet" href="/frontend/css/glassmorphism.css">  <!-- member -->
<link rel="stylesheet" href="/frontend/css/responsive.css">
```
- `<html lang="vi" data-theme="admin">` cho trang admin, `data-theme="member"` cho trang member.
- Font: Inter (Google Fonts link có sẵn trong login.html — copy vào head).
- JS load CUỐI body, thứ tự: `api.js → icons.js → toast.js → utils.js → auth.js → celebration.js (member) → trang`.

### Class sẵn có (KHÔNG tự viết lại)
- Layout admin: `.admin-shell > .admin-sidebar + .admin-main` → `.admin-topbar` + `.admin-content`. Sidebar: `.side-brand`, `.side-nav > .nav-label + .nav-item(.active)`, `.side-foot`. Burger: `.btn.btn-ghost.burger` toggle `.nav-open` trên `.admin-shell` + `.scrim`.
- Layout member: `.member-shell` (max 560px) → `.member-header` + content; nav: `.bottom-nav > a(.active, .nav-cta)`.
- Component: `.btn .btn-primary|btn-violet|btn-outline|btn-ghost|btn-danger .btn-sm|btn-lg|btn-block|btn-icon`; `.card .card-pad|card-header|card-body|card-footer`; `.table-wrap > table.table` (`.num`, `.actions`); `.badge .badge-success|danger|warning|info|accent|neutral`; `.modal-backdrop > .modal` (`.modal-head|modal-body|modal-foot`, `.modal-close`); `.form-group > .form-label + .form-input|.form-select|.form-textarea + .form-hint|.form-error`; `.form-row` (2 cột); `.input-wrap + .input-trailing`; `.tabs > .tab(.active)`; `.pagination` (`.page-info`, `.page-btns`); `.kpi-grid > .kpi` (`.kpi-icon`, `.kpi-value`, `.kpi-label`); `.avatar(.avatar-lg|.avatar-sm|.violet)`; `.progress > span` (width %); `.searchbar`; `.autocomplete > .ac-list > .ac-item`; `.menu-wrap > .menu > .menu-item`; `.skeleton` + `.skeleton-row/.skeleton-avatar/.skeleton-lines`; `.empty` + `.empty-icon`.
- Member glass: `.glass`, `.glass-strong`, `.glass-accent`, `.page-title`, `.radar` (+ `.radar-ring`, `.radar-sweep`, `.radar-dot.ok|.far`), `.podium > .podium-slot.first|second|third` + `.pillar-1|2|3` + `.crown`, `.holo-card`, `.holo-id`, `.ticket` (`.ticket-top`, `.ticket-notch > .dash`, `.ticket-qr`, `.ticket-code`), `.streak-chip`, `.level-ring` (CSS var `--pct`).
- Utilities: `.hidden .muted .secondary .small .xs .bold .mono .w-100 .mt-2 .mt-4 .mt-6 .mb-2 .mb-4 .mb-6 .flex .flex-1 .items-center .justify-between .gap-2 .gap-3 .gap-4 .wrap .text-center`.

### JS helpers (chỉ DÙNG, không định nghĩa lại)
```js
Icons.render(name, size) / Icons.el(name)   // tên icon xem js/icons.js
Toast.success|error|warning|info(msg, title?)
Utils.fmtVND(n) .fmtNum(n) .fmtDate(s) .fmtDateTime(s) .fmtTime(s) .timeAgo(s)
Utils.initials(name) .escapeHtml(s) .debounce(fn, ms) .guard(fn)
Utils.qs(sel) .qsa(sel) .getQueryParam(name)
Utils.skeleton(container, rows, {avatar:true})        // trạng thái tải
Utils.empty(container, {icon, title, desc, actionLabel, onAction})  // trạng thái trống
Utils.btnLoading(btn, text) → undo()                  // nút loading
Utils.badge(text, tone)                               // span badge
Celebrate.cheer() / Celebrate.at(el)                  // confetti
new QRCode(el, {text, width, height, correctLevel})   // assets/qrcode.min.js
```

### Quy tắc bắt buộc (từ skill design-taste-frontend)
1. Form: label TRÊN input, không dùng placeholder làm label; error dưới input (`.form-error`).
2. Mọi list phải có 3 trạng thái: skeleton (đang tải) → dữ liệu → empty state.
3. Nút submit luôn qua `Utils.btnLoading`, bọc handler bằng try/catch + Toast.error(err.message).
4. `escapeHtml` MỌI dữ liệu động chèn vào innerHTML (hoặc tạo node + textContent).
5. Bo góc: cards 16px, controls 10px, badge pill — KHÔNG dùng radius khác.
6. Icon: chỉ dùng `Icons.render` (Feather). Emoji chỉ nơi spec yêu cầu (streak 🔥, podium).
7. Mobile: mọi grid 2 cột phải rõ ràng hoạt động 1 cột <768px (đã có `.form-row`, `.kpi-grid`; grid riêng tự khai `@media`).
8. Không dùng màu ngoài tokens; không auto-themed dark/light lẫn lộn (mỗi trang 1 theme).
9. `Admin sidebar nav` active class theo trang; member bottom-nav tương tự.
10. Ngôn ngữ 100% tiếng Việt, giọng thân thiện Gen Z cho member, chuyên nghiệp cho admin.

### 4b. Ngoại lệ được duyệt — Trang chủ member (Landing M3) — `frontend/member/home.html`
Trang chủ thành viên được thiết kế lại theo bản thiết kế Material 3 của chủ dự án (10/2026) — KHÔNG theo khung member-shell/bottom-nav:
- Layout: sidebar thu gọn + topbar + hero + feed 2 cột + widget. Font Plus Jakarta Sans + Material Symbols (Google Fonts).
- CSS: `frontend/css/landing.css` là Tailwind **biên dịch TĨNH** (không có runtime `cdn.tailwindcss.com` — CSP chặn script ngoài). Thứ tự nạp: `variables.css` → `components.css` (cho Toast) → `landing.css` → `<style>` page-scoped. `data-theme="member"` vẫn giữ trên `<html>`.
- Guard/API/Toast/Utils dùng chung như mọi trang; icon dùng Material Symbols ligature (`<span class="material-symbols-outlined">ten_icon</span>`) thay `Icons.render` (Feather) — đúng theo design.
- Reaction ❤️/🔥, lưu bài 🔖 là **local-first** (localStorage key có prefix user id) — chờ backend reaction API; bình chọn khóa nhờ `has_voted` từ server.
- Free-text từ backend đã qua bleach (escape `&`) → trang decode entity trước khi escape lại (helper `unesc`) để không hiện `&amp;` kép.
- Các trang member KHÁC vẫn theo §4/§5 chuẩn (member-shell + bottom-nav).

## 5. Skeleton HTML chuẩn

### Trang ADMIN (copy đầu + cuối, thay nội dung)
```html
<!DOCTYPE html>
<html lang="vi" data-theme="admin">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>… — Quản trị CLB IP</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/frontend/css/variables.css">
  <link rel="stylesheet" href="/frontend/css/base.css">
  <link rel="stylesheet" href="/frontend/css/components.css">
  <link rel="stylesheet" href="/frontend/css/responsive.css">
</head>
<body>
<div class="admin-shell" id="shell">
  <aside class="admin-sidebar">
    <div class="side-brand">
      <span class="logo" id="brand-logo"></span>
      <div><div class="t1">CLB IP ĐHSP Huế</div><div class="t2">Quản trị 2.0</div></div>
    </div>
    <nav class="side-nav" id="side-nav"><!-- JS render nav — xem §6 --></nav>
    <div class="side-foot">
      <button class="btn btn-ghost w-100" id="btn-logout" style="color:var(--tx-sidebar)">Đăng xuất</button>
    </div>
  </aside>
  <div class="scrim hidden" id="scrim"></div>
  <div class="admin-main">
    <header class="admin-topbar">
      <div class="flex items-center gap-3">
        <button class="btn btn-ghost burger" id="btn-burger" aria-label="Mở menu"><span id="burger-icon"></span></button>
        <h1 style="font-size:var(--text-lg)">Tên trang</h1>
      </div>
      <div class="flex items-center gap-3" id="topbar-user"><!-- avatar + tên --></div>
    </header>
    <main class="admin-content">
      <!-- NỘI DUNG TRANG -->
    </main>
  </div>
</div>
<script src="/frontend/js/api.js"></script>
<script src="/frontend/js/icons.js"></script>
<script src="/frontend/js/toast.js"></script>
<script src="/frontend/js/utils.js"></script>
<script src="/frontend/js/auth.js"></script>
<script>
  // 1. Icons tĩnh
  // 2. Auth.requireRole(["ADMIN","BCN"]).then(init)
  // 3. renderAdminNav("dashboard") — hàm chung §6
  // 4. NỘI DUNG logic trang
</script>
</body>
</html>
```

### Trang MEMBER (tương tự, theme member)
```html
<html lang="vi" data-theme="member">
...css + glassmorphism.css + responsive.css...
<body>
  <div class="member-shell">
    <header class="member-header">
      <div class="flex items-center gap-3">
        <span class="avatar" id="me-avatar"></span>
        <div><div class="bold small" id="me-name">…</div><div class="xs muted" id="me-level">…</div></div>
      </div>
      <button class="btn btn-ghost btn-icon" id="btn-logout" aria-label="Đăng xuất"><span id="logout-icon"></span></button>
    </header>
    <!-- NỘI DUNG -->
    <div style="height:8px"></div>
  </div>
  <nav class="bottom-nav" id="bottom-nav"><!-- JS render — §6 --></nav>
  <script …api/icons/toast/utils/auth/celebration…></script>
  <script> Auth.requireRole(["MEMBER"]).then(init); renderMemberNav("home"); </script>
</body>
```

## 6. Nav dùng chung (DÁN VÀO MỖI TRANG — hàm có sẵn shape, copy vào script)

```js
// ADMIN — gọi renderAdminNav("dashboard"|"members"|"funds"|"events"|"attendance"|"documents")
function renderAdminNav(active) {
  document.getElementById("brand-logo").innerHTML = Icons.render("zap", 20);
  const items = [
    ["dashboard", "layout", "Dashboard", "/frontend/admin/dashboard.html"],
    ["members", "users", "Thành viên", "/frontend/admin/members.html"],
    ["funds", "wallet", "Quỹ CLB", "/frontend/admin/funds.html"],
    ["events", "calendar", "Sự kiện", "/frontend/admin/events.html"],
    ["attendance", "compass", "Điểm danh", "/frontend/admin/attendance.html"],
    ["documents", "book-open", "Tài liệu", "/frontend/admin/documents.html"],
  ];
  document.getElementById("side-nav").innerHTML =
    '<div class="nav-label">Quản lý</div>' +
    items.map(([k, ic, label, href]) =>
      `<a class="nav-item${k === active ? " active" : ""}" href="${href}">${Icons.render(ic, 18)}<span>${label}</span></a>`
    ).join("");
  // topbar user + logout + burger (bắt buộc có ở mọi trang admin)
  const user = Auth.cachedUser();
  document.getElementById("topbar-user").innerHTML =
    `<span class="small bold">${Utils.escapeHtml(user?.ho_ten || user?.email || "")}</span>
     <span class="avatar avatar-sm" title="${Utils.escapeHtml(user?.role || "")}">${Utils.initials(user?.ho_ten || user?.email)}</span>`;
  document.getElementById("burger-icon").innerHTML = Icons.render("menu", 20);
  document.getElementById("logout-icon-burger");
  document.getElementById("btn-burger").addEventListener("click", () => {
    document.getElementById("shell").classList.add("nav-open");
    document.getElementById("scrim").classList.remove("hidden");
  });
  document.getElementById("scrim").addEventListener("click", () => {
    document.getElementById("shell").classList.remove("nav-open");
    document.getElementById("scrim").classList.add("hidden");
  });
  document.getElementById("btn-logout").addEventListener("click", () => Auth.logout());
}

// MEMBER — gọi renderMemberNav("home"|"events"|"checkin"|"leaderboard"|"profile"|"documents")
function renderMemberNav(active) {
  const items = [
    ["home", "home", "Nhà", "/frontend/member/home.html"],
    ["events", "calendar", "Sự kiện", "/frontend/member/events.html"],
    ["checkin", "compass", "Check-in", "/frontend/member/checkin.html", true],  // nav-cta
    ["leaderboard", "trophy", "Xếp hạng", "/frontend/member/leaderboard.html"],
    ["profile", "user", "Hồ sơ", "/frontend/member/profile.html"],
    ["documents", "book-open", "Tài liệu", "/frontend/member/documents.html"],
  ];
  document.getElementById("bottom-nav").innerHTML = items.map(([k, ic, label, href, cta]) =>
    `<a href="${href}" class="${k === active ? "active" : ""}${cta ? " nav-cta" : ""}" ${k === active ? 'aria-current="page"' : ""}>
      ${Icons.render(ic, cta ? 24 : 21)}<span>${label}</span></a>`
  ).join("");
  document.getElementById("logout-icon").innerHTML = Icons.render("logout", 20);
  document.getElementById("btn-logout").addEventListener("click", () => Auth.logout());
  // fill thông tin tôi (nếu các id tồn tại)
  const me = Auth.cachedUser();
  const av = document.getElementById("me-avatar");
  if (av && me) av.textContent = Utils.initials(me.ho_ten || me.email);
  const nm = document.getElementById("me-name");
  if (nm && me) nm.textContent = me.ho_ten || me.email;
  const lv = document.getElementById("me-level");
  if (lv && me) lv.textContent = `Level ${me.current_level ?? "?"} · ${me.xp_points ?? 0} XP`;
}
```
(Điều chỉnh nhỏ nếu id khác — giữ đúng hành vi: burger mở/đóng drawer + scrim, logout, active state.)

## 7. Modal helper (không có sẵn — dùng pattern này ở mọi trang cần modal)
```js
function openModal({ title, bodyHTML, onMount, footerHTML = "" }) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-label="${Utils.escapeHtml(title)}">
      <div class="modal-head"><h3>${Utils.escapeHtml(title)}</h3>
        <button class="modal-close">${Icons.render("x", 20)}</button></div>
      <div class="modal-body">${bodyHTML}</div>
      ${footerHTML ? `<div class="modal-foot">${footerHTML}</div>` : ""}
    </div>`;
  const close = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  backdrop.querySelector(".modal-close").addEventListener("click", close);
  document.body.appendChild(backdrop);
  if (onMount) onMount(backdrop, close);
  return { el: backdrop, close };
}
```

## 8. Bản đồ trang ↔ API (tóm tắt tính năng DSA phải hiện trên UI)
| Trang | API chính | Hiệu ứng DSA bắt buộc |
|---|---|---|
| member/checkin.html | sessions?trang_thai=OPEN, nonce (BCN), check-in | `.radar` pulse + geolocation + khoảng cách Haversine hiển thị số mét + nút khóa/mở + confetti khi thành công |
| member/leaderboard.html | gamification/leaderboard | Podium `.podium` Top 1-2-3 + bảng còn lại + thẻ my_position (rank, gap) |
| member/events.html | events/, {id}/register/, registrations của tôi | Vé QR: `new QRCode(el,{text: ma_ve})` + `.ticket` Apple Wallet |
| member/documents.html | documents/search/?q= | Trie autocomplete `.ac-list` debounce 300ms |
| admin/members.html | members/, search, profile360, import/export | Trie autocomplete tìm thành viên |
| admin/events.html | events/, tasks/, topological-order | DAG checklist: thứ tự topo, khóa task chưa đủ điều kiện |
| admin/attendance.html | sessions CRUD, nonce, bulk-override | Hiện nonce lớn xoay 60s + bản đồ khoảng cách |
| admin/funds.html | funds/, stats, lock-period | KPI + cảnh báo quỹ thấp + khóa sổ |
| admin/dashboard.html | posts/, polls/, members/, funds/stats, events/ | KPI + feed ghim bài + poll vote |
| admin/documents.html | documents/, upload, download | Upload + preview PDF (iframe) |

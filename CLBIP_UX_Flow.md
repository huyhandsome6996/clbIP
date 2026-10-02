# CLBIP — LUỒNG UX 17 MÀN HÌNH (UX Flow)

> Tài liệu đáp ứng QA-Audit: mô tả **17 màn hình** theo đặc tả `CLBIP_Master_Coding_Prompt.md` §4, đối chiếu trung thực với code.
> URL "thực tế" = đường dẫn frontend thật do `core/urls.py` phục vụ (`/frontend/...`). Spec viết tắt kiểu `/admin/dashboard` — thực tế là file HTML tĩnh `/frontend/admin/dashboard.html` (xem mục **Deviations** cuối file).
> Mọi endpoint trong luồng đều đã grep xác nhận tồn tại trong `apps/*/urls.py` và được gọi thật từ file HTML tương ứng (tìm `ApiClient.*`).

---

## 🅰️ PHÂN HỆ QUẢN TRỊ BCN (10 MÀN HÌNH)

### Màn hình 1 — Đăng nhập
- **URL thực tế:** `/frontend/login.html` (hub điều hướng: `/frontend/index.html`)
- **Vai trò:** chung (ADMIN / BCN / MEMBER đều đăng nhập từ đây)
- **Luồng chính:**
  1. User nhập Email + Mật khẩu → bấm `[Đăng nhập]` → `POST /api/v1/auth/token/` (throttle `auth_login` 5/phút).
  2. Thành công: nhận `{access, refresh, user}` → `Auth.login()` lưu token + user_info vào localStorage → điều hướng theo role: ADMIN/BCN → `/frontend/admin/dashboard.html`, MEMBER → `/frontend/member/home.html` (`frontend/js/auth.js` `ROLE_HOME`).
  3. Trang còn token hợp lệ → `Auth.redirectIfLoggedIn()` tự chuyển thẳng về trang nhà.
  4. Mọi request sau đó: `ApiClient` tự gắn `Authorization: Bearer`; gặp 401 → refresh đúng 1 lần qua `POST /api/v1/auth/token/refresh/`, fail → đá về `login.html?expired=1`.
- **Trạng thái rỗng/lỗi:** sai thông tin → toast/inline lỗi tiếng Việt (`#email-error`, `#password-error`); nút có loading spinner (`Utils.btnLoading`); đăng nhập sai liên tục 5 lần → django-axes khóa 15 phút (`apps/common/axes_callbacks.py`).
- **Chưa có so với spec:** checkbox "Ghi nhớ đăng nhập", link "Quên mật khẩu?" + modal OTP email.

### Màn hình 2 — Dashboard BCN
- **URL thực tế:** `/frontend/admin/dashboard.html`
- **Vai trò:** ADMIN / BCN
- **Luồng chính:**
  1. Tải KPI song song: `GET /api/v1/members/`, `GET /api/v1/funds/stats/` (cảnh báo quỹ thấp nếu `low_balance`), `GET /api/v1/events/?trang_thai=OPEN_REGISTRATION`, `GET /api/v1/attendance/sessions/?trang_thai=OPEN`.
  2. `[Đăng thông báo mới]` → modal soạn `tieu_de` + `noi_dung` → `POST /api/v1/posts/` (backend bleach chống XSS + ghi `PostAuditLog`).
  3. `[Ghim/Bỏ ghim]` → `PATCH /api/v1/posts/{id}/pin/` · `[Xóa bài]` (có xác nhận) → `DELETE /api/v1/posts/{id}/` (soft delete + audit).
  4. Bình chọn: `GET /api/v1/polls/` → `[Tạo bình chọn]` → `POST /api/v1/polls/` (question + options) → BCN vote thử `POST /api/v1/polls/{id}/vote/`.
  5. `[Xem hòm thư góp ý]` → `GET /api/v1/feedback/` (danh sách ẩn danh, không lộ người gửi).
- **Trạng thái rỗng/lỗi:** KPI lỗi từng khối hiển thị "—"; poll rỗng → `Utils.empty("Chưa có bình chọn nào…")`; feed rỗng → empty state; mọi lỗi → Toast (`toast.js`).
- **Chưa có so với spec:** biểu đồ Chart.js; modal đăng bài chưa có upload ảnh; sửa bài chưa có nút UI (API `PUT/PATCH /posts/{id}/` có sẵn).

### Màn hình 3 — Quản lý Thành viên
- **URL thực tế:** `/frontend/admin/members.html`
- **Vai trò:** ADMIN / BCN
- **Luồng chính:**
  1. Bảng thành viên: `GET /api/v1/members/?page&lop&trang_thai_hd&search` (sort whitelist ở backend).
  2. Ô tìm kiếm gõ nhanh → debounce → `GET /api/v1/members/search/?q=` (Prefix Trie, trả `{items:[...]}`) → dropdown gợi ý.
  3. `[+ Thêm thành viên]` → form → `POST /api/v1/members/` (backend dup-check email/MSSV).
  4. Click dòng → modal **Hồ sơ 360°**: `GET /api/v1/members/{id}/profile360/` (số sự kiện, chuyên cần %, XP/Level/Streak, huy hiệu, vai trò BCN).
  5. `[Sửa]` → `GET /api/v1/members/{id}/` đổ form → `PATCH /api/v1/members/{id}/`; `[Khóa]` → `PATCH /api/v1/members/{id}/` với `trang_thai_hd`.
  6. `[Nhập từ Excel]` → `POST /api/v1/members/import-excel/` (FormData) → hiển thị preview `{created, errors:[{row, ho_ten, error}]}`.
  7. `[Xuất Excel]` → `ApiClient.download("/members/export-excel/")`.
  8. Cơ cấu BCN: `GET /api/v1/members/board/` → `[Bổ nhiệm]` → tìm người qua `/members/search/` → `POST /api/v1/members/board/`.
- **Trạng thái rỗng/lỗi:** skeleton bảng khi tải; bảng rỗng → "Không tìm thấy thành viên nào — thử đổi từ khóa hoặc xóa bộ lọc"; lỗi từng dòng import được liệt kê, dòng hợp lệ vẫn lưu.

### Màn hình 4 — Quản lý Quỹ CLB
- **URL thực tế:** `/frontend/admin/funds.html`
- **Vai trò:** ADMIN / BCN
- **Luồng chính:**
  1. Tải KPI: `GET /api/v1/funds/stats/` → tổng thu / tổng chi / số dư + **cảnh báo vàng nếu `low_balance` (<200.000đ)**.
  2. Sổ quỹ: `GET /api/v1/funds/?page&loai_gd&from_date&to_date&sort` (phân trang).
  3. `[+ Lập phiếu Thu/Chi]` → form (số tiền, người thực hiện, hình thức, ngày GD, ghi chú) → `POST /api/v1/funds/` → nhận `so_du_sau` → toast "Số dư mới: …". Backend chạy atomic + `select_for_update` + invariants (chi vượt dư → 400).
  4. `[Khóa sổ kỳ]` → `POST /api/v1/funds/lock-period/` (tu_ngay/den_ngay) → giao dịch trong kỳ bị đóng băng; danh sách kỳ đã khóa: `GET /api/v1/funds/locks/`.
  5. `[Xuất sổ quỹ Excel]` → `ApiClient.download("/funds/export-excel/")`.
- **Trạng thái rỗng/lỗi:** skeleton bảng; rỗng → "Chưa có giao dịch nào — ghi sổ thu/chi đầu tiên…"; lỗi validate hiển thị theo field; thiếu tiền → thông báo 400 từ envelope.

### Màn hình 5 — Quản lý Kế hoạch & Sự kiện
- **URL thực tế:** `/frontend/admin/events.html`
- **Vai trò:** ADMIN / BCN
- **Luồng chính:**
  1. Danh sách sự kiện: `GET /api/v1/events/` (lọc/trang).
  2. `[+ Tạo kế hoạch sự kiện]` → form (có thể kèm nested `budget_details`) → `POST /api/v1/events/` (mã `EV{năm}{seq}` tự sinh).
  3. Mở chi tiết: `GET /api/v1/events/{id}/` → modal 4 tab:
     - **Tab Công việc (DAG):** `GET /api/v1/events/{id}/tasks/` → nhận `{tasks, is_valid_dag, topological_order, cycle, executable_now}` → sắp theo thứ tự topo, cảnh báo deadlock nếu `cycle`; `[+ Thêm task]` → `POST /api/v1/events/{id}/tasks/` (chọn người phụ trách qua `GET /api/v1/members/?page_size=100`, chọn phụ thuộc); tick hoàn thành → `PATCH /api/v1/events/{id}/tasks/{task_id}/` (`is_completed`).
     - **Tab Dự trù kinh phí:** `GET /api/v1/events/{id}/budget/` → thêm hạng mục → `POST /api/v1/events/{id}/budget/` → tổng tiền tự cập nhật lên sự kiện.
     - **Tab Đăng ký:** `GET /api/v1/events/{id}/registrations/` (danh sách vé + mã `ma_ve` dạng text).
     - **Tab Truyền thông:** `GET /api/v1/events/{id}/communications/` → thêm bài đăng FB/TikTok + deadline + link → `POST /api/v1/events/{id}/communications/`.
  4. Sửa nhanh trạng thái sự kiện → `PATCH /api/v1/events/{id}/`.
- **Trạng thái rỗng/lỗi:** tab rỗng → empty state; `is_valid_dag=false` → cảnh báo vòng lặp ngay trong tab; lỗi form hiển thị theo field.

### Màn hình 6 — Quản lý Điểm danh GPS
- **URL thực tế:** `/frontend/admin/attendance.html`
- **Vai trò:** ADMIN / BCN
- **Luồng chính:**
  1. Card "phiên đang mở": `GET /api/v1/attendance/sessions/?trang_thai=OPEN`.
  2. `[+ Mở phiên điểm danh mới]` → form tự điền tọa độ bằng `navigator.geolocation` (nút "Dùng GPS hiện tại") + bán kính + hiệu lực + gắn sự kiện (tuỳ chọn, danh sách từ `GET /api/v1/events/`) → `POST /api/v1/attendance/sessions/` → backend tự tạo bản ghi VẮNG cho mọi thành viên ACTIVE.
  3. Hiển thị **mã nonce cho máy chiếu**: `GET /api/v1/attendance/sessions/{id}/nonce/` → số 6 chữ số + đếm ngược `expires_in`, tự lấy mã mới mỗi 60s.
  4. `[Đóng phiên]` → `POST /api/v1/attendance/sessions/{id}/close/` → chốt danh sách.
  5. `[Cập nhật thủ công hàng loạt]` → lấy danh sách thành viên `GET /api/v1/members/?page_size=100` → chọn trạng thái từng người → **`PUT /api/v1/attendance/sessions/{id}/bulk-override/`** với `{items:[{member_id, trang_thai}]}`.
  6. Lịch sử phiên: `GET /api/v1/attendance/sessions/?trang_thai=CLOSED` (bảng + phân trang).
- **Trạng thái rỗng/lỗi:** không có phiên mở → card hướng dẫn mở phiên; không lấy được GPS → Toast lỗi `err.message`; bắt buộc điền tọa độ trước khi lưu.

### Màn hình 7 — Kho Tài liệu BCN
- **URL thực tế:** `/frontend/admin/documents.html`
- **Vai trò:** ADMIN / BCN
- **Luồng chính:**
  1. Danh sách: `GET /api/v1/documents/` (lọc `nhom`, `search` icontains, phân trang).
  2. `[+ Tải lên tài liệu]` → FormData (file, tieu_de, nhom, tags, mo_ta, pham_vi) → `POST /api/v1/documents/` (backend hardening 4 tầng, +100 XP).
  3. Tìm nhanh: `GET /api/v1/documents/search/?q=` (Prefix Trie, BCN tra vùng FULL).
  4. `[Xem trước PDF]` → fetch blob file + `Authorization` header → nhúng xem ngay trong modal.
  5. `[Tải về]` → `ApiClient.download("/documents/{id}/download/")` (auth + đếm lượt tải).
  6. `[Xóa]` → `DELETE /api/v1/documents/{id}/`; phân nhóm chuyên môn qua bộ lọc `nhom` (CHUYEN_MON/NGHIEP_VU/KY_NANG).
- **Trạng thái rỗng/lỗi:** skeleton + empty state khi kho trống; file vượt 15MB / sai loại → lỗi 400 tiếng Việt từ `DocumentService.validate_file`.

### Màn hình 8 — Cơ cấu Ban Chủ nhiệm
- **URL thực tế:** **chưa có trang riêng** — chức năng nằm dưới dạng modal trong `/frontend/admin/members.html` (tham khảo Feature List #13)
- **Vai trò:** ADMIN / BCN
- **Luồng hiện tại (trong members.html):**
  1. `GET /api/v1/members/board/` — danh sách BCN theo nhiệm kỳ.
  2. `[Bổ nhiệm]` → tìm thành viên (`GET /api/v1/members/search/?q=`) → `POST /api/v1/members/board/` (chức vụ, ban phụ trách, nhiệm kỳ).
- **Thiếu:** sơ đồ tổ chức dạng cây (Org Chart), sửa/xóa nhiệm kỳ, màn hình độc lập theo spec §4 màn hình 8.

### Màn hình 9 — Báo cáo & Thống kê
- **URL thực tế:** **chưa có** (không file HTML, không endpoint báo cáo tổng hợp)
- **Vai trò:** ADMIN / BCN
- **Thực tế:** chỉ có số liệu rời rạc — `GET /api/v1/funds/stats/`, thống kê trong `GET /api/v1/members/{id}/profile360/`, leaderboard `GET /api/v1/gamification/leaderboard/`. Không có xuất PDF tổng kết kỳ (không có thư viện PDF trong `requirements.txt`), không có biểu đồ xu hướng chuyên cần.

### Màn hình 10 — Cài đặt Hệ thống
- **URL thực tế:** **chưa có**
- **Vai trò:** ADMIN
- **Thực tế:** cấu hình làm qua biến môi trường (`core/settings.py`, `render.yaml`) và Django admin `/admin/`. Chưa có UI "Cấu hình niên khóa", "Sao lưu Database", "Phân quyền quản trị viên".

---

## 🅱️ PHÂN HỆ THÀNH VIÊN (7 MÀN HÌNH)

### Màn hình 11 — Trang Chủ & Social Feed (Landing M3)
- **URL thực tế:** `/frontend/member/home.html`
- **Vai trò:** MEMBER (BCN/ADMIN bị điều hướng về dashboard theo phân hệ)
- **Thiết kế:** Material 3 Expressive theo bản thiết kế của chủ dự án (10/2026): sidebar thu gọn được + topbar + hero spotlight + quick actions + stories + feed 2 cột + widget. Font Plus Jakarta Sans + Material Symbols; CSS Tailwind biên dịch TĨNH tại `frontend/css/landing.css` (CSP chặn script CDN nên KHÔNG nạp Tailwind runtime). Guard/API/Toast dùng chung theo FRONTEND_CONTRACT.
- **Luồng chính:**
  1. Đăng nhập xong → hero chào theo giờ ("Chào buổi sáng/chiều/tối, {tên}! 🚀") + pill 🔥 streak: `GET /api/v1/gamification/me/` (`xp`, `level`, `streak_count`); XP pill trên topbar.
  2. **Hero pod "Sự kiện sắp tới"**: `GET /api/v1/events/` → sự kiện gần nhất chưa diễn ra (thời gian, địa điểm, `registered_count`, thanh tiến độ + "Chỉ còn X vé" từ `so_luong_toi_da`); CTAs → events/checkin.
  3. **4 Quick Action**: Điểm danh GPS (sub-text "Mở cổng HH:MM" từ `GET /attendance/sessions/?trang_thai=OPEN`), Đăng ký sự kiện (đếm sự kiện sắp tới), Tải bài giảng mới (tài liệu mới nhất từ `GET /documents/`), Hòm thư CLB (modal góp ý ẩn danh `POST /feedback/`).
  4. **Stories**: poster sự kiện (fallback gradient + icon), bấm → events.
  5. **Feed**: `GET /api/v1/posts/` (ghim trước) — card tác giả + thời gian + badge "GHIM THÔNG BÁO" + ảnh `anh_dinh_kem` + hành động ❤️/🔥/Góp ý BCN/🔖 (xem Deviation) + ô góp ý ẩn danh trên bài đầu → `POST /feedback/`.
  6. **Thẻ thành viên số**: họ tên, MSSV, lớp, Cấp + tên level, XP, thanh tiến độ theo `LEVEL_THRESHOLDS` backend, QR định danh render từ MSSV (`frontend/assets/qrcode.min.js`).
  7. **Top Chiến Thần**: `GET /gamification/leaderboard/` Top 3 + thanh "Vị trí của bạn" (rank, gap vào Top 10).
  8. **Nhiệm vụ tuần**: `weekly_quests` (điểm danh / chia sẻ tài liệu / task) + "+XP tuần này".
  9. **Bình chọn cộng đồng**: `GET /polls/` — khóa UI ngay từ tải đầu nhờ `has_voted` (server); vote → `POST /polls/{id}/vote/`; khóa toàn bộ option khi request chạy.
  10. Bell = thông báo đã ghim; user menu = hồ sơ + đăng xuất; footer = liên kết + modal Quy chế thành viên.
- **Trạng thái rỗng/lỗi:** mỗi khối tự skeleton → dữ liệu → empty/error riêng (Promise.allSettled) — lỗi 1 khối không chặn khối khác.
- **Deviation so với mockup (chủ ý, giữ tính trung thực dữ liệu):** số ❤️/🔥 không phải mock 48/115 — reaction local-first theo user; "Top Chiến Thần" là bảng vàng XP toàn CLB (backend chưa có leaderboard theo tuần); ảnh hero được vendor tại `frontend/assets/hero_bg.jpg`; nút "Tạo tin" ẩn (feed chỉ BCN đăng từ trang admin).

### Màn hình 12 — Điểm danh GPS Radar
- **URL thực tế:** `/frontend/member/checkin.html`
- **Vai trò:** MEMBER
- **Luồng chính:**
  1. Mở trang → xin quyền GPS (`navigator.geolocation`, nút `[Lấy vị trí lại]`).
  2. Tìm phiên đang mở: `GET /api/v1/attendance/sessions/?trang_thai=OPEN`.
  3. Nhập **mã nonce 6 chữ số** hiển thị trên máy chiếu (state.nonce).
  4. Radar quét: hiển thị khoảng cách đến tâm phiên (`radar-distance`) — trong/ ngoài bán kính → đổi màu nút xác nhận.
  5. Bấm `[XÁC NHẬN ĐIỂM DANH GPS]` → `POST /api/v1/attendance/check-in/` với `{session_id, latitude, longitude, client_time, device_id, nonce, is_mock, accuracy}`.
  6. Backend chạy 7 lớp anti-cheat → trả trạng thái (`CÓ MẶT`/`ĐI MUỘN`), XP nhận được, streak.
  7. UI: card kết quả (XP + 🔥 chuỗi điểm danh) + hiệu ứng confetti `Celebrate.cheer()` (`frontend/js/celebration.js`).
  8. Lịch sử cá nhân: `GET /api/v1/attendance/me/`.
- **Trạng thái rỗng/lỗi:** không có phiên mở → hướng dẫn chờ BCN; sai nonce / ngoài bán kính / fake GPS / teleport → thông báo lỗi tiếng Việt từ anti-cheat; không có quyền GPS → hướng dẫn bật lại.

### Màn hình 13 — Hub Sự kiện & Vé Điện Tử
- **URL thực tế:** `/frontend/member/events.html`
- **Vai trò:** MEMBER
- **Luồng chính:**
  1. Danh sách sự kiện: `GET /api/v1/events/?page` (phân trang).
  2. `[Đăng Ký Vé Tham Gia (Miễn phí)]` → `POST /api/v1/events/{id}/register/` → nhận `ma_ve` (`VE-XXXXXXXXXXXX`).
  3. Tab "🎟️ Vé của tôi": `GET /api/v1/events/my-tickets/` → `[Xem vé QR]` → render QR client-side từ `ma_ve` (`frontend/assets/qrcode.min.js`, khung kiểu ví Apple Wallet).
  4. `[Hủy vé]` → `POST /api/v1/events/{id}/cancel-registration/` → xóa khỏi danh sách vé.
- **Trạng thái rỗng/lỗi:** chưa có vé → empty state mời đăng ký; đăng ký trùng / sự kiện đóng đăng ký → lỗi 400/409 envelope → Toast.
- **Chưa có so với spec:** đồng hồ đếm ngược "giờ G" trên thẻ sự kiện; quét QR tại cửa hội trường (không có màn hình check-in vé cho BCN — tham khảo Feature List #32).

### Màn hình 14 — Bảng Vàng & Đua Top Thi Đua
- **URL thực tế:** `/frontend/member/leaderboard.html`
- **Vai trò:** MEMBER (BCN/ADMIN xem không có `my_position`)
- **Luồng chính:**
  1. `GET /api/v1/gamification/leaderboard/` → `{top_10, my_position, total_members}` (backend Min-Heap O(N log K)).
  2. Render bục vinh quang Top 1-2-3 + danh sách Top 10.
  3. Thanh ghim vị trí cá nhân: "Bạn đang ở Rank #N" + tính khoảng cách XP tới mốc Top 10 client-side → "Còn X XP nữa để vào Top 10 💪" (đã trong Top 10 thì hiện "Bạn đã ở trong Top 10 rồi! 🎉").
- **Trạng thái rỗng/lỗi:** BCN/ADMIN → ẩn thanh rank (`my_position` null); leaderboard rỗng → empty state.
- **Chưa có so với spec:** tab "nhiệm vụ tuần kiếm XP" nằm ở **Màn hình 11 (home)** thay vì trên bảng vàng (dữ liệu có sẵn trong `GET /gamification/me/`).

### Màn hình 15 — Hồ Sơ Cá Nhân & VIP Member Pass
- **URL thực tế:** `/frontend/member/profile.html`
- **Vai trò:** MEMBER (và mọi role đăng nhập)
- **Luồng chính:**
  1. Tải song song: `GET /api/v1/members/{profileId}/profile360/` + `GET /api/v1/gamification/me/` + `GET /api/v1/gamification/badges/`.
  2. Thanh cấp độ XP (Level 1→10) từ `xp`/`level`.
  3. Bộ sưu tập huy hiệu: badge đã mở (kèm thời điểm) + badge chưa mở (khóa).
  4. Rank cá nhân: `GET /api/v1/gamification/leaderboard/` (`my_position`); chuyên cần: `GET /api/v1/attendance/me/` (fallback khi profile360 thiếu).
  5. Sửa SĐT: `PATCH /api/v1/members/{profileId}/` (`{sdt}` — chỉ trường này được member tự sửa).
- **Trạng thái rỗng/lỗi:** user chưa có hồ sơ → 404 envelope → hướng dẫn; lỗi 1 nguồn dữ liệu vẫn render phần còn lại.
- **Chưa có so với spec:** thẻ thành viên Holographic lật xoay / lưu ảnh về máy.

### Màn hình 16 — Kho Báu Tài Liệu Học Thuật
- **URL thực tế:** `/frontend/member/documents.html`
- **Vai trò:** MEMBER
- **Luồng chính:**
  1. Danh sách: `GET /api/v1/documents/` (lọc `nhom`, phân trang) — backend tự scope: MEMBER chỉ thấy `PUBLIC_MEMBER`.
  2. Tìm kiếm thông minh: gõ tiền tố → `GET /api/v1/documents/search/?q=` (Prefix Trie, normalize bỏ dấu tiếng Việt).
  3. `[Đọc thử PDF]` → fetch blob file + Authorization → preview ngay trong modal, không rời trang.
  4. `[Tải về]` → `ApiClient.download("/documents/{id}/download/")` (auth + đếm lượt tải).
- **Trạng thái rỗng/lỗi:** kho trống → "Kho đang trống trơn — gõ từ khóa để tìm…"; không có quyền tài liệu BCN_ONLY → không xuất hiện trong kết quả.
- **Chưa có so với spec:** nút `[Chia sẻ tài liệu mới]` — API `POST /api/v1/documents/` thực tế mở cho mọi user đăng nhập (MEMBER upload sẽ được +100 XP, `pham_vi` BCN_ONLY bị ép về PUBLIC_MEMBER) nhưng **trang member chưa build form upload**; thao tác upload đang chỉ có ở `/frontend/admin/documents.html`.

### Màn hình 17 — Lịch Sinh Hoạt Thông Minh
- **URL thực tế:** **chưa có** (không có `frontend/member/calendar.html`, không có endpoint lịch tổng hợp, không có iCal/Google Calendar sync)
- **Vai trò:** MEMBER
- **Thực tế:** danh sách sự kiện chỉ xem được trong `/frontend/member/home.html` (chip sự kiện) và `/frontend/member/events.html`. Chưa có lịch tháng/tuần color-coded, chưa có `[+ Đồng bộ Google Calendar / iCal]`.

---

## SO SÁNH LUỒNG ADMIN vs MEMBER

| Khía cạnh | ADMIN / BCN | MEMBER |
|-----------|-------------|--------|
| Trang nhà sau login | `/frontend/admin/dashboard.html` | `/frontend/member/home.html` |
| Số màn hình có thật (trên 10/7 spec) | 7/10 (thiếu board, reports, settings) | 6/7 (thiếu calendar) |
| Điểm danh | Mở phiên + GPS tâm + nonce máy chiếu + bulk override (`PUT .../bulk-override/`) | Check-in GPS + nonce + radar + lịch sử `/attendance/me/` |
| Sự kiện | CRUD kế hoạch, DAG tasks, kinh phí, truyền thông, xem danh sách vé | Đăng ký / hủy vé, xem vé QR (`/events/my-tickets/`) |
| Quỹ | Toàn quyền ghi sổ, khóa sổ, xuất Excel | Không có quyền (endpoint chặn bằng `IsBCNOrAdmin`) |
| Thành viên | CRUD + import/export Excel + hồ sơ 360° của bất kỳ ai | Xem/sửa giới hạn hồ sơ mình (`IsOwnerOrBCN`, chỉ `sdt`) |
| Tài liệu | Upload (kể cả `BCN_ONLY`), xóa, xem toàn bộ kho (Trie vùng FULL) | Xem/tải/preview tài liệu `PUBLIC_MEMBER` (Trie vùng PUBLIC), chưa có form upload |
| Bảng tin | Đăng / ghim / xóa bài, đọc góp ý ẩn danh, tạo poll | Đọc feed, vote poll, gửi góp ý ẩn danh |
| Gamification | Xem leaderboard (không có rank cá nhân) | XP/Level/Streak/badge/nhiệm vụ tuần + rank + khoảng cách Top 10 |
| Tìm kiếm | Trie thành viên (đầy đủ trường) + Trie tài liệu vùng FULL | Trie tài liệu vùng PUBLIC; không gọi `/members/search/` từ UI member |

## MÀN HÌNH THEO SPEC CHƯA CÓ (4)

| Spec §4 | Màn hình | Trạng thái | Điểm thay thế hiện có |
|---------|----------|------------|------------------------|
| MH 8 | `/admin/board` — Cơ cấu BCN + Org Chart | ❌ Chưa có trang | Modal BCN trong `frontend/admin/members.html` (`/members/board/`) — thiếu Org Chart |
| MH 9 | `/admin/reports` — Báo cáo PDF + biểu đồ chuyên cần | ❌ Chưa có | Chỉ có số liệu rời (`/funds/stats/`, `profile360`) |
| MH 10 | `/admin/settings` — Niên khóa, backup DB, phân quyền | ❌ Chưa có | Qua biến môi trường + Django admin `/admin/` |
| MH 17 | `/member/calendar` — Lịch sinh hoạt + iCal | ❌ Chưa có | Danh sách sự kiện trong home/events |

## DEVIATIONS THỰC TẾ (spec vs code — tra cứu nhanh)

1. **URL frontend là file tĩnh:** spec viết `/admin/dashboard`, thực tế `/frontend/admin/dashboard.html` do `core/urls.py` `re_path(r"^frontend/...")` phục vụ. Không có URL rewrite kiểu `/admin/dashboard`.
2. **Bulk override là `PUT`, không phải `POST`:** spec §5 ghi `POST .../bulk-override/`, code là `PUT /api/v1/attendance/sessions/{id}/bulk-override/` (`apps/attendance/urls.py`, `frontend/admin/attendance.html` gọi `ApiClient.put`).
3. **`/members/search/` trả `{items:[...]}`** (không phải mảng trần) — `frontend/admin/members.html` đọc `raw.items`.
4. **Topological order:** frontend admin **không gọi** `GET /events/{id}/tasks/topological-order/` riêng — dùng `is_valid_dag` + `topological_order` trả kèm trong `GET /events/{id}/tasks/`. Endpoint topological-order vẫn tồn tại độc lập.
5. **Tạo giao dịch quỹ chưa gửi `Idempotency-Key`:** backend nhận header `Idempotency-Key` (hoặc trường body) nhưng `frontend/admin/funds.html` chưa gửi → chống ghi trùng chỉ phát huy khi client khác dùng.
6. **Đăng bài:** spec MH2 có "Upload ảnh + checkbox Ghim trong modal" — modal thực tế chỉ có `tieu_de` + `noi_dung`; ghim là nút riêng trên bài đã đăng; model Post không có trường ảnh.
7. **Feed chưa có thả cảm xúc ❤️/🔥** (spec MH11) — model/serializer Post không có reactions.
8. **Đếm ngược "giờ G"** trên thẻ sự kiện (spec MH13) chưa có; chỉ hiển thị thời gian sự kiện.
9. **Nhiệm vụ tuần** nằm ở home (MH11) chứ không phải tab trong leaderboard (MH14) như spec.
10. **Thẻ thành viên VIP** (lật xoay/lưu ảnh) của MH15 chưa có — profile hiện là form thông tin + XP + badge.
11. **Upload tài liệu ở member:** spec MH16 có nút `[Chia sẻ tài liệu mới]` (+100 XP) — API cho phép nhưng UI member chưa build; upload hiện chỉ ở trang BCN.
12. **Media preview chỉ khi DEBUG:** `core/urls.py` chỉ mount `/media/` khi `settings.DEBUG`; production tải file luôn qua `/documents/{id}/download/` (có auth + phạm vi).
13. **Khóa sổ — số dư âm:** spec mô tả cảnh báo vàng khi số dư < 200.000đ (có, `low_balance` trong `/funds/stats/`); việc **chi vượt số dư** bị chặn cứng bởi `FundInvariantsEngine` (400), không phải chỉ cảnh báo.
14. **Login "Ghi nhớ đăng nhập"** (spec MH1) chưa có; token luôn lưu localStorage (refresh 7 ngày).
15. **Swagger guard:** `/api/docs/` công khai ở dev, nhưng ở production trả **404** (không phải 403) cho non-ADMIN — chủ ý để không hé lộ endpoint (`core/urls.py` `_AdminOnlySchemaMixin`).

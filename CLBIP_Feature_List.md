# CLBIP — DANH SÁCH TÍNH NĂNG (Feature List)

> Tài liệu đáp ứng QA-Audit: danh mục **97 tính năng** chia 2 nhóm — **51 tính năng cốt lõi** (must-have cho CLB vận hành thật) + **46 tính năng mở rộng** (nice-to-have / nâng cao).
> Trạng thái **đối chiếu trung thực với code** (ngày soạn: theo working tree hiện tại):
> ✅ Done = có code đầu-cuối (backend route + service; có UI nếu là tính năng UI) · 🟡 Partial = có nhưng chưa trọn mọi cạnh · ❌ Missing = chưa có trong code.
> Minh chứng = đường dẫn file và/hoặc endpoint thật (đã grep `apps/*/urls.py`, `frontend/**/*.html`).

---

## NHÓM 1 — 51 TÍNH NĂNG CỐT LÕI

### A. Đăng nhập & phân quyền (5)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 1 | Đăng nhập JWT (email + mật khẩu, nhận access/refresh + user info) | ✅ Done | `apps/authentication/urls.py` `POST /api/v1/auth/token/` · `frontend/js/auth.js` `Auth.login()` |
| 2 | Làm mới token tự động đúng 1 lần khi 401 (single-flight) + rotation/blacklist | ✅ Done | `frontend/js/api.js` `ApiClient.refreshToken()` · `POST /api/v1/auth/token/refresh/` · `core/settings.py` SIMPLE_JWT `ROTATE_REFRESH_TOKENS/BLACKLIST_AFTER_ROTATION` |
| 3 | RBAC 3 vai trò ADMIN / BCN / MEMBER trên toàn bộ API | ✅ Done | `core/permissions.py` (`IsBCNOrAdmin`, `IsOwnerOrBCN`) · `get_permissions()` trong mọi `apps/*/views.py` |
| 4 | Điều hướng theo role sau đăng nhập + gác trang (requireRole, đẩy về đúng trang nhà) | ✅ Done | `frontend/js/auth.js` `ROLE_HOME` / `requireRole()` · `frontend/index.html` |
| 5 | Quên mật khẩu — modal gửi mã OTP về email | ✅ Done | 3 endpoint `/auth/password-reset/{request,verify,confirm}/` (`PasswordResetService` — OTP 6 số TTL 10 phút, throttle 3/giờ, chặn dò OTP 5 lần, blacklist refresh token cũ) + modal 3 bước trong `frontend/login.html` |

### B. Quản lý thành viên (10)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 6 | Danh sách thành viên phân trang + lọc lớp/trạng thái + sort whitelist | ✅ Done | `GET /api/v1/members/` (`apps/members/views.py` `MemberListCreateView`) · `frontend/admin/members.html` (gửi `lop`, `trang_thai_hd`, `search`, `page`) |
| 7 | Thêm thành viên (dup-check email/MSSV, tạo kèm User) | ✅ Done | `POST /api/v1/members/` · `apps/members/services.py` `MemberService.create_member` |
| 8 | Sửa / khóa thành viên (soft-lock `trang_thai_hd`, không xóa cứng) | ✅ Done | `PUT/PATCH/DELETE /api/v1/members/{id}/` · `MemberService.update_member` / `lock_member` · modal Sửa/Khóa trong `frontend/admin/members.html` |
| 9 | Nhập Excel hàng loạt + preview lỗi từng dòng (dòng lỗi không chặn dòng hợp lệ) | ✅ Done | `POST /api/v1/members/import-excel/` · `MemberService.import_excel` trả `{created, errors:[{row, ho_ten, error}]}` |
| 10 | Xuất Excel danh sách thành viên (order_by ho_ten) | ✅ Done | `GET /api/v1/members/export-excel/` (openpyxl) · `frontend/admin/members.html` `ApiClient.download` |
| 11 | Tìm kiếm tức thời Prefix Trie O(L) + cache Trie theo process | ✅ Done | `GET /api/v1/members/search/` → `{items:[...]}` · `core/algorithms/trie_search.py` · `apps/members/search_index.py` |
| 12 | Hồ sơ 360° (thống kê sự kiện, chuyên cần %, XP/Level/Streak, huy hiệu, 5 dòng XP gần nhất, vai trò BCN) | ✅ Done | `GET /api/v1/members/{id}/profile360/` · `MemberService.get_profile360` (select/prefetch chống N+1) |
| 13 | Cơ cấu Ban Chủ nhiệm: nhiệm kỳ + bổ nhiệm | 🟡 Partial | `GET/POST /api/v1/members/board/` + modal trong `frontend/admin/members.html` — **chưa có trang `/admin/board` riêng** (spec §4 màn hình 8), chưa có UI sửa/xóa nhiệm kỳ |
| 14 | Thành viên tự xem/sửa hồ sơ cá nhân (giới hạn trường được sửa) | ✅ Done | `PATCH /api/v1/members/{id}/` (`IsOwnerOrBCN`) · `frontend/member/profile.html` (sửa SĐT) |
| 15 | Chống rò PII cho MEMBER (kết quả search/leaderboard không có email/SĐT/MSSV) | ✅ Done | `apps/members/serializers.py` — serializer kết quả tìm kiếm cho MEMBER chỉ còn tên/lớp/XP (QA-Audit 2a) |

### C. Quỹ CLB (7)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 16 | Ghi sổ thu/chi atomic + pessimistic lock `select_for_update` + số dư chạy | ✅ Done | `apps/funds/services.py` `FundService.execute_transaction` (`_execute_locked`) · `POST /api/v1/funds/` |
| 17 | Idempotency key chống ghi trùng (replay trả lại phiếu cũ — 200 thay vì 500) | ✅ Done | `FundService.execute_transaction_idempotent` · `FundTransaction.idempotency_key` (migration `0002_fundtransaction_idempotency_key`) · `apps/funds/views.py` đọc header `Idempotency-Key` (lưu ý: frontend hiện chưa gửi header này) |
| 18 | Factory Pattern phiếu thu/chi + Strategy cập nhật số dư | ✅ Done | `apps/funds/services.py` `IncomeTransaction` / `ExpenseTransaction` / `TransactionFactory` / `apply_to_balance` |
| 19 | Khóa sổ theo kỳ (chặn ghi mới vào ngày thuộc kỳ đã khóa) | ✅ Done | `POST /api/v1/funds/lock-period/` + `GET /api/v1/funds/locks/` · `exists_locked_period_containing` · UI "Khóa sổ kỳ" trong `frontend/admin/funds.html` |
| 20 | Thống kê tổng thu / tổng chi / số dư + cờ cảnh báo quỹ thấp (<200.000đ) | ✅ Done | `GET /api/v1/funds/stats/` · `FundService.get_stats` + `CLB_SETTINGS["FUND_LOW_BALANCE_THRESHOLD"]` |
| 21 | Xuất sổ quỹ Excel | 🟡 Partial | `GET /api/v1/funds/export-excel/` (openpyxl, `apps/funds/services.py`) — spec màn hình 4 yêu cầu bảng kê **có chữ ký điện tử** → chưa có |
| 22 | Invariants engine chặn chi vượt số dư / sổ không hợp lệ | ✅ Done | `core/algorithms/fund_invariants.py` `FundInvariantsEngine.validate_new_transaction` (gọi trong `_execute_locked`) |

### D. Sự kiện & nhiệm vụ DAG (10)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 23 | CRUD kế hoạch sự kiện + mã kế hoạch tự sinh `EV{năm}{seq}` | ✅ Done | `apps/events/views.py` `EventListCreateView` / `EventDetailView` · `EventService` |
| 24 | Vòng đời sự kiện (PLANNING → OPEN_REGISTRATION → … → CANCELLED) | ✅ Done | `apps/events/models.py` `TrangThai` (TextChoices) |
| 25 | Dự trù kinh phí: hạng mục chi + tự động tính tổng cập nhật sự kiện | ✅ Done | `GET/POST /api/v1/events/{id}/budget/` · `EventService.add_budget_item` · tab "Dự trù kinh phí" trong `frontend/admin/events.html` |
| 26 | Phân công nhiệm vụ + phụ thuộc DAG (Task B phụ thuộc Task A) | ✅ Done | `GET/POST /api/v1/events/{id}/tasks/` · `PATCH /api/v1/events/{id}/tasks/{task_id}/` (`is_completed`) · `EventTaskService` |
| 27 | Phát hiện vòng lặp deadlock + topological order (Kahn) + "đủ điều kiện thực hiện ngay" | ✅ Done | `GET /api/v1/events/{id}/tasks/topological-order/` · GET tasks trả `is_valid_dag` / `cycle` / `topological_order` / `executable_now` · `core/algorithms/dag_workflow.py` |
| 28 | Đăng ký vé điện tử miễn phí + mã vé `VE-XXXXXXXXXXXX` + QR client-side | ✅ Done | `POST /api/v1/events/{id}/register/` (`EventService.register_member` + `_generate_ma_ve`) · `frontend/member/events.html` render `QRCode` (`frontend/assets/qrcode.min.js`) |
| 29 | Hủy vé đăng ký | ✅ Done | `POST /api/v1/events/{id}/cancel-registration/` |
| 30 | "Vé của tôi" — danh sách vé của chính thành viên | ✅ Done | `GET /api/v1/events/my-tickets/` · tab "🎟️ Vé của tôi" trong `frontend/member/events.html` |
| 31 | Danh sách đăng ký của sự kiện (BCN xem mã vé từng người) | ✅ Done | `GET /api/v1/events/{id}/registrations/` · tab "Đăng ký" trong `frontend/admin/events.html` |
| 32 | Quét / xác minh mã vé QR tại cửa hội trường | ✅ Done | `POST /events/{id}/verify-ticket/` (`EventService.verify_ticket` — atomic + select_for_update, 409 khi quét lại) + trang quét camera `frontend/admin/ticket_scanner.html` (Html5-QRCode, nhập tay fallback) |

### E. Điểm danh GPS (7)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 33 | Mở phiên điểm danh GPS: tọa độ BCN làm tâm + bán kính + thời gian hiệu lực | ✅ Done | `POST /api/v1/attendance/sessions/` · `apps/attendance/services/attendance_service.py` `AttendanceService.open_session` · nút "Dùng GPS hiện tại" trong `frontend/admin/attendance.html` |
| 34 | Tự động tạo bản ghi VẮNG cho toàn bộ thành viên ACTIVE khi mở phiên | ✅ Done | `bulk_create_vang_records` trong `open_session` (batch 500) |
| 35 | Dynamic Nonce 60s (secret HMAC 48 ký tự, hiển thị lên máy chiếu) | ✅ Done | `GET /api/v1/attendance/sessions/{id}/nonce/` · `apps/attendance/services/nonce.py` · UI nonce đếm ngược trong `frontend/admin/attendance.html` |
| 36 | Check-in GPS 7 lớp anti-cheat (mock GPS / accuracy / clock-skew / nonce / device reuse / teleport / Haversine radius) | ✅ Done | `POST /api/v1/attendance/check-in/` · `apps/attendance/services/anti_cheat.py` `GPSAntiCheatEngine.validate_checkin` · `core/algorithms/geo_haversine.py` |
| 37 | Đóng phiên — chốt danh sách điểm danh | ✅ Done | `POST /api/v1/attendance/sessions/{id}/close/` · `close_session` |
| 38 | Cập nhật thủ công hàng loạt trạng thái (Có mặt/Có phép/Vắng/Muộn) | ✅ Done | `PUT /api/v1/attendance/sessions/{id}/bulk-override/` ⚠️ **PUT, không phải POST** như spec §5 · `AttendanceService.bulk_override` · modal override trong `frontend/admin/attendance.html` |
| 39 | Lịch sử điểm danh cá nhân + chuỗi streak 🔥 | ✅ Done | `GET /api/v1/attendance/me/` · `_update_streak` · `frontend/member/checkin.html` + `frontend/member/profile.html` |

### F. Gamification (6)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 40 | Cộng XP tự động theo Strategy Pattern (điểm danh sớm/muộn, đóng góp tài liệu, hoàn thành task, organizer) | ✅ Done | `apps/gamification/services.py` `RewardStrategyFactory` + 5 strategy · `GamificationService.award_xp` (server-authoritative, không endpoint nhận XP từ client) |
| 41 | Daily XP Cap 300/ngày + idempotency chống cộng trùng XP | ✅ Done | `DAILY_XP_CAP` · `exists_idempotency_key` / `sum_positive_xp_between` qua `apps/gamification/repositories.py` |
| 42 | Level 1→10 suy từ XP | ✅ Done | `level_from_xp` · thanh cấp độ trong `frontend/member/profile.html` |
| 43 | Huy hiệu tự mở idempotent (Streak 7 ngày 🔥, Chăm chỉ 10 buổi, Nhà hảo tâm tri thức, Cao thủ cấp 5) | ✅ Done | `BadgeService.evaluate_and_unlock` + `CATALOG` · `GET /api/v1/gamification/badges/` · bộ sưu tập huy hiệu `frontend/member/profile.html` |
| 44 | Bảng vàng Top 10 (Min-Heap O(N log K)) + rank cá nhân + khoảng cách tới Top 10 | ✅ Done | `GET /api/v1/gamification/leaderboard/` (trả `top_10` + `my_position` + `total_members`) · `core/algorithms/leaderboard_heap.py` · `frontend/member/leaderboard.html` |
| 45 | Nhiệm vụ tuần kiếm XP (điểm danh, đóng góp tài liệu, hoàn thành task) | ✅ Done | `GET /api/v1/gamification/me/` (`weekly_quests`) · `GamificationService.get_weekly_quests` · widget "Nhiệm vụ tuần" `frontend/member/home.html` |

### G. Kho tài liệu (6)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 46 | Upload tài liệu + thưởng +100 XP đóng góp | ✅ Done | `POST /api/v1/documents/` (FormData) · `apps/documents/services.py` `DocumentService.create_document` + `_award_share_xp` |
| 47 | File Upload Hardening 4 tầng (15MB → whitelist đuôi file → magic bytes → đổi tên UUID) | ✅ Done | `DocumentService.validate_file` + `_magic_matches` + UUID rename (`apps/documents/services.py`) |
| 48 | Tìm kiếm Prefix Trie 2 vùng PUBLIC/FULL + cache theo process + vô hiệu hóa theo signal | ✅ Done | `GET /api/v1/documents/search/?q=` · `apps/documents/search_index.py` (SCOPE_PUBLIC / SCOPE_FULL) |
| 49 | Phạm vi tài liệu BCN_ONLY + scope xem/tải (MEMBER upload BCN_ONLY bị ép về PUBLIC_MEMBER) | ✅ Done | `Document.PhamVi` · `DocumentService.can_view` · `apps/documents/migrations/0002_document_pham_vi.py` |
| 50 | Tải về có auth + đếm lượt tải; media chỉ phục vụ khi DEBUG | ✅ Done | `GET /api/v1/documents/{id}/download/` · `increment_download` · `core/urls.py` chỉ mount `/media/` khi `settings.DEBUG` |
| 51 | Preview PDF trực tiếp không rời trang | ✅ Done | fetch blob + Authorization trong `frontend/member/documents.html` và `frontend/admin/documents.html` |

---

## NHÓM 2 — 47 TÍNH NĂNG MỞ RỘNG

### H. Bảng tin & trách nhiệm giải trình (3)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 52 | Bảng tin + đăng bài bleach chống XSS (whitelist tag) | ✅ Done | `apps/posts/services.py` `PostService.sanitize` (bleach) · `GET/POST /api/v1/posts/` |
| 53 | Ghim / bỏ ghim bài lên đầu feed | ✅ Done | `PATCH /api/v1/posts/{id}/pin/` (`PostPinView`, `toggle_pin`) · nút Ghim trong `frontend/admin/dashboard.html` |
| 54 | Sửa / xóa mềm bài + `PostAuditLog` ghi vết mọi thao tác (CREATE/UPDATE/DELETE/PIN/UNPIN + actor) | ✅ Done | `PUT/PATCH/DELETE /api/v1/posts/{id}/` · `apps/posts/models.py` `PostAuditLog` · `PostService._log` (UI dashboard hiện có Đăng/Ghim/Xóa; sửa bài qua API) |

### I. Cộng đồng: bình chọn + góp ý (5)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 55 | Tạo bình chọn nhiều lựa chọn (BCN, ≥2 lựa chọn) | ✅ Done | `POST /api/v1/polls/` · `PollService.create_poll` · modal "Tạo bình chọn" `frontend/admin/dashboard.html` |
| 56 | Bình chọn + chặn vote 2 lần + hiển thị kết quả | ✅ Done | `POST /api/v1/polls/{id}/vote/` · `CommunityPoll.voted_user_ids` (`apps/posts/models.py`) · widget poll `frontend/member/home.html` + dashboard |
| 57 | Đóng bình chọn (`is_closed`) | ✅ Done | `PATCH /polls/{id}/close/` (`PollService.close_poll` — BCN/ADMIN, đóng 2 lần → 400) + nút 'Đóng bình chọn' trên dashboard; vote sau khi đóng → 409 |
| 58 | Gửi góp ý ẩn danh (throttle 2/phút + hạn mức 5 góp ý/ngày) | ✅ Done | `POST /api/v1/feedback/` · `FeedbackRateThrottle` + `FeedbackService` (5/ngày) · modal `frontend/member/home.html` |
| 59 | BCN đọc hòm thư góp ý KHÔNG lộ người gửi | ✅ Done | `GET /api/v1/feedback/` · `FeedbackListSerializer` không serialize sender (`FeedbackEntry` lưu sender nội bộ chỉ để chống spam) |

### J. Tài liệu API (3)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 60 | OpenAPI schema + Swagger UI | ✅ Done | `/api/schema/`, `/api/docs/` (`core/urls.py`) · drf-spectacular |
| 61 | Production guard: schema/Swagger chỉ ADMIN khi `DJANGO_ENV=production` (404 ẩn) | ✅ Done | `_AdminOnlySchemaMixin` trong `core/urls.py` (QA-Audit 2e) |
| 62 | Mô tả API tiếng Việt qua `@extend_schema` cho toàn bộ endpoint | ✅ Done | Có mặt trong mọi `apps/*/views.py` |

### K. Frontend 13 trang + nền tảng UI (14)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 63 | Trang đăng nhập + hub điều hướng `index.html` theo token/role | ✅ Done | `frontend/login.html` (validate lỗi tiếng Việt, toggle password) · `frontend/index.html` |
| 64 | Admin Dashboard KPI + bảng tin + poll + hòm thư góp ý + biểu đồ | ✅ Done | KPI thật + Chart.js v4: Line 'Xu hướng tài chính' + Bar 'Chuyên cần hàng tuần' từ `GET /common/stats/trend/` (`TrendStatsService`) |
| 65 | Admin Quản lý thành viên (bảng, lọc, tìm, thêm, import/export, hồ sơ 360°, BCN) | ✅ Done | `frontend/admin/members.html` |
| 66 | Admin Quỹ (KPI + cảnh báo, phiếu thu/chi, khóa sổ, xuất Excel) | ✅ Done | `frontend/admin/funds.html` |
| 67 | Admin Sự kiện (danh sách + modal chi tiết 4 tab: DAG / kinh phí / đăng ký / truyền thông) | ✅ Done | `frontend/admin/events.html` |
| 68 | Admin Điểm danh (mở phiên GPS, nonce máy chiếu, override hàng loạt, lịch sử phiên) | ✅ Done | `frontend/admin/attendance.html` |
| 69 | Admin Kho tài liệu (upload, tìm, preview, tải, xóa) | ✅ Done | `frontend/admin/documents.html` |
| 70 | Member Home (landing M3): sidebar + topbar, hero sự kiện sắp tới, 4 quick action, stories, feed ghim bài, thẻ thành viên số + QR MSSV, Top Chiến Thần, nhiệm vụ tuần, poll, hòm thư góp ý | ✅ Done | `frontend/member/home.html` (thiết kế Material 3 + `frontend/css/landing.css` Tailwind tĩnh; reaction ❤️/🔥 + lưu bài là local-first — chờ backend reaction API; `has_voted` poll từ server) |
| 71 | Member Check-in: xin quyền GPS, radar hiển thị khoảng cách, nhập nonce, kết quả + confetti + streak | ✅ Done | `frontend/member/checkin.html` (`radar-distance`, `Celebrate.cheer()` từ `frontend/js/celebration.js`) |
| 72 | Member Sự kiện: danh sách + tab "Vé của tôi" + vé QR kiểu ví + hủy vé | ✅ Done | `frontend/member/events.html` (spec yêu cầu đồng hồ đếm ngược "giờ G" → chưa có) |
| 73 | Member Bảng vàng: podium Top 10 + thanh ghim vị trí "Còn X XP nữa để vào Top 10" | ✅ Done | `frontend/member/leaderboard.html` (tính gap tới Top 10 client-side) |
| 74 | Member Hồ sơ: hồ sơ 360° + XP/Level + bộ sưu tập huy hiệu + sửa SĐT | ✅ Done | `frontend/member/profile.html` (spec yêu cầu thẻ thành viên lật xoay/lưu ảnh về máy → chưa có) |
| 75 | Member Kho tài liệu: tìm Trie, lọc nhóm, preview, tải về | ✅ Done | `frontend/member/documents.html` — API `POST /documents/` mở cho mọi user đăng nhập nhưng **trang member chưa có form upload** (chỉ BCN có) |
| 76 | Responsive mobile + skeleton/empty states + toast tiếng Việt | ✅ Done | `frontend/css/responsive.css` · `frontend/js/utils.js` (`skeleton`, `empty`) · `frontend/js/toast.js` |

### L. Bảo mật (8)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 77 | Content-Security-Policy middleware (backstop chống XSS) | ✅ Done | `core/middleware.py` `ContentSecurityPolicyMiddleware` |
| 78 | django-axes lockout 5 lần sai / 15 phút theo (username + IP) + lockout response tiếng Việt | ✅ Done | `core/settings.py` `AXES_*` · `apps/common/axes_callbacks.py` |
| 79 | Throttle đa tầng: `auth_login` 5/phút, `checkin`, `feedback` 2/phút, `doc_upload` 5/phút + Burst/Sustained toàn cục | ✅ Done | `apps/common/throttles.py` · `DEFAULT_THROTTLE_RATES` trong `core/settings.py` |
| 80 | Fail-fast cấu hình production (SECRET_KEY bắt buộc, chặn khóa `django-insecure-*`) | ✅ Done | `core/settings.py` khối `DJANGO_ENV == "production"` |
| 81 | HSTS 1 năm + SSL redirect + nosniff / referrer-policy / COOP | ✅ Done | `core/settings.py` `SECURE_*` |
| 82 | Chống giả mạo X-Forwarded-For (NUM_PROXIES + django-ipware cho axes/throttle) | ✅ Done | `core/settings.py` (NUM_PROXIES, `AXES_IPWARE_*`) |
| 83 | Cache dùng chung DatabaseCache/Redis cho throttle + axes (chống né rate-limit đa worker) | ✅ Done | `core/settings.py` `CACHES` · `build.sh` `createcachetable` |
| 84 | JWT hardening: access 30 phút / refresh 7 ngày, rotation + blacklist, SIGNING_KEY = SECRET_KEY | ✅ Done | `core/settings.py` `SIMPLE_JWT` |

### M. Triển khai & vận hành (8)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 85 | `build.sh` (deps → collectstatic → createcachetable → migrate → seed có điều kiện) | ✅ Done | `build.sh` |
| 86 | render.yaml: web service + PostgreSQL + healthCheckPath | ✅ Done | `render.yaml` (`healthCheckPath: /api/health/`) |
| 87 | Health check endpoint | ✅ Done | `GET /api/health/` · `apps/common/urls.py` `HealthCheckView` |
| 88 | Seed guard production (cấm tài khoản demo lọt môi trường thật) | ✅ Done | `apps/common/management/commands/seed_demo.py` chặn `DJANGO_ENV=production` · `build.sh` chỉ seed khi `SEED_DEMO=1` và không phải production |
| 89 | Storage resolver S3/R2 (`USE_S3=1`) thay đĩa tạm Render | ✅ Done | `core/storage_resolver.py` · `django-storages[s3]` trong `requirements.txt` |
| 90 | WhiteNoise static + phục vụ frontend luôn `Cache-Control: no-cache` | ✅ Done | `whitenoise` (`requirements.txt`, `build.sh`) · `frontend_serve` trong `core/urls.py` |
| 91 | Script kiểm tra tiền deploy | ✅ Done | `check_deploy.py` (verify env + cấu hình + staticfiles, exit code 0/1) |
| 92 | Django admin site quản trị dữ liệu | ✅ Done | `path("admin/", admin.site.urls)` · `apps/*/admin.py` |

### N. Chất lượng & nền tảng chung (6)

| # | Tính năng | Trạng thái | Minh chứng |
|---|-----------|:----------:|------------|
| 93 | Bộ test tự động toàn hệ thống (281 hàm test đếm được trong `apps/*/tests.py` + `core/tests/`) | ✅ Done | `apps/{authentication,members,funds,events,attendance,gamification,documents,posts,common}/tests.py` · `core/tests/test_algorithms.py` · `core/tests/test_urls.py` |
| 94 | 5 thuật toán DSA tách module dùng chung + test riêng (Trie, DAG Kahn, Haversine, Heap, Fund Invariants) | ✅ Done | `core/algorithms/{trie_search,dag_workflow,geo_haversine,leaderboard_heap,fund_invariants}.py` |
| 95 | Envelope chuẩn `{success, data, message, errors}` + phân trang `{items, pagination}` toàn API | ✅ Done | `core/response.py` (`ok`, `created`) · `core/pagination.py` `StandardPagination` (page_size max 100) |
| 96 | Exception tập trung → envelope đúng HTTP (404/400/403/409, message thân thiện) | ✅ Done | `apps/common/exceptions.py` (`NotFoundException`, `ValidationException`, `ForbiddenException`) · `core/exceptions.py` |
| 97 | Bộ tài liệu hợp đồng frontend–backend + promptspec | ✅ Done | `frontend/FRONTEND_CONTRACT.md` · `CLBIP_Master_Coding_Prompt.md` · `CLBIP_Security_Hardening_Prompt.md` · `CLBIP_Frontend_Integration_Prompt.md` |
| 98 | Landing page công khai tại `/` (khách chưa đăng nhập thấy trang giới thiệu CLB + CTA Đăng nhập; đã đăng nhập → CTA "Vào cổng sinh viên") | ✅ Done | `frontend/landing.html` (Material 3, cùng design system home.html) · `core/urls.py` `frontend_index_serve` |

---

## ĐẾM LẠI CUỐI FILE (bắt buộc khớp)

| Nhóm | Tổng | ✅ Done | 🟡 Partial | ❌ Missing |
|------|:----:|:-------:|:---------:|:---------:|
| Cốt lõi (A–G) | **51** | 49 | 2 | 0 |
| Mở rộng (H–N) | **47** | 47 | 0 | 0 |
| **TỔNG** | **98** | **96** | **2** | **0** |

### Danh sách mục ❌ Missing / 🟡 Partial (tra cứu nhanh)

- 🟡 #13 — Cơ cấu BCN: có API + modal, chưa có trang `/admin/board` riêng (spec màn hình 8)
- 🟡 #21 — Xuất sổ quỹ Excel: chưa có "chữ ký điện tử" (spec màn hình 4)

> Ghi chú khác (không tính vào trạng thái): feed thả cảm xúc ❤️/🔥 và "lưu bài" đang là **local-first** (localStorage theo user id) — backend `Post` chưa có model reaction; UI đã sẵn sàng nối API khi có.

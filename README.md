# 🎯 CLB IP ĐHSP Huế 2.0 — Backend API (Django REST Framework)

Hệ thống quản lý toàn diện CLB Tin học (IP) ĐHSP Huế: thành viên, quỹ, sự kiện, điểm danh GPS chống gian lận, gamification XP/Leaderboard, kho tài liệu, bảng tin — xây dựng theo **Clean Layered Architecture + DSA/OOP** với đầy đủ lớp bảo mật Defense-in-Depth.

> 📖 Tài liệu đặc tả: `CLBIP_Master_Coding_Prompt.md` | Bảo mật: `CLBIP_Security_Hardening_Prompt.md` | Kiến trúc DSA/OOP: `.agents/skills/dsa-oop-backend-architecture/SKILL.md`

---

## 🚀 Deploy lên Render (5 phút)

### Cách 1 — Blueprint (khuyên dùng, tự động 100%)
1. Vào [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**
2. Chọn repo `huyhandsome6996/clbIP` → Render đọc `render.yaml` tự động
3. Bấm **Apply** — Render sẽ tự:
   - Tạo **PostgreSQL** `clbip-postgres` (free) và inject `DATABASE_URL`
   - Chạy `build.sh`: install → collectstatic → migrate → seed data demo
   - Start Gunicorn với health check tại `/api/health/`
4. URL sẽ có dạng `https://clbip-backend-xxxx.onrender.com`

### Cách 2 — Web Service thủ công
**New + → Web Service** → chọn repo → Runtime: `Python 3` → Build: `./build.sh` → Start: `gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 30` → thêm env vars: `DJANGO_ENV=production`, `DEBUG=False`, `ALLOWED_HOSTS=.onrender.com` → tạo **PostgreSQL** instance → link biến `DATABASE_URL`.

### Kiểm tra trước deploy (tuỳ chọn)
```bash
DJANGO_ENV=production DEBUG=False SECRET_KEY=xxx python check_deploy.py
# → 33 PASS = Sẵn sàng deploy
```

## 🔒 Triển khai an toàn (bắt buộc đọc)

Hệ thống **chặn cứng** việc tạo tài khoản demo trên môi trường thật:

| Hàng chặn | Hành vi |
|---|---|
| `build.sh` | Chỉ chạy `seed_demo` khi **đủ 2 điều kiện**: `SEED_DEMO=1` **và** `DJANGO_ENV != production` |
| `Procfile` (`release:`) | Chỉ chạy `migrate` — không seed |
| `seed_demo` | Tự raise `CommandError` khi `DJANGO_ENV=production` (phòng thủ tầng cuối nếu ai đó gọi tay) |

**Mật khẩu demo** không còn hardcode trong mã nguồn: lấy từ tham số `--password`
hoặc biến môi trường `DEMO_PASSWORD`; nếu thiếu, lệnh sẽ sinh mật khẩu ngẫu nhiên
và chỉ in một lần ra console.

**Việc con người PHẢI làm sau khi nhận bàn giao production** (không thể tự động hóa):
1. **Đổi hoặc xóa ngay** các tài khoản demo đã tồn tại trong DB production từ các
   lần deploy cũ (admin@clbip.vn, bcn@clbip.vn, 22a401101@... — mật khẩu cũ
   `CLBIP@2026` đã từng công khai trong repo). Trên Render: `render shell` →
   `python manage.py shell` → đổi `password`/`is_active=False`, hoặc xóa hẳn.
2. Đặt biến môi trường trên Render: `DJANGO_ENV=production`, `DEBUG=False`,
   `SECRET_KEY` (generateValue), `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
   `NUM_PROXIES=1`, `SEED_DEMO` (để trống/không đặt).
3. Kiểm tra lại domain CORS trùng với domain frontend thật đang dùng.

---

## 🔑 Tài khoản demo (tự sinh bởi `seed_demo`)

Mật khẩu do bạn chọn qua `--password` / biến môi trường `DEMO_PASSWORD`
(không còn mật khẩu chung hardcode trong mã nguồn):

| Vai trò | Email |
|---|---|
| ADMIN | `admin@clbip.vn` |
| BCN (Chủ nhiệm) | `bcn@clbip.vn` |
| MEMBER | `22a401101@student.hueuni.edu.vn` |

> Demo gồm: 19 thành viên, sổ quỹ 2.750.000₫, 2 sự kiện (1 mở đăng ký), phiên điểm danh GPS đang mở, bảng tin, poll, 5 huy hiệu.

---

## 📚 API Documentation — Swagger UI

- **Swagger UI:** `GET /api/docs/` (OpenAPI 3.0, sinh tự động bởi drf-spectacular)
- **Raw schema:** `GET /api/schema/`
- **Health check:** `GET /api/health/`

Mọi response chuẩn hóa envelope:
```json
{ "success": true, "data": { ... }, "message": "Thành công", "errors": null }
```
Đăng nhập: `POST /api/v1/auth/token/` với `{"email", "password"}` → JWT access (30 phút) + refresh (7 ngày, rotation + blacklist).

## 🗺️ Endpoint chính (prefix `/api/v1/`)

| Phân hệ | Endpoints |
|---|---|
| **Auth** | `POST auth/token/` · `POST auth/token/refresh/` · `GET auth/me/` |
| **Members** | `GET/POST members/` · `GET/PUT/DELETE members/{id}/` · `GET members/{id}/profile360/` · `GET members/search/?q=` (Trie) · `POST members/import-excel/` · `GET members/export-excel/` · `GET/POST members/board/` |
| **Funds** | `GET/POST funds/` · `GET funds/stats/` · `POST funds/lock-period/` · `GET funds/locks/` · `GET funds/export-excel/` |
| **Events** | `GET/POST events/` · `GET/PUT events/{id}/` · `GET/POST events/{id}/tasks/` (DAG) · `GET events/{id}/tasks/topological-order/` · `POST events/{id}/register/` (vé QR) · `POST events/{id}/cancel-registration/` · `GET events/{id}/registrations/` · `GET/POST events/{id}/budget/` · `GET/POST events/{id}/communications/` |
| **Attendance** | `GET/POST attendance/sessions/` · `POST attendance/sessions/{id}/close/` · `GET attendance/sessions/{id}/nonce/` (mã xoay 60s) · `PUT attendance/sessions/{id}/bulk-override/` · `POST attendance/check-in/` (GPS + Anti-Cheat) · `GET attendance/me/` |
| **Gamification** | `GET gamification/leaderboard/` (Min-Heap Top 10 + rank cá nhân) · `GET gamification/badges/` · `GET gamification/me/` |
| **Documents** | `GET/POST documents/` · `GET documents/search/?q=` (Trie) · `GET documents/{id}/download/` · `GET/DELETE documents/{id}/` |
| **Posts** | `GET/POST posts/` · `GET/PUT/DELETE posts/{id}/` · `PATCH posts/{id}/pin/` · `GET/POST feedback/` (ẩn danh) · `GET/POST polls/` · `POST polls/{id}/vote/` |

## 🧠 Cấu trúc dự án (Clean Layered Architecture)

```
core/
├── settings.py          # Bảo mật Defense-in-Depth + CLB_SETTINGS
├── response.py          # Envelope {success, data, message, errors}
├── exceptions.py        # Custom exception handler
├── permissions.py       # IsOwnerOrBCN, IsBCNOrAdmin... (chống IDOR)
├── pagination.py        # Phân trang bắt buộc (max 100)
├── viewsets.py          # EnvelopeModelViewSet
├── algorithms/          # ⭐ 5 DSA modules
│   ├── geo_haversine.py     # DSA 1: Haversine + Bounding Box pruning
│   ├── leaderboard_heap.py  # DSA 2: Min-Heap Top-K O(N log K)
│   ├── trie_search.py       # DSA 3: Trie autocomplete O(L)
│   ├── dag_workflow.py      # DSA 4: Kahn Topological Sort + cycle detection
│   └── fund_invariants.py   # DSA 5: Bất biến tài chính
└── tests/               # 35 unit tests DSA

apps/
├── common/              # Throttles, business exceptions, seed_demo, health
├── authentication/      # User (email login, RBAC ADMIN/BCN/MEMBER) + JWT + axes lockout
├── members/             # MemberProfile, BoardMember + Repository ABC + Profile360 + Excel
├── funds/               # FundTransaction + select_for_update + Factory Pattern + khóa sổ
├── events/              # ActivityEvent, EventTask DAG, EventRegistration (vé QR), Budget, Comms
├── attendance/          # AttendanceSession/Record + services/anti_cheat.py + nonce HMAC 60s
├── gamification/        # XpLedger (idempotency + cap 300/day) + Strategy Pattern + Leaderboard
├── documents/           # Document + File Upload Hardening 4 tầng (magic bytes pure-python)
└── posts/               # Post + PostAuditLog + bleach anti-XSS + Poll + Feedback ẩn danh
```

## 🛡️ Lớp bảo mật đã triển khai (Security Hardening)

| Tầng | Biện pháp |
|---|---|
| **SQL Injection** | 100% ORM parameterized; whitelist `order_by`/filter mọi endpoint |
| **DoS/DDoS** | DRF Throttle đa tầng: anon 60/m, user 300/m, burst 10/s, auth 5/m, checkin 3/m, feedback 2/m; pagination bắt buộc; payload limit 5MB; Gunicorn timeout 30s |
| **Nhận diện IP sau proxy** | `NUM_PROXIES=1` (env, mặc định 1 khi production) cho DRF throttle + `AXES_IPWARE_PROXY_COUNT` cho django-axes — IP thật là phần tử cuối của `X-Forwarded-For`, client không thể giả mạo để né rate-limit |
| **Cache dùng chung** | Throttle + axes dùng `DatabaseCache` (hoặc Redis khi có `REDIS_URL`) — bộ đếm dùng chung giữa các worker gunicorn, không né khóa bằng cách trúng worker khác. Dev cần chạy `python manage.py createcachetable` một lần |
| **Brute-force** | django-axes: khóa 5 lần sai / 15 phút (username+IP) |
| **JWT** | Access 30 phút, refresh 7 ngày, rotation + blacklist sau rotation |
| **PII (QA-Audit 2a)** | Thành viên thường KHÔNG nhận email/sdt/mssv của người khác qua `/members/search/` (chỉ tên/lớp/XP, chỉ thấy thành viên ACTIVE), `/members/board/` (ẩn MSSV cán bộ), `/documents/` (uploaded_by là tên), `/posts/` (tên hiển thị), chi tiết sự kiện (ẩn created_by_email). BCN/ADMIN giữ nguyên đầy đủ |
| **Tài liệu nội bộ (2d)** | `Document.pham_vi`: `PUBLIC_MEMBER` / `BCN_ONLY` — kiểm tra ở list, detail, search VÀ download; thành viên không thấy tài liệu BCN_ONLY (trả 404, không hé lộ sự tồn tại) |
| **API docs (2e)** | `/api/schema/`, `/api/docs/` chỉ ADMIN khi production (404 với người khác) |
| **Fake GPS** | `GPSAntiCheatEngine`: mock location, accuracy >100m, timestamp skew >60s (replay), nonce HMAC xoay 60s, device fingerprint (1 thiết bị/1 MSSV), teleportation >100 km/h, Haversine radius |
| **XP Cheat** | Server-Authoritative (client không gửi xp được), idempotency key, trần 300 XP/ngày |
| **Race Condition** | `transaction.atomic()` + `select_for_update()` cho quỹ, vé sự kiện, poll vote |
| **IDOR/BOLA** | `IsOwnerOrBCN` trên mọi object-level access |
| **File Upload** | Whitelist đuôi → size ≤15MB → magic bytes (pure-python) → UUID rename |
| **XSS** | bleach sanitize toàn bộ nội dung bài đăng; `Utils.escapeHtml` mọi dữ liệu động ở frontend; **CSP header** (middleware `core/middleware.py`) làm lớp backstop |
| **Fail-fast config (2c)** | `DEBUG` mặc định False; production BẮT BUỘC `SECRET_KEY` thật (RuntimeError khi thiếu hoặc tiền tố `django-insecure`); đã bỏ `SECURE_BROWSER_XSS_FILTER` (Django loại bỏ từ 4.0) |
| **Headers** | HSTS 1 năm, X-Frame-Options DENY, nosniff, SSL redirect, CORS whitelist |

### Ghi chú rủi ro: refresh token trong localStorage

Frontend thuần (không build-step) lưu JWT trong `localStorage` (`clbip_access_token`,
`clbip_refresh_token`) — đây là điểm yếu XSS đã biết. **Quyết định của bản này**: giữ
localStorage (chuyển sang cookie HttpOnly đòi hỏi đổi toàn bộ `api.js`, CSRF flow và
FRONTEND_CONTRACT — ngoài phạm vi), bù lại:
1. CSP nghiêm ngặt chặn script/iframe ngoại vi kể cả khi lọt XSS;
2. Access token ngắn hạn 30 phút + refresh rotation + blacklist sau rotation;
3. Mọi dữ liệu động qua `escapeHtml`/`textContent` (đã audit toàn bộ 14 trang).

Lộ trình khuyến nghị: chuyển refresh sang cookie HttpOnly SameSite=Lax trong phiên bản sau.


## 🧪 Chạy tests & dev local

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # dữ liệu demo
python manage.py test               # 172 tests — 100% PASS
python manage.py runserver          # http://localhost:8000/api/docs/
```

## ⚠️ Lưu ý production
- **Free plan Render**: disk ephemeral — file tài liệu/ảnh upload sẽ mất khi restart. Production thực tế nên gắn S3/Cloudinary (`django-storages`).
- Postgres free tier tự suspend sau 90 ngày không hoạt động — dùng `render shell` hoặc curl health check định kỳ.
- Đổi mật khẩu các tài khoản demo ngay sau khi nhận bàn giao.

## 🐬 Cấu hình MySQL làm CSDL chính (local dev)

Dự án dùng **MySQL** làm CSDL chính khi chạy local (theo `CLBIP_Frontend_Integration_Prompt.md`).
Driver `pymysql` thuần Python (đã cài cùng `cryptography`) — không cần biên dịch mysqlclient.

1. Tạo CSDL:
   ```sql
   CREATE DATABASE IF NOT EXISTS clb_ip_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. Tạo file `.env` ở thư mục gốc (Django tự nạp — xem `core/settings.py` §0.5):
   ```ini
   DB_ENGINE=mysql
   MYSQL_DATABASE=clb_ip_db
   MYSQL_USER=root
   MYSQL_PASSWORD=your_mysql_password
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   ```
3. Chạy migration + seed:
   ```bash
   python manage.py migrate
   python manage.py seed_demo
   ```
4. Không muốn dùng MySQL? Xóa/bỏ-comment `DB_ENGINE` → hệ thống tự rơi về SQLite
   (hoặc đặt `DATABASE_URL=postgres://...` khi deploy Render).

> ⚠️ Toàn bộ lọc theo ngày trong hệ thống đã dùng **khoảng datetime aware**
> (`apps/common/timeutils.py`) thay vì lookup `__date` — không cần nạp bảng
> timezone vào MySQL (máy Windows thường thiếu `CONVERT_TZ`).

## 🎨 Frontend (HTML5 + CSS + Vanilla JS)

Giao diện tĩnh nằm tại `frontend/` — Django tự phục vụ tại **`http://127.0.0.1:8000/`**:

```
http://127.0.0.1:8000/                          → điều hướng thông minh theo đăng nhập
http://127.0.0.1:8000/frontend/login.html       → đăng nhập (chips demo điền nhanh)
http://127.0.0.1:8000/frontend/admin/*.html     → phân hệ Ban chủ nhiệm (Navy)
http://127.0.0.1:8000/frontend/member/*.html    → phân hệ Thành viên (Cyber-Glass)
```

**Tài khoản demo**: chạy `python manage.py seed_demo --password=<mật-khẩu-của-bạn>` (hoặc đặt `DEMO_PASSWORD`); trang đăng nhập không còn chip điền nhanh tự động:
| Vai trò | Email |
|---|---|
| Quản trị | admin@clbip.vn |
| Ban chủ nhiệm | bcn@clbip.vn |
| Thành viên | 22a401101@student.hueuni.edu.vn |

Điểm nhấn DSA trên giao diện: radar GPS Haversine + confetti (member/checkin),
bục vinh danh Top 1-2-3 (member/leaderboard), vé điện tử QR Apple-Wallet
(member/events), autocomplete cây Trie (admin/members, member/documents,
admin/documents), checklist DAG khóa theo phụ thuộc (admin/events), mã nonce
xoay 60s (admin/attendance).

`ApiClient` (`frontend/js/api.js`) tự gắn Bearer Token + tự refresh khi 401
(single-flight) — mọi trang chỉ gọi qua client này.

Tài liệu hợp đồng API frontend: `frontend/FRONTEND_CONTRACT.md`.
Swagger UI (OpenAPI 3.0): `http://127.0.0.1:8000/api/docs/`.

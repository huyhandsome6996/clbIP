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

## 🔑 Tài khoản demo (tự sinh bởi `seed_demo`)

| Vai trò | Email | Mật khẩu |
|---|---|---|
| ADMIN | `admin@clbip.vn` | `CLBIP@2026` |
| BCN (Chủ nhiệm) | `bcn@clbip.vn` | `CLBIP@2026` |
| MEMBER | `22a401101@student.hueuni.edu.vn` | `CLBIP@2026` |

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
| **Brute-force** | django-axes: khóa 5 lần sai / 15 phút (username+IP) |
| **JWT** | Access 30 phút, refresh 7 ngày, rotation + blacklist sau rotation |
| **Fake GPS** | `GPSAntiCheatEngine`: mock location, accuracy >100m, timestamp skew >60s (replay), nonce HMAC xoay 60s, device fingerprint (1 thiết bị/1 MSSV), teleportation >100 km/h, Haversine radius |
| **XP Cheat** | Server-Authoritative (client không gửi xp được), idempotency key, trần 300 XP/ngày |
| **Race Condition** | `transaction.atomic()` + `select_for_update()` cho quỹ, vé sự kiện, poll vote |
| **IDOR/BOLA** | `IsOwnerOrBCN` trên mọi object-level access |
| **File Upload** | Whitelist đuôi → size ≤15MB → magic bytes (pure-python) → UUID rename |
| **XSS** | bleach sanitize toàn bộ nội dung bài đăng |
| **Headers** | HSTS 1 năm, X-Frame-Options DENY, nosniff, SSL redirect, CORS whitelist |

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

# Frontend test suites — CLB IP

Bộ kiểm thử frontend **committed** theo yêu cầu review R04 (69db15d) + N04
(review ac51233): contract tests chạy mã JS thật trong VM sandbox, E2E chạy
qua backend thật. Không cần cài dependency nào — chỉ Node 18+.

## 1. Contract tests (không cần backend)

```bash
node frontend/tests/api.test.js     # R02 — getBlob 401/auth policy (30 asserts)
node frontend/tests/nonce.test.js   # R03 — nonce expiry/backoff (45 asserts)
```

- `api.test.js` nạp **frontend/js/api.js thật** vào VM sandbox với fetch mô
  phỏng theo kịch bản: refresh single-flight, forceLogout đúng chính sách,
  403/404/429 không logout nhầm, blob không bị parse JSON.
- `nonce.test.js` nạp **inline script thật của frontend/admin/attendance.html**
  (trích từ HTML, chèn điểm expose trong sandbox) với **timer giả**: hết hạn
  vô hiệu hóa mã ngay, không spam toast khi offline, backoff ≤ 1 lần tự thử,
  response phiên cũ không đè phiên mới.

> ⚠️ Sau khi đổi logic nonce trong `attendance.html` (tri-view mới), chạy lại
> `nonce.test.js` — harness trích script từ trang, đổi trang là phải retest.

## 2. E2E với backend thật

Môi trường kiểm thử **tách biệt hoàn toàn** với production (N04):

| Thành phần | Yêu cầu |
|---|---|
| DB | Local/staging riêng (SQLite hoặc MariaDB local). **CẤM** trỏ DATABASE_URL production |
| Cache | Nếu `DJANGO_CACHE_BACKEND=django.core.cache.backends.db.DatabaseCache` (mặc định) → **BẮT BUỘC** `createcachetable` sau migrate, không thì mọi login → 500 (`django_cache_table` không tồn tại — lỗi setup đã gặp ở vòng QA ac51233) |
| Media/storage | Upload test ghi vào `MEDIA_ROOT` local; dùng thư mục tạm, xóa sau khi test. KHÔNG cấu hình S3 production |
| DEBUG/ALLOWED_HOSTS | Chạy local với `DJANGO_ENV=development` (DEBUG=True) + `ALLOWED_HOSTS=localhost,127.0.0.1` — không tắt bảo mật trên staging dùng chung |
| Secrets | Mật khẩu fixture truyền qua biến môi trường, KHÔNG log secret ra console/artifacts |

```bash
# 0) Env kiểm thử (KHÔNG bao giờ chạy các lệnh này trên production)
export DJANGO_ENV=development

# 1) Chuẩn bị DB — migrate → createcachetable → seed (THỨ TỰ BẮT BUỘC)
python manage.py migrate
python manage.py createcachetable          # N04: thiếu bước này → login 500
python manage.py seed_e2e_fixtures         # 130 members, 25 events, 121 vé, 2 OPEN + 2 CLOSED
#    (seed tự chặn production: DJANGO_ENV=production → CommandError)
#    Chạy lại nhiều lần được — seed idempotent, cleanup dữ liệu cũ trước khi tạo.

# 2) Chạy server
python manage.py runserver 0.0.0.0:8000

# 3) Chạy E2E (terminal khác)
node frontend/tests/e2e_api.test.mjs
#    BASE_URL=https://staging.example.com E2E_PASSWORD=... node frontend/tests/e2e_api.test.mjs

# 4) Dọn dẹp (tùy chọn — seed lần sau tự xử lý dữ liệu cũ)
#    DB test: drop database riêng; media: xóa MEDIA_ROOT test.
```

Fixtures tạo tài khoản `e2e-bcn@clbip.test` / `e2e-memberNNN@clbip.test` với
mật khẩu truyền qua `--password` (mặc định `E2eTest@2026`, chỉ dùng local).

### Phạm vi E2E (`e2e_api.test.mjs`)

| Khu vực | Kiểm chứng (assert ĐÚNG ITEM, không chỉ status 200) |
|---|---|
| Anonymous | `/` → 200 landing; API → 401 |
| F06 | `/members/?trang_thai=` canonical filter — items trả về đúng trạng thái lọc |
| §6 | total_members authoritative ≥ 130; **assert identity** thành viên #121 (MSSV/email khớp) qua search |
| F09 | `/events/?search=` — assert đúng sự kiện khớp từ khóa, không khớp → 0 items |
| F10 | records theo phiên OPEN + phân trang 2 trang thật — assert member cụ thể ở trang 2 |
| §6 | vé #25 trong tầm qua phân trang registrations — assert ma_ve identity |
| F12 | `has_voted` true/false theo từng user (server-authoritative) |
| Idempotency | POST quỹ 201 → retry cùng Idempotency-Key → replay cùng phiếu (assert ma_phieu GIỐNG NHAU) |
| F13 | `chart.umd.min.js` cùng origin 200 |

N04: suite đã siết assertion theo hướng "xác minh item mong đợi / định danh"
(thành viên #121, vé #25, ma_phieu replay) thay vì chỉ 200/count.

## 3. Những gì NẰM NGOÀI suite này

- `F04/R02` chi tiết luồng refresh: `api.test.js` (contract).
- `R03` chi tiết timer/backoff: `nonce.test.js` (contract, timer giả).
- `F05 preview, F07 late-checkin, F08 reopen, F14 khóa kỳ, R01 DAG`: đã có
  regression Django trong `apps/*/tests_audit_fix.py` + concurrency trong
  `apps/*/tests_concurrency.py` (chạy MariaDB/MySQL; skip có lý do trên SQLite).
- Concurrency (quỹ/điểm danh/DAG) bắt buộc chạy trên engine production-like
  (MariaDB/MySQL/PostgreSQL local hoặc CI) — **skip trên SQLite không được ghi
  nhận là concurrency pass** (N04). Báo cáo kèm engine/version/isolation.
- Browser E2E (click-through 6 trang trên UI merge): bắt buộc cho nghiệm thu
  merge — chạy bằng trình duyệt thật hoặc agent-browser với backend thật;
  HTTP suite KHÔNG thay thế browser E2E.

# Frontend test suites — CLB IP

Bộ kiểm thử frontend **committed** theo yêu cầu review R04 (69db15d): contract
tests chạy mã JS thật trong VM sandbox, E2E chạy qua backend thật. Không cần
cài dependency nào — chỉ Node 18+.

## 1. Contract tests (không cần backend)

```bash
node frontend/tests/api.test.js     # R02 — getBlob 401/auth policy (30 asserts)
node frontend/tests/nonce.test.js   # R03 — nonce expiry/backoff (26 asserts)
```

- `api.test.js` nạp **frontend/js/api.js thật** vào VM sandbox với fetch mô
  phỏng theo kịch bản: refresh single-flight, forceLogout đúng chính sách,
  403/404/429 không logout nhầm, blob không bị parse JSON.
- `nonce.test.js` nạp **inline script thật của frontend/admin/attendance.html**
  (trích từ HTML, chèn điểm expose trong sandbox) với **timer giả**: hết hạn
  vô hiệu hóa mã ngay, không spam toast khi offline, backoff ≤ 1 lần tự thử,
  response phiên cũ không đè phiên mới.

## 2. E2E với backend thật

```bash
# 1) Chuẩn bị DB (local/staging — cấm production)
python manage.py migrate
python manage.py seed_e2e_fixtures          # 130 members, 25 events, 121 vé, 2 OPEN + 2 CLOSED
# 2) Chạy server
python manage.py runserver 0.0.0.0:8000
# 3) Chạy E2E (terminal khác)
node frontend/tests/e2e_api.test.mjs
#    BASE_URL=https://staging.example.com E2E_PASSWORD=... node frontend/tests/e2e_api.test.mjs
```

Fixtures tạo tài khoản `e2e-bcn@clbip.test` / `e2e-memberNNN@clbip.test` với
mật khẩu truyền qua `--password` (mặc định `E2eTest@2026`, chỉ dùng local).
Lệnh seed **tự chặn production** (DJANGO_ENV=production → CommandError).

### Phạm vi E2E (`e2e_api.test.mjs`)

| Khu vực | Kiểm chứng |
|---|---|
| Anonymous | `/` → 200 landing; API → 401 |
| F06 | `/members/?trang_thai=` canonical filter |
| §6 | total_members authoritative ≥ 130; thành viên #121 chọn được qua search |
| F09 | `/events/?search=` |
| F10 | records theo phiên OPEN + phân trang 2 trang thật |
| §6 | vé #25 trong tầm qua phân trang registrations |
| F12 | `has_voted` true/false theo từng user (server-authoritative) |
| Idempotency | POST quỹ 201 → retry cùng Idempotency-Key → replay cùng phiếu |
| F13 | `chart.umd.min.js` cùng origin 200 |

## 3. Những gì NẰM NGOÀI suite này

- `F04/R02` chi tiết luồng refresh: `api.test.js` (contract).
- `R03` chi tiết timer/backoff: `nonce.test.js` (contract, timer giả).
- `F05 preview, F07 late-checkin, F08 reopen, F14 khóa kỳ, R01 DAG`: đã có
  regression Django trong `apps/*/tests_audit_fix.py` + concurrency trong
  `apps/*/tests_concurrency.py` (chạy MariaDB/MySQL; skip có lý do trên SQLite).
- Browser E2E (click-through 6 trang): chạy thủ công bằng trình duyệt hoặc
  agent-browser; các bước smoke ghi trong PR/kỳ nghiệm thu.

# 🛡️ CLB IP 2.0 — CẨM NANG & PROMPT BẢO MẬT TOÀN DIỆN CHO CODING AGENT
## HƯỚNG DẪN BẢO VỆ TOÀN DIỆN: CHỐNG SQL INJECTION, DOS/DDOS, SPAM, HACK, CHEAT GPS & GIAN LẬN

> **Mục tiêu:** Cung cấp bộ quy tắc bảo mật cấp quân sự (Defense-in-Depth) bắt buộc Coding Agent phải tuân thủ nghiêm ngặt, đảm bảo trang web CLB IP ĐHSP Huế không thể bị hack, phá hoại dữ liệu, spam hòm thư, hay gian lận điểm danh và điểm thưởng XP.

---

## 📑 MỤC LỤC
1. [Nguyên Tắc Cốt Lõi: Defense-in-Depth (Phòng Thủ Đa Tầng)](#1-nguyên-tắc-cốt-lõi-defense-in-depth)
2. [Chống Tấn Công Dữ Liệu & Injection (SQLi, NoSQLi, XSS)](#2-chống-tấn-công-dữ-liệu--injection)
3. [Chống DoS, DDoS & Tấn Công Làm Quá Tải Máy Chủ](#3-chống-dos-ddos--tấn-công-làm-quá-tải)
4. [Chống Brute-force, Dò Mật Khẩu & Chiếm Đoạt Tài Khoản](#4-chống-brute-force--bảo-vệ-tài-khoản)
5. [Chống Gian Lận Nghiệp Vụ CLB (Anti-Cheat Engine)](#5-chống-gian-lận-nghiệp-vụ-clb-anti-cheat-engine)
   - [5.1 Chống Fake GPS Điểm Danh (GPS Spoofing & Teleportation)](#51-chống-fake-gps-điểm-danh)
   - [5.2 Chống Gian Lận Điểm Thưởng XP & Cày Cấp Ảo](#52-chống-gian-lận-điểm-thưởng-xp)
   - [5.3 Chống Race Condition & Double-Spending Quỹ / Vé Sự Kiện](#53-chống-race-condition--double-spending)
6. [Bảo Vệ Kiểm Soát Truy Cập (Chống IDOR / BOLA)](#6-bảo-vệ-kiểm-soát-truy-cập-chống-idor)
7. [Bảo Mật Tải Lên Tệp Tin (File Upload Hardening)](#7-bảo-mật-tải-lên-tệp-tin)
8. [Cấu Hình Header Trình Duyệt & Hạ Tầng Render](#8-cấu-hình-header-trình-duyệt--hạ-tầng-render)
9. [Prompt Thực Thi Bảo Mật Dành Riêng Cho Coding Agent](#9-prompt-thực-thi-bảo-mật-dành-cho-coding-agent)

---

## 1. NGUYÊN TẮC CỐT LÕI: DEFENSE-IN-DEPTH

Coding Agent **KHÔNG BAO GIỜ** được tin tưởng bất kỳ dữ liệu nào đến từ Client (trình duyệt, mobile app, Postman, curl). Mọi kiểm tra ở Frontend chỉ mang tính chất hỗ trợ UX; **Backend là phòng tuyến duy nhất chịu trách nhiệm về an toàn dữ liệu.**

```
[Client / Hackers] 
       │ 
       ▼ (Tầng 1: Cloudflare / Render Reverse Proxy - DDoS, WAF, SSL)
[Render Infrastructure]
       │
       ▼ (Tầng 2: Django Middlewares - SecurityHeaders, IP Throttling, CORS)
[Django Middlewares]
       │
       ▼ (Tầng 3: DRF Permissions & JWT - AuthN / AuthZ / RBAC)
[Authentication & RBAC]
       │
       ▼ (Tầng 4: Service Layer - Business Logic, Anti-Cheat, Invariants)
[Service Layer & Anti-Cheat]
       │
       ▼ (Tầng 5: ORM & Database - Parameterized Queries, Pessimistic Locks)
[PostgreSQL Database]
```

---

## 2. CHỐNG TẤN CÔNG DỮ LIỆU & INJECTION

### 2.1 Tuyệt đối cấm Raw SQL Ghép Chuỗi (Anti-SQL Injection)
- **Quy tắc bắt buộc:** 100% truy vấn dữ liệu phải sử dụng **Django ORM** chuẩn hóa (`filter()`, `exclude()`, `select_related()`).
- **Nghiêm cấm:**
  ```python
  # ❌ TUYỆT ĐỐI CẤM (Lỗ hổng SQL Injection chết người)
  cursor.execute(f"SELECT * FROM members WHERE mssv = '{user_input}'")
  Member.objects.raw(f"SELECT * FROM members WHERE name = '{name}'")
  ```
- **Quy chuẩn đúng:**
  ```python
  # ✅ LUÔN SỬ DỤNG ORM Parameterized
  Member.objects.filter(mssv=user_input)

  # ✅ Nếu bắt buộc phải dùng raw SQL (rất hiếm khi), PHẢI dùng params tuple:
  cursor.execute("SELECT * FROM members WHERE mssv = %s", [user_input])
  ```
- **Chống SQL Injection qua `order_by()` động:**
  Khi người dùng truyền tham số sắp xếp (VD: `?sort=name`), PHẢI kiểm tra whitelist các trường hợp lệ:
  ```python
  ALLOWED_SORT_FIELDS = {'created_at', '-created_at', 'xp_points', '-xp_points', 'ho_ten'}
  sort_param = request.query_params.get('sort', '-created_at')
  if sort_param not in ALLOWED_SORT_FIELDS:
      sort_param = '-created_at'
  queryset = queryset.order_by(sort_param)
  ```

### 2.2 Chống XSS (Cross-Site Scripting)
- Toàn bộ dữ liệu văn bản từ người dùng (nội dung bài đăng, bình luận, góp ý) khi lưu phải được làm sạch qua `bleach` hoặc thư viện HTML sanitizer.
- Không bao giờ render dữ liệu HTML thô (`innerHTML` hoặc `|safe`) nếu chưa qua kiểm duyệt tag an toàn.
- Bật Content Security Policy (CSP) chặt chẽ.

---

## 3. CHỐNG DOS, DDOS & TẤN CÔNG LÀM QUÁ TẢI

### 3.1 Rate Limiting Đa Tầng (DRF Throttling)
Áp dụng giới hạn tần suất gọi API nghiêm ngặt theo từng phân loại endpoint:

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'apps.common.throttles.BurstRateThrottle',
        'apps.common.throttles.SustainedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/minute',        # Khách vãng lai: tối đa 60 request/phút
        'user': '300/minute',       # Người dùng đăng nhập: 300 request/phút
        'burst': '10/second',       # Chống flood burst ngắn hạn
        'auth_login': '5/minute',   # Đăng nhập: tối đa 5 lần thử/phút (chống dò pass)
        'checkin': '3/minute',      # Điểm danh GPS: tối đa 3 lần bấm/phút
        'feedback': '2/minute',     # Góp ý/Poll: tối đa 2 lần gửi/phút (chống spam)
    }
}
```

### 3.2 Chống Slowloris & Request Timeout
- Giới hạn kích thước payload tối đa trong request body (tránh upload file rác làm cạn kiệt RAM server):
  `DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880` (5 MB).
- Cấu hình Timeout trong Gunicorn: `--timeout 30` (ngắt các kết nối cố tình giữ socket mở quá 30 giây).

### 3.3 Phân trang bắt buộc (Pagination Enforcement)
- Không bao giờ trả về toàn bộ dữ liệu bảng (`SELECT * FROM table`). Tất cả API danh sách đều phải có phân trang bắt buộc (`PageNumberPagination` với `max_page_size = 100`), tránh trường hợp hacker gọi lấy 1 triệu bản ghi làm sập server.

---

## 4. CHỐNG BRUTE-FORCE & BẢO VỆ TÀI KHOẢN

### 4.1 Khóa Tài Khoản Tạm Thời (Account Lockout)
Sử dụng `django-axes` để tự động theo dõi và khóa IP / tài khoản khi đăng nhập thất bại:
- Sau **5 lần nhập sai mật khẩu liên tiếp**: Tự động khóa đăng nhập 15 phút.
- Gửi email cảnh báo đến sinh viên: *"Phát hiện nỗ lực đăng nhập bất thường vào tài khoản của bạn"*.

### 4.2 Lưu Trữ Mật Khẩu Bằng Thuật Toán Kháng GPU
Cấu hình thuật toán băm mật khẩu chuẩn hiện đại thay vì MD5/SHA1 lỗi thời:
```python
# settings.py
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]
```

### 4.3 JWT Token Hardening
- Access Token có thời hạn ngắn: **30 - 60 phút**.
- Refresh Token có thời hạn **7 ngày**, lưu dạng `HttpOnly` Secure Cookie (không cho phép JavaScript đọc để chống đánh cắp qua XSS).
- Áp dụng cơ chế **Token Rotation**: Mỗi khi đổi Access Token mới, Refresh Token cũ bị vô hiệu hóa ngay lập tức.
- Blacklist Token khi đăng xuất (`rest_framework_simplejwt.token_blacklist`).

---

## 5. CHỐNG GIAN LẬN NGHIỆP VỤ CLB (ANTI-CHEAT ENGINE)

Đây là tính năng đặc thù giúp CLB hoạt động công bằng, minh bạch:

### 5.1 Chống Fake GPS Điểm Danh (GPS Spoofing & Teleportation)

Thành viên có thể sử dụng ứng dụng Fake GPS (Mock Location) trên điện thoại Android/iOS hoặc sửa request Postman để điểm danh từ xa khi đang ở nhà. Hệ thống cần bảo vệ bằng **Engine Chống Gian Lận Tọa Độ**:

1. **Kiểm tra Mock Location Flag:**
   Client khi gửi tọa độ phải gửi kèm thuộc tính cảm biến thiết bị (`is_mock: false`, `accuracy: float`). Nếu `is_mock == true` hoặc `accuracy > 100m` (độ chính xác quá kém), từ chối ngay lập tức.
2. **Kiểm tra Nhảy Cóc Tọa Độ (Impossible Speed / Teleportation Detection):**
   Nếu tài khoản vừa đăng nhập ở TP. Hồ Chí Minh cách đây 10 phút, không thể xuất hiện tại Huế để điểm danh.
   $$V = \frac{\text{Khoảng cách giữa 2 lần check-in}}{\text{Thời gian giữa 2 lần}} > 100 \text{ km/h} \implies \text{Cờ cảnh báo gian lận!}$$
3. **Mã Hash Phiên Điểm Danh Động (Dynamic Session Nonce):**
   Mỗi phiên điểm danh có một mã token bí mật thay đổi mỗi 60 giây (Dynamic TOTP hoặc QR xoay vòng). Chỉ ai có mặt tại phòng sinh hoạt và nhìn lên máy chiếu mới có mã Nonce này để gửi kèm request GPS.
4. **Giới Hạn 1 Thiết Bị / 1 Tài Khoản:**
   Một điện thoại không thể điểm danh hộ cho 5 người bạn khác. Kiểm tra `Device-Fingerprint` (User-Agent + Screen Resolution + Hardware Concurrency Hash). Nếu 1 thiết bị điểm danh cho quá 2 MSSV khác nhau trong 1 buổi, gắn cờ `SUSPICIOUS_FRAUD` và báo về BCN.

```python
# apps/attendance/services/anti_cheat.py
class GPSAntiCheatEngine:
    @staticmethod
    def validate_checkin(member, session, client_lat, client_lon, client_time, device_id):
        # 1. Kiểm tra thiết bị đã điểm danh cho ai khác chưa
        recent_checkin = AttendanceRecord.objects.filter(
            session=session, device_id=device_id
        ).exclude(member=member).exists()
        if recent_checkin:
            raise AntiCheatException("Thiết bị này đã được sử dụng để điểm danh cho sinh viên khác!")

        # 2. Kiểm tra độ lệch thời gian (Timestamp Skew) chống Replay Attack
        server_now = timezone.now()
        if abs((server_now - client_time).total_seconds()) > 60:
            raise AntiCheatException("Thời gian trên thiết bị không đồng bộ với máy chủ!")

        # 3. Tính khoảng cách Haversine chuẩn xác
        is_valid, dist = GeoSpatialService.is_within_radius(
            session.vi_do, session.kinh_do, client_lat, client_lon, session.ban_kinh_m
        )
        if not is_valid:
            raise AntiCheatException(f"Bạn đang ở cách địa điểm {dist:.1f}m (vượt quá bán kính {session.ban_kinh_m}m)!")
        
        return True, dist
```

### 5.2 Chống Gian Lận Điểm Thưởng XP & Cày Cấp Ảo
- **Server-Authoritative Only:** Client **TUYỆT ĐỐI KHÔNG ĐƯỢC** gửi trường `xp` lên server. Mọi phép cộng trừ XP chỉ được thực hiện tại Backend dựa trên các sự kiện đã xác minh.
- **Giới Hạn Trần Hàng Ngày (Daily XP Cap):** Một thành viên không thể nhận quá 300 XP trong 1 ngày để chống bug spam request.
- **Idempotency Key (Khóa chống lặp):** Mỗi hành động thưởng điểm (ví dụ: hoàn thành nhiệm vụ X) gắn với một `idempotency_key = f"action_{user_id}_{event_id}_{date}"`. Nếu gọi lại lần 2, hệ thống trả về kết quả cũ mà không cộng thêm điểm.

### 5.3 Chống Race Condition & Double-Spending Quỹ / Vé Sự Kiện

Khi có 2 request gửi đồng thời cùng 1 mili-giây (ví dụ: 2 người cùng tranh 1 vé sự kiện cuối cùng hoặc 2 thủ quỹ cùng bấm chi tiền):

- **Pessimistic Locking (`select_for_update`):**
```python
# apps/funds/services/fund_service.py
from django.db import transaction

class FundService:
    @classmethod
    def execute_transaction(cls, loai_gd, so_tien, nguoi_thuc_hien, ghi_chu):
        with transaction.atomic():
            # Khóa bi quan bản ghi số dư gần nhất, các request khác phải chờ
            last_trans = FundTransaction.objects.select_for_update().order_by('-id').first()
            current_balance = last_trans.so_du_sau if last_trans else 0

            if loai_gd == 'CHI' and current_balance < so_tien:
                raise InsufficientFundException("Số dư quỹ không đủ để thực hiện khoản chi này!")

            new_balance = current_balance + so_tien if loai_gd == 'THU' else current_balance - so_tien

            return FundTransaction.objects.create(
                loai_gd=loai_gd,
                so_tien=so_tien,
                so_du_sau=new_balance,
                nguoi_thuc_hien=nguoi_thuc_hien,
                ghi_chu=ghi_chu
            )
```

---

## 6. BẢO VỆ KIỂM SOÁT TRUY CẬP (CHỐNG IDOR / BOLA)

Lỗ hổng Broken Object Level Authorization xảy ra khi thành viên đổi `id` trên URL (VD: `GET /api/v1/members/45/profile360/` đổi thành `id=12` của người khác) để xem trộm hoặc sửa dữ liệu.

- **Quy tắc bắt buộc:**
  ```python
  # permissions.py
  class IsOwnerOrBCN(permissions.BasePermission):
      def has_object_permission(self, request, view, obj):
          # BCN hoặc Admin có quyền xem/sửa
          if request.user.role in ['ADMIN', 'BCN']:
              return True
          # Thành viên thường CHỈ ĐƯỢC xem/sửa bản ghi của chính họ
          return hasattr(obj, 'user') and obj.user == request.user
  ```
- Mọi ViewSet đều phải gán `permission_classes = [IsAuthenticated, IsOwnerOrBCN]`.

---

## 7. BẢO MẬT TẢI LÊN TỆP TIN (FILE UPLOAD HARDENING)

Kẻ tấn công có thể đổi đuôi file virus hoặc file mã độc PHP/Python thành `hack.pdf` để upload lên server.

- **4 Tầng Kiểm Soát File Upload Bắt Buộc:**
  1. **Whitelist Đuôi File (Extension):** Chỉ cho phép `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.png`, `.jpg`, `.jpeg`. Nghiêm cấm tuyệt đối `.exe`, `.py`, `.sh`, `.php`, `.js`, `.html`.
  2. **Kiểm Tra Kích Thước (File Size):** Tối đa 15MB cho tài liệu, 3MB cho ảnh đại diện.
  3. **Kiểm Tra Magic Bytes (File Signature):** Dùng thư viện `python-magic` đọc 512 bytes đầu tiên để xác minh nội dung tệp thực tế có đúng là PDF/Image hay không, không tin vào đuôi mở rộng.
  4. **Randomize Tên File:** Đổi tên file khi lưu trên đĩa bằng UUID: `uuid.uuid4().hex + ext`, tránh lộ đường dẫn nhạy cảm hoặc tấn công Path Traversal (`../../etc/passwd`).

---

## 8. CẤU HÌNH HEADER TRÌNH DUYỆT & HẠ TẦNG RENDER

File `core/settings.py` khi chạy Production trên Render **BẮT BUỘC** phải có các cài đặt:

```python
# Cấu hình bảo mật HTTPS & Browser Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'  # Chống Clickjacking (không cho nhúng iframe trang admin)
SECURE_HSTS_SECONDS = 31536000  # 1 năm buộc dùng HTTPS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_ENV') == 'production'
SESSION_COOKIE_SECURE = os.environ.get('DJANGO_ENV') == 'production'
CSRF_COOKIE_SECURE = os.environ.get('DJANGO_ENV') == 'production'

# CORS Whitelist nghiêm ngặt (KHÔNG BAO GIỜ để CORS_ALLOW_ALL_ORIGINS = True trên Production)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://clbip-hue.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
```

---

## 9. PROMPT THỰC THI BẢO MẬT DÀNH CHO CODING AGENT

> **Dành cho bạn copy gửi trực tiếp cho bất kỳ Coding Agent nào đang thực thi:**

```text
Bạn là Kỹ Sư An Toàn Thông Tin & Backend Tech Lead chịu trách nhiệm bảo mật cho hệ thống CLB IP ĐHSP Huế (Django REST Framework).
Hãy đọc kỹ tài liệu `CLBIP_Security_Hardening_Prompt.md` và thực thi các biện pháp bảo vệ sau vào toàn bộ codebase:

1. Chống SQL Injection & Parameter Injection:
   - Đảm bảo 100% truy vấn dùng Django ORM parameterized. Cấm toàn bộ chuỗi nối SQL thô.
   - Kiểm tra whitelist cho các tham số sắp xếp `order_by` và lọc filter.

2. Cài đặt Rate Limiting (DRF Throttles):
   - Thiết lập AnonRateThrottle (60/m), UserRateThrottle (300/m), và ScopedRateThrottles riêng cho auth (5/m), check-in GPS (3/m), feedback (2/m).

3. Xây dựng Anti-Cheat Engine cho Điểm Danh GPS & Gamification:
   - Triển khai `GPSAntiCheatEngine`: Kiểm tra cự ly Haversine, cấm Mock Location, kiểm tra độ lệch thời gian (Replay Attack), và ngăn 1 thiết bị điểm danh cho nhiều sinh viên.
   - Khóa Idempotency cho phần thưởng XP, giới hạn trần 300 XP/ngày/thành viên.
   - Áp dụng `select_for_update()` cho các giao dịch Quỹ và Đăng ký vé sự kiện để chống Race Condition / Double-spending.

4. Chống IDOR & Phân quyền chặt chẽ (RBAC):
   - Tạo `IsOwnerOrBCN` permission class. Không cho phép thành viên xem/sửa hồ sơ cá nhân hoặc kết quả điểm danh của người khác qua ID trên URL.

5. File Upload Sanitization:
   - Kiểm tra magic bytes thực tế, whitelist định dạng an toàn, đổi tên file ngẫu nhiên bằng UUID trước khi lưu đĩa.

6. Cấu hình Production Headers:
   - Cài đặt đầy đủ HSTS, Content-Type NoSniff, X-Frame-Options DENY, và thiết lập CORS Whitelist nghiêm ngặt cho domain Render.

Hãy viết mã sạch, tuân thủ Clean Architecture, và bổ sung Unit Tests kiểm tra các trường hợp tấn công (SQLi payload, Brute-force rate limit, Fake GPS cự ly xa) để đảm bảo toàn bộ bài test đều PASS.
```

---
*Tài liệu tiêu chuẩn bảo mật cho dự án CLB IP ĐHSP Huế — 2026*

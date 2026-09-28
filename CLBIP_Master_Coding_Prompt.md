# 🚀 TÀI LIỆU YÊU CẦU & PROMPT TỔNG THỂ CHO CODING AGENT (MASTER PROMPT)
## HỆ THỐNG QUẢN LÝ TOÀN DIỆN CLB IP ĐHSP HUẾ (PHIÊN BẢN 2.0)

> **Mục tiêu:** Xây dựng hệ thống hoàn chỉnh từ Backend API (Django REST Framework) đến Frontend (hiện đại, thẩm mỹ cao theo Stitch UI & skill `design-taste-frontend`), áp dụng triệt để Cấu trúc Dữ liệu & Giải thuật (DSA) và Lập trình Hướng đối tượng (OOP), sẵn sàng deploy lên Render.

---

## 📑 MỤC LỤC
1. [Tổng Quan Kiến Trúc & Công Nghệ](#1-tổng-quan-kiến-trúc--công-nghệ)
2. [Sơ Đồ Thực Thể - Quan Hệ (ERD) & Database Schema](#2-sơ-đồ-thực-thể---quan-hệ-erd--database-schema)
3. [Thiết Kế Cấu Trúc Dữ Liệu & Giải Thuật (DSA) & OOP](#3-thiết-kế-cấu-trúc-dữ-liệu--giải-thuật-dsa--oop)
4. [Đặc Tả Chi Tiết 17 Màn Hình, Luồng & Nút Bấm](#4-đặc-tả-chi-tiết-17-màn-hình-luồng--nút-bấm)
5. [Đặc Tả RESTful API Endpoints](#5-đặc-tả-restful-api-endpoints)
6. [Cấu Hình Triển Khai Lên Render (Render Deployment Ready)](#6-cấu-hình-triển-khai-lên-render-render-deployment-ready)
7. [Checklist Thực Thi Từng Bước Cho Coding Agent](#7-checklist-thực-thi-từng-bước-cho-coding-agent)

---

## 1. TỔNG QUAN KIẾN TRÚC & CÔNG NGHỆ

### 1.1 Tech Stack Tiêu Chuẩn
- **Backend Framework:** Python 3.11+, Django 5.x, Django REST Framework (DRF).
- **Authentication:** `djangorestframework-simplejwt` (Access Token + Refresh Token).
- **Database:** PostgreSQL (Render Managed Postgres) hoặc SQLite cục bộ khi dev.
- **Tài liệu API:** `drf-spectacular` (OpenAPI 3.0 / Swagger UI tại `/api/docs/`).
- **Xử lý Tệp Tin:** `django-storages` hoặc local `/media/` + Cloudinary / Supabase Storage.
- **Triển khai (Deployment):** Render Web Service (Gunicorn / Uvicorn + `render.yaml`).
- **Frontend Standard:** Tuân thủ giao diện Stitch và quy chuẩn kỹ thuật trong skill `.agents/skills/design-taste-frontend/SKILL.md`.
- **Kiến trúc Codebase:** Clean Layered Architecture (Models $\rightarrow$ Repositories $\rightarrow$ Services $\rightarrow$ Serializers $\rightarrow$ ViewSets).

---

## 2. SƠ ĐỒ THỰC THỂ - QUAN HỆ (ERD) & DATABASE SCHEMA

```
+-------------------+       +-----------------------+       +----------------------+
|       User        | 1---1 |     MemberProfile     | 1---* |   AttendanceRecord   |
| (Auth, Role, JWT) |       | (MSSV, XP, Level, Hot)|       | (GPS, Status, XP)    |
+-------------------+       +-----------------------+       +----------------------+
          |                             |                              *
          |                             |                              |
          v                             v                              v 1
+-------------------+       +-----------------------+       +----------------------+
|    BoardMember    |       |   EventRegistration   | *---1 |  AttendanceSession   |
| (Nhiệm kỳ, Vai trò)|      | (QR Ticket, Status)   |       | (Radar, Radius, Lat) |
+-------------------+       +-----------------------+       +----------------------+
                                        |                              *
                                        v 1                            | 1
                            +-----------------------+       +----------------------+
                            |     ActivityEvent     | 1---* |      EventTask       |
                            | (Kế hoạch, Tọa độ GPS)|       | (DAG Topological)    |
                            +-----------------------+       +----------------------+
                                  | 1             | 1
                                  v *             v *
                        +-------------------+   +--------------------+
                        | EventBudgetDetail |   | EventCommunication |
                        | (Dự trù kinh phí) |   | (Đa kênh truyền thông)|
                        +-------------------+   +--------------------+

+-------------------+       +-----------------------+       +----------------------+
|  FundTransaction  | 1---* |    FundPeriodLock     |       |       Document       |
| (Thu/Chi, Balance)|       | (Khóa sổ định kỳ)     |       | (Kho tài liệu, Nhóm) |
+-------------------+       +-----------------------+       +----------------------+

+-------------------+       +-----------------------+       +----------------------+
|       Post        | 1---* |     PostAuditLog      |       |    CommunityPoll     |
| (Bảng tin, Ghim)  |       | (Lịch sử Sửa/Xóa/Ghim)|       | (Bình chọn, Góp ý)   |
+-------------------+       +-----------------------+       +----------------------+
```

### Chi tiết các bảng (Django Models):
1. **`User` (Kế thừa `AbstractUser`):**
   - `email`: Email đăng nhập (Unique).
   - `mssv`: Mã sinh viên (Unique, nullable cho giảng viên cố vấn).
   - `role`: Choices (`ADMIN`, `BCN`, `MEMBER`).
   - `is_active`: Boolean.
2. **`MemberProfile`:**
   - `user`: OneToOneField(`User`).
   - `ho_ten`, `ngay_sinh`, `gioi_tinh`, `lop`, `sdt`.
   - `avatar`: ImageField/URLField.
   - `xp_points`: Integer (Mặc định 0).
   - `current_level`: Integer (1-10).
   - `streak_count`: Integer (Chuỗi chuyên cần 🔥).
   - `trang_thai_hd`: Choices (`ACTIVE`, `INACTIVE`, `LEAVE`).
3. **`BoardMember`:**
   - `member`: ForeignKey(`MemberProfile`).
   - `nhiem_ky`: CharField (VD: `2025-2026`).
   - `chuc_vu`: Choices (`CHỦ NHIỆM`, `PHÓ CHỦ NHIỆM`, `TRƯỞNG BAN`, `PHÓ BAN`).
   - `ban_phu_trach`: Choices (`HỌC THUẬT`, `TRUYỀN THÔNG`, `SỰ KIỆN`, `TÀI CHÍNH`).
4. **`FundTransaction`:**
   - `ma_phieu`: CharField (Unique, sinh tự động `PT...` hoặc `PC...`).
   - `loai_gd`: Choices (`THU`, `CHI`).
   - `so_tien`: BigIntegerField.
   - `so_du_sau`: BigIntegerField (Lũy kế được kiểm soát qua Transaction).
   - `nguoi_thuc_hien`: CharField.
   - `hinh_thuc`: Choices (`TIỀN MẶT`, `CHUYỂN KHOẢN`).
   - `ngay_gd`: DateTimeField.
   - `ghi_chu`: TextField.
   - `is_locked`: Boolean (Thuộc kỳ đã khóa sổ).
5. **`ActivityEvent`:**
   - `ma_hd`: CharField (Unique).
   - `ten_hoat_dong`: CharField.
   - `loai_hd`: Choices (`WORKSHOP`, `HACKATHON`, `SINH HOẠT ĐỊNH KỲ`, `TEAMBUILDING`).
   - `thoi_gian_bat_dau`, `thoi_gian_ket_thuc`: DateTimeField.
   - `dia_diem`: CharField.
   - `vi_do`, `kinh_do`: FloatField (Tọa độ tâm điểm danh).
   - `ban_kinh_m`: FloatField (Bán kính cho phép check-in, mặc định 50m).
   - `tong_kinh_phi_du_tru`: BigIntegerField.
   - `so_luong_toi_da`: IntegerField.
   - `trang_thai`: Choices (`PLANNING`, `OPEN_REGISTRATION`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`).
6. **`EventTask` (Hỗ trợ đồ thị DAG):**
   - `event`: ForeignKey(`ActivityEvent`).
   - `ten_task`: CharField.
   - `nguoi_phu_trach`: ForeignKey(`MemberProfile`).
   - `depends_on`: ManyToManyField(`self`, symmetrical=False) - Phụ thuộc các task trước.
   - `is_completed`: Boolean.
   - `deadline`: DateTimeField.
7. **`EventRegistration`:**
   - `event`: ForeignKey(`ActivityEvent`).
   - `member`: ForeignKey(`MemberProfile`).
   - `ma_ve`: CharField (Mã vé duy nhất, sinh QR code).
   - `trang_thai`: Choices (`REGISTERED`, `APPROVED`, `CHECKED_IN`, `CANCELLED`).
   - `created_at`: DateTimeField.
8. **`AttendanceSession` & `AttendanceRecord`:**
   - Phiên điểm danh gắn với sự kiện, lưu chi tiết trạng thái (`CO_MAT`, `VANG`, `CO_PHEP`, `DI_MUON`), khoảng cách mét tính được, giờ check-in thực tế.
9. **`Document`:**
   - `tieu_de`, `nhom` (`CHUYEN_MON`, `NGHIEP_VU`, `KY_NANG`), `file_path`, `file_type`, `file_size`, `luot_tai`.
10. **`Post` & `PostAuditLog`:**
    - Bài đăng, ghim, audit lịch sử chỉnh sửa.

---

## 3. THIẾT KẾ CẤU TRÚC DỮ LIỆU & GIẢI THUẬT (DSA) & OOP

Coding agent **BẮT BUỘC** triển khai các module giải thuật trong thư mục `core/algorithms/` và tuân theo skill `.agents/skills/dsa-oop-backend-architecture/SKILL.md`:

### 3.1 DSA 1: Haversine & Bounding Box Spatial Pruning (`geo_haversine.py`)
- **Tác dụng:** Điểm danh GPS tức thì, xác minh tọa độ thành viên có nằm trong bán kính cho phép của BCN hay không.
- **Tối ưu:** Tính Bounding Box $[\text{lat} \pm \Delta, \text{lon} \pm \Delta]$ để prune $99\%$ trường hợp ngoài phạm vi trước khi tính hàm lượng giác Haversine.

### 3.2 DSA 2: Min-Heap / PriorityQueue Leaderboard (`leaderboard_heap.py`)
- **Tác dụng:** Xếp hạng thi đua thời gian thực cho hàng trăm thành viên với độ phức tạp $O(N \log K)$ thay vì Sort toàn bộ bảng $O(N \log N)$.
- **Cấu trúc:** Min-Heap kích thước $K=10$ duy trì Top 10 cao nhất, kèm Hash Map cho phép tra cứu vị trí tức thời của người dùng hiện tại trong $O(1)$.

### 3.3 DSA 3: Trie Prefix Autocomplete & Search (`trie_search.py`)
- **Tác dụng:** Tìm kiếm tức thời theo MSSV, Họ tên không dấu và Tiêu đề tài liệu với độ phức tạp $O(L)$ ($L$ là độ dài từ khóa).

### 3.4 DSA 4: Directed Acyclic Graph (DAG) & Topological Sort (`dag_workflow.py`)
- **Tác dụng:** Sắp xếp tiến trình chuẩn bị sự kiện (Checklist Tasks). Phát hiện phụ thuộc vòng tròn (Deadlock Cycle Detection) bằng thuật toán Kahn (BFS) hoặc DFS.

### 3.5 OOP Clean Layered Architecture
- **Rule 1:** Tuyệt đối không viết business logic tính toán hay ORM queries nặng trong `views.py`.
- **Rule 2:** Toàn bộ logic điểm danh, cộng trừ quỹ, cấp badge, tính toán XP đặt trong thư mục `services/` (`AttendanceService`, `FundService`, `GamificationService`, `EventService`).
- **Rule 3:** Áp dụng Strategy Pattern cho việc tính điểm thưởng và Factory Pattern cho việc tạo phiếu thu/chi.

---

## 4. ĐẶC TẢ CHI TIẾT 17 MÀN HÌNH, LUỒNG & NÚT BẤM

### 🅰️ PHÂN HỆ QUẢN TRỊ BCN (ADMIN PORTAL — 10 MÀN HÌNH)

#### 1. Màn hình Đăng nhập (`/login`)
- **Luồng:** Nhập Email/MSSV + Mật khẩu $\rightarrow$ Gọi API `/api/v1/auth/token/` $\rightarrow$ Nhận JWT Token $\rightarrow$ Điều hướng theo Role (`ADMIN`/`BCN` vào `/admin/dashboard`, `MEMBER` vào `/member/home`).
- **Nút bấm & Tương tác:**
  * Nút `[Đăng nhập]`: Kiểm tra form, hiển thị loading spinner, thông báo lỗi nếu sai thông tin.
  * Checkbox `[Ghi nhớ đăng nhập]`: Lưu refresh token vào localStorage/cookie.
  * Link `[Quên mật khẩu?]`: Modal gửi mã OTP xác nhận về email sinh viên.

#### 2. Dashboard BCN (`/admin/dashboard`)
- **Luồng:** Tải KPI thời gian thực, biểu đồ Chart.js và bài đăng mới nhất.
- **Nút bấm & Tương tác:**
  * Nút `[Đăng thông báo mới]`: Mở modal soạn bài (Text + Upload ảnh + Checkbox `[Ghim bài]`).
  * Nút `[Sửa bài]`, `[Xóa bài]`: Yêu cầu xác thực tài khoản BCN, ghi vào `PostAuditLog`.
  * Nút `[Ghim/Bỏ ghim]`: Đẩy bài lên đầu trang.
  * Nút `[Xem hòm thư góp ý]`: Mở modal đọc ý kiến ẩn danh của thành viên.

#### 3. Quản lý Thành viên (`/admin/members`)
- **Luồng:** Xem bảng danh sách thành viên, lọc lớp, trạng thái hoạt động, tìm kiếm nhanh qua Trie.
- **Nút bấm & Tương tác:**
  * Nút `[+ Thêm thành viên]`: Form nhập thông tin đầy đủ.
  * Nút `[Nhập từ Excel]`: Upload file `.xlsx`, preview các dòng lỗi trước khi lưu.
  * Nút `[Xuất Excel]`: Tải file danh sách thành viên hiện tại.
  * Click vào dòng thành viên: Mở modal **Hồ sơ 360°** (tổng số sự kiện tham gia, chuyên cần %, vai trò).
  * Nút `[Sửa]`, `[Xóa (Khóa)]`: Cập nhật trạng thái thành viên.

#### 4. Quản lý Quỹ CLB (`/admin/funds`)
- **Luồng:** Thống kê Tổng thu, Tổng chi, Số dư thực tế. Cảnh báo vàng nếu số dư < 200.000 VNĐ.
- **Nút bấm & Tương tác:**
  * Nút `[+ Lập phiếu Thu]` / `[+ Lập phiếu Chi]`: Form nhập số tiền, người thực hiện, ghi chú, đính kèm hóa đơn. Chạy atomic transaction kiểm tra số dư.
  * Nút `[Khóa sổ kỳ này]`: Đóng băng toàn bộ giao dịch của kỳ, ngăn chặn sửa/xóa dữ liệu cũ.
  * Nút `[Xuất sổ quỹ Excel]`: Tải bảng kê chi tiết có chữ ký điện tử.

#### 5. Quản lý Kế hoạch & Sự kiện (`/admin/events`)
- **Luồng:** Quản lý vòng đời sự kiện từ lúc lên kế hoạch, dự trù kinh phí, phân công công việc đến truyền thông.
- **Nút bấm & Tương tác:**
  * Nút `[+ Tạo kế hoạch sự kiện]`: Form nhập thông tin, địa điểm, thời gian, kinh phí.
  * Tab `[Dự trù kinh phí]`: Bảng nhập các hạng mục chi tiêu, tự động tính tổng tiền.
  * Tab `[Phân công nhiệm vụ (DAG)]`: Thiết lập task và chọn phụ thuộc (Task B phụ thuộc Task A), hiển thị cảnh báo nếu phát hiện vòng lặp deadlock.
  * Tab `[Kế hoạch truyền thông]`: Quản lý các bài đăng Facebook, TikTok, deadline và link bài viết.

#### 6. Quản lý Điểm danh GPS (`/admin/attendance`)
- **Luồng:** BCN tạo phiên điểm danh, lấy GPS tại chỗ làm tâm, tự động tạo bản ghi `VẮNG` cho mọi thành viên đang hoạt động.
- **Nút bấm & Tương tác:**
  * Nút `[+ Mở phiên điểm danh mới]`: Tự động lấy tọa độ hiện tại của thiết bị BCN, chọn bán kính (VD: 50m) và thời gian hiệu lực.
  * Nút `[Đóng phiên]`: Kết thúc điểm danh, chốt danh sách.
  * Nút `[Cập nhật thủ công hàng loạt]`: Override trạng thái (Có mặt / Có phép / Vắng / Muộn) cho trường hợp điện thoại thành viên hết pin hoặc lỗi định vị.

#### 7. Kho Tài liệu BCN (`/admin/documents`)
- **Nút bấm:** `[+ Tải lên tài liệu]`, `[Xem trước PDF trực tiếp]`, `[Phân nhóm chuyên môn]`, `[Xóa/Sửa]`.

#### 8. Cơ cấu Ban Chủ Nhiệm (`/admin/board`)
- **Nút bấm:** `[Chọn nhiệm kỳ]`, `[+ Bổ nhiệm thành viên BCN]`, `[Xem sơ đồ tổ chức dạng cây (Org Chart)]`.

#### 9. Báo cáo & Thống kê (`/admin/reports`)
- **Nút bấm:** `[Chọn khoảng thời gian]`, `[Xuất báo cáo PDF tổng kết kỳ]`, `[Xem biểu đồ xu hướng chuyên cần]`.

#### 10. Cài đặt Hệ thống (`/admin/settings`)
- **Nút bấm:** `[Cấu hình niên khóa]`, `[Sao lưu Database]`, `[Phân quyền quản trị viên]`.

---

### 🅱️ PHÂN HỆ THÀNH VIÊN (MEMBER PORTAL — 7 MÀN HÌNH)

#### 11. Trang Chủ & Social Feed (`/member/home`)
- **Giao diện:** Phong cách Gen Z Cyber-Glass, rực rỡ, hiện đại theo `CLBIP_Member_Stitch_Prompts.md`.
- **Tương tác:**
  * Banner chào đón cá nhân hóa kèm chuỗi Streak 🔥.
  * Feed tin tức: Thả cảm xúc ❤️/🔥, xem bài ghim của BCN.
  * Widget Thẻ thành viên số mini và Top 3 chiến thần chuyên cần tuần này.

#### 12. Điểm danh GPS Radar (`/member/checkin`)
- **Luồng:** Mở trang $\rightarrow$ Trình duyệt xin quyền GPS $\rightarrow$ Radar quét hiển thị khoảng cách đến tâm $\rightarrow$ Nếu $\le$ bán kính cho phép: Nút sáng lên $\rightarrow$ Bấm `[XÁC NHẬN ĐIỂM DANH GPS]` $\rightarrow$ Ghi nhận `CÓ MẶT`, cộng +50 XP, hiệu ứng chúc mừng (Confetti) và tăng chuỗi 🔥 Streak.

#### 13. Hub Sự kiện & Vé Điện Tử (`/member/events`)
- **Tương tác:**
  * Lướt xem danh sách sự kiện kèm đồng hồ đếm ngược giờ G.
  * Nút `[Đăng Ký Vé Tham Gia (Miễn phí)]`: Sinh mã vé điện tử QR Code tức thì (kiểu Apple Wallet) dùng để check-in tại cửa hội trường.

#### 14. Bảng Vàng & Đua Top Thi Đua (`/member/leaderboard`)
- **Giao diện:** Bục vinh quang 3D Podium mạ Vàng - Bạc - Đồng cho Top 1-2-3 (tính từ giải thuật Max-Heap).
- **Tương tác:**
  * Thanh ghim vị trí hiện tại của chính người dùng ("Bạn đang ở Rank #14 - Còn 80 XP để vào Top 10!").
  * Tab nhiệm vụ tuần kiếm XP (Điểm danh thứ 7 +50 XP, nộp bài tập +30 XP).

#### 15. Hồ Sơ Cá Nhân & VIP Member Pass (`/member/profile`)
- **Tương tác:**
  * Thẻ thành viên số Holographic có thể lật xoay hoặc lưu ảnh về máy.
  * Thanh cấp độ XP (Level 1 $\rightarrow$ 10).
  * Bộ sưu tập huy hiệu thành tích 3D (Huy hiệu 100% chuyên cần, Code Ninja...).

#### 16. Kho Báu Tài Liệu Học Thuật (`/member/documents`)
- **Tương tác:**
  * Thanh tìm kiếm thông minh (Prefix Trie), lọc tag theo chủ đề (C++, Web, Đề thi).
  * Nút `[Đọc thử PDF]` (Preview trực tiếp không rời trang), nút `[Tải về]`.
  * Nút `[Chia sẻ tài liệu mới]` (nhận +100 XP đóng góp cộng đồng).

#### 17. Lịch Sinh Hoạt Thông Minh (`/member/calendar`)
- **Tương tác:**
  * Lịch tháng/tuần hiển thị các sự kiện color-coded.
  * Nút `[+ Đồng bộ Google Calendar / iCal]`.

---

## 5. ĐẶC TẢ RESTFUL API ENDPOINTS

Tất cả API có tiền tố: `/api/v1/`
Response chuẩn:
```json
{
  "success": true,
  "data": { ... },
  "message": "Thông báo thân thiện",
  "errors": null
}
```

### Danh mục Endpoints chính:
- **Auth:**
  * `POST /api/v1/auth/token/` — Lấy JWT Token (Đăng nhập)
  * `POST /api/v1/auth/token/refresh/` — Làm mới Access Token
  * `GET /api/v1/auth/me/` — Thông tin người dùng hiện tại
- **Members:**
  * `GET, POST /api/v1/members/` — Danh sách & Thêm thành viên
  * `GET, PUT, DELETE /api/v1/members/{id}/` — Chi tiết & Cập nhật thành viên
  * `GET /api/v1/members/{id}/profile360/` — Hồ sơ 360° tổng hợp
  * `POST /api/v1/members/import-excel/` — Nhập hàng loạt từ Excel
  * `GET /api/v1/members/export-excel/` — Xuất danh sách Excel
- **Funds:**
  * `GET, POST /api/v1/funds/` — Danh sách thu chi & Tạo giao dịch mới
  * `POST /api/v1/funds/lock-period/` — Khóa sổ giao dịch theo kỳ
  * `GET /api/v1/funds/export-excel/` — Xuất sổ quỹ Excel
- **Attendance & GPS:**
  * `GET, POST /api/v1/attendance/sessions/` — Danh sách & Mở phiên điểm danh GPS
  * `POST /api/v1/attendance/check-in/` — Thành viên tự check-in GPS (Haversine Verification)
  * `PUT /api/v1/attendance/sessions/{id}/bulk-override/` — BCN cập nhật thủ công hàng loạt
- **Events & Tasks:**
  * `GET, POST /api/v1/events/` — Danh sách & Tạo sự kiện
  * `GET, PUT /api/v1/events/{id}/tasks/` — Quản lý công việc DAG và kiểm tra Topological order
  * `POST /api/v1/events/{id}/register/` — Thành viên đăng ký lấy vé QR
- **Leaderboard & Gamification:**
  * `GET /api/v1/gamification/leaderboard/` — Lấy Top 10 qua Max-Heap + Rank cá nhân
  * `GET /api/v1/gamification/badges/` — Danh sách huy hiệu thành viên
- **Documents:**
  * `GET, POST /api/v1/documents/` — Danh sách & Upload tài liệu mới
  * `GET /api/v1/documents/search/?q={query}` — Tìm kiếm nhanh qua Trie
- **Posts & Feedback:**
  * `GET, POST /api/v1/posts/` — Bảng tin hoạt động
  * `PATCH /api/v1/posts/{id}/pin/` — Ghim bài viết
  * `POST /api/v1/feedback/` — Gửi ý kiến ẩn danh / Bình chọn Poll

---

## 6. CẤU HÌNH TRIỂN KHAI LÊN RENDER (RENDER DEPLOYMENT READY)

### 6.1 File `render.yaml` chuẩn:
```yaml
services:
  - type: web
    name: clbip-backend
    env: python
    buildCommand: "./build.sh"
    startCommand: "gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 3"
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.8
      - key: DJANGO_SETTINGS_MODULE
        value: core.settings
      - key: SECRET_KEY
        generateValue: true
      - key: DEBUG
        value: "False"
      - key: ALLOWED_HOSTS
        value: ".onrender.com,localhost,127.0.0.1"
      - key: DATABASE_URL
        fromDatabase:
          name: clbip-postgres
          property: connectionString

databases:
  - name: clbip-postgres
    plan: free
```

### 6.2 Script `build.sh`:
```bash
#!/usr/bin/env bash
# exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate
```

---

## 7. CHECKLIST THỰC THI TỪNG BƯỚC CHO CODING AGENT

- [ ] **Bước 1: Khởi tạo Project Django & Virtual Environment:** Tạo cấu trúc dự án chuẩn modular (`core/`, `apps/authentication/`, `apps/members/`, `apps/funds/`, `apps/events/`, `apps/attendance/`, `apps/gamification/`, `apps/documents/`).
- [ ] **Bước 2: Cài đặt và cấu hình thư viện:** Cài `djangorestframework`, `djangorestframework-simplejwt`, `django-cors-headers`, `drf-spectacular`, `psycopg2-binary`, `gunicorn`.
- [ ] **Bước 3: Implement core DSA modules trong `core/algorithms/`:** Viết `geo_haversine.py`, `leaderboard_heap.py`, `trie_search.py`, `dag_workflow.py` kèm unit test độc lập.
- [ ] **Bước 4: Định nghĩa Models & Database Migrations:** Triển khai 100% schema theo mục 2, chạy `makemigrations` và `migrate`.
- [ ] **Bước 5: Xây dựng Service Layer (OOP):** Triển khai các Service classes xử lý logic và kết nối với các module giải thuật DSA.
- [ ] **Bước 6: Xây dựng Serializers & API ViewSets:** Hoàn thành 100% các RESTful API endpoints với OpenAPI docstring.
- [ ] **Bước 7: Tích hợp Frontend & CORS:** Đảm bảo CORS header cho phép mọi origin cần thiết; giao diện tuân theo `design-taste-frontend` và các Stitch Prompts.
- [ ] **Bước 8: Kiểm thử & Chuẩn bị Deploy Render:** Chạy `python manage.py test`, kiểm tra file `render.yaml`, `build.sh` và `Procfile`.

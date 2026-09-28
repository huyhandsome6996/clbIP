# 🌐 PROMPT NỐI BACKEND VỚI GIAO DIỆN FRONTEND & CẤU HÌNH MYSQL
## DỰ ÁN: HỆ THỐNG QUẢN LÝ TOÀN DIỆN CLB IP ĐHSP HUẾ 2.0

> **Dành riêng cho Coding Agent:** Hướng dẫn kết nối toàn bộ hệ thống Backend Django REST Framework với giao diện Frontend (HTML5, Modern CSS, Vanilla JS), thiết lập hệ CSDL chính là **MySQL**, đồng thời tuân thủ các skill `design-taste-frontend` và `dsa-oop-backend-architecture`.

---

## 🎯 NHIỆM VỤ CỐT LÕI
1. **Thiết lập MySQL làm hệ CSDL chính:** Kết nối Django với MySQL, chạy migration và seed demo data.
2. **Xây dựng tầng Frontend Web Client:** Tạo các trang HTML/CSS/JS hoạt động hoàn chỉnh, có giao diện đẹp mắt, hiện đại, chuẩn bị sẵn cấu trúc module hóa để người dùng nâng cấp dần theo các bản thiết kế từ Stitch sau này.
3. **Nối 100% các API Backend:** Tích hợp đầy đủ xác thực JWT (tự động Refresh Token), phân quyền theo Role (`ADMIN`/`BCN` và `MEMBER`), gọi API và render dữ liệu động thời gian thực.
4. **Phản ánh các thuật toán DSA trên giao diện:** Radar quét GPS, Bảng vàng Top 1-2-3 (Min-Heap), Autocomplete tức thì (Trie), Sắp xếp checklist phụ thuộc (DAG), Vé điện tử mã QR.

---

## 🐬 PHẦN 1: CẤU HÌNH MYSQL LÀM HỆ CƠ SỞ DỮ LIỆU CHÍNH

### 1.1 Kiểm tra thư viện driver đã cài đặt
Trong virtual environment `.venv`, driver `pymysql` và `cryptography` đã được cài sẵn và tích hợp vào `core/settings.py`.

### 1.2 Khởi tạo Database trong MySQL
Chạy lệnh tạo CSDL (nếu chưa có):
```sql
CREATE DATABASE IF NOT EXISTS clb_ip_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 1.3 Cấu hình biến môi trường kết nối MySQL
Tạo hoặc cập nhật file `.env` tại thư mục gốc của dự án:
```ini
# Cấu hình CSDL MySQL chính
DB_ENGINE=mysql
MYSQL_DATABASE=clb_ip_db
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306

# Hoặc dùng dạng chuỗi DATABASE_URL:
# DATABASE_URL=mysql://root:your_mysql_password@127.0.0.1:3306/clb_ip_db
```

### 1.4 Chạy Migration và Seed dữ liệu sang MySQL
```powershell
$env:PYTHONUTF8="1"
& .venv\Scripts\python.exe manage.py migrate
& .venv\Scripts\python.exe manage.py seed_demo
```
*Kết quả:* Toàn bộ 15 bảng, quan hệ khóa ngoại và dữ liệu mẫu sẽ được tạo tự động 100% trên MySQL.

---

## 🎨 PHẦN 2: THIẾT KẾ KIẾN TRÚC FRONTEND & TUÂN THỦ SKILL

### 2.1 Cấu trúc thư mục Frontend khuyến nghị:
```
frontend/
├── index.html                   # Chuyển hướng thông minh dựa trên trạng thái đăng nhập
├── login.html                   # Trang đăng nhập chung (Split-screen hiện đại)
│
├── css/
│   ├── variables.css            # Hệ thống màu sắc (Indigo #6366F1, Violet #8B5CF6, Navy #0F4C81)
│   ├── base.css                 # Reset, typography Inter, scrollbars mượt mà
│   ├── components.css           # Buttons, cards, modals, toast, badge, table, skeleton
│   └── responsive.css           # Breakpoints sm/md/lg, mobile bottom navigation
│
├── js/
│   ├── api.js                   # HTTP Client: Fetch wrapper tự động gắn Bearer Token & Refresh Token
│   ├── auth.js                  # Quản lý Session, lưu localStorage, kiểm tra quyền RBAC, Logout
│   ├── toast.js                 # Hiển thị thông báo Toast nổi góc màn hình (Success, Error, Warning)
│   └── utils.js                 # Định dạng tiền tệ VNĐ, ngày tháng, debounce tìm kiếm
│
├── admin/                       # PHÂN HỆ QUẢN TRỊ BCN (Tone màu Classic Navy #0F4C81)
│   ├── dashboard.html           # Thống kê KPI, biểu đồ, bảng tin BCN, ghim bài
│   ├── members.html             # Quản lý thành viên, xem hồ sơ 360°, import/export Excel
│   ├── funds.html               # Sổ quỹ Thu/Chi, khóa sổ kỳ, cảnh báo quỹ thấp
│   ├── events.html              # Vòng đời sự kiện, dự trù kinh phí, DAG tasks checklist
│   ├── attendance.html          # Quản lý phiên điểm danh GPS, override trạng thái hàng loạt
│   └── documents.html           # Kho tài liệu, upload, xem trước PDF
│
└── member/                      # PHÂN HỆ THÀNH VIÊN (Tone màu Gen Z Cyber-Glass theo Stitch)
    ├── home.html                # Feed hoạt động, chuỗi streak 🔥, thẻ thành viên số mini
    ├── checkin.html             # Điểm danh GPS Radar sci-fi, xác thực cự ly, nhận XP
    ├── events.html              # Danh sách sự kiện, vé điện tử QR Code (Apple Wallet style)
    ├── leaderboard.html         # Bục vinh danh 3D Top 1-2-3 (Min-Heap), nhiệm vụ tuần
    ├── profile.html             # Hồ sơ cá nhân, thẻ thành viên Hologram, kho huy hiệu 3D
    └── documents.html           # Thư viện Notion-style, tìm kiếm nhanh Trie, đọc thử PDF
```

---

## ⚡ PHẦN 3: HTTP API CLIENT CHUẨN (`frontend/js/api.js`)

Coding Agent **PHẢI** tạo file `frontend/js/api.js` xử lý tập trung mọi tương tác mạng:

```javascript
/**
 * API Client tập trung — Tự động gắn Token & Tự làm mới Token khi hết hạn
 */
const API_BASE = "http://127.0.0.1:8000/api/v1";

class ApiClient {
  static getAccessToken() {
    return localStorage.getItem("clbip_access_token");
  }

  static getRefreshToken() {
    return localStorage.getItem("clbip_refresh_token");
  }

  static setTokens(access, refresh) {
    if (access) localStorage.setItem("clbip_access_token", access);
    if (refresh) localStorage.setItem("clbip_refresh_token", refresh);
  }

  static clearTokens() {
    localStorage.removeItem("clbip_access_token");
    localStorage.removeItem("clbip_refresh_token");
    localStorage.removeItem("clbip_user_info");
  }

  static async request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    options.headers = options.headers || {};

    const token = this.getAccessToken();
    if (token) {
      options.headers["Authorization"] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !options.headers["Content-Type"]) {
      options.headers["Content-Type"] = "application/json";
    }

    let response = await fetch(url, options);

    // Xử lý khi Token hết hạn (401) -> Tự động Refresh Token 1 lần
    if (response.status === 401 && this.getRefreshToken()) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        options.headers["Authorization"] = `Bearer ${this.getAccessToken()}`;
        response = await fetch(url, options);
      } else {
        this.clearTokens();
        window.location.href = "/login.html?expired=1";
        return null;
      }
    }

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || "Có lỗi xảy ra khi gọi API");
    }
    return data;
  }

  static async refreshToken() {
    try {
      const res = await fetch(`${API_BASE}/auth/token/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: this.getRefreshToken() })
      });
      if (res.ok) {
        const json = await res.json();
        this.setTokens(json.data.access, json.data.refresh);
        return true;
      }
    } catch (e) {
      console.error("Lỗi làm mới token:", e);
    }
    return false;
  }
}
```

---

## 🧩 PHẦN 4: HIỂN THỊ CÁC THUẬT TOÁN DSA TRÊN GIAO DIỆN

### 1. Điểm Danh GPS Radar (`member/checkin.html`):
- Sử dụng `navigator.geolocation.getCurrentPosition` lấy tọa độ thực tế.
- Kiểm tra cự ly và hiển thị radar quét hiệu ứng sóng xung quanh (pulse effect).
- Khi trong bán kính $\le$ bán kính phiên: Bật sáng nút `[XÁC NHẬN ĐIỂM DANH]`.
- Gọi API `POST /api/v1/attendance/check-in/` gửi `{ session_id, vi_do, kinh_do, device_id }`.
- Thành công: Bắn hiệu ứng Confetti ăn mừng và tăng chuỗi 🔥 Streak.

### 2. Bảng Vàng Min-Heap Leaderboard (`member/leaderboard.html`):
- Gọi API `GET /api/v1/gamification/leaderboard/`.
- Render bục vinh quang 3D Podium cho Top 1 (Vàng), Top 2 (Bạc), Top 3 (Đồng).
- Render thẻ vị trí của chính người dùng (Rank hiện tại, XP cần để thăng hạng).

### 3. Autocomplete Cây Tiền Tố Trie (`documents.html` & `members.html`):
- Lắng nghe sự kiện `input` trên ô tìm kiếm với hàm `debounce(300ms)`.
- Gọi API `GET /api/v1/documents/search/?q={query}` hoặc `GET /api/v1/members/search/?q={query}`.
- Hiển thị danh sách kết quả gợi ý tức thời không giật lag.

### 4. Checklist Sự Kiện Đồ Thị DAG (`admin/events.html`):
- Hiển thị danh sách công việc theo thứ tự Topo hợp lệ (Topological Sort).
- Các task có phụ thuộc (`depends_on`) sẽ bị disable checkbox cho đến khi các task điều kiện tiên quyết được tích hoàn thành.

### 5. Vé Sự Kiện Điện Tử QR Code (`member/events.html`):
- Sau khi bấm `[Đăng Ký Tham Gia]` thành công, nhận `ma_ve` từ API.
- Render mã QR Code trực quan trên tấm vé phong cách Apple Wallet (sử dụng thư viện `qrcode.min.js`).

---

## 📋 PROMPT RA LỆNH CHO CODING AGENT THỰC HIỆN NGAY

> **Copy toàn bộ nội dung trong ô dưới đây gửi cho Coding Agent:**

```text
Bạn là Senior Fullstack Web Developer. Hãy thực hiện ngay 2 nhiệm vụ sau cho dự án CLB IP ĐHSP Huế 2.0:

Nhiệm vụ 1: Chuyển cấu hình cơ sở dữ liệu sang MySQL
- Driver pymysql và cryptography đã được cài sẵn trong virtual environment.
- File core/settings.py đã được cấu hình nhận diện các biến môi trường MySQL.
- Hãy kiểm tra kết nối MySQL, cấu hình file .env với thông tin CSDL (mặc định database 'clb_ip_db', user 'root', host '127.0.0.1', port 3306).
- Chạy 'python manage.py migrate' để sinh toàn bộ bảng trên MySQL và chạy 'python manage.py seed_demo' để nạp sẵn dữ liệu mẫu.

Nhiệm vụ 2: Xây dựng giao diện Frontend hoàn chỉnh và kết nối với Backend API
- Tham khảo tài liệu 'CLBIP_Frontend_Integration_Prompt.md' và các tiêu chuẩn trong skill '.agents/skills/design-taste-frontend/SKILL.md'.
- Tạo thư mục 'frontend/' với cấu trúc đầy đủ:
  + css/ (variables, base, components, glassmorphism, responsive mobile-first)
  + js/ (api.js với fetch wrapper tự động gắn Bearer Token & Refresh Token, auth.js quản lý đăng nhập/phân quyền, toast.js)
  + login.html (Trang đăng nhập split-screen hiện đại, đăng nhập bằng email + mật khẩu, chuyển hướng đúng theo role ADMIN/BCN hoặc MEMBER)
  + Phân hệ BCN Admin trong admin/: dashboard.html, members.html, funds.html, events.html, attendance.html, documents.html.
  + Phân hệ Thành viên trong member/: home.html, checkin.html (kèm radar GPS Haversine), events.html (kèm vé điện tử QR), leaderboard.html (kèm bục vinh danh 3D Min-Heap), profile.html, documents.html (kèm Trie autocomplete).
- Đảm bảo 100% các nút bấm, form nhập liệu, modal và bảng dữ liệu đều được nối với các API Backend tại http://127.0.0.1:8000/api/v1/.
- Cấu hình Django core/settings.py và core/urls.py để có thể phục vụ (serve) các file giao diện tĩnh này một cách mượt mà hoặc mở trực tiếp trên trình duyệt.

Hãy thực hiện từng bước một cách chỉn chu, viết mã HTML/CSS/JS sạch, đẹp, hiện đại và kiểm thử kết nối API thực tế!
```

---
*Tài liệu hướng dẫn kết nối Frontend & MySQL — CLB IP ĐHSP Huế 2.0*

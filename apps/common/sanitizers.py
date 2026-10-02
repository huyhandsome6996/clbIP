"""
Sanitizer dùng chung — bleach cho trường văn bản thuần (QA-Audit P3)
=====================================================================
Trước đây chỉ posts/feedback được sanitize backend-side; các trường
free-text khác (mô tả sự kiện, tài liệu, hồ sơ) dựa vào việc frontend
escape khi render — phòng thủ chỉ 1 lớp. Chuẩn defense-in-depth: dữ liệu
khi vào DB phải đã sạch tag HTML, bất kể client gửi gì.

Dùng `clean_text()` cho CHAR/TEXT thuần (không cho phép tag nào).
Nội dung HTML có chủ ý (bài đăng bảng tin) vẫn dùng whitelist riêng của
PostService.sanitize — không dùng hàm này.
"""
import bleach


def clean_text(value: str) -> str:
    """
    Làm sạch văn bản thuần: strip TOÀN BỘ tag HTML (bleach strip=True),
    giữ lại nội dung chữ. `<script>alert(1)</script>Xin chào` → `alert(1)Xin chào`.

    Áp dụng cho: tên/mô tả sự kiện, task, hạng mục kinh phí, truyền thông,
    tiêu đề/mô tả/tags tài liệu, họ tên/lớp hồ sơ thành viên.
    """
    return bleach.clean(value or "", tags=[], strip=True).strip()

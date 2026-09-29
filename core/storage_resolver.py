"""
Media Storage Resolver (QA-Audit nhóm 5)
=========================================
Đĩa Render là TẠM THỜI (ephemeral) — mọi file upload (tài liệu, hóa đơn,
poster) BỊ MẤT khi service restart/redeploy nếu vẫn lưu đĩa cục bộ.

Hàm này chọn storage cho STORAGES["default"] theo biến môi trường:
    - USE_S3=1 → S3-compatible (AWS S3 / Cloudflare R2 / MinIO…) qua
      django-storages; cấu hình qua các biến AWS_* (xem .env.example).
    - Còn lại → FileSystemStorage (dev cục bộ; production cần mount disk
      hoặc chuyển S3 — ghi rõ trong README "Lưu ý production").

Hàm thuần (pure function trên dict env) để unit-test được mà không cần
re-import settings.
"""
from typing import Mapping


def resolve_default_storage(env: Mapping[str, str]) -> dict:
    """
    Args:
        env: mapping biến môi trường (thường là os.environ).

    Returns:
        Entry cấu hình cho STORAGES["default"] ({"BACKEND": ..., "OPTIONS": ...}).
    """
    if env.get("USE_S3", "").strip() == "1":
        # django-storages S3Storage (tương thích AWS S3 / Cloudflare R2 / MinIO
        # thông qua endpoint_url). file_overwrite=False tránh ghi đè lẫn nhau.
        options = {
            "access_key": env.get("AWS_ACCESS_KEY_ID", ""),
            "secret_key": env.get("AWS_SECRET_ACCESS_KEY", ""),
            "bucket_name": env.get("AWS_STORAGE_BUCKET_NAME", ""),
            "region_name": env.get("AWS_S3_REGION_NAME", "") or None,
            "endpoint_url": env.get("AWS_S3_ENDPOINT_URL", "") or None,
            "file_overwrite": False,
            "default_acl": "private",
        }
        custom_domain = env.get("AWS_S3_CUSTOM_DOMAIN", "").strip()
        if custom_domain:
            options["custom_domain"] = custom_domain
        return {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": options}
    return {"BACKEND": "django.core.files.storage.FileSystemStorage"}

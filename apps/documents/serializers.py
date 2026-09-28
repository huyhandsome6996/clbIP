"""
Serializers — apps.documents
============================
- DocumentSerializer:        Đầu ra chuẩn cho danh sách/chi tiết tài liệu.
- DocumentCreateSerializer:  Đầu vào upload tài liệu (multipart/form-data).
"""
from rest_framework import serializers

from apps.documents.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    """Biểu diễn tài liệu trả về cho client (chỉ đọc — file không ghi qua đây)."""

    uploaded_by = serializers.SerializerMethodField("get_uploaded_by_email")
    uploaded_by_ho_ten = serializers.SerializerMethodField()
    file = serializers.FileField(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "tieu_de",
            "nhom",
            "tags",
            "mo_ta",
            "file",
            "file_type",
            "file_size",
            "luot_tai",
            "uploaded_by",
            "uploaded_by_ho_ten",
            "created_at",
        ]
        read_only_fields = fields

    def get_uploaded_by_email(self, obj: Document) -> str:
        """Email người chia sẻ (an toàn khi uploaded_by bị SET_NULL)."""
        owner = obj.uploaded_by
        return owner.email if owner else ""

    def get_uploaded_by_ho_ten(self, obj: Document) -> str:
        """Họ tên hiển thị qua MemberProfile nếu có, ngược lại rỗng."""
        owner = obj.uploaded_by
        profile = getattr(owner, "member_profile", None) if owner else None
        return profile.ho_ten if profile else ""


class DocumentCreateSerializer(serializers.ModelSerializer):
    """Input upload tài liệu — tệp bắt buộc, nhom phải thuộc choices của model."""

    file = serializers.FileField(required=True, allow_null=False, allow_empty_file=False)

    class Meta:
        model = Document
        fields = ["file", "tieu_de", "nhom", "tags", "mo_ta"]
        extra_kwargs = {
            "tieu_de": {"required": True, "allow_blank": False, "max_length": 255},
            "tags": {"required": False, "allow_blank": True},
            "mo_ta": {"required": False, "allow_blank": True},
        }

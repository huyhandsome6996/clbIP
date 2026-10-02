"""
Serializers — apps.posts
========================
- PostListSerializer / PostDetailSerializer:  đầu ra bảng tin (+ audit log).
- PostCreateUpdateSerializer:                 input đăng/sửa bài (BCN).
- FeedbackCreateSerializer / FeedbackListSerializer: hòm thư ẨN DANH (không sender!).
- PollSerializer / PollVoteSerializer / PollCreateSerializer: bình chọn.
"""
from rest_framework import serializers

from apps.posts.models import CommunityPoll, FeedbackEntry, Post, PostAuditLog


# ----------------------------------------------------------------------
# Post
# ----------------------------------------------------------------------
class PostAuditLogSerializer(serializers.ModelSerializer):
    """Một dòng audit — ai làm gì, lúc nào."""

    performed_by = serializers.SerializerMethodField()

    class Meta:
        model = PostAuditLog
        fields = ["action", "performed_by", "timestamp", "chi_tiet"]

    def get_performed_by(self, obj: PostAuditLog) -> str:
        """Email người thực hiện (an toàn khi performed_by bị SET_NULL)."""
        actor = obj.performed_by
        return actor.email if actor else ""


class PostListSerializer(serializers.ModelSerializer):
    """Bài đăng trong feed — created_by hiển thị TÊN người đăng (QA-Audit 2a:
    không lộ email cá nhân của chủ bài cho người đọc trong feed)."""

    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ["id", "tieu_de", "noi_dung", "anh_dinh_kem", "is_pinned", "created_by", "created_at"]
        read_only_fields = fields

    def get_created_by(self, obj: Post) -> str:
        owner = obj.created_by
        if owner is None:
            return ""
        # Ưu tiên tên hiển thị từ hồ sơ thành viên; email chỉ là fallback
        # (vd: tài khoản hệ thống chưa có profile) — vẫn là một chuỗi hiển thị,
        # giữ nguyên shape hợp đồng frontend.
        try:
            ho_ten = owner.member_profile.ho_ten
        except Exception:  # noqa: BLE001 — profile không tồn tại (SET_NULL/ơ lại)
            ho_ten = ""
        return ho_ten or owner.email


class PostDetailSerializer(PostListSerializer):
    """Chi tiết bài đăng + 10 dòng audit gần nhất (trách nhiệm giải trình)."""

    audit_logs = serializers.SerializerMethodField()

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ["pinned_at", "updated_at", "audit_logs"]

    def get_audit_logs(self, obj: Post) -> list:
        """10 audit log gần nhất (model Meta ordering: mới nhất trước)."""
        logs = obj.audit_logs.all()[:10]
        return PostAuditLogSerializer(logs, many=True).data


class PostCreateUpdateSerializer(serializers.ModelSerializer):
    """Input đăng bài / sửa bài của BCN — nội dung sẽ được Service bleach."""

    class Meta:
        model = Post
        fields = ["tieu_de", "noi_dung", "anh_dinh_kem"]
        extra_kwargs = {
            "tieu_de": {"required": True, "allow_blank": False, "max_length": 200},
            "noi_dung": {"required": True, "allow_blank": False},
            "anh_dinh_kem": {"required": False, "allow_blank": True, "allow_null": True},
        }


# ----------------------------------------------------------------------
# Feedback — ẨN DANH ĐÚNG NGHĨA: không field sender nào được serialize
# ----------------------------------------------------------------------
class FeedbackCreateSerializer(serializers.Serializer):
    """Input gửi góp ý ẩn danh — trim_whitespace=False để Service tự kiểm whitespace."""

    noi_dung = serializers.CharField(
        required=True, allow_blank=False, max_length=2000, trim_whitespace=False
    )


class FeedbackListSerializer(serializers.ModelSerializer):
    """
    Output góp ý cho BCN — CHỈ nội dung + thời gian.
    TUYỆT ĐỐI không chứa sender/email/id người gửi (spec FeedbackService).
    """

    class Meta:
        model = FeedbackEntry
        fields = ["id", "noi_dung", "created_at"]
        read_only_fields = fields


# ----------------------------------------------------------------------
# CommunityPoll
# ----------------------------------------------------------------------
class PollSerializer(serializers.ModelSerializer):
    """Bình chọn: options + votes (dict index→số phiếu) + tổng phiếu + has_voted."""

    total_votes = serializers.SerializerMethodField()
    has_voted = serializers.SerializerMethodField()

    class Meta:
        model = CommunityPoll
        fields = ["id", "question", "options", "votes", "is_closed", "total_votes", "has_voted", "created_at"]
        read_only_fields = fields

    def get_total_votes(self, obj: CommunityPoll) -> int:
        """Tổng số phiếu đã ghi nhận = sum(votes.values())."""
        return sum((obj.votes or {}).values())

    def get_has_voted(self, obj: CommunityPoll) -> bool:
        """User hiện tại đã bình chọn chưa — để frontend khóa UI ngay từ lần
        tải đầu trên mọi trình duyệt (không phụ thuộc localStorage)."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return str(user.pk) in (obj.voted_user_ids or [])


class PollVoteSerializer(serializers.Serializer):
    """Input bình chọn: index lựa chọn (0-based)."""

    option_index = serializers.IntegerField(required=True, min_value=0)


class PollCreateSerializer(serializers.Serializer):
    """Input BCN tạo bình chọn — tối thiểu 2 lựa chọn (validate sâu ở Service)."""

    question = serializers.CharField(required=True, allow_blank=False, max_length=255)
    options = serializers.ListField(
        child=serializers.CharField(min_length=1, max_length=255),
        min_length=2,
        max_length=10,
        allow_empty=False,
    )

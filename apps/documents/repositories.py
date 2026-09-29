"""
Repository Layer — apps.documents
=================================
Tách biệt tầng truy vấn CSDL khỏi tầng nghiệp vụ (Repository Pattern — SKILL.md
Phần 1 §2.A, nguyên tắc Dependency Inversion).

`DocumentService` chỉ phụ thuộc vào trừu tượng `IDocumentRepository`, không đụng
trực tiếp vào ORM của `Document`. 100% truy vấn dùng Django ORM parameterized
(TUYỆT ĐỐI không raw SQL — Security Hardening §2.1).

Lưu ý phạm vi (QA-Audit 2d): phương thức `visible_for` / `list_documents` là
CHỖ DUY NHẤT quyết định tài liệu BCN_ONLY bị ẩn khỏi thành viên thường —
list, chi tiết, search, download đều đi qua cùng một nguồn sự thật này.
"""
from abc import ABC, abstractmethod
from typing import Iterator, List, Optional

from django.db.models import F, Q, QuerySet

from apps.documents.models import Document

# Whitelist sắp xếp cho API danh sách (chống SQL Injection qua order_by — §2.1).
# Giá trị ngoài whitelist → fallback DEFAULT_SORT.
ALLOWED_SORT_FIELDS: frozenset = frozenset(
    {"-created_at", "luot_tai", "-luot_tai", "tieu_de"}
)
DEFAULT_SORT: str = "-created_at"


class IDocumentRepository(ABC):
    """Hợp đồng (interface) truy cập dữ liệu Kho tài liệu — phụ thuộc trừu tượng (DIP)."""

    @abstractmethod
    def visible_for(self, user) -> QuerySet[Document]:
        """Queryset tài liệu theo phạm vi: MEMBER chỉ thấy PUBLIC_MEMBER."""

    @abstractmethod
    def list_documents(
        self,
        user,
        nhom: Optional[str] = None,
        search: str = "",
        sort: str = DEFAULT_SORT,
    ) -> QuerySet[Document]:
        """Danh sách tài liệu: scope pham_vi + select_related + filter nhom/search
        (icontains parameterized) + sort whitelist."""

    @abstractmethod
    def detail_queryset(self) -> QuerySet[Document]:
        """Queryset cơ sở cho view chi tiết (select_related người upload, chưa scope)."""

    @abstractmethod
    def get_by_id_select_related(self, pk: int) -> Optional[Document]:
        """Lấy 1 tài liệu theo pk kèm select_related (None nếu không tồn tại)."""

    @abstractmethod
    def delete_document(self, doc: Document) -> None:
        """Xóa bản ghi tài liệu trong DB (file vật lý do tầng service lo)."""

    @abstractmethod
    def increment_download(self, pk: int) -> None:
        """Tăng luot_tai +1 một cách atomic (F expression — chống race condition)."""

    @abstractmethod
    def iter_indexable_documents(
        self, scope_filter: Optional[dict] = None
    ) -> Iterator[Document]:
        """Iterator tài liệu phục vụ build Trie (chỉ tải id/tieu_de/tags)."""

    @abstractmethod
    def get_by_ids_ordered(self, ids, limit: int) -> List[Document]:
        """Tra cứu theo danh sách id (thứ tự mặc định -created_at), tối đa `limit` kết quả."""

    @abstractmethod
    def get_member_profile_by_user(self, user):
        """Tra cứu MemberProfile theo user (hợp đồng chéo-app phục vụ thưởng XP)."""


class DjangoDocumentRepository(IDocumentRepository):
    """Triển khai cụ thể bằng Django ORM cho `IDocumentRepository`."""

    def visible_for(self, user) -> QuerySet[Document]:
        """QA-Audit 2d: thành viên thường chỉ thấy tài liệu PUBLIC_MEMBER."""
        queryset = Document.objects.all()
        if not getattr(user, "is_bcn", False):
            queryset = queryset.filter(pham_vi=Document.PhamVi.PUBLIC_MEMBER)
        return queryset

    def list_documents(
        self,
        user,
        nhom: Optional[str] = None,
        search: str = "",
        sort: str = DEFAULT_SORT,
    ) -> QuerySet[Document]:
        """Danh sách tài liệu cho GET /documents/ — filter/sort đều whitelist."""
        queryset = self.visible_for(user).select_related(
            "uploaded_by__member_profile"
        )

        if nhom in Document.Nhom.values:  # whitelist nhóm
            queryset = queryset.filter(nhom=nhom)

        search = (search or "").strip()
        if search:
            queryset = queryset.filter(
                Q(tieu_de__icontains=search)
                | Q(tags__icontains=search)
                | Q(mo_ta__icontains=search)
            )

        if sort not in ALLOWED_SORT_FIELDS:  # whitelist chống SQLi qua order_by
            sort = DEFAULT_SORT
        return queryset.order_by(sort)

    def detail_queryset(self) -> QuerySet[Document]:
        """Queryset cơ sở cho view chi tiết — tối ưu join người upload."""
        return Document.objects.select_related("uploaded_by__member_profile")

    def get_by_id_select_related(self, pk: int) -> Optional[Document]:
        """Lấy 1 tài liệu theo pk (None nếu không tồn tại) kèm select_related."""
        return (
            Document.objects.select_related("uploaded_by__member_profile")
            .filter(pk=pk)
            .first()
        )

    def delete_document(self, doc: Document) -> None:
        """Xóa bản ghi tài liệu (DELETE một dòng)."""
        doc.delete()

    def increment_download(self, pk: int) -> None:
        """
        Tăng lượt tải +1 atomic (F expression, không read-modify-write).

        ⚠ Chống race condition khi nhiều user tải cùng lúc (Security §5.3).
        """
        Document.objects.filter(pk=pk).update(luot_tai=F("luot_tai") + 1)

    def iter_indexable_documents(
        self, scope_filter: Optional[dict] = None
    ) -> Iterator[Document]:
        """
        Iterator phục vụ build Prefix Trie (DSA 3) — chỉ tải 3 trường cần thiết
        (`only`) và stream từng row (`iterator`, không giữ toàn bộ queryset).

        Args:
            scope_filter: dict lookup áp lên queryset (VD: {"pham_vi":
                "PUBLIC_MEMBER"}) hoặc None để index toàn bộ.
        """
        queryset = Document.objects.all()
        if scope_filter:
            queryset = queryset.filter(**scope_filter)
        return queryset.only("id", "tieu_de", "tags").iterator()

    def get_by_ids_ordered(self, ids, limit: int) -> List[Document]:
        """Tra cứu theo id — thứ tự mặc định của model (-created_at), slice `limit`."""
        return list(Document.objects.filter(id__in=ids)[:limit])

    def get_member_profile_by_user(self, user):
        """
        Tra cứu MemberProfile của user (None nếu chưa có profile).

        Dùng cho thưởng XP chia sẻ tài liệu — ủy quyền cho members repository
        (nguồn chuẩn của truy vấn user→profile, tránh nhân bản chéo-app).
        """
        from apps.members.repositories import DjangoMemberRepository  # noqa: PLC0415

        return DjangoMemberRepository().get_by_user(user)

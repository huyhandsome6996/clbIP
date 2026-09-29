"""
Service Layer — apps.documents
==============================
Toàn bộ nghiệp vụ Kho Tài liệu nằm tại đây (Clean Architecture — Rule 1/2):
    - DocumentService.validate_file:   File Upload Hardening 4 tầng (Security §7).
    - DocumentService.create_document: Lưu tài liệu + đổi tên UUID + thưởng XP.
    - DocumentService.search:          Tìm kiếm prefix O(L) qua DSA 3 (Prefix Trie).
    - DocumentService.increment_download: Đếm lượt tải atomic (F expression).
    - DocumentService.delete_document: Phân quyền xóa + dọn file vật lý.

Truy vấn CSDL được ủy quyền cho `IDocumentRepository` (Repository Pattern — DIP):
Service chỉ orchestration nghiệp vụ, KHÔNG đụng ORM trực tiếp. DI qua
`_repository_class` + `_repo()` (giống `FundService`).

KHÔNG viết logic trong views.py — view chỉ là controller mỏng.
"""
import logging
import os
import uuid
from typing import ClassVar, Iterable, List, Optional

from django.conf import settings

from apps.common.exceptions import (
    FileValidationException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from apps.documents.models import Document
from apps.documents.repositories import IDocumentRepository, DjangoDocumentRepository

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Tập hợp nghiệp vụ kho tài liệu CLB.

    File Upload Hardening 4 tầng (bắt buộc theo CLBIP_Security_Hardening_Prompt.md §7):
        Tầng 1 — Whitelist đuôi file (.pdf/.docx/.pptx/.xlsx/.png/.jpg/.jpeg).
        Tầng 2 — Kích thước tối đa 15MB.
        Tầng 3 — Magic bytes: đọc 512 bytes đầu, kiểm tra chữ ký nhị phân THẬT
                 của nội dung (chống đổi đuôi file .exe/.php thành .pdf).
                 Pure-python, không cần python-magic.
        Tầng 4 — Đổi tên file thành uuid4().hex + ext khi lưu (chống Path
                 Traversal, tránh lộ tên gốc nhạy cảm).
    """

    # Tầng 1: whitelist đuôi cho phép
    ALLOWED_EXTENSIONS: set = {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}

    # Tầng 2: dung lượng tối đa 15MB cho tài liệu
    MAX_SIZE_BYTES: int = 15 * 1024 * 1024

    # Tầng 3: (magic signature, tập đuôi thuộc nhóm signature đó)
    MAGIC_SIGNATURES: List[tuple] = [
        (b"%PDF-", {".pdf"}),
        (b"\x89PNG\r\n", {".png"}),
        (b"\xff\xd8\xff", {".jpg", ".jpeg"}),
        # DOCX/PPTX/XLSX đều là container ZIP (OOXML)
        (b"PK\x03\x04", {".docx", ".pptx", ".xlsx"}),
    ]

    # Content-Type phục vụ download (chống MIME sniffing — Security §8)
    CONTENT_TYPES: dict = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    # Repository Pattern (DIP): truy vấn CSDL ủy quyền cho IDocumentRepository
    _repository_class: ClassVar[type[IDocumentRepository]] = DjangoDocumentRepository

    @classmethod
    def _repo(cls) -> IDocumentRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    # ==================================================================
    # Tầng kiểm tra tệp (4 tầng hardening)
    # ==================================================================
    @classmethod
    def validate_file(cls, django_file) -> str:
        """
        Kiểm tra tệp upload theo 3 tầng đầu (tầng 4 thực hiện khi lưu).

        Args:
            django_file: Đối tượng file upload của Django (UploadedFile).

        Returns:
            Phần mở rộng hợp lệ (có dấu chấm, lowercase), VD ".pdf".

        Raises:
            FileValidationException: Nếu vi phạm whitelist / dung lượng / magic bytes.
        """
        # ---- Tầng 1: Whitelist đuôi file ----
        ext: str = os.path.splitext(django_file.name or "")[1].lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise FileValidationException(
                "Định dạng không được phép. Chỉ chấp nhận: PDF, DOCX, PPTX, XLSX, PNG, JPG, JPEG.",
                errors={"extension": ext},
            )

        # ---- Tầng 2: Kích thước tối đa 15MB ----
        if (django_file.size or 0) > cls.MAX_SIZE_BYTES:
            raise FileValidationException(
                "Tệp vượt quá 15MB. Vui lòng nén hoặc chọn tệp nhỏ hơn.",
                errors={"size": django_file.size},
            )

        # ---- Tầng 3: Magic bytes — nội dung phải khớp định dạng ----
        django_file.seek(0)
        head: bytes = django_file.read(512)
        django_file.seek(0)

        if not cls._magic_matches(head, ext):
            raise FileValidationException(
                "Nội dung tệp không khớp định dạng. Tệp có thể đã bị đổi đuôi hoặc hỏng.",
                errors={"extension": ext, "magic_head": head[:8].hex()},
            )
        return ext

    @classmethod
    def _magic_matches(cls, head: bytes, ext: str) -> bool:
        """
        So khớp chữ ký nhị phân của 512 bytes đầu với đuôi file.

        Args:
            head: Bytes đầu tiên của tệp (tối đa 512).
            ext:  Đuôi file (có dấu chấm, lowercase).

        Returns:
            True nếu nội dung khớp định dạng khai báo.
        """
        for signature, family_exts in cls.MAGIC_SIGNATURES:
            if ext in family_exts:
                return head.startswith(signature)
        return False  # Đuôi lạ → không chấp nhận

    # ==================================================================
    # CRUD qua Service
    # ==================================================================
    @classmethod
    def _assert_persistent_storage(cls) -> None:
        """
        FAIL LOUD khi production vẫn lưu upload vào đĩa TẠM (QA-Audit P2-3).

        Đĩa Render là ephemeral — file nhận về rồi sẽ MẤT khi restart/redeploy.
        Chặn rõ ràng ngay từ request upload (400 kèm hướng dẫn cấu hình) thay
        vì im lặng nhận file rồi mất.

        Bỏ chặn khi (2 cách, theo thứ tự ưu tiên):
            - `MEDIA_STORAGE_PERSISTENT=True` (đã cấu hình USE_S3=1 hoặc
              MEDIA_ROOT_PERSISTENT=1 — xem core/storage_resolver.py), hoặc
            - `ALLOW_EPHEMERAL_UPLOADS=1` — cờ chấp nhận rủi ro cho demo/pilot:
              chỉ log WARNING, upload vẫn nhận (mất khi restart là biết trước).
        """
        from django.conf import settings  # noqa: PLC0415

        if getattr(settings, "MEDIA_STORAGE_PERSISTENT", True):
            return  # S3/R2 hoặc đĩa bền vững — mọi thứ ổn
        if settings.DJANGO_ENV != "production":
            return  # dev cục bộ vẫn dùng đĩa cục bộ như thường lệ
        if getattr(settings, "ALLOW_EPHEMERAL_UPLOADS", False):
            logger.warning(
                "UPLOAD SẼ MẤT KHI RESTART: production đang lưu file vào đĩa "
                "tạm theo cờ ALLOW_EPHEMERAL_UPLOADS=1 — chỉ dùng cho demo/pilot."
            )
            return
        raise ValidationException(
            "Máy chủ chưa cấu hình nơi lưu trữ bền vững (S3/R2) — file upload "
            "sẽ mất khi restart nên tạm chặn. Quản trị viên cần đặt USE_S3=1 + "
            "các biến AWS_* (hoặc ALLOW_EPHEMERAL_UPLOADS=1 nếu chấp nhận rủi ro "
            "cho demo), xem README mục 'Lưu ý production'.",
            errors={"storage": "ephemeral_media_root_in_production"},
        )

    @classmethod
    def create_document(cls, user, uploaded_file, data: dict) -> Document:
        """
        Tạo tài liệu mới: validate 4 tầng → đặt tên UUID → lưu DB → thưởng XP.

        Args:
            user: Người chia sẻ (đã đăng nhập).
            uploaded_file: Tệp upload.
            data: dict gồm tieu_de, nhom, tags, mo_ta, pham_vi (đã qua serializer validate).

        Returns:
            Instance Document đã lưu.
        """
        # Chặn sớm lỗi cấu hình storage (trước cả validate file — đây là lỗi
        # hệ thống, không phải lỗi dữ liệu người dùng)
        cls._assert_persistent_storage()
        ext: str = cls.validate_file(uploaded_file)

        # Phạm vi truy cập (QA-Audit 2d): thành viên thường chỉ được chia sẻ
        # tài liệu công khai — yêu cầu BCN_ONLY từ MEMBER bị ép về PUBLIC_MEMBER.
        pham_vi = data.get("pham_vi") or Document.PhamVi.PUBLIC_MEMBER
        if pham_vi not in Document.PhamVi.values:
            pham_vi = Document.PhamVi.PUBLIC_MEMBER
        if pham_vi == Document.PhamVi.BCN_ONLY and not getattr(user, "is_bcn", False):
            pham_vi = Document.PhamVi.PUBLIC_MEMBER

        doc = Document(
            tieu_de=data.get("tieu_de", "").strip(),
            nhom=data.get("nhom", Document.Nhom.CHUYEN_MON),
            pham_vi=pham_vi,
            tags=(data.get("tags", "") or "").strip(),
            mo_ta=(data.get("mo_ta", "") or "").strip(),
            file=uploaded_file,
            uploaded_by=user,
        )

        # ---- Tầng 4: Randomize tên file bằng UUID (chống Path Traversal) ----
        uploaded_file.name = f"{uuid.uuid4().hex}{ext}"
        doc.file_size = uploaded_file.size
        doc.file_type = ext.lstrip(".")
        doc.save()

        logger.info(
            "Tài liệu mới #%s '%s' (%s, %s bytes) bởi %s",
            doc.pk, doc.tieu_de, ext, doc.file_size, getattr(user, "email", "?"),
        )
        cls._award_share_xp(user, doc)
        return doc

    @classmethod
    def _award_share_xp(cls, user, doc: Document) -> None:
        """
        Thưởng XP chia sẻ tài liệu (+100) — HỢP ĐỒNG CHÉO-APP với Agent B.

        - Lazy import bên trong hàm (gamification có thể chưa sẵn sàng).
        - Chỉ thành viên có MemberProfile mới được cộng XP.
        - Mọi lỗi XP KHÔNG được làm fail upload tài liệu.
        """
        try:
            from apps.gamification.services import GamificationService  # noqa: PLC0415
        except ImportError:
            logger.debug("GamificationService chưa khả dụng — bỏ qua thưởng XP.")
            return

        member = cls._repo().get_member_profile_by_user(user)
        if member is None:
            return  # Không có profile → không cộng XP, upload vẫn OK

        try:
            GamificationService.award_xp(
                member=member,
                amount=settings.CLB_SETTINGS["XP_DOCUMENT_SHARE"],
                reason=f"Chia sẻ tài liệu: {doc.tieu_de}",
                source="DOCUMENT_SHARE",
                idempotency_key=f"doc_{doc.pk}_share",
            )
        except Exception:  # noqa: BLE001 — XP fail không làm fail upload
            logger.warning("award_xp thất bại cho doc #%s — bỏ qua.", doc.pk, exc_info=True)

    @classmethod
    def delete_document(cls, doc: Document, actor) -> None:
        """
        Xóa tài liệu — chỉ BCN/ADMIN hoặc chính người upload.

        Xóa cả file vật lý trên storage để không rác đĩa.

        Raises:
            ForbiddenException: Nếu actor không có quyền.
        """
        is_board: bool = getattr(actor, "role", None) in ("ADMIN", "BCN") or getattr(actor, "is_superuser", False)
        if not (is_board or doc.uploaded_by_id == actor.pk):
            raise ForbiddenException(
                "Chỉ Ban Chủ Nhiệm hoặc người chia sẻ tài liệu mới được xóa tài liệu này."
            )
        doc_id = doc.pk
        try:
            doc.file.delete(save=False)
        except Exception:  # noqa: BLE001 — file có thể đã mất, vẫn xóa record
            logger.warning("Không xóa được file vật lý của doc #%s.", doc_id, exc_info=True)
        cls._repo().delete_document(doc)
        logger.info("Đã xóa tài liệu #%s bởi %s", doc_id, getattr(actor, "email", "?"))

    # ==================================================================
    # Phạm vi truy cập (QA-Audit 2d)
    # ==================================================================
    @classmethod
    def visible_documents(cls, user):
        """Queryset tài liệu theo phạm vi: MEMBER chỉ thấy PUBLIC_MEMBER (qua Repository)."""
        return cls._repo().visible_for(user)

    @classmethod
    def list_documents(
        cls,
        user,
        nhom: Optional[str] = None,
        search: str = "",
        sort: str = "-created_at",
    ):
        """
        Danh sách tài liệu cho GET /documents/ — scope pham_vi + select_related
        + filter nhom/search (icontains parameterized) + sort whitelist.

        Whitelist sort sống ở tầng Repository (nguồn sự thật duy nhất).
        """
        return cls._repo().list_documents(user, nhom=nhom, search=search, sort=sort)

    @classmethod
    def detail_queryset(cls):
        """Queryset cơ sở cho view chi tiết (select_related) — qua Repository."""
        return cls._repo().detail_queryset()

    @staticmethod
    def can_view(doc: Document, user) -> bool:
        """Quyền xem/tải một tài liệu cụ thể: BCN_ONLY chỉ dành cho BCN/ADMIN."""
        if doc.pham_vi == Document.PhamVi.BCN_ONLY:
            return getattr(user, "is_bcn", False)
        return True

    # ==================================================================
    # DSA 3 — Trie Prefix Search (O(L))
    # ==================================================================
    @classmethod
    def search(cls, q: str, limit: int = 20, user=None) -> List[Document]:
        """
        Tìm kiếm tức thời tiêu đề/tags qua Prefix Trie — O(L) mỗi truy vấn.

        Trie được index từ: tiêu đề (có/không dấu tự chuẩn hóa), từng từ của
        tiêu đề, và từng tag. Nhờ normalize (bỏ dấu + lower) tìm "de thi"
        khớp "Đề thi Web".

        Args:
            q: Từ khóa tìm kiếm (tiền tố).
            limit: Số kết quả tối đa.
            user: Người tìm (QA-Audit 2d) — MEMBER chỉ tìm được trong phạm vi
                PUBLIC_MEMBER, tài liệu BCN_ONLY không xuất hiện kể cả khi khớp.

        Returns:
            Danh sách Document (mới nhất trước). q rỗng → [].
        """
        q = (q or "").strip()
        if not q:
            return []

        from apps.documents.search_index import (  # noqa: PLC0415
            SCOPE_FULL,
            SCOPE_PUBLIC,
            get_trie,
        )

        # Trie cache theo process (QA-Audit nhóm 5): 2 vùng theo phạm vi —
        # MEMBER chỉ tra cứu trie PUBLIC (tài liệu BCN_ONLY không bao giờ vào
        # index → không lộ), BCN/ADMIN tra cứu trie FULL. Invalidation qua
        # signals post_save/post_delete trong apps.py, dựng lại lười.
        is_board = user is not None and getattr(user, "is_bcn", False)
        trie = get_trie(SCOPE_FULL if is_board else SCOPE_PUBLIC)

        matched_ids: Iterable[int] = trie.search_prefix(q)
        if not matched_ids:
            return []
        return cls._repo().get_by_ids_ordered(matched_ids, limit)

    # ==================================================================
    # Đếm lượt tải — atomic chống race condition
    # ==================================================================
    @classmethod
    def increment_download(cls, doc: Document) -> Document:
        """
        Tăng lượt tải +1 một cách atomic (F expression) rồi refresh instance.

        Returns:
            Document với luot_tai mới nhất.
        """
        cls._repo().increment_download(doc.pk)
        doc.refresh_from_db(fields=["luot_tai"])
        return doc

    @classmethod
    def get_or_404(cls, pk: int) -> Document:
        """Lấy Document theo pk hoặc raise NotFoundException (envelope 404)."""
        doc = cls._repo().get_by_id_select_related(pk)
        if doc is None:
            raise NotFoundException("Không tìm thấy tài liệu yêu cầu.")
        return doc

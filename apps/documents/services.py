"""
Service Layer — apps.documents
==============================
Toàn bộ nghiệp vụ Kho Tài liệu nằm tại đây (Clean Architecture — Rule 1/2):
    - DocumentService.validate_file:   File Upload Hardening 4 tầng (Security §7).
    - DocumentService.create_document: Lưu tài liệu + đổi tên UUID + thưởng XP.
    - DocumentService.search:          Tìm kiếm prefix O(L) qua DSA 3 (Prefix Trie).
    - DocumentService.increment_download: Đếm lượt tải atomic (F expression).
    - DocumentService.delete_document: Phân quyền xóa + dọn file vật lý.

KHÔNG viết logic trong views.py — view chỉ là controller mỏng.
"""
import logging
import os
import uuid
from typing import Iterable, List, Optional

from django.conf import settings
from django.db.models import F

from apps.common.exceptions import FileValidationException, ForbiddenException, NotFoundException
from apps.documents.models import Document

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

    @staticmethod
    def _award_share_xp(user, doc: Document) -> None:
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

        from apps.members.models import MemberProfile  # noqa: PLC0415

        member: Optional[MemberProfile] = MemberProfile.objects.filter(user=user).first()
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
        doc.delete()
        logger.info("Đã xóa tài liệu #%s bởi %s", doc_id, getattr(actor, "email", "?"))

    # ==================================================================
    # Phạm vi truy cập (QA-Audit 2d)
    # ==================================================================
    @staticmethod
    def visible_documents(user):
        """Queryset tài liệu theo phạm vi: MEMBER chỉ thấy PUBLIC_MEMBER."""
        qs = Document.objects.all()
        if not getattr(user, "is_bcn", False):
            qs = qs.filter(pham_vi=Document.PhamVi.PUBLIC_MEMBER)
        return qs

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

        from core.algorithms.trie_search import PrefixSearchTrie  # noqa: PLC0415

        # Chỉ index những tài liệu người tìm được phép thấy — không lộ ID
        queryset = Document.objects.all()
        if user is not None and not getattr(user, "is_bcn", False):
            queryset = queryset.filter(pham_vi=Document.PhamVi.PUBLIC_MEMBER)

        trie = PrefixSearchTrie()
        for doc in queryset.only("id", "tieu_de", "tags").iterator():
            aliases: List[str] = [doc.tieu_de, *doc.tieu_de.split()]
            aliases += [tag.strip() for tag in (doc.tags or "").split(",") if tag.strip()]
            trie.insert_multi(aliases, doc.pk)

        matched_ids: Iterable[int] = trie.search_prefix(q)
        if not matched_ids:
            return []
        return list(Document.objects.filter(id__in=matched_ids)[:limit])

    # ==================================================================
    # Đếm lượt tải — atomic chống race condition
    # ==================================================================
    @staticmethod
    def increment_download(doc: Document) -> Document:
        """
        Tăng lượt tải +1 một cách atomic (F expression) rồi refresh instance.

        Returns:
            Document với luot_tai mới nhất.
        """
        Document.objects.filter(pk=doc.pk).update(luot_tai=F("luot_tai") + 1)
        doc.refresh_from_db(fields=["luot_tai"])
        return doc

    @staticmethod
    def get_or_404(pk: int) -> Document:
        """Lấy Document theo pk hoặc raise NotFoundException (envelope 404)."""
        try:
            return Document.objects.select_related("uploaded_by__member_profile").get(pk=pk)
        except Document.DoesNotExist as exc:
            raise NotFoundException("Không tìm thấy tài liệu yêu cầu.") from exc

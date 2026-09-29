"""
Service Layer — apps.members
Toàn bộ nghiệp vụ thành viên: CRUD, Hồ sơ 360°, Trie search, Excel import/export.
"""
import io
from datetime import date, datetime
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from apps.common.exceptions import (
    DuplicateDataException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from apps.members.models import MemberProfile
from apps.members.repositories import DjangoMemberRepository, IMemberRepository

User = get_user_model()

# Whitelist các trường được phép sort (chống SQL injection qua order_by — Security §2.1)
ALLOWED_SORT_FIELDS = {
    "created_at", "-created_at",
    "xp_points", "-xp_points",
    "ho_ten", "-ho_ten",
}


class MemberService:
    """Nghiệp vụ quản lý thành viên — chỉ BCN/ADMIN mới thao tác ghi."""

    def __init__(self, repository: Optional[IMemberRepository] = None) -> None:
        self._repo: IMemberRepository = repository or DjangoMemberRepository()

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------
    @classmethod
    def create_member(cls, data: dict, actor: Any) -> MemberProfile:
        """
        Tạo User + MemberProfile mới.

        Args:
            data: {email, mssv, ho_ten, lop, sdt, gioi_tinh, ngay_sinh, password?}
            actor: User thực hiện (phải là BCN/ADMIN).

        Raises:
            ForbiddenException: actor không phải BCN.
            DuplicateDataException: email/mssv đã tồn tại.
        """
        if not actor.is_bcn:
            raise ForbiddenException("Chỉ Ban Chủ Nhiệm mới được thêm thành viên.")

        email: str = (data.get("email") or "").strip().lower()
        mssv: str = (data.get("mssv") or "").strip() or None

        if User.objects.filter(email=email).exists():
            raise DuplicateDataException(f"Email {email} đã được sử dụng.")
        if mssv and User.objects.filter(mssv=mssv).exists():
            raise DuplicateDataException(f"MSSV {mssv} đã tồn tại.")

        password: str = data.get("password") or "CLBIP@2026"

        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                password=password,
                mssv=mssv,
                role=User.Role.MEMBER,
            )
            profile = MemberProfile.objects.create(
                user=user,
                ho_ten=data.get("ho_ten") or email.split("@")[0],
                lop=data.get("lop") or "",
                sdt=data.get("sdt") or "",
                gioi_tinh=data.get("gioi_tinh") or "",
                ngay_sinh=cls._parse_date(data.get("ngay_sinh")),
            )
        return profile

    # ------------------------------------------------------------------
    # UPDATE / LOCK
    # ------------------------------------------------------------------
    @classmethod
    def update_member(cls, member_id: int, data: dict, actor: Any,
                      is_self_edit: bool = False) -> MemberProfile:
        """
        Cập nhật hồ sơ.

        Thành viên tự sửa: KHÔNG được đổi email/mssv/trạng thái (chỉ BCN).
        """
        profile = cls._get_or_404(member_id)
        user = profile.user

        with transaction.atomic():
            if not is_self_edit:  # BCN sửa toàn bộ
                if "mssv" in data and data["mssv"]:
                    new_mssv = data["mssv"].strip()
                    if User.objects.filter(mssv=new_mssv).exclude(pk=user.pk).exists():
                        raise DuplicateDataException(f"MSSV {new_mssv} đã tồn tại.")
                    user.mssv = new_mssv
                if "email" in data and data["email"]:
                    new_email = data["email"].strip().lower()
                    if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                        raise DuplicateDataException(f"Email {new_email} đã được sử dụng.")
                    user.email = new_email
                if "trang_thai_hd" in data and data["trang_thai_hd"]:
                    user.is_active = data["trang_thai_hd"] == MemberProfile.TrangThai.ACTIVE
                if "role" in data and data["role"]:
                    user.role = data["role"]
                user.save()

            for field in ("ho_ten", "lop", "sdt", "gioi_tinh", "avatar"):
                if field in data and data[field] is not None:
                    setattr(profile, field, data[field])
            if "ngay_sinh" in data:
                profile.ngay_sinh = cls._parse_date(data.get("ngay_sinh"))
            if "trang_thai_hd" in data and data["trang_thai_hd"]:
                profile.trang_thai_hd = data["trang_thai_hd"]
            profile.save()

        return profile

    @classmethod
    def lock_member(cls, member_id: int, actor: Any) -> MemberProfile:
        """'Xóa (Khóa)': vô hiệu hóa tài khoản (soft lock) — không xóa dữ liệu."""
        if not actor.is_bcn:
            raise ForbiddenException("Chỉ Ban Chủ Nhiệm mới được khóa thành viên.")
        profile = cls._get_or_404(member_id)
        profile.user.is_active = False
        profile.user.save(update_fields=["is_active"])
        profile.trang_thai_hd = MemberProfile.TrangThai.INACTIVE
        profile.save(update_fields=["trang_thai_hd"])
        return profile

    # ------------------------------------------------------------------
    # HỒ SƠ 360°
    # ------------------------------------------------------------------
    @classmethod
    def get_profile360(cls, member_id: int) -> dict:
        """
        Hồ sơ 360° tổng hợp — dùng select/prefetch chống N+1.

        Trả về: thông tin cá nhân, vai trò BCN, thống kê sự kiện/điểm danh,
        XP/Level/Streak, huy hiệu, 5 dòng XP ledger gần nhất.
        """
        profile = cls._get_or_404(member_id)
        user = profile.user

        registrations = profile.event_registrations.exclude(
            trang_thai="CANCELLED"
        ).select_related("event")

        records = profile.attendance_records.select_related("session")
        total_sessions = records.count()
        attended = records.filter(trang_thai__in=["CO_MAT", "DI_MUON"]).count()
        attendance_rate = round(attended / total_sessions * 100, 1) if total_sessions else None

        badges = profile.badges.select_related("badge")
        recent_xp = profile.xp_ledger.all()[:5]

        return {
            "id": profile.pk,
            "user_id": user.pk,
            "mssv": user.mssv,
            "email": user.email,
            "ho_ten": profile.ho_ten,
            "lop": profile.lop,
            "sdt": profile.sdt,
            "gioi_tinh": profile.gioi_tinh,
            "ngay_sinh": profile.ngay_sinh,
            "avatar": profile.avatar,
            "trang_thai_hd": profile.trang_thai_hd,
            "is_active": user.is_active,
            "board_positions": [
                {
                    "chuc_vu": b.chuc_vu,
                    "ban_phu_trach": b.ban_phu_trach,
                    "nhiem_ky": b.nhiem_ky,
                }
                for b in profile.board_positions.all()
            ],
            "stats": {
                "events_registered": registrations.count(),
                "attendance_sessions": total_sessions,
                "attendance_attended": attended,
                "attendance_rate_percent": attendance_rate,
                "xp_points": profile.xp_points,
                "current_level": profile.current_level,
                "streak_count": profile.streak_count,
            },
            "badges": [
                {"ten_badge": b.badge.ten_badge, "icon": b.badge.icon, "awarded_at": b.awarded_at}
                for b in badges
            ],
            "recent_xp": [
                {"reason": x.reason, "amount": x.amount, "created_at": x.created_at}
                for x in recent_xp
            ],
        }

    # ------------------------------------------------------------------
    # TRIE SEARCH (DSA 3)
    # ------------------------------------------------------------------
    @staticmethod
    def search_profiles(q: str, limit: int = 20, only_active: bool = False) -> list:
        """
        Tìm kiếm tức thời O(L) bằng PrefixSearchTrie.

        Index: MSSV + họ tên (tự động bỏ dấu). Trả tối đa `limit` profile,
        sắp theo XP giảm dần.

        Args:
            only_active: True → chỉ trả thành viên đang hoạt động (dùng cho
                thành viên thường, QA-Audit 2a — không lộ danh sách cán bộ ẩn).
        """
        q = (q or "").strip()
        if not q:
            return []

        from core.algorithms.trie_search import PrefixSearchTrie

        trie = PrefixSearchTrie()
        for profile in MemberProfile.objects.select_related("user").only(
            "id", "ho_ten", "user__mssv", "user__email", "lop", "sdt", "gioi_tinh",
            "avatar", "xp_points", "current_level", "streak_count", "trang_thai_hd",
        ):
            mssv = profile.user.mssv or ""
            words = {profile.ho_ten, mssv}
            trie.insert_multi([w for w in words if w], profile.pk)

        matched_ids = trie.search_prefix(q)
        if not matched_ids:
            return []

        profiles = (
            MemberProfile.objects.select_related("user")
            .filter(pk__in=matched_ids)
            .order_by("-xp_points")
        )
        if only_active:
            profiles = profiles.filter(
                trang_thai_hd=MemberProfile.TrangThai.ACTIVE
            )
        return list(profiles[:limit])

    # ------------------------------------------------------------------
    # EXCEL IMPORT / EXPORT
    # ------------------------------------------------------------------
    @classmethod
    def import_excel(cls, file: UploadedFile, actor: Any) -> dict:
        """
        Nhập danh sách thành viên từ file .xlsx.

        Header hàng 1: ho_ten | email | mssv | lop | sdt (cột bắt buộc: ho_ten, email, mssv).
        Dòng lỗi KHÔNG chặn các dòng hợp lệ khác — trả về preview lỗi cho BCN.
        """
        if not actor.is_bcn:
            raise ForbiddenException("Chỉ Ban Chủ Nhiệm mới được nhập Excel.")
        try:
            workbook = load_workbook(filename=io.BytesIO(file.read()), data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ValidationException("Không đọc được file Excel. Vui lòng kiểm tra định dạng .xlsx") from exc

        sheet = workbook.active
        created_count = 0
        errors: list = []
        seen_emails: set = set()
        seen_mssvs: set = set()

        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        for idx, row in enumerate(rows, start=2):
            if row is None or all(cell is None for cell in row):
                continue
            ho_ten = (row[0] or "").strip() if len(row) > 0 else ""
            email = (row[1] or "").strip().lower() if len(row) > 1 else ""
            mssv = (row[2] or "").strip() if len(row) > 2 else ""
            lop = (row[3] or "").strip() if len(row) > 3 else ""
            sdt = (row[4] or "").strip() if len(row) > 4 else ""

            row_error = None
            if not ho_ten or not email or not mssv:
                row_error = "Thiếu cột bắt buộc (ho_ten / email / mssv)"
            elif email in seen_emails:
                row_error = f"Email {email} bị lặp trong file"
            elif mssv in seen_mssvs:
                row_error = f"MSSV {mssv} bị lặp trong file"
            elif User.objects.filter(email=email).exists():
                row_error = f"Email {email} đã tồn tại trong hệ thống"
            elif User.objects.filter(mssv=mssv).exists():
                row_error = f"MSSV {mssv} đã tồn tại trong hệ thống"

            if row_error:
                errors.append({"row": idx, "ho_ten": str(ho_ten), "error": row_error})
                continue

            try:
                cls.create_member(
                    {
                        "ho_ten": ho_ten,
                        "email": email,
                        "mssv": mssv,
                        "lop": lop,
                        "sdt": sdt,
                        "password": "CLBIP@2026",
                    },
                    actor,
                )
                seen_emails.add(email)
                seen_mssvs.add(mssv)
                created_count += 1
            except Exception as exc:  # noqa: BLE001 — ghi nhận lỗi từng dòng
                errors.append({"row": idx, "ho_ten": str(ho_ten), "error": str(exc)})

        return {"created": created_count, "errors": errors}

    @classmethod
    def export_excel(cls) -> bytes:
        """Xuất danh sách thành viên ra file .xlsx (kèm styled header)."""
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Thành viên"

        headers = ["MSSV", "Họ tên", "Email", "Lớp", "SĐT", "Giới tính", "XP", "Level", "Streak", "Trạng thái"]
        header_fill = PatternFill(start_color="6366F1", end_color="6366F1", fill_type="solid")
        for col, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        status_labels = dict(MemberProfile.TrangThai.choices)
        for row_idx, profile in enumerate(
            MemberProfile.objects.select_related("user").order_by("ho_ten"), start=2
        ):
            sheet.cell(row=row_idx, column=1, value=profile.user.mssv or "")
            sheet.cell(row=row_idx, column=2, value=profile.ho_ten)
            sheet.cell(row=row_idx, column=3, value=profile.user.email)
            sheet.cell(row=row_idx, column=4, value=profile.lop)
            sheet.cell(row=row_idx, column=5, value=profile.sdt)
            sheet.cell(row=row_idx, column=6, value=profile.gioi_tinh)
            sheet.cell(row=row_idx, column=7, value=profile.xp_points)
            sheet.cell(row=row_idx, column=8, value=profile.current_level)
            sheet.cell(row=row_idx, column=9, value=profile.streak_count)
            sheet.cell(row=row_idx, column=10, value=status_labels.get(profile.trang_thai_hd, profile.trang_thai_hd))

        for col, width in enumerate([14, 24, 28, 12, 14, 10, 10, 8, 8, 16], start=1):
            sheet.column_dimensions[sheet.cell(row=1, column=col).column_letter].width = width

        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Danh sách + whitelist sort (chống SQLi)
    # ------------------------------------------------------------------
    @staticmethod
    def list_profiles(lop: Optional[str] = None, trang_thai: Optional[str] = None,
                      search: Optional[str] = None, sort: Optional[str] = None):
        """Queryset danh sách thành viên với filter/sort an toàn."""
        repo = DjangoMemberRepository()
        queryset = repo.get_all()

        if lop:
            queryset = queryset.filter(lop=lop)
        if trang_thai:
            queryset = queryset.filter(trang_thai_hd=trang_thai)
        if search:
            queryset = queryset.filter(_build_search_q(search))

        sort_param = sort if sort in ALLOWED_SORT_FIELDS else "-xp_points"
        return queryset.order_by(sort_param)

    # ------------------------------------------------------------------
    # Nội bộ
    # ------------------------------------------------------------------
    @staticmethod
    def _get_or_404(member_id: int) -> MemberProfile:
        profile = MemberProfile.objects.select_related("user").filter(pk=member_id).first()
        if profile is None:
            raise NotFoundException("Không tìm thấy thành viên.")
        return profile

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        """Parse ngày sinh từ ISO string / date — bỏ qua giá trị rỗng."""
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _build_search_q(search: str):
    """Q object tìm kiếm họ tên / MSSV (ORM parameterized — an toàn SQLi)."""
    from django.db.models import Q

    return Q(ho_ten__icontains=search) | Q(user__mssv__icontains=search) | Q(user__email__icontains=search)

"""
Service Layer — apps.members
Toàn bộ nghiệp vụ thành viên: CRUD, Hồ sơ 360°, Trie search, Excel import/export.

Repository Pattern (DIP): mọi truy vấn CSDL được ủy quyền cho `IMemberRepository`
(mặc định `DjangoMemberRepository`) — service KHÔNG gọi `*.objects` trực tiếp.
"""
import io
from datetime import date, datetime
from typing import Any, ClassVar, Optional

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
from django.utils.crypto import get_random_string
from apps.members.repositories import (
    DjangoMemberRepository,
    IMemberRepository,
)


class MemberService:
    """
    Nghiệp vụ quản lý thành viên — chỉ BCN/ADMIN mới thao tác ghi.

    DI theo mẫu funds: `_repository_class` là ClassVar, `_repo()` là factory
    method — unit test có thể thay repository giả bằng cách ghi đè class var.
    """

    _repository_class: ClassVar[type[IMemberRepository]] = DjangoMemberRepository

    @classmethod
    def _repo(cls) -> IMemberRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

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

        if cls._repo().exists_user_by_email(email):
            raise DuplicateDataException(f"Email {email} đã được sử dụng.")
        if mssv and cls._repo().exists_user_by_mssv(mssv):
            raise DuplicateDataException(f"MSSV {mssv} đã tồn tại.")

        # QA-Audit P0/DoD: không dùng mật khẩu mặc định công khai — BCN truyền
        # mật khẩu rõ, hoặc hệ thống sinh ngẫu nhiên (view sẽ hiển thị 1 lần)
        password: str = data.get("password") or get_random_string(14)

        return cls._repo().create_user_with_profile(
            email=email,
            password=password,
            mssv=mssv,
            ho_ten=data.get("ho_ten") or email.split("@")[0],
            lop=data.get("lop") or "",
            sdt=data.get("sdt") or "",
            gioi_tinh=data.get("gioi_tinh") or "",
            ngay_sinh=cls._parse_date(data.get("ngay_sinh")),
        )

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
        repo = cls._repo()

        with transaction.atomic():
            if not is_self_edit:  # BCN sửa toàn bộ
                if "mssv" in data and data["mssv"]:
                    new_mssv = data["mssv"].strip()
                    if repo.exists_user_by_mssv(new_mssv, exclude_pk=user.pk):
                        raise DuplicateDataException(f"MSSV {new_mssv} đã tồn tại.")
                    user.mssv = new_mssv
                if "email" in data and data["email"]:
                    new_email = data["email"].strip().lower()
                    if repo.exists_user_by_email(new_email, exclude_pk=user.pk):
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
        repo = cls._repo()

        total_sessions = repo.count_profile_attendance(profile)
        attended = repo.count_profile_attendance(
            profile, trang_thai_in=["CO_MAT", "DI_MUON"]
        )
        attendance_rate = round(attended / total_sessions * 100, 1) if total_sessions else None

        badges = repo.get_profile_badges(profile)
        recent_xp = repo.get_recent_xp_entries(profile, limit=5)

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
                for b in repo.get_profile_board_positions(profile)
            ],
            "stats": {
                "events_registered": repo.count_profile_registrations(profile),
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
    @classmethod
    def search_profiles(cls, q: str, limit: int = 20, only_active: bool = False) -> list:
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

        from apps.members.search_index import get_trie  # noqa: PLC0415

        # Trie cache theo process (QA-Audit nhóm 5) — tra cứu O(L), tự dựng lại
        # lười khi có tín hiệu post_save/post_delete (signals trong apps.py).
        # Ngưỡng "1 ký tự" như cũ: tiền tố rỗng trả toàn bộ ID (hành vi cũ).
        trie = get_trie()
        matched_ids = trie.search_prefix(q)
        if not matched_ids:
            return []

        repo = cls._repo()
        return list(
            repo.get_by_ids_ordered_by_xp(matched_ids, only_active=only_active)[:limit]
        )

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
        generated_passwords: list = []  # (QA-Audit P0) BCN cần mật khẩu để gửi cho thành viên
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
            elif cls._repo().exists_user_by_email(email):
                row_error = f"Email {email} đã tồn tại trong hệ thống"
            elif cls._repo().exists_user_by_mssv(mssv):
                row_error = f"MSSV {mssv} đã tồn tại trong hệ thống"

            if row_error:
                errors.append({"row": idx, "ho_ten": str(ho_ten), "error": row_error})
                continue

            try:
                row_password = get_random_string(14)
                cls.create_member(
                    {
                        "ho_ten": ho_ten,
                        "email": email,
                        "mssv": mssv,
                        "lop": lop,
                        "sdt": sdt,
                        "password": row_password,
                    },
                    actor,
                )
                generated_passwords.append(
                    {"email": email, "mssv": mssv, "password": row_password}
                )
                seen_emails.add(email)
                seen_mssvs.add(mssv)
                created_count += 1
            except Exception as exc:  # noqa: BLE001 — ghi nhận lỗi từng dòng
                errors.append({"row": idx, "ho_ten": str(ho_ten), "error": str(exc)})

        return {
            "created": created_count,
            "errors": errors,
            # Mật khẩu khởi tạo ngẫu nhiên — hiển thị cho BCN đúng một lần
            "passwords": generated_passwords,
        }

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
            cls._repo().get_all_ordered_by_name(), start=2
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
    @classmethod
    def list_profiles(cls, lop: Optional[str] = None, trang_thai: Optional[str] = None,
                      search: Optional[str] = None, sort: Optional[str] = None):
        """Queryset danh sách thành viên với filter/sort an toàn (ủy quyền Repository)."""
        return cls._repo().filter_profiles(
            lop=lop, trang_thai=trang_thai, q=search, sort=sort
        )

    # ------------------------------------------------------------------
    # Nội bộ
    # ------------------------------------------------------------------
    @classmethod
    def _get_or_404(cls, member_id: int) -> MemberProfile:
        profile = cls._repo().get_by_id(member_id)
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

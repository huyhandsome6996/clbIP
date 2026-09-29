"""
Management Command: seed_demo
==============================
Tạo dữ liệu demo idempotent (chạy lại không nhân đôi) cho môi trường thử nghiệm:
- 1 tài khoản ADMIN + 5 BCN (Ban chủ nhiệm đầy đủ chức vụ)
- 14 thành viên sinh viên
- Giao dịch quỹ (thu/chi) có số dư lũ kế đúng bất biến
- 2 sự kiện (1 đang mở đăng ký) + tasks DAG + dự trù kinh phí
- 1 phiên điểm danh đang mở
- Bài đăng bảng tin + poll + badge

Chạy: python manage.py seed_demo
"""
import os
import random
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.authentication.models import User
from apps.members.models import BoardMember, MemberProfile

# Không hardcode mật khẩu demo công khai: mật khẩu lấy từ tham số --password
# hoặc biến môi trường DEMO_PASSWORD; nếu thiếu sẽ sinh ngẫu nhiên và in 1 lần.
DEFAULT_PASSWORD = None

BCN_DATA = [
    ("bcn@clbip.vn", "Lê Văn Chủ Nhiệm", "22A401001", "CHU_NHIEM", "HOC_THUAT"),
    ("phocn@clbip.vn", "Trần Thị Phó CN", "22A401002", "PHO_CHU_NHIEM", "SU_KIEN"),
    ("truongban@clbip.vn", "Phạm Văn Trưởng Ban", "22A401003", "TRUONG_BAN", "TAI_CHINH"),
    ("hosu@clbip.vn", "Nguyễn Văn Giảng Viên", None, "PHO_BAN", "TRUYEN_THONG"),
]

MEMBER_NAMES = [
    ("Nguyễn Nhật Nam", "22A401101", "22A401", "NAM"),
    ("Hoàng Bảo Trân", "22A401102", "22A401", "NU"),
    ("Trần Công Danh", "22A401103", "22A401", "NAM"),
    ("Lê Thị Kiều Anh", "22A402101", "22A402", "NU"),
    ("Phạm Đăng Khoa", "22A402102", "22A402", "NAM"),
    ("Ngô Mai Linh", "22A402103", "22A402", "NU"),
    ("Đỗ Trọng Nhân", "22A403101", "22A403", "NAM"),
    ("Bùi Thu Hằng", "22A403102", "22A403", "NU"),
    ("Vũ Minh Quân", "22A403103", "22A403", "NAM"),
    ("Dương Ngọc Diệp", "22A404101", "22A404", "NU"),
    ("Lý Thanh Phong", "22A404102", "22A404", "NAM"),
    ("Trương Ánh Dương", "22A404103", "22A404", "NAM"),
    ("Cao Diễm My", "22A405101", "22A405", "NU"),
    ("Hồ Quang Huy", "22A405102", "22A405", "NAM"),
]


class Command(BaseCommand):
    help = (
        "Tạo dữ liệu demo cho hệ thống CLB IP (idempotent). "
        "BỊ CHẶN khi DJANGO_ENV=production."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--password", type=str, default=None,
            help=(
                "Mật khẩu cho các tài khoản demo. Mặc định lấy từ biến môi "
                "trường DEMO_PASSWORD; nếu thiếu sẽ sinh mật khẩu ngẫu nhiên."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # -------------------------------------------------------------
        # Chốt an toàn P0: không bao giờ tạo tài khoản demo trên production.
        # Tài khoản demo dùng mật khẩu công khai → nếu lọt vào DB thật sẽ
        # trở thành cửa hậu cho mọi người (chống lặp lại sự cố QA-Audit P0).
        # -------------------------------------------------------------
        if getattr(settings, "DJANGO_ENV", "development") == "production":
            raise CommandError(
                "seed_demo BỊ CHẶN trên production (DJANGO_ENV=production). "
                "Hệ thống thật phải tạo tài khoản qua admin/sổ tay nội bộ, "
                "không dùng dữ liệu demo."
            )

        password: str = (
            options.get("password")
            or os.environ.get("DEMO_PASSWORD", "")
            or secrets.token_urlsafe(12)
        )
        generated = options.get("password") is None and not os.environ.get("DEMO_PASSWORD")

        self.stdout.write(self.style.MIGRATE_HEADING("=== SEED DEMO DATA — CLB IP ĐHSP Huế 2.0 ==="))
        if generated:
            self.stdout.write(self.style.WARNING(
                "⚠ Không có --password hay DEMO_PASSWORD — đã sinh mật khẩu ngẫu nhiên "
                "(chỉ hiển thị một lần bên dưới)."
            ))

        # ---------------------------------------------------------------
        # 1. ADMIN + BCN
        # ---------------------------------------------------------------
        admin = self._ensure_user(
            email="admin@clbip.vn", password=password, role="ADMIN",
            mssv=None, ho_ten="Quản Trị Hệ Thống",
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.save(update_fields=["is_staff", "is_superuser"])

        bcn_profiles = []
        for email, ho_ten, mssv, chuc_vu, ban in BCN_DATA:
            user = self._ensure_user(email, password, "BCN", mssv, ho_ten)
            profile = self._ensure_profile(user, ho_ten, lop="CB-CLB" if mssv is None else "22A401")
            BoardMember.objects.get_or_create(
                member=profile,
                nhiem_ky="2025-2026",
                defaults={"chuc_vu": chuc_vu, "ban_phu_trach": ban},
            )
            bcn_profiles.append(profile)
        self.stdout.write(self.style.SUCCESS(f"✓ ADMIN + {len(BCN_DATA)} BCN"))

        # ---------------------------------------------------------------
        # 2. Thành viên
        # ---------------------------------------------------------------
        member_profiles = []
        xp_pool = [320, 180, 95, 60, 40, 25, 15, 0, 0, 0, 0, 0, 0, 0]
        for (ho_ten, mssv, lop, gioi_tinh), xp in zip(MEMBER_NAMES, xp_pool):
            email = f"{mssv.lower()}@student.hueuni.edu.vn"
            user = self._ensure_user(email, password, "MEMBER", mssv, ho_ten)
            profile = self._ensure_profile(user, ho_ten, lop, gioi_tinh)
            if xp and profile.xp_points == 0:
                profile.xp_points = xp
                profile.current_level = self._level_from_xp(xp)
                profile.streak_count = random.randint(0, 6)
                profile.save(update_fields=["xp_points", "current_level", "streak_count"])
            member_profiles.append(profile)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(member_profiles)} thành viên"))

        # ---------------------------------------------------------------
        # 3. Quỹ (nếu chưa có giao dịch nào)
        # ---------------------------------------------------------------
        from apps.funds.models import FundTransaction
        from apps.funds.services import FundService

        if FundTransaction.objects.count() == 0:
            treasurer = bcn_profiles[2]
            FundService.execute_transaction(
                loai_gd="THU", so_tien=2_500_000,
                nguoi_thuc_hien="Quỹ CLB - Hội phí kỳ 1",
                hinh_thuc="CHUYEN_KHOAN",
                ghi_chu="Hội phí thành viên kỳ 2025-2026 (25 x 100k)",
                created_by=treasurer.user,
            )
            FundService.execute_transaction(
                loai_gd="THU", so_tien=1_000_000,
                nguoi_thuc_hien="Nhà tài trợ Công ty ABC",
                hinh_thuc="CHUYEN_KHOAN",
                ghi_chu="Tài trợ hackathon mùa 3",
                created_by=treasurer.user,
            )
            FundService.execute_transaction(
                loai_gd="CHI", so_tien=750_000,
                nguoi_thuc_hien="Trưởng ban Tài chính",
                hinh_thuc="TIEN_MAT",
                ghi_chu="Mua nước + bánh cho sinh hoạt định kỳ tháng 9",
                created_by=treasurer.user,
            )
            self.stdout.write(self.style.SUCCESS("✓ Sổ quỹ demo: 2 THU + 1 CHI (số dư 2.750.000₫)"))

        # ---------------------------------------------------------------
        # 4. Sự kiện + tasks DAG + dự trù kinh phí
        # ---------------------------------------------------------------
        from apps.events.models import (
            ActivityEvent,
            EventBudgetDetail,
            EventCommunication,
            EventTask,
        )

        now = timezone.now()
        ev1, created1 = ActivityEvent.objects.get_or_create(
            ma_hd="EV2026001",
            defaults={
                "ten_hoat_dong": "TechTalk: AI & Cloud Computing",
                "mo_ta": "Buổi chia sẻ chuyên đề về AI, LLM và Cloud computing cùng các khách mời từ doanh nghiệp.",
                "loai_hd": "WORKSHOP",
                "thoi_gian_bat_dau": now + timedelta(days=3, hours=2),
                "thoi_gian_ket_thuc": now + timedelta(days=3, hours=5),
                "dia_diem": "Hội trường A - ĐHSP Huế",
                "vi_do": 16.4637,
                "kinh_do": 107.5909,
                "ban_kinh_m": 50,
                "tong_kinh_phi_du_tru": 1_200_000,
                "so_luong_toi_da": 60,
                "trang_thai": ActivityEvent.TrangThai.OPEN_REGISTRATION,
                "created_by": admin,
            },
        )
        if created1:
            EventBudgetDetail.objects.create(event=ev1, ten_hang_muc="Trà + bánh cho khán giả", so_tien=500_000)
            EventBudgetDetail.objects.create(event=ev1, ten_hang_muc="Quà tặng diễn giả", so_tien=500_000)
            EventBudgetDetail.objects.create(event=ev1, ten_hang_muc="In ấn poster, backdrop", so_tien=200_000)
            t1 = EventTask.objects.create(event=ev1, ten_task="Đặt hội trường A", nguoi_phu_trach=bcn_profiles[1], deadline=now + timedelta(days=1))
            t2 = EventTask.objects.create(event=ev1, ten_task="Thiết kế poster truyền thông", nguoi_phu_trach=bcn_profiles[3], deadline=now + timedelta(days=1))
            EventTask.objects.create(event=ev1, ten_task="Đăng bài fanpage + TikTok", nguoi_phu_trach=bcn_profiles[3], deadline=now + timedelta(days=2))
            t4 = EventTask.objects.create(event=ev1, ten_task="Setup âm thanh máy chiếu", nguoi_phu_trach=member_profiles[0])
            t4.depends_on.set([t1])
            EventCommunication.objects.create(event=ev1, kenh="FACEBOOK", tieu_de="TechTalk AI & Cloud — Mời tham gia!", deadline=now + timedelta(days=2))
        ev2, _ = ActivityEvent.objects.get_or_create(
            ma_hd="EV2026002",
            defaults={
                "ten_hoat_dong": "Hackathon CLB IP Mùa 3",
                "mo_ta": "48 giờ code cày cuốc giải quyết bài toán thực địa. Giải nhất 2.000.000₫.",
                "loai_hd": "HACKATHON",
                "thoi_gian_bat_dau": now + timedelta(days=21),
                "thoi_gian_ket_thuc": now + timedelta(days=23),
                "dia_diem": "Phòng lab 3 - Trường ĐHSP Huế",
                "vi_do": 16.4630,
                "kinh_do": 107.5915,
                "ban_kinh_m": 80,
                "tong_kinh_phi_du_tru": 5_000_000,
                "so_luong_toi_da": 40,
                "trang_thai": ActivityEvent.TrangThai.PLANNING,
                "created_by": admin,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"✓ 2 sự kiện (EV2026001 mở đăng ký, EV2026002 lên kế hoạch)"))

        # Đăng ký vé demo cho 3 thành viên
        from apps.events.services import EventService

        for profile in member_profiles[:3]:
            try:
                EventService.register_member(ev1.pk, profile)
            except Exception:  # noqa: BLE001 — đã đăng ký rồi thì bỏ qua
                pass
        self.stdout.write(self.style.SUCCESS("✓ 3 vé demo đã đăng ký TechTalk"))

        # ---------------------------------------------------------------
        # 5. Phiên điểm danh đang mở
        # ---------------------------------------------------------------
        from apps.attendance.services import AttendanceService

        from apps.attendance.models import AttendanceSession

        if not AttendanceSession.objects.filter(trang_thai="OPEN").exists():
            AttendanceService.open_session(
                ten_phien="Sinh hoạt định kỳ tháng 9/2026",
                vi_do=16.4637,
                kinh_do=107.5909,
                ban_kinh_m=50,
                event_id=ev2.pk,
            )
        self.stdout.write(self.style.SUCCESS("✓ 1 phiên điểm danh đang MỞ (tọa độ ĐHSP Huế, bán kính 50m)"))

        # ---------------------------------------------------------------
        # 6. Bảng tin + Poll
        # ---------------------------------------------------------------
        from apps.posts.models import CommunityPoll, Post

        if Post.objects.count() == 0:
            Post.objects.create(
                tieu_de="📢 Thông báo: Sinh hoạt định kỳ tháng 9",
                noi_dung=(
                    "<p>Sinh hoạt định kỳ của CLB IP diễn ra vào <strong>19h00 Chủ nhật tuần này</strong> "
                    "tại phòng 201. Năm nay chúng ta có các chuyên đề cực chất: AI, Web, Cybersecurity.</p>"
                    "<p>Thành viên nhớ <strong>điểm danh GPS đúng giờ</strong> để tăng chuỗi 🔥 và nhận XP nhé!</p>"
                ),
                is_pinned=True,
                created_by=bcn_profiles[0].user,
            )
            Post.objects.create(
                tieu_de="🏆 Kết quả cuộc thi Code Duel tháng 8",
                noi_dung="<p>Chúc mừng 3 bạn đạt giải cuộc thi Code Duel tháng 8! Giải thưởng đã được trao qua quỹ CLB.</p>",
                created_by=bcn_profiles[1].user,
            )
            CommunityPoll.objects.get_or_create(
                question="Bạn muốn chuyên đề nào cho tháng tới?",
                defaults={
                    "options": ["Deep Learning thực chiến", "Backend Django avanzado", "DevOps & Docker", "UI/UX Design"],
                    "votes": {"0": 5, "1": 3, "2": 2, "3": 1},
                    "created_by": admin,
                },
            )
        self.stdout.write(self.style.SUCCESS("✓ 2 bài bảng tin + 1 poll"))

        # ---------------------------------------------------------------
        # 7. Badge mặc định
        # ---------------------------------------------------------------
        from apps.gamification.models import Badge

        for ma, ten, mo_ta, icon in [
            ("STREAK_7", "Chuyên Cần 🔥", "Điểm danh liên tục 7 ngày", "🔥"),
            ("ATTENDANCE_10", "Điểm danh x10", "Có mặt 10 buổi sinh hoạt", "🎯"),
            ("DOC_CONTRIBUTOR_3", "Người Chia Sẻ", "Chia sẻ 3 tài liệu cho CLB", "📚"),
            ("LEVEL_5", "Dev Khá Bảnh", "Đạt cấp độ 5 trong hệ thống XP", "⭐"),
            ("CODE_NINJA", "Code Ninja", "Đặc biệt — do BCN trao tặng", "🥷"),
        ]:
            Badge.objects.get_or_create(
                ma_badge=ma,
                defaults={"ten_badge": ten, "mo_ta": mo_ta, "icon": icon},
            )
        self.stdout.write(self.style.SUCCESS("✓ 5 huy hiệu mặc định"))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== HOÀN TẤT — Tài khoản demo ==="))
        self.stdout.write(f"  ADMIN : admin@clbip.vn / {password}")
        self.stdout.write(f"  BCN   : bcn@clbip.vn / {password}")
        self.stdout.write(f"  MEMBER: 22a401101@student.hueuni.edu.vn / {password}")
        self.stdout.write(f"  (Tất cả mật khẩu demo: {password})")
        self.stdout.write("  Swagger UI: /api/docs/  |  Health: /api/health/")

    # ------------------------------------------------------------------
    def _ensure_user(self, email: str, password: str, role: str, mssv, ho_ten: str) -> User:
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email, password=password, role=role, mssv=mssv
            )
        return user

    def _ensure_profile(self, user: User, ho_ten: str, lop: str = "", gioi_tinh: str = "") -> MemberProfile:
        profile, _ = MemberProfile.objects.get_or_create(
            user=user, defaults={"ho_ten": ho_ten, "lop": lop, "gioi_tinh": gioi_tinh}
        )
        return profile

    @staticmethod
    def _level_from_xp(xp: int) -> int:
        thresholds = [0, 100, 250, 500, 900, 1400, 2000, 2800, 3800, 5000]
        level = 1
        for i, t in enumerate(thresholds, start=1):
            if xp >= t:
                level = i
        return level

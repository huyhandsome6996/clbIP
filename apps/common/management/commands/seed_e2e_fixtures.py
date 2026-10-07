"""
Seed fixtures cho E2E — quy mô lớn để kiểm chứng phân trang/selector (review R04 §6)
=====================================================================================
Chạy:  python manage.py seed_e2e_fixtures --password 'E2eTest@2026'

Tạo dữ liệu có NHẬN DẠNG RIÊNG (prefix `e2e-` / mã `E2E...`) — KHÔNG đụng
dữ liệu demo/cũ:
  - 130 thành viên (e2e-memberNNN@clbip.test) — người #121 phải chọn được
    qua picker/override (page_size 20 → cần tổng > 120, count lấy total
    authoritative từ backend).
  - 25 sự kiện E2E + ≥121 đăng ký cho sự kiện E2E-01 (vé #25 xem được).
  - 2 phiên OPEN + 2 phiên CLOSED (F10: chọn phiên OPEN bất kỳ).
  - 1 poll E2E + options (F12 has_voted), budget hạng mục (P1-c), vài giao
    dịch quỹ E2E, 1 tài liệu E2E (F05 preview).
Chỉ chạy khi KHÔNG phải production (cùng rào chắn với seed_demo).
"""
import random

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.authentication.models import User
from django.conf import settings


class Command(BaseCommand):
    help = "Seed dữ liệu quy mô lớn cho E2E (prefix e2e-/E2E) — cấm chạy production."

    def add_arguments(self, parser):
        parser.add_argument("--members", type=int, default=130)
        parser.add_argument("--events", type=int, default=25)
        parser.add_argument("--registrations", type=int, default=121)
        parser.add_argument("--password", type=str, default="E2eTest@2026")

    def handle(self, *args, **opts):
        if getattr(settings, "DJANGO_ENV", "") == "production" or settings.DEBUG is False and settings.ALLOWED_HOSTS and "*" not in settings.ALLOWED_HOSTS:
            raise CommandError("seed_e2e_fixtures chỉ chạy local/staging — production bị chặn.")

        random.seed(42)  # dữ liệu lặp lại được giữa các lần chạy
        pw = opts["password"]
        now = timezone.now()

        # ---------------- Members ----------------
        created_members = 0
        for i in range(1, opts["members"] + 1):
            email = f"e2e-member{i:03d}@clbip.test"
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"username": email, "role": "MEMBER"},
            )
            if created:
                user.set_password(pw)
                user.save()
                created_members += 1
            from apps.members.models import MemberProfile

            MemberProfile.objects.get_or_create(
                user=User.objects.get(email=email),
                defaults={"ho_ten": f"E2E Thành Viên {i:03d}"},
            )
        self.stdout.write(f"[members] tổng {opts['members']} (mới tạo {created_members})")

        # ---------------- BCN E2E ----------------
        bcn, created = User.objects.get_or_create(
            email="e2e-bcn@clbip.test",
            defaults={"username": "e2e-bcn@clbip.test", "role": "BCN"},
        )
        if created:
            bcn.set_password(pw)
            bcn.save()
        self.stdout.write("[bcn] e2e-bcn@clbip.test sẵn sàng")

        # ---------------- Events ----------------
        from apps.events.models import ActivityEvent, EventRegistration

        created_events = 0
        for i in range(1, opts["events"] + 1):
            _, created = ActivityEvent.objects.get_or_create(
                ma_hd=f"E2EEV{i:03d}",
                defaults=dict(
                    ten_hoat_dong=f"E2E Sự kiện kiểm thử {i:03d}",
                    loai_hd="WORKSHOP",
                    thoi_gian_bat_dau=now + timezone.timedelta(days=i),
                    thoi_gian_ket_thuc=now + timezone.timedelta(days=i, hours=3),
                    dia_diem="Huế",
                    trang_thai="OPEN_REGISTRATION",
                    so_luong_toi_da=1000,
                ),
            )
            created_events += created
        self.stdout.write(f"[events] tổng {opts['events']} (mới tạo {created_events})")

        # ---------------- Registrations cho E2EEV001 ----------------
        main_event = ActivityEvent.objects.get(ma_hd="E2EEV001")
        reg_created = 0
        for i in range(1, opts["registrations"] + 1):
            member_user = User.objects.get(email=f"e2e-member{i:03d}@clbip.test")
            from apps.members.models import MemberProfile

            profile = MemberProfile.objects.get(user=member_user)
            _, created = EventRegistration.objects.get_or_create(
                event=main_event, member=profile,
                defaults={"trang_thai": "REGISTERED", "ma_ve": f"E2EVE{i:05d}"},
            )
            reg_created += created
        self.stdout.write(f"[registrations] {opts['registrations']} vé cho E2EEV001 (mới {reg_created})")

        # ---------------- Sessions OPEN/CLOSED ----------------
        from apps.attendance.models import AttendanceSession
        from apps.attendance.services import AttendanceService

        open_sessions = AttendanceSession.objects.filter(ten_phien__startswith="E2E OPEN", trang_thai="OPEN").count()
        if open_sessions < 2:
            for j in (1, 2):
                AttendanceService.open_session(
                    ten_phien=f"E2E OPEN {j}",
                    vi_do=16.4637, kinh_do=107.5909, ban_kinh_m=50,
                )
        closed_count = AttendanceSession.objects.filter(ten_phien__startswith="E2E CLOSED").count()
        if closed_count < 2:
            for j in (1, 2):
                s = AttendanceService.open_session(
                    ten_phien=f"E2E CLOSED {j}",
                    vi_do=16.4637, kinh_do=107.5909, ban_kinh_m=50,
                )
                AttendanceService.close_session(s)
        self.stdout.write("[sessions] ≥2 OPEN + ≥2 CLOSED E2E")

        # ---------------- Poll (F12 — has_voted) ----------------
        from apps.posts.models import CommunityPoll

        poll, _ = CommunityPoll.objects.get_or_create(
            question="E2E: Bình chọn kiểm thử has_voted?",
            defaults={
                "options": ["Phương án A", "Phương án B"],
                "votes": {},
                "voted_user_ids": [],
                "is_closed": False,
            },
        )
        self.stdout.write("[poll] E2E poll sẵn sàng")

        # ---------------- Quỹ E2E ----------------
        from apps.funds.models import FundTransaction

        if not FundTransaction.objects.filter(nguoi_thuc_hien="E2E Quỹ").exists():
            FundTransaction.objects.create(
                ma_phieu="E2EPT001", loai_gd="THU", so_tien=500_000, so_du_sau=500_000,
                nguoi_thuc_hien="E2E Quỹ", ngay_gd=now,
            )
        self.stdout.write("[funds] phiếu E2EPT001")

        self.stdout.write(self.style.SUCCESS("DONE — fixtures E2E sẵn sàng (mật khẩu: tham số --password)"))

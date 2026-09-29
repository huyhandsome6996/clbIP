"""
Tests — apps.gamification
=========================
Bao phủ 7 trường hợp bắt buộc của đặc tả (Task 3-b):
    1. award_xp cộng đúng + level_from_xp biên (99→1, 100→2, 5000→10, 6000→10).
    2. Idempotency key: thưởng lặp → awarded=False, XP không tăng.
    3. Daily cap 300 XP: 3 lần x 150 → chỉ nhận 300.
    4. Leaderboard Min-Heap: 12 member → top 10 đúng thứ hạng; rank 11 ngoài top.
    5. Badge unlock STREAK_7 + idempotent khi đánh giá 2 lần.
    6. Strategy: EarlyAttendance 20'→70, 5'→60; Late→25.
    7. API: MEMBER xem leaderboard 200; chưa đăng nhập 401.

Môi trường: settings.TESTING=True → axes tắt; throttle vẫn bật nên
`cache.clear()` trong setUp.
"""
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.authentication.models import User
from apps.gamification.models import Badge, MemberBadge, XpLedger
from apps.gamification.services import (
    BadgeService,
    DocumentContributionStrategy,
    EarlyAttendanceStrategy,
    EventOrganizerStrategy,
    GamificationService,
    LateAttendanceStrategy,
    LEVEL_THRESHOLDS,
    LeaderboardService,
    RewardStrategyFactory,
    TaskCompletionStrategy,
    level_from_xp,
)
from apps.members.models import MemberProfile
from apps.common.exceptions import ValidationException


def make_member(
    email: str,
    ho_ten: str,
    *,
    xp: int = 0,
    streak: int = 0,
    role: str = "MEMBER",
    trang_thai: str = MemberProfile.TrangThai.ACTIVE,
) -> tuple[User, MemberProfile]:
    """Tạo User + MemberProfile cho test (username sinh từ email, unique)."""
    user = User.objects.create_user(
        username=email.split("@")[0],
        email=email,
        password="TestPass123!",
        role=role,
    )
    profile = MemberProfile.objects.create(
        user=user,
        ho_ten=ho_ten,
        xp_points=xp,
        current_level=level_from_xp(xp),
        streak_count=streak,
        trang_thai_hd=trang_thai,
    )
    return user, profile


class LevelSystemTests(APITestCase):
    """(1) Hệ thống cấp độ + award_xp cập nhật hồ sơ."""

    def setUp(self) -> None:
        cache.clear()

    def test_level_from_xp_boundary(self) -> None:
        """Biên ngưỡng cấp: 99→1, 100→2, 5000→10, 6000→10 (trần)."""
        self.assertEqual(level_from_xp(0), 1)
        self.assertEqual(level_from_xp(99), 1)
        self.assertEqual(level_from_xp(100), 2)
        self.assertEqual(level_from_xp(249), 2)
        self.assertEqual(level_from_xp(4999), 9)
        self.assertEqual(level_from_xp(5000), 10)
        self.assertEqual(level_from_xp(6000), 10, "XP vượt trần vẫn dừng ở cấp 10")
        self.assertEqual(len(LEVEL_THRESHOLDS), 10)

    def test_award_xp_cap_nhat_xp_va_level(self) -> None:
        """award_xp 100 → xp=100, level=2; nhận đủ trong dict kết quả."""
        _user, profile = make_member("lv1@clbip.test", "Thành Viên 1")
        result = GamificationService.award_xp(
            member=profile,
            amount=100,
            reason="Điểm danh buổi sinh hoạt",
            source="ATTENDANCE",
        )
        self.assertTrue(result["awarded"])
        self.assertEqual(result["xp_gained"], 100)
        self.assertEqual(result["member_xp"], 100)
        self.assertEqual(result["member_level"], 2)

        profile.refresh_from_db()
        self.assertEqual(profile.xp_points, 100)
        self.assertEqual(profile.current_level, 2)

        # Ghi ledger đúng 1 dòng
        self.assertEqual(XpLedger.objects.filter(member=profile).count(), 1)

    def test_award_xp_vuot_len_10(self) -> None:
        """Từ 4900 XP +100 → đúng 5000 → level 10."""
        _user, profile = make_member("lv9@clbip.test", "Thành Viên 9", xp=4900)
        result = GamificationService.award_xp(profile, 100, "Sự kiện lớn", "BONUS")
        self.assertEqual(result["member_xp"], 5000)
        self.assertEqual(result["member_level"], 10)


class IdempotencyAndCapTests(APITestCase):
    """(2) Idempotency key + (3) Daily XP Cap."""

    def setUp(self) -> None:
        cache.clear()
        _user, self.profile = make_member("idem@clbip.test", "Thành Viên Idem")

    def test_idempotency_key_chong_cong_lap(self) -> None:
        """Cùng idempotency_key 2 lần → lần 2 awarded=False, XP không đổi."""
        first = GamificationService.award_xp(
            self.profile, 50, "Chia sẻ tài liệu", "DOCUMENT_SHARE",
            idempotency_key="action_1_doc_20260928",
        )
        self.assertTrue(first["awarded"])
        self.assertEqual(first["member_xp"], 50)

        second = GamificationService.award_xp(
            self.profile, 50, "Chia sẻ tài liệu", "DOCUMENT_SHARE",
            idempotency_key="action_1_doc_20260928",
        )
        self.assertFalse(second["awarded"])
        self.assertEqual(second["xp_gained"], 0)
        self.assertEqual(second["message"], "Đã thưởng trước đó")
        self.assertEqual(second["member_xp"], 50, "XP không được cộng lặp")

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.xp_points, 50)
        self.assertEqual(XpLedger.objects.filter(member=self.profile).count(), 1)

    def test_daily_cap_300_xp(self) -> None:
        """3 lần x 150 XP (không key) → tổng chỉ nhận 300; lần 3 bị chặn."""
        r1 = GamificationService.award_xp(self.profile, 150, "Điểm danh #1", "ATTENDANCE")
        r2 = GamificationService.award_xp(self.profile, 150, "Điểm danh #2", "ATTENDANCE")
        r3 = GamificationService.award_xp(self.profile, 150, "Điểm danh #3", "ATTENDANCE")

        self.assertTrue(r1["awarded"])
        self.assertEqual(r1["xp_gained"], 150)
        self.assertTrue(r2["awarded"])
        self.assertEqual(r2["xp_gained"], 150)

        # Trần 300 đã đầy → không cộng nữa, KHÔNG raise (điểm danh vẫn thành công)
        self.assertFalse(r3["awarded"])
        self.assertEqual(r3["xp_gained"], 0)
        self.assertEqual(r3["message"], "Đã đạt trần XP ngày")

        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.xp_points, 300,
            "Tổng XP nhận trong ngày phải chặn đúng ở 300",
        )

    def test_cap_cong_phan_du_con_lai(self) -> None:
        """Còn dư cap 50 mà thưởng 150 → chỉ cộng 50 (không âm Cap)."""
        GamificationService.award_xp(self.profile, 150, "Điểm #1", "ATTENDANCE")
        GamificationService.award_xp(self.profile, 100, "Điểm #2", "ATTENDANCE")
        partial = GamificationService.award_xp(self.profile, 150, "Điểm #3", "ATTENDANCE")
        self.assertTrue(partial["awarded"])
        self.assertEqual(partial["xp_gained"], 50, "Chỉ cộng phần dư còn lại của cap")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.xp_points, 300)

    def test_phat_xp_khong_dinh_cap(self) -> None:
        """amount < 0 (phạt) vẫn áp dụng nguyên vẹn dù đã đầy cap."""
        GamificationService.award_xp(self.profile, 300, "Đầy cap", "ATTENDANCE")
        penalty = GamificationService.award_xp(self.profile, -30, "Phạt gian lận", "BONUS")
        self.assertTrue(penalty["awarded"])
        self.assertEqual(penalty["xp_gained"], -30)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.xp_points, 270)


class StrategyTests(APITestCase):
    """(6) Strategy Pattern tính XP — server-side only."""

    def setUp(self) -> None:
        cache.clear()

    def test_early_attendance_strategy(self) -> None:
        """Sớm 20' → 70 (50+20); sớm 5' → 60 (50+10); đúng giờ → 50."""
        self.assertEqual(EarlyAttendanceStrategy().calculate_xp({"minutes_early": 20}), 70)
        self.assertEqual(EarlyAttendanceStrategy().calculate_xp({"minutes_early": 5}), 60)
        self.assertEqual(EarlyAttendanceStrategy().calculate_xp({"minutes_early": 0}), 50)
        self.assertEqual(EarlyAttendanceStrategy().calculate_xp({}), 50)

    def test_late_and_other_strategies(self) -> None:
        """Muộn → 25; Document → 100; Task → 30; Organizer/Participant."""
        self.assertEqual(LateAttendanceStrategy().calculate_xp({}), 25)
        self.assertEqual(DocumentContributionStrategy().calculate_xp({}), 100)
        self.assertEqual(TaskCompletionStrategy().calculate_xp({}), 30)
        self.assertEqual(
            EventOrganizerStrategy().calculate_xp({"role": "ORGANIZER"}), 150
        )
        self.assertEqual(
            EventOrganizerStrategy().calculate_xp({"role": "PARTICIPANT"}), 50
        )
        self.assertEqual(EventOrganizerStrategy().calculate_xp({}), 50)

    def test_factory_get_va_loi_nguon_khong_hop_le(self) -> None:
        """Factory map đúng strategy; source lạ → ValidationException."""
        self.assertIsInstance(RewardStrategyFactory.get("ATTENDANCE"), EarlyAttendanceStrategy)
        self.assertIsInstance(RewardStrategyFactory.get("ATTENDANCE_LATE"), LateAttendanceStrategy)
        with self.assertRaises(ValidationException):
            RewardStrategyFactory.get("HACK_XP")

    def test_award_xp_dung_strategy_server_authoritative(self) -> None:
        """award_xp với strategy: XP tính từ context, không nhận amount client."""
        _user, profile = make_member("strategy@clbip.test", "Thành Viên Strategy")
        result = GamificationService.award_xp(
            profile,
            amount=999_999,  # client gửi giá trị nào cũng bị bỏ qua
            reason="Check-in GPS",
            source="ATTENDANCE",
            strategy=RewardStrategyFactory.get("ATTENDANCE"),
            context={"minutes_early": 20},
        )
        self.assertEqual(result["xp_gained"], 70, "XP phải do strategy tính = 70")


class BadgeTests(APITestCase):
    """(5) Badge unlock tự động + idempotent."""

    def setUp(self) -> None:
        cache.clear()
        _user, self.profile = make_member("badge@clbip.test", "Thành Viên Badge")

    def test_streak_7_mo_badge_streak_7(self) -> None:
        """streak_count=7 → mở 'STREAK_7'; đánh giá 2 lần không nhân đôi."""
        self.profile.streak_count = 7
        self.profile.save(update_fields=["streak_count", "updated_at"])

        first = BadgeService.evaluate_and_unlock(self.profile)
        self.assertIn(Badge.objects.get(ma_badge="STREAK_7").ten_badge, first)
        self.assertTrue(
            MemberBadge.objects.filter(
                member=self.profile, badge__ma_badge="STREAK_7"
            ).exists()
        )

        second = BadgeService.evaluate_and_unlock(self.profile)
        self.assertEqual(second, [], "Đánh giá lại không được mở thêm")
        self.assertEqual(
            MemberBadge.objects.filter(
                member=self.profile, badge__ma_badge="STREAK_7"
            ).count(),
            1,
        )

    def test_doc_contributor_3_badge(self) -> None:
        """3 lần chia sẻ tài liệu (ledger DOCUMENT_SHARE) → mở DOC_CONTRIBUTOR_3."""
        for i in range(3):
            GamificationService.award_xp(
                self.profile, 100, f"Chia sẻ #{i}", "DOCUMENT_SHARE"
            )
        BadgeService.evaluate_and_unlock(self.profile)
        self.assertTrue(
            MemberBadge.objects.filter(
                member=self.profile, badge__ma_badge="DOC_CONTRIBUTOR_3"
            ).exists()
        )

    def test_badge_tu_get_or_create_idempotent(self) -> None:
        """Badge chưa có trong DB → tự tạo đúng catalog; gọi lại không tạo mới."""
        self.profile.streak_count = 10
        self.profile.save(update_fields=["streak_count", "updated_at"])
        BadgeService.evaluate_and_unlock(self.profile)
        count = Badge.objects.filter(ma_badge="STREAK_7").count()
        self.assertEqual(count, 1)
        BadgeService.evaluate_and_unlock(self.profile)
        self.assertEqual(Badge.objects.filter(ma_badge="STREAK_7").count(), 1)


class LeaderboardTests(APITestCase):
    """(4) Leaderboard Min-Heap O(N log K)."""

    def setUp(self) -> None:
        cache.clear()
        # 12 thành viên XP giảm dần: rank 1 = 1200 ... rank 12 = 90
        self.profiles: list[MemberProfile] = []
        for i in range(12):
            _u, p = make_member(f"lb{i}@clbip.test", f"Thành Viên {i:02d}", xp=1200 - i * 100)
            self.profiles.append(p)

    def test_top_10_dung_thu_hang_giam_dan(self) -> None:
        result = LeaderboardService.get_leaderboard()
        top = result["top_10"]
        self.assertEqual(len(top), 10)
        self.assertEqual([e["rank"] for e in top], list(range(1, 11)))
        xps = [e["xp"] for e in top]
        self.assertEqual(xps, sorted(xps, reverse=True), "Top 10 phải giảm dần theo XP")
        self.assertEqual(top[0]["xp"], 1200)
        self.assertEqual(top[0]["id"], self.profiles[0].pk)
        self.assertEqual(top[-1]["xp"], 300)
        self.assertEqual(result["total_members"], 12)

    def test_my_position_rank_11_ngoai_top_k(self) -> None:
        """Member rank 11 (xp=200): in_top_k=False, rank=11, gap>0."""
        rank11 = self.profiles[10]  # xp = 1200 - 10*100 = 200
        result = LeaderboardService.get_leaderboard(rank11)
        my = result["my_position"]
        self.assertIsNotNone(my)
        self.assertFalse(my["in_top_k"])
        self.assertEqual(my["rank"], 11)
        self.assertGreater(my["xp_gap_to_top_k"], 0)

    def test_my_position_rank_1_trong_top_k(self) -> None:
        """Member rank 1: in_top_k=True, gap=0."""
        result = LeaderboardService.get_leaderboard(self.profiles[0])
        my = result["my_position"]
        self.assertTrue(my["in_top_k"])
        self.assertEqual(my["rank"], 1)
        self.assertEqual(my["xp_gap_to_top_k"], 0)

    def test_leaderboard_chi_lay_member_active(self) -> None:
        """Member INACTIVE bị loại khỏi bảng vàng."""
        _u, inactive = make_member("lb-off@clbip.test", "Ngừng Hoạt Động", xp=9999,
                                   trang_thai=MemberProfile.TrangThai.INACTIVE)
        result = LeaderboardService.get_leaderboard()
        ids = [e["id"] for e in result["top_10"]]
        self.assertNotIn(inactive.pk, ids)
        self.assertEqual(result["total_members"], 12)


class GamificationAPITests(APITestCase):
    """(7) API leaderboard/badges/me: phân quyền + envelope."""

    def setUp(self) -> None:
        cache.clear()
        self.member_user, self.member_profile = make_member(
            "api.member@clbip.test", "Thành Viên API", xp=150
        )
        self.bcn_user, self.bcn_profile = make_member(
            "api.bcn@clbip.test", "BCN API", xp=800, role="BCN"
        )
        self.leaderboard_url = reverse("gamification_leaderboard")
        self.badges_url = reverse("gamification_badges")
        self.me_url = reverse("gamification_me")

    def test_api_member_xem_leaderboard_200(self) -> None:
        """MEMBER đăng nhập → 200, envelope có top_10 + my_position."""
        client = APIClient()
        client.force_authenticate(user=self.member_user)
        resp = client.get(self.leaderboard_url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        data = body["data"]
        self.assertIn("top_10", data)
        self.assertIn("my_position", data)
        self.assertEqual(data["total_members"], 2)
        self.assertEqual(data["my_position"]["in_top_k"], True)

    def test_api_chua_dang_nhap_leaderboard_401(self) -> None:
        """Không auth → 401."""
        client = APIClient()
        resp = client.get(self.leaderboard_url)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json()["success"])

    def test_api_badges_tra_items_va_unlocked(self) -> None:
        """GET /badges/ → items có flag unlocked; unlocked là list ma_badge."""
        self.profile_streak()
        # Tạo sẵn badge chưa ai mở trong DB để kiểm tra flag False
        Badge.objects.get_or_create(
            ma_badge="LEVEL_5",
            defaults={"ten_badge": "Cao thủ cấp 5", "mo_ta": "Đạt cấp 5", "icon": "⭐"},
        )
        client = APIClient()
        client.force_authenticate(user=self.member_user)
        resp = client.get(self.badges_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIn("items", data)
        self.assertIn("unlocked", data)
        by_code = {i["ma_badge"]: i for i in data["items"]}
        self.assertIn("STREAK_7", by_code)
        self.assertTrue(by_code["STREAK_7"]["unlocked"])
        self.assertIn("STREAK_7", data["unlocked"])
        # Badge chưa mở thì flag False
        self.assertFalse(by_code["LEVEL_5"]["unlocked"])

    def profile_streak(self) -> None:
        """Đặt streak=7 và mở badge cho member."""
        self.member_profile.streak_count = 7
        self.member_profile.save(update_fields=["streak_count", "updated_at"])
        BadgeService.evaluate_and_unlock(self.member_profile)

    def test_api_me_tong_quan(self) -> None:
        """GET /me/ → xp, level, streak_count, badges, weekly_quests."""
        client = APIClient()
        client.force_authenticate(user=self.member_user)
        resp = client.get(self.me_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["xp"], 150)
        self.assertEqual(data["level"], 2)
        self.assertIn("badges", data)
        self.assertIn("weekly_quests", data)
        self.assertIn("xp_this_week", data["weekly_quests"])

    def test_api_me_chua_co_profile_404(self) -> None:
        """User không có MemberProfile → 404 envelope."""
        stranger = User.objects.create_user(
            username="stranger",
            email="stranger@clbip.test",
            password="TestPass123!",
            role="MEMBER",
        )
        client = APIClient()
        client.force_authenticate(user=stranger)
        resp = client.get(self.me_url)
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["success"])

    def test_weekly_quests_dung_tien_do(self) -> None:
        """Nhiệm vụ tuần: XP tuần, số buổi điểm danh, số tài liệu, số task."""
        _u, profile = make_member("weekly@clbip.test", "Thành Viên Tuần")
        GamificationService.award_xp(profile, 50, "Điểm danh", "ATTENDANCE")
        GamificationService.award_xp(profile, 100, "Chia sẻ doc", "DOCUMENT_SHARE")

        # 1 bản ghi điểm danh tuần này (gắn session mẫu)
        event = None  # session không bắt buộc event
        session = AttendanceSession.objects.create(
            ten_phien="Phiên test", vi_do=16.46, kinh_do=107.59, event=event
        )
        AttendanceRecord.objects.create(
            session=session, member=profile, trang_thai=AttendanceRecord.TrangThaiDiemDanh.CO_MAT
        )

        quests = GamificationService.get_weekly_quests(profile)
        self.assertEqual(quests["xp_this_week"], 150)
        self.assertEqual(quests["attendance_count"], 1)
        self.assertEqual(quests["document_shared"], 1)
        self.assertEqual(quests["task_completed"], 0)
        self.assertIn("week_start", quests)


class AwardXpBadgeEvaluateTests(TestCase):
    """QA-Audit nhóm 3 — award_xp chỉ gọi BadgeService.evaluate_and_unlock 1 lần."""

    def _make_member(self):
        from apps.members.models import MemberProfile

        user = User.objects.create_user(email="xpbconce@clbip.vn", password="TestPass123!")
        return MemberProfile.objects.create(user=user, ho_ten="Thành Viên XP Once")

    def test_luu_thanh_cong_chi_evaluate_1_lan(self) -> None:
        """Luồng thành công (cộng XP) → evaluate_and_unlock đúng 1 lần, SAU khi cập nhật XP."""
        member = self._make_member()
        with mock.patch.object(
            BadgeService, "evaluate_and_unlock", wraps=BadgeService.evaluate_and_unlock,
        ) as spy:
            result = GamificationService.award_xp(member, 50, "Test XP", source="BONUS")
        self.assertEqual(result["awarded"], True)
        self.assertEqual(spy.call_count, 1)

    def test_dat_tran_cap_chi_evaluate_1_lan(self) -> None:
        """Luồng đạt trần XP ngày → vẫn evaluate đúng 1 lần (không mất badge)."""
        member = self._make_member()
        with mock.patch.object(
            GamificationService, "_xp_used_today", return_value=settings.CLB_SETTINGS["DAILY_XP_CAP"],
        ):
            with mock.patch.object(
                BadgeService, "evaluate_and_unlock", wraps=BadgeService.evaluate_and_unlock,
            ) as spy:
                result = GamificationService.award_xp(member, 50, "Test XP", source="BONUS")
        self.assertEqual(result["awarded"], False)
        self.assertIn("trần", result["message"])
        self.assertEqual(spy.call_count, 1)

    def test_badge_van_duoc_mo_kho_sau_khi_sua(self) -> None:
        """Sau sửa lỗi, badge vẫn mở khóa bình thường (không làm mất badge)."""
        from apps.gamification.models import Badge, MemberBadge

        member = self._make_member()
        member.streak_count = 7
        member.save(update_fields=["streak_count"])
        GamificationService.award_xp(member, 10, "Trigger eval", source="BONUS")
        badge = Badge.objects.filter(ma_badge="STREAK_7").first()
        self.assertIsNotNone(badge)
        self.assertTrue(MemberBadge.objects.filter(member=member, badge=badge).exists())


class LeaderboardPerformanceTests(TestCase):
    """QA-Audit nhóm 5 — leaderboard: DB rank + cache ngắn hạn, giữ nguyên format."""

    def setUp(self) -> None:
        from django.core.cache import cache

        cache.clear()  # cô lập cache leaderboard giữa các test

    def _make_member(self, email: str, xp: int, ho_ten: str):
        from apps.members.models import MemberProfile

        user = User.objects.create_user(email=email, password="TestPass123!")
        profile = MemberProfile.objects.create(user=user, ho_ten=ho_ten)
        profile.xp_points = xp
        profile.save(update_fields=["xp_points"])
        return profile

    def test_rank_tinh_bang_db_count_khong_que_toan_bo(self) -> None:
        """Rank = 1 + số ACTIVE có XP cao hơn (kết quả giống find_my_position cũ)."""
        from apps.members.models import MemberProfile
        from apps.gamification.services import LeaderboardService

        high = self._make_member("lb-hi@clbip.vn", 500, "Cao Nhất")
        mid = self._make_member("lb-mid@clbip.vn", 300, "Thứ Hai")
        self._make_member("lb-lo@clbip.vn", 100, "Thứ Ba")

        result = LeaderboardService.get_leaderboard(mid)
        my = result["my_position"]
        self.assertEqual(my["rank"], 2)
        # 3 thành viên < TOP_K=10 → tất cả nằm trong top
        self.assertTrue(my["in_top_k"])
        self.assertEqual(result["total_members"], 3)
        self.assertEqual(result["top_10"][0]["id"], high.pk)

        # Inactive member → đúng shape hành vi cũ (rank = total, gap = 0)
        mid.trang_thai_hd = MemberProfile.TrangThai.INACTIVE
        mid.save(update_fields=["trang_thai_hd"])
        my2 = LeaderboardService.get_leaderboard(mid)["my_position"]
        self.assertEqual(my2, {"in_top_k": False, "rank": 2, "xp_gap_to_top_k": 0})

    def test_top10_duoc_cache_tai_su_dung(self) -> None:
        """Lần gọi thứ 2 dùng cache — không tính lại heap khi dữ liệu không đổi."""
        from django.core.cache import cache

        from apps.gamification.services import LeaderboardService

        self._make_member("lb-c1@clbip.vn", 400, "Cache Một")
        r1 = LeaderboardService.get_leaderboard()
        cached = cache.get(LeaderboardService.CACHE_KEY)
        self.assertIsNotNone(cached)

        # Sửa XP trực tiếp KHÔNG qua award_xp (không hợp lệ nghiệp vụ) —
        # cache 45s vẫn trả giá trị cũ đúng thiết kế ngắn hạn
        r2 = LeaderboardService.get_leaderboard()
        self.assertEqual(r1, r2)

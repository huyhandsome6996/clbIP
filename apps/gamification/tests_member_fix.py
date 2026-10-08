"""
Regression tests — audit luồng thành viên 1114efd (M06/M09/M10)
===============================================================
- M10: `level_progress_for_xp` đúng toàn bộ biên theo LEVEL_THRESHOLDS
  [0,100,250,500,900,1400,2000,2800,3800,5000]; Level 10 KHÔNG gợi Level 11.
- M06/M10: GET /gamification/me/ trả `level_progress` là nguồn chuẩn cho UI.
- M09: GamificationService.award_xp PERSIST qua repository — XP/level vẫn ghi
  đúng DB (hành vi không đổi, đường ghi đổi).
"""
from django.test import override_settings
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.gamification.services import (
    GamificationService,
    LEVEL_THRESHOLDS,
    level_progress_for_xp,
)
from apps.gamification.tests import make_member
from apps.gamification.models import XpLedger
from django.test import TestCase


class LevelProgressBoundaryTests(TestCase):
    """M10 — toàn bộ biên QA yêu cầu: 0/50/99/100/249/250/499/500/4999/5000/>5000."""

    def _assert(self, xp, level, into, to_next, pct, max_level=False):
        p = level_progress_for_xp(xp)
        self.assertEqual(p["current_level"], level, f"xp={xp} level")
        self.assertEqual(p["xp_into_level"], into, f"xp={xp} into")
        self.assertEqual(p["xp_to_next"], to_next, f"xp={xp} to_next")
        self.assertEqual(p["max_level"], max_level, f"xp={xp} max")
        self.assertTrue(0 <= p["progress_percent"] <= 100, f"xp={xp} clamp")
        if max_level:
            self.assertIsNone(p["next_level_xp"], f"xp={xp} next")
            self.assertEqual(p["progress_percent"], 100)
        else:
            self.assertIsNotNone(p["next_level_xp"], f"xp={xp} next")
            self.assertEqual(p["progress_percent"], pct, f"xp={xp} pct")

    def test_boundaries(self) -> None:
        # (xp, level, into, to_next, pct, max)
        cases = [
            (0, 1, 0, 100, 0),
            (50, 1, 50, 50, 50),
            (99, 1, 99, 1, 99),
            (100, 2, 0, 150, 0),
            (249, 2, 149, 1, 99),
            (250, 3, 0, 250, 0),
            (499, 3, 249, 1, 100),  # 249/250 làm tròn → 100 nhưng vẫn clamp ≤100
            (500, 4, 0, 400, 0),
            (1400, 6, 0, 600, 0),
            (4999, 9, 1199, 1, 100),
            (5000, 10, 0, None, 100, True),
            (6000, 10, 1000, None, 100, True),
        ]
        for case in cases:
            self._assert(*case)

    def test_negative_xp_clamped(self) -> None:
        """XP âm (dữ liệu lạ) → không crash, xử lý như 0."""
        p = level_progress_for_xp(-5)
        self.assertEqual(p["current_level"], 1)
        self.assertEqual(p["xp_into_level"], 0)
        self.assertEqual(p["progress_percent"], 0)

    def test_thresholds_table_unchanged(self) -> None:
        """Khóa bảng ngưỡng — tránh ai sửa bảng làm UI/backend lệch nhau."""
        self.assertEqual(LEVEL_THRESHOLDS, [0, 100, 250, 500, 900, 1400, 2000, 2800, 3800, 5000])


@override_settings(AXES_ENABLED=False)
class GamificationMeProgressApiTests(TestCase):
    """M06/M10 — /gamification/me/ có level_progress nhất quán với xp."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.user, self.profile = make_member("lvlprog@clb.vn", "Thành Viên Tiến Độ", xp=350)

    def test_me_includes_level_progress(self) -> None:
        self.client.force_authenticate(self.user)
        res = self.client.get("/api/v1/gamification/me/")
        self.assertEqual(res.status_code, 200)
        data = res.data["data"]
        self.assertEqual(data["xp"], 350)
        self.assertEqual(data["level"], 3)
        lp = data["level_progress"]
        self.assertEqual(lp["current_level"], 3)
        self.assertEqual(lp["current_level_xp"], 250)
        self.assertEqual(lp["next_level_xp"], 500)
        self.assertEqual(lp["xp_into_level"], 100)
        self.assertEqual(lp["xp_to_next"], 150)
        self.assertEqual(lp["progress_percent"], 40)
        self.assertFalse(lp["max_level"])

    def test_me_max_level_no_level_11_hint(self) -> None:
        """xp ≥ 5000 → max_level=True, next_level_xp=None (UI không vẽ Level 11)."""
        self.profile.xp_points = 5200
        self.profile.current_level = 10
        self.profile.save(update_fields=["xp_points", "current_level"])
        self.client.force_authenticate(self.user)
        res = self.client.get("/api/v1/gamification/me/")
        lp = res.data["data"]["level_progress"]
        self.assertTrue(lp["max_level"])
        self.assertIsNone(lp["next_level_xp"])
        self.assertEqual(lp["progress_percent"], 100)

    def test_me_unauthenticated_401(self) -> None:
        res = self.client.get("/api/v1/gamification/me/")
        self.assertEqual(res.status_code, 401)


class AwardXpPersistsViaRepositoryTests(TestCase):
    """M09 — award_xp ghi DB qua repo method mới, hành vi giữ nguyên."""

    def test_award_xp_persists_xp_and_level(self) -> None:
        user, profile = make_member("persistxp@clb.vn", "Thành Viên Persist", xp=90)
        result = GamificationService.award_xp(
            member=profile,
            amount=10,
            reason="Test persist",
            source="BONUS",
        )
        self.assertTrue(result["awarded"])
        profile.refresh_from_db()
        self.assertEqual(profile.xp_points, 100)
        self.assertEqual(profile.current_level, 2)
        # Sổ cái ghi đúng 1 dòng
        self.assertTrue(
            XpLedger.objects.filter(member=profile, amount=10).exists()
        )

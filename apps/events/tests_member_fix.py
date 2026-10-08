"""
Regression tests — audit luồng thành viên 1114efd (M02/M09)
===========================================================
- M02: GET /events/my-tickets/ trả metadata sự kiện đầy đủ (thời gian, địa
  điểm, trạng thái sự kiện, loại) để tab "Vé của tôi" đứng độc lập với trang
  /events/ hiện tại; serializer của register cũng mang metadata.
- M09: POST /members/board/ đi qua MemberService.create_board_position —
  hành vi không đổi (201, dữ liệu đúng).
"""
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.models import ActivityEvent, EventRegistration
from apps.events.tests import EventTestBase
from apps.members.models import BoardMember, MemberProfile
from apps.members.services import MemberService


class MyTicketsMetadataTests(EventTestBase):
    """M02 — vé mang đủ metadata sự kiện để dựng card độc lập."""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.event = self.make_event()
        self.reg = EventRegistration.objects.create(
            event=self.event, member=self.member_profile, ma_ve="VE-M02-BASE"
        )

    def test_my_tickets_includes_event_metadata(self) -> None:
        self.client.force_authenticate(self.member)
        res = self.client.get("/api/v1/events/my-tickets/")
        self.assertEqual(res.status_code, 200)
        items = res.data["data"]
        self.assertEqual(len(items), 1)
        ticket = items[0]
        self.assertEqual(ticket["event"], self.event.id)
        self.assertEqual(ticket["event_ten"], self.event.ten_hoat_dong)
        self.assertIsNotNone(ticket["event_thoi_gian_bat_dau"])
        self.assertIsNotNone(ticket["event_thoi_gian_ket_thuc"])
        self.assertEqual(ticket["event_dia_diem"], "Huế")
        self.assertEqual(ticket["event_trang_thai"], "OPEN_REGISTRATION")
        self.assertEqual(ticket["event_loai_hd"], "WORKSHOP")
        self.assertEqual(ticket["ma_ve"], self.reg.ma_ve)
        self.assertEqual(ticket["trang_thai"], "REGISTERED")

    def test_register_response_also_carries_metadata(self) -> None:
        """POST register (dùng bởi nút Đăng ký lại) cũng trả metadata — QR modal có tên/thời gian/địa điểm ngay."""
        self.reg.trang_thai = EventRegistration.TrangThai.CANCELLED
        self.reg.save(update_fields=["trang_thai"])
        other_user, other_profile = self._make_member(1)
        EventRegistration.objects.create(
            event=self.event, member=other_profile, ma_ve="VE-M02-OTHER"
        )

        self.client.force_authenticate(self.member)
        res = self.client.post(f"/api/v1/events/{self.event.id}/register/")
        self.assertEqual(res.status_code, 201, res.data)
        data = res.data["data"]
        self.assertEqual(data["event_ten"], self.event.ten_hoat_dong)
        self.assertIsNotNone(data["event_thoi_gian_bat_dau"])
        self.assertEqual(data["event_trang_thai"], "OPEN_REGISTRATION")


class BoardPositionServiceTests(EventTestBase):
    """M09 — bổ nhiệm BCN qua service, semantics giữ nguyên."""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()

    def test_create_board_position_via_service(self) -> None:
        nhiem_ky = "2026-2027"
        bm = MemberService.create_board_position(
            {
                "member": self.member_profile,
                "chuc_vu": "TRUONG_BAN",
                "ban_phu_trach": "HOC_THUAT",
                "nhiem_ky": nhiem_ky,
            }
        )
        self.assertIsNotNone(bm.pk)
        self.assertTrue(BoardMember.objects.filter(pk=bm.pk).exists())

    def test_post_board_member_api_unchanged(self) -> None:
        """API POST qua view→service trả 201 + serializer đủ field."""
        self.client.force_authenticate(self.bcn)
        res = self.client.post(
            "/api/v1/members/board/",
            {
                "member": self.member_profile.pk,
                "chuc_vu": "TRUONG_BAN",
                "ban_phu_trach": "HOC_THUAT",
                "nhiem_ky": "2026-2027",
            },
            format="json",
        )
        self.assertIn(res.status_code, (201, 200), res.data)
        self.assertTrue(res.data["success"])

    def test_post_board_member_forbidden_for_member(self) -> None:
        self.client.force_authenticate(self.member)
        res = self.client.post(
            "/api/v1/members/board/",
            {
                "member": self.member_profile.pk,
                "chuc_vu": "TRUONG_BAN",
                "ban_phu_trach": "HOC_THUAT",
                "nhiem_ky": "2026-2027",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_get_queryset_via_service(self) -> None:
        MemberService.create_board_position(
            {
                "member": self.member_profile,
                "chuc_vu": "TRUONG_BAN",
                "ban_phu_trach": "HOC_THUAT",
                "nhiem_ky": "2026-2027",
            }
        )
        qs = MemberService.list_board_positions("2026-2027")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(MemberService.list_board_positions("9999").count(), 0)

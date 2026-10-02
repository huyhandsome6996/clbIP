"""
Tests — apps.posts
===================
Phủ bắt buộc:
    1. BCN đăng bài → 201; MEMBER đăng → 403.
    2. XSS: <script> bị bleach strip, <p>Xin chào</p> vẫn còn, href hợp lệ được giữ.
    3. Pin: is_pinned=True + audit PIN; feed trả bài ghim lên đầu.
    4. Audit: sửa bài → UPDATE; xóa → DELETE + is_deleted=True + feed không hiện.
    5. Feedback: member gửi 201; BCN GET thấy nội dung NHƯNG không lộ email/sender;
       member GET → 403.
    6. Anti-spam: góp ý thứ 6 trong ngày → 400.
    7. Poll: vote đúng, double-vote 409, index sai 400, poll đóng 409.
Lưu ý: throttle tầng view được tắt trong test (burst 10/s gây 429 nhiễu);
    tầng chống spam 5 góp ý/ngày vẫn được kiểm tra đầy đủ ở tầng Service.
"""
from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from apps.authentication.models import User
from apps.members.models import MemberProfile
from apps.posts.models import CommunityPoll, Post, PostAuditLog
from apps.posts.views import FeedbackView, PollVoteView


class NoThrottleMixin:
    """
    Tắt mọi throttle khi test:
      - APIView.throttle_classes: tắt 4 throttle mặc định (burst 10/s gây 429).
      - FeedbackView / PollVoteView: view tự khai throttle_classes riêng nên
        phải patch đè từng view.
    """

    def setUp(self) -> None:
        super().setUp()
        for target in (APIView, FeedbackView, PollVoteView):
            patcher = mock.patch.object(target, "throttle_classes", [])
            patcher.start()
            self.addCleanup(patcher.stop)


class PostBaseTests(NoThrottleMixin, APITestCase):
    """Nền tảng dùng chung: 1 BCN + 2 member (có profile)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.bcn = User.objects.create_user(
            username="bcn", email="bcn@clbip.test", password="TestPass123!",
            role=User.Role.BCN, mssv="22A4010101",
        )
        MemberProfile.objects.create(user=cls.bcn, ho_ten="Trần Văn Chủ Nhiệm")
        cls.member = User.objects.create_user(
            username="member_a", email="membera@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010102",
        )
        MemberProfile.objects.create(user=cls.member, ho_ten="Nguyễn Thị A")
        cls.member_b = User.objects.create_user(
            username="member_b", email="memberb@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010103",
        )
        cls.post_list_url = reverse("post_list")

    def _create_post(self, tieu_de: str = "Sinh hoạt định kỳ tháng này", noi_dung: str = "<p>Nội dung</p>") -> Post:
        """Helper: BCN đăng bài qua API, trả về Post."""
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.post(
            self.post_list_url,
            {"tieu_de": tieu_de, "noi_dung": noi_dung},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        return Post.objects.get(pk=resp.data["data"]["id"])


class PostPermissionAndXSSTests(PostBaseTests):
    """(1) RBAC đăng bài + (2) bleach chống XSS."""

    def test_01a_bcn_dang_bai_201(self) -> None:
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.post(
            self.post_list_url,
            {"tieu_de": "Thông báo tuyển thành viên", "noi_dung": "<p>CLB tuyển thành viên mới!</p>"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["success"])
        self.assertEqual(resp.data["message"], "Đăng thông báo thành công")
        self.assertTrue(Post.objects.filter(tieu_de="Thông báo tuyển thành viên").exists())

    def test_01b_member_dang_bai_403(self) -> None:
        self.client.force_authenticate(user=self.member)
        resp = self.client.post(
            self.post_list_url,
            {"tieu_de": "Tự ý đăng bài", "noi_dung": "<p>Không được phép</p>"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(resp.data["success"])
        self.assertEqual(Post.objects.count(), 0)

    def test_02_xss_script_bi_strip_p_giu_nguyen(self) -> None:
        """bleach: <script> bị loại hoàn toàn, <p> nằm trong whitelist được giữ."""
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.post(
            self.post_list_url,
            {
                "tieu_de": "Bài test XSS",
                "noi_dung": '<script>alert(1)</script><p>Xin chào</p><a href="https://clbip.vn">Link</a>',
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        post = Post.objects.get(tieu_de="Bài test XSS")
        self.assertNotIn("<script>", post.noi_dung)   # script tag đã bị strip
        self.assertIn("<p>Xin chào</p>", post.noi_dung)      # tag whitelist được giữ
        self.assertIn('<a href="https://clbip.vn">Link</a>', post.noi_dung)

        # Audit CREATE đã ghi
        self.assertTrue(post.audit_logs.filter(action=PostAuditLog.Action.CREATE).exists())


class PostPinTests(PostBaseTests):
    """(3) Ghim bài: trạng thái + audit PIN + thứ tự feed."""

    def test_03a_pin_bai_ghim_len_dau_feed(self) -> None:
        # Post A cũ hơn, post B mới hơn
        post_a = self._create_post("Bài A (cũ)")
        post_b = self._create_post("Bài B (mới)")

        self.client.force_authenticate(user=self.bcn)
        resp = self.client.patch(reverse("post_pin", kwargs={"pk": post_a.pk}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["message"], "Đã ghim bài")

        post_a.refresh_from_db()
        self.assertTrue(post_a.is_pinned)
        self.assertIsNotNone(post_a.pinned_at)
        # Audit PIN
        self.assertTrue(post_a.audit_logs.filter(action=PostAuditLog.Action.PIN).exists())

        # Feed: bài ghim A đứng trước B dù B mới hơn
        feed = self.client.get(self.post_list_url)
        items = feed.data["data"]["items"]
        self.assertEqual(items[0]["id"], post_a.pk)
        self.assertEqual(items[1]["id"], post_b.pk)

    def test_03b_bo_ghim_bai(self) -> None:
        post = self._create_post("Bài sẽ bỏ ghim")
        self.client.force_authenticate(user=self.bcn)
        self.client.patch(reverse("post_pin", kwargs={"pk": post.pk}))   # ghim
        resp = self.client.patch(reverse("post_pin", kwargs={"pk": post.pk}))  # bỏ ghim
        self.assertEqual(resp.data["message"], "Đã bỏ ghim")

        post.refresh_from_db()
        self.assertFalse(post.is_pinned)
        self.assertIsNone(post.pinned_at)
        self.assertTrue(post.audit_logs.filter(action=PostAuditLog.Action.UNPIN).exists())

    def test_03c_member_khong_duoc_ghim_403(self) -> None:
        post = self._create_post("Bài của BCN")
        self.client.force_authenticate(user=self.member)
        resp = self.client.patch(reverse("post_pin", kwargs={"pk": post.pk}))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class PostAuditTests(PostBaseTests):
    """(4) Audit trail UPDATE/DELETE + soft delete khỏi feed."""

    def test_04a_sua_bai_ghi_audit_update(self) -> None:
        post = self._create_post("Tiêu đề cũ")
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.patch(
            reverse("post_detail", kwargs={"pk": post.pk}),
            {"tieu_de": "Tiêu đề mới"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        post.refresh_from_db()
        self.assertEqual(post.tieu_de, "Tiêu đề mới")
        audit = post.audit_logs.filter(action=PostAuditLog.Action.UPDATE).first()
        self.assertIsNotNone(audit)
        self.assertIn("tieu_de", audit.chi_tiet)
        self.assertEqual(audit.performed_by, self.bcn)

    def test_04b_xoa_bai_soft_delete_khoi_feed(self) -> None:
        post = self._create_post("Bài sắp bị xóa")
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.delete(reverse("post_detail", kwargs={"pk": post.pk}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["message"], "Đã xóa bài đăng")

        post.refresh_from_db()
        self.assertTrue(post.is_deleted)  # soft delete — vẫn còn trong DB
        audit = post.audit_logs.filter(action=PostAuditLog.Action.DELETE).first()
        self.assertIsNotNone(audit)

        # Feed không còn hiện bài đã xóa
        feed = self.client.get(self.post_list_url)
        ids = [item["id"] for item in feed.data["data"]["items"]]
        self.assertNotIn(post.pk, ids)

    def test_04c_member_khong_duoc_xoa_403(self) -> None:
        post = self._create_post("Bài bảo vệ")
        self.client.force_authenticate(user=self.member)
        resp = self.client.delete(reverse("post_detail", kwargs={"pk": post.pk}))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        post.refresh_from_db()
        self.assertFalse(post.is_deleted)


class FeedbackTests(PostBaseTests):
    """(5) Hòm thư ẩn danh + (6) chống spam 5 góp ý/ngày."""

    def setUp(self) -> None:
        super().setUp()
        self.feedback_url = reverse("feedback")

    def test_05a_member_gui_feedback_201(self) -> None:
        self.client.force_authenticate(user=self.member)
        resp = self.client.post(
            self.feedback_url,
            {"noi_dung": "Mong CLB mở workshop Git cơ bản ạ."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["success"])
        self.assertIn("Ẩn danh", resp.data["message"])

    def test_05b_bcn_doc_khong_lo_danh_tinh(self) -> None:
        self.client.force_authenticate(user=self.member)
        self.client.post(self.feedback_url, {"noi_dung": "Góp ý nội bộ cần thiết."}, format="json")

        # MEMBER đọc hòm thư → 403
        self.client.force_authenticate(user=self.member_b)
        resp_member = self.client.get(self.feedback_url)
        self.assertEqual(resp_member.status_code, status.HTTP_403_FORBIDDEN)

        # BCN đọc → thấy nội dung nhưng KHÔNG thấy email / danh tính người gửi
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.get(self.feedback_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        content = resp.content.decode("utf-8")
        self.assertIn("Góp ý nội bộ cần thiết.", content)
        self.assertNotIn(self.member.email, content)   # KHÔNG lộ email
        self.assertNotIn("membera", content)           # KHÔNG lộ username/username-prefix
        # Cấu trúc item chỉ gồm id/noi_dung/created_at — không field sender
        item = resp.data["data"]["items"][0]
        self.assertEqual(set(item.keys()), {"id", "noi_dung", "created_at"})

    def test_05c_feedback_rong_400(self) -> None:
        self.client.force_authenticate(user=self.member)
        resp = self.client.post(self.feedback_url, {"noi_dung": "   "}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("để trống", resp.data["message"])

    def test_06_anti_spam_gop_y_thu_6_bat_400(self) -> None:
        """Tầng Service: 5 góp ý đầu OK, thứ 6 trong cùng ngày → 400."""
        self.client.force_authenticate(user=self.member)
        for i in range(5):
            resp = self.client.post(
                self.feedback_url,
                {"noi_dung": f"Góp ý hợp lệ thứ {i + 1} trong ngày."},
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED, f"Lần {i + 1}")

        resp6 = self.client.post(
            self.feedback_url,
            {"noi_dung": "Góp ý thứ 6 — vượt hạn mức!"},
            format="json",
        )
        self.assertEqual(resp6.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp6.data["success"])
        self.assertIn("quá nhiều góp ý hôm nay", resp6.data["message"])


class PollTests(PostBaseTests):
    """(7) Bình chọn: tạo poll, vote, double-vote, index sai, poll đóng."""

    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.post(
            reverse("poll_list"),
            {"question": "Buổi sinh hoạt tuần này nên tổ chức lúc nào?", "options": ["Sáng thứ 7", "Chiều thứ 7"]},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        self.poll_id = resp.data["data"]["id"]
        self.vote_url = reverse("poll_vote", kwargs={"pk": self.poll_id})

    def _vote(self, user, option_index) -> dict:
        self.client.force_authenticate(user=user)
        resp = self.client.post(self.vote_url, {"option_index": option_index}, format="json")
        return resp

    def test_07a_tao_poll_khoi_tao_phieu_0(self) -> None:
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.get(reverse("poll_list"))
        poll = resp.data["data"]["items"][0]
        self.assertEqual(poll["votes"], {"0": 0, "1": 0})
        self.assertEqual(poll["total_votes"], 0)
        self.assertFalse(poll["is_closed"])

    def test_07b_tao_poll_1_option_400(self) -> None:
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.post(
            reverse("poll_list"),
            {"question": "Poll thiếu option?", "options": ["Chỉ một lựa chọn"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_07c_vote_dung_va_chan_double_vote(self) -> None:
        # Member A vote option 0 → votes["0"] == 1
        resp = self._vote(self.member, 0)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["message"], "Đã ghi nhận bình chọn")
        self.assertEqual(resp.data["data"]["votes"]["0"], 1)

        # Member A vote lần 2 → 409 DuplicateDataException
        resp_dup = self._vote(self.member, 1)
        self.assertEqual(resp_dup.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("đã bình chọn rồi", resp_dup.data["message"])

        # Member B vote option 1 → votes["1"] == 1
        resp_b = self._vote(self.member_b, 1)
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_b.data["data"]["votes"]["1"], 1)

    def test_07d_option_index_ngoai_pham_vi_400(self) -> None:
        resp = self._vote(self.member, 5)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("không hợp lệ", resp.data["message"])

    def test_07e_vote_poll_da_dong_409(self) -> None:
        CommunityPoll.objects.filter(pk=self.poll_id).update(is_closed=True)
        resp = self._vote(self.member, 0)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("đã đóng", resp.data["message"])

    def test_07f_has_voted_phan_hoi_dung_theo_user(self) -> None:
        """has_voted: False trước khi vote / True sau khi vote / False với user khác."""
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(reverse("poll_list"))
        poll = resp.data["data"]["items"][0]
        self.assertIn("has_voted", poll)
        self.assertFalse(poll["has_voted"])

        self._vote(self.member, 0)
        resp = self.client.get(reverse("poll_list"))
        poll = resp.data["data"]["items"][0]
        self.assertTrue(poll["has_voted"])

        # User khác chưa vote → has_voted của họ vẫn False (scoping theo user)
        self.client.force_authenticate(user=self.member_b)
        resp = self.client.get(reverse("poll_list"))
        poll = resp.data["data"]["items"][0]
        self.assertFalse(poll["has_voted"])


class PostAuthorDisplayNameTests(APITestCase):
    """QA-Audit 2a — feed hiển thị TÊN người đăng, không lộ email (PII)."""

    def test_feed_hien_ten_khong_lo_email(self) -> None:
        from apps.authentication.models import User
        from apps.members.models import MemberProfile

        bcn = User.objects.create_user(email="poster2@clbip.vn", password="TestPass123!", role="BCN")
        MemberProfile.objects.create(user=bcn, ho_ten="Lê Văn Chủ Nhiệm")
        Post.objects.create(tieu_de="Thong bao", noi_dung="<p>Noi dung</p>", created_by=bcn)

        self.client.force_authenticate(user=bcn)
        res = self.client.get("/api/v1/posts/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        item = res.data["data"]["items"][0]
        self.assertEqual(item["created_by"], "Lê Văn Chủ Nhiệm")


class PollCloseTests(PostBaseTests):
    """QA-Audit đợt 3 — TASK 6A (P2): PATCH /polls/<id>/close/ (chỉ BCN/ADMIN)."""

    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.post(
            reverse("poll_list"),
            {"question": "Nên chọn logo nào?", "options": ["Logo A", "Logo B"]},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        self.poll_id = resp.data["data"]["id"]
        self.close_url = reverse("poll_close", kwargs={"pk": self.poll_id})
        self.vote_url = reverse("poll_vote", kwargs={"pk": self.poll_id})

    def test_6a_bcn_dong_binh_chon_200(self) -> None:
        """BCN đóng poll → 200, is_closed=True."""
        resp = self.client.patch(self.close_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["is_closed"])
        self.assertEqual(resp.data["message"], "Đã đóng bình chọn")

    def test_6b_member_duoc_dong_403(self) -> None:
        """MEMBER không được đóng bình chọn → 403."""
        self.client.force_authenticate(user=self.member)
        resp = self.client.patch(self.close_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_6c_dong_lan_2_400(self) -> None:
        """Đóng poll lần 2 → 400 'đã đóng rồi' (idempotent-strict)."""
        self.client.patch(self.close_url, format="json")
        resp = self.client.patch(self.close_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("đã đóng rồi", resp.data["message"])

    def test_6d_poll_da_dong_vote_bi_chan_409(self) -> None:
        """Poll đóng xong → member vote trả 409, phiếu không đổi."""
        self.client.patch(self.close_url, format="json")
        self.client.force_authenticate(user=self.member)
        resp = self.client.post(self.vote_url, {"option_index": 0}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        detail = self.client.get(reverse("poll_list")).data["data"]["items"][0]
        self.assertEqual(detail["total_votes"], 0)

    def test_6e_poll_khong_ton_tai_404(self) -> None:
        resp = self.client.patch(reverse("poll_close", kwargs={"pk": 99999}), format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

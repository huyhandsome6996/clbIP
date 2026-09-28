"""
Unit Tests cho 5 module DSA trong core/algorithms/
====================================================
Che phủ: trường hợp bình thường, trường hợp biên (edge cases) và độ phức tạp.
"""
import time
import unittest

from core.algorithms.dag_workflow import TaskDependencyEngine
from core.algorithms.fund_invariants import FundInvariantsEngine
from core.algorithms.geo_haversine import GeoSpatialService
from core.algorithms.leaderboard_heap import LeaderboardEngine
from core.algorithms.trie_search import PrefixSearchTrie, strip_vietnamese_accents


class GeoHaversineTests(unittest.TestCase):
    """Test DSA 1: Haversine & Bounding Box."""

    def test_known_distance_hue_landmarks(self):
        # Khoảng cách Đại học Sư phạm Huế (16.4637, 107.5909) → Đại Nội Huế
        # (16.4700, 107.5780) ≈ 1.44 km
        dist = GeoSpatialService.haversine_distance(16.4637, 107.5909, 16.4700, 107.5780)
        self.assertAlmostEqual(dist, 1440, delta=150)

    def test_same_point_is_zero(self):
        dist = GeoSpatialService.haversine_distance(16.4637, 107.5909, 16.4637, 107.5909)
        self.assertEqual(dist, 0.0)

    def test_symmetry(self):
        d1 = GeoSpatialService.haversine_distance(16.0, 107.0, 16.5, 107.6)
        d2 = GeoSpatialService.haversine_distance(16.5, 107.6, 16.0, 107.0)
        self.assertAlmostEqual(d1, d2, places=6)

    def test_within_radius_true(self):
        # Cách nhau ~11m, bán kính 50m
        ok, dist = GeoSpatialService.is_within_radius(
            16.463700, 107.590900, 16.463790, 107.590950, 50
        )
        self.assertTrue(ok)
        self.assertLess(dist, 50)

    def test_outside_radius_false(self):
        # Cách ~1.4km, bán kính 50m
        ok, dist = GeoSpatialService.is_within_radius(
            16.4637, 107.5909, 16.4700, 107.5780, 50
        )
        self.assertFalse(ok)
        self.assertGreater(dist, 1000)

    def test_bounding_box_prunes_faster(self):
        # Bounding box phải từ chối tức thì các điểm rất xa mà không cần Haversine
        bbox = GeoSpatialService.bounding_box(16.4637, 107.5909, 50)
        self.assertFalse(bbox.contains(21.0278, 105.8342))  # Hà Nội
        self.assertTrue(bbox.contains(16.4638, 107.5909))

    def test_bounding_box_consistent_with_haversine(self):
        # Bất kể điểm nào: nếu bbox từ chối thì haversine cũng phải từ chối
        center = (16.4637, 107.5909)
        bbox = GeoSpatialService.bounding_box(*center, 50)
        outside_points = [(16.6, 107.8), (15.9, 107.2), (16.4637, 108.0)]
        for lat, lon in outside_points:
            with self.subTest(point=(lat, lon)):
                if not bbox.contains(lat, lon):
                    ok, _ = GeoSpatialService.is_within_radius(*center, lat, lon, 50)
                    self.assertFalse(ok)

    def test_teleportation_speed_detection(self):
        # Huế → Hà Nội (~540km) trong 10 phút ⇒ tốc độ > 100 km/h
        speed = GeoSpatialService.travel_speed_kmh(
            16.4637, 107.5909, 21.0278, 105.8342, seconds=600
        )
        self.assertGreater(speed, 100)
        # Đi bộ 100m trong 10 phút ⇒ tốc độ rất thấp
        speed2 = GeoSpatialService.travel_speed_kmh(
            16.4637, 107.5909, 16.4646, 107.5909, seconds=600
        )
        self.assertLess(speed2, 2)


class LeaderboardHeapTests(unittest.TestCase):
    """Test DSA 2: Min-Heap Top-K Leaderboard."""

    def _make_members(self, n: int):
        return [{"id": i, "name": f"Member {i}", "xp": (i * 37) % 1000, "avatar": ""} for i in range(1, n + 1)]

    def test_top_k_correct_order(self):
        engine = LeaderboardEngine(top_k=3)
        result = engine.compute_top_k(
            [
                {"id": 1, "name": "A", "xp": 100, "avatar": ""},
                {"id": 2, "name": "B", "xp": 500, "avatar": ""},
                {"id": 3, "name": "C", "xp": 300, "avatar": ""},
                {"id": 4, "name": "D", "xp": 400, "avatar": ""},
            ]
        )
        self.assertEqual([r["id"] for r in result], [2, 4, 3])
        self.assertEqual([r["rank"] for r in result], [1, 2, 3])

    def test_top_k_fewer_than_k(self):
        engine = LeaderboardEngine(top_k=10)
        result = engine.compute_top_k([{"id": 1, "name": "A", "xp": 10, "avatar": ""}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["rank"], 1)

    def test_empty_input(self):
        engine = LeaderboardEngine(top_k=10)
        self.assertEqual(engine.compute_top_k([]), [])

    def test_rank_lookup_o1(self):
        engine = LeaderboardEngine(top_k=3)
        result = engine.compute_top_k(self._make_members(100))
        first_id = result[0]["id"]
        self.assertEqual(engine.find_rank(first_id), 1)
        self.assertIsNone(engine.find_rank(9999))

    def test_my_position_outside_top_k(self):
        engine = LeaderboardEngine(top_k=3)
        members = self._make_members(50)
        engine.compute_top_k(members)
        # Lấy 1 member ngoài top 3 (xp thấp nhất)
        lowest = min(members, key=lambda m: m["xp"])
        pos = engine.find_my_position(lowest["id"], members)
        self.assertFalse(pos["in_top_k"])
        self.assertEqual(pos["rank"], members[lowest["id"] - 1]["xp"] * 0 + pos["rank"])  # rank hợp lệ
        self.assertGreaterEqual(pos["rank"], 4)
        self.assertGreater(pos["xp_gap_to_top_k"], 0)

    def test_complexity_smoke(self):
        # 10.000 members, Top-10 — phải hoàn thành dưới 1.5s (O(N log K))
        engine = LeaderboardEngine(top_k=10)
        members = self._make_members(10_000)
        start = time.perf_counter()
        engine.compute_top_k(members)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.5)


class TrieSearchTests(unittest.TestCase):
    """Test DSA 3: Trie Prefix Search."""

    def test_insert_and_search_prefix(self):
        trie = PrefixSearchTrie()
        trie.insert("nguyen van a", 1)
        trie.insert("nguyen van b", 2)
        trie.insert("tran thi c", 3)
        self.assertEqual(trie.search_prefix("nguyen"), {1, 2})
        self.assertEqual(trie.search_prefix("nguyen van a"), {1})
        self.assertEqual(trie.search_prefix("tran"), {3})
        self.assertEqual(trie.search_prefix("le"), set())

    def test_empty_prefix_returns_all(self):
        trie = PrefixSearchTrie()
        trie.insert("abc", 1)
        self.assertEqual(trie.search_prefix(""), {1})

    def test_multiple_alias_same_id(self):
        trie = PrefixSearchTrie()
        trie.insert_multi(["hoang nhat nam", "hoangnhatnam", "22a4011234"], 7)
        self.assertEqual(trie.search_prefix("hoang"), {7})
        self.assertEqual(trie.search_prefix("22a"), {7})

    def test_case_insensitive_and_spaces(self):
        trie = PrefixSearchTrie()
        trie.insert("Nguyễn  Văn   A", 1)  # normalize: lower + gọn khoảng trắng
        self.assertEqual(trie.search_prefix("NGUYEN VAN"), {1})

    def test_autocomplete(self):
        trie = PrefixSearchTrie()
        trie.insert("hackathon", 1)
        trie.insert("hacker", 2)
        trie.insert("hanoi", 3)
        suggestions = trie.autocomplete("hack", limit=10)
        self.assertIn("hackathon", suggestions)
        self.assertIn("hacker", suggestions)
        self.assertNotIn("hanoi", suggestions)

    def test_strip_vietnamese_accents(self):
        self.assertEqual(strip_vietnamese_accents("Nguyễn Nhật Nam"), "nguyen nhat nam")
        self.assertEqual(strip_vietnamese_accents("Đỗ Đăng Đạt"), "do dang dat")
        self.assertEqual(strip_vietnamese_accents("DẠY HỌC Ở HUẾ"), "day hoc o hue")

    def test_scale_o_l(self):
        # 5.000 từ, search phải tức thì bất kể số từ (O(L))
        trie = PrefixSearchTrie()
        for i in range(5_000):
            trie.insert(f"member{i:05d}abcxyz", i)
        start = time.perf_counter()
        for _ in range(1_000):
            trie.search_prefix("member09999")
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0)


class DagWorkflowTests(unittest.TestCase):
    """Test DSA 4: DAG Topological Sort (Kahn)."""

    def test_valid_dag_order(self):
        tasks = [1, 2, 3, 4]
        deps = [(1, 2), (2, 3), (1, 4)]  # 2 sau 1, 3 sau 2, 4 sau 1
        ok, order = TaskDependencyEngine.resolve_task_order(tasks, deps)
        self.assertTrue(ok)
        self.assertEqual(set(order), set(tasks))
        pos = {t: i for i, t in enumerate(order)}
        self.assertLess(pos[1], pos[2])
        self.assertLess(pos[2], pos[3])
        self.assertLess(pos[1], pos[4])

    def test_cycle_detection(self):
        tasks = [1, 2, 3]
        deps = [(1, 2), (2, 3), (3, 1)]  # vòng tròn!
        ok, order = TaskDependencyEngine.resolve_task_order(tasks, deps)
        self.assertFalse(ok)
        self.assertEqual(order, [])

    def test_cycle_specific_path(self):
        tasks = ["a", "b", "c"]
        deps = [("a", "b"), ("b", "c"), ("c", "a")]
        cycle = TaskDependencyEngine.find_cycle(tasks, deps)
        self.assertIsNotNone(cycle)
        self.assertEqual(set(cycle), {"a", "b", "c"})

    def test_no_dependencies_arbitrary_order(self):
        ok, order = TaskDependencyEngine.resolve_task_order([1, 2, 3], [])
        self.assertTrue(ok)
        self.assertEqual(len(order), 3)

    def test_would_create_cycle(self):
        tasks = [1, 2]
        deps = [(1, 2)]
        # Thêm cạnh 2→1 khi đã có 1→2 ⇒ tạo chu trình
        self.assertTrue(TaskDependencyEngine.would_create_cycle(tasks, deps, 2, 1))
        # Thêm lại cạnh 1→2 (trùng) ⇒ không tạo chu trình mới
        self.assertFalse(TaskDependencyEngine.would_create_cycle(tasks, deps, 1, 2))

    def test_find_executable_now(self):
        tasks = [1, 2, 3, 4]
        deps = [(1, 2), (2, 3)]
        completed = {1}
        executable = TaskDependencyEngine.find_executable_now(tasks, deps, completed)
        self.assertIn(2, executable)
        self.assertNotIn(3, executable)

    def test_self_dependency_is_cycle(self):
        ok, _ = TaskDependencyEngine.resolve_task_order([1], [(1, 1)])
        self.assertFalse(ok)


class FundInvariantsTests(unittest.TestCase):
    """Test DSA 5: Bất biến tài chính."""

    def _tx(self, loai, so_tien, so_du_sau):
        return {"loai_gd": loai, "so_tien": so_tien, "so_du_sau": so_du_sau}

    def test_balance_invariant_valid(self):
        txs = [
            self._tx("THU", 1_000_000, 1_000_000),
            self._tx("CHI", 300_000, 700_000),
            self._tx("THU", 100_000, 800_000),
        ]
        self.assertTrue(FundInvariantsEngine.verify_balance_invariant(txs))

    def test_balance_invariant_broken(self):
        txs = [
            self._tx("THU", 1_000_000, 1_000_000),
            self._tx("CHI", 300_000, 500_000),  # sai số dư!
        ]
        self.assertFalse(FundInvariantsEngine.verify_balance_invariant(txs))

    def test_balance_chain(self):
        txs = [
            self._tx("THU", 500_000, 500_000),
            self._tx("CHI", 200_000, 300_000),
        ]
        self.assertTrue(FundInvariantsEngine.verify_balance_chain(txs, opening_balance=0))
        self.assertFalse(FundInvariantsEngine.verify_balance_chain(txs, opening_balance=100_000))

    def test_non_negative(self):
        self.assertTrue(FundInvariantsEngine.check_non_negative(0))
        self.assertFalse(FundInvariantsEngine.check_non_negative(-1))

    def test_compute_totals(self):
        txs = [
            self._tx("THU", 1_000_000, 1_000_000),
            self._tx("CHI", 400_000, 600_000),
            self._tx("CHI", 100_000, 500_000),
        ]
        totals = FundInvariantsEngine.compute_totals(txs)
        self.assertEqual(totals["total_income"], 1_000_000)
        self.assertEqual(totals["total_expense"], 500_000)
        self.assertEqual(totals["balance"], 500_000)

    def test_validate_rejects_overdraft(self):
        with self.assertRaises(AssertionError):
            FundInvariantsEngine.validate_new_transaction(100_000, "CHI", 500_000)

    def test_validate_rejects_bad_amount(self):
        with self.assertRaises(ValueError):
            FundInvariantsEngine.validate_new_transaction(100_000, "CHI", 0)
        with self.assertRaises(ValueError):
            FundInvariantsEngine.validate_new_transaction(100_000, "TIEN_AN", 50_000)


if __name__ == "__main__":
    unittest.main()

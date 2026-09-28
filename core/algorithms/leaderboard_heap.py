"""
DSA 2: Min-Heap / PriorityQueue Leaderboard — O(N log K)
========================================================
Nghiệp vụ: Xếp hạng thi đua thời gian thực cho hàng trăm thành viên.

Cấu trúc:
- Min-Heap kích thước K=10 duy trì Top K cao nhất trong O(N log K)
  (thay vì sort toàn bộ bảng O(N log N)).
- Hash Map (dict) cho phép tra cứu vị trí (rank) tức thời O(1).
"""
import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(order=True)
class LeaderboardEntry:
    """Phần tử xếp hạng — chỉ so sánh theo xp (các trường khác bất biến sắp xếp)."""

    xp: int
    member_id: int = field(compare=False)
    name: str = field(compare=False)
    avatar: str = field(compare=False, default="")
    extra: dict = field(compare=False, default_factory=dict)


class LeaderboardEngine:
    """
    Engine bảng xếp hạng Top-K dùng Min-Heap + Hash Map tra cứu rank O(1).

    Độ phức tạp:
        - compute_top_k:  O(N log K) với N tổng thành viên.
        - find_rank:      O(1) nhờ hash map nội bộ.
    """

    def __init__(self, top_k: int = 10) -> None:
        if top_k <= 0:
            raise ValueError("top_k phải là số nguyên dương.")
        self.top_k: int = top_k
        self._rank_map: Dict[int, int] = {}       # member_id -> rank (1-based)
        self._top_sorted: List[LeaderboardEntry] = []
        self._total_members: int = 0

    # ------------------------------------------------------------------
    # API chính
    # ------------------------------------------------------------------
    def compute_top_k(self, members: List[dict]) -> List[dict]:
        """
        Trích xuất Top K thành viên có XP cao nhất bằng Min-Heap.

        Args:
            members: danh sách dict dạng {"id": int, "xp": int, "name": str, "avatar": str, ...}

        Returns:
            Danh sách Top K đã sắp giảm dần theo XP, dạng
            [{"rank": 1, "id": ..., "name": ..., "xp": ..., "avatar": ...}, ...]
        """
        heap: List[Tuple[int, int, dict]] = []  # (xp, member_id, member_dict)

        for m in members:
            self._total_members += 1
            entry: Tuple[int, int, dict] = (m["xp"], m["id"], m)
            if len(heap) < self.top_k:
                heapq.heappush(heap, entry)          # O(log K)
            elif entry[0] > heap[0][0]:
                heapq.heappushpop(heap, entry)       # O(log K) — thay thế phần tử nhỏ nhất

        # Sắp xếp lại Top K giảm dần theo XP (K log K, K ≪ N)
        top_sorted: List[Tuple[int, int, dict]] = sorted(heap, key=lambda x: x[0], reverse=True)

        result: List[dict] = []
        self._rank_map = {}
        for idx, (xp, member_id, payload) in enumerate(top_sorted, start=1):
            self._rank_map[member_id] = idx
            result.append(
                {
                    "rank": idx,
                    "id": member_id,
                    "name": payload.get("name", ""),
                    "xp": xp,
                    "avatar": payload.get("avatar", ""),
                    "extra": {
                        k: v
                        for k, v in payload.items()
                        if k not in ("id", "xp", "name", "avatar")
                    },
                }
            )
        self._top_sorted = [
            LeaderboardEntry(xp=xp, member_id=mid, name=p.get("name", ""), avatar=p.get("avatar", ""))
            for xp, mid, p in top_sorted
        ]
        return result

    # ------------------------------------------------------------------
    # Tra cứu rank O(1)
    # ------------------------------------------------------------------
    def find_rank(self, member_id: int) -> Optional[int]:
        """Trả về rank của thành viên trong Top K, hoặc None nếu ngoài Top K."""
        return self._rank_map.get(member_id)

    def find_my_position(self, member_id: int, members: List[dict]) -> dict:
        """
        Xác định vị trí của `member_id` trong toàn bộ danh sách
        (kể cả khi nằm ngoài Top K) kèm khoảng cách XP tới Top K.

        Args:
            member_id: ID thành viên cần tra cứu.
            members: danh sách đầy đủ (giống compute_top_k).

        Returns:
            {"in_top_k": bool, "rank": int, "xp_gap_to_top_k": int}
        """
        # Tính ngưỡng XP của người cuối Top K hiện tại
        threshold_xp: int = 0
        if self._top_sorted:
            threshold_xp = self._top_sorted[-1].xp

        # Rank ngoài Top K = số người có XP cao hơn + 1
        my_xp: Optional[dict] = next((m for m in members if m["id"] == member_id), None)
        if my_xp is None:
            return {"in_top_k": False, "rank": self._total_members, "xp_gap_to_top_k": 0}

        higher: int = sum(1 for m in members if m["xp"] > my_xp["xp"])
        rank: int = higher + 1
        in_top: bool = member_id in self._rank_map
        gap: int = max(threshold_xp - my_xp["xp"] + 1, 0) if not in_top else 0
        return {"in_top_k": in_top, "rank": rank, "xp_gap_to_top_k": gap}

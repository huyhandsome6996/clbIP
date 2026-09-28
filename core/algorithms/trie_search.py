"""
DSA 3: Trie Prefix Autocomplete & Search — O(L)
===============================================
Nghiệp vụ: Tìm kiếm tức thời theo MSSV, Họ tên không dấu và Tiêu đề tài liệu
với độ phức tạp O(L) (L = độ dài từ khóa), độc lập với số lượng bản ghi N.

Cấu trúc: Cây tiền tố (Trie) — mỗi node lưu `children` và tập `data_ids`
các bản ghi đi qua node đó (hỗ trợ autocomplete gộp nhiều nguồn).
"""
from typing import Dict, List, Optional, Set


class TrieNode:
    """Một node trong cây tiền tố."""

    __slots__ = ("children", "is_end_of_word", "data_ids")

    def __init__(self) -> None:
        self.children: Dict[str, "TrieNode"] = {}
        self.is_end_of_word: bool = False
        self.data_ids: Set[int] = set()


class PrefixSearchTrie:
    """
    Cây tiền tố hỗ trợ insert nhiều "từ khóa" trỏ về cùng một bản ghi dữ liệu.

    Ví dụ: MemberProfile(id=7) được index bởi ["nguyen van a", "nguyenvana", "22a4011234"].
    """

    def __init__(self) -> None:
        self.root: TrieNode = TrieNode()
        self._indexed_words: int = 0
        self._all_ids: Set[int] = set()

    # ------------------------------------------------------------------
    # Chỉ số hóa
    # ------------------------------------------------------------------
    @staticmethod
    def normalize(word: str) -> str:
        """
        Chuẩn hóa: lower + bỏ dấu tiếng Việt + gọn khoảng trắng.
        Nhờ đó tìm kiếm khớp cả "Nguyễn Văn A" lẫn "nguyen van a".
        """
        return " ".join(strip_vietnamese_accents(word).split())

    def insert(self, word: str, data_id: int) -> None:
        """
        Chèn `word` vào trie và đánh dấu `data_id` trên toàn bộ đường đi.

        Độ phức tạp: O(len(word)).
        """
        node: TrieNode = self.root
        normalized: str = self.normalize(word)
        if not normalized:
            return
        for char in normalized:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            node.data_ids.add(data_id)
        node.is_end_of_word = True
        self._indexed_words += 1
        self._all_ids.add(data_id)

    def insert_multi(self, words: List[str], data_id: int) -> None:
        """Chèn nhiều alias cho cùng một bản ghi (VD: có dấu + không dấu + MSSV)."""
        for w in words:
            self.insert(w, data_id)

    # ------------------------------------------------------------------
    # Tìm kiếm
    # ------------------------------------------------------------------
    def search_prefix(self, prefix: str) -> Set[int]:
        """
        Trả về tập ID bản ghi khớp tiền tố — O(L).

        Returns:
            Tập data_id (có thể rỗng).
        """
        node: TrieNode = self._walk(prefix)
        if node is None:
            return set()
        if self.normalize(prefix) == "":
            # Prefix rỗng ⇒ trả về toàn bộ ID đã index
            return set(self._all_ids)
        return set(node.data_ids)

    def search_exact(self, word: str) -> Set[int]:
        """Trả về tập ID của từ khớp chính xác (kết thúc tại node cuối)."""
        node: TrieNode = self._walk(word)
        if node is None or not node.is_end_of_word:
            return set()
        return set(node.data_ids)

    def autocomplete(self, prefix: str, limit: int = 10) -> List[str]:
        """
        Gợi ý tối đa `limit` từ hoàn chỉnh bắt đầu bằng `prefix`
        (duyệt DFS từ node tiền tố).
        """
        start: TrieNode = self._walk(prefix)
        if start is None:
            return []
        results: List[str] = []
        self._dfs_collect(start, self.normalize(prefix), results, limit)
        return results

    # ------------------------------------------------------------------
    # Nội bộ
    # ------------------------------------------------------------------
    def _walk(self, prefix: str) -> Optional[TrieNode]:
        """Đi xuống trie theo prefix — O(L). Trả None nếu prefix không tồn tại."""
        node: TrieNode = self.root
        normalized: str = self.normalize(prefix)
        for char in normalized:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def _dfs_collect(
        self, node: TrieNode, current: str, results: List[str], limit: int
    ) -> None:
        """DFS thu thập các từ hoàn chỉnh tới khi đủ `limit`."""
        if len(results) >= limit:
            return
        if node.is_end_of_word:
            results.append(current)
        for char, child in sorted(node.children.items()):
            if len(results) >= limit:
                return
            self._dfs_collect(child, current + char, results, limit)

    @property
    def indexed_words(self) -> int:
        """Tổng số từ đã index (thống kê)."""
        return self._indexed_words


def strip_vietnamese_accents(text: str) -> str:
    """
    Bỏ dấu tiếng Việt: "Nguyễn Nhật Nam" → "nguyen nhat nam".
    Dùng unicodedata decomposition (NFD) rồi loại bỏ combining marks.
    """
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    # Ký tự đ/Đ chuyển về d/D
    without_marks = without_marks.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", without_marks).lower()

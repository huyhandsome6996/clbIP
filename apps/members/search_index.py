"""
Cache theo process cho PrefixSearchTrie thành viên (QA-Audit nhóm 5)
=====================================================================
Vấn đề: bản cũ dựng lại toàn bộ Trie ở MỖI request tìm kiếm — O(N·L) CPU +
full table scan mỗi lần gõ phím của autocomplete.

Giải pháp:
    1. Trie giữ ở module-level (mỗi process gunicorn một bản — tra cứu O(L)).
    2. Invalidation bằng version counter: post_save/post_delete của
       MemberProfile và User (mssv là khóa tìm kiếm) tăng counter; lần tra
       cứu kế tiếp thấy version lệch thì dựng lại lười (lazy rebuild).
    3. Thread-safe bằng Lock (gunicorn sync worker vẫn phục vụ request
       đồng thời trong cùng process qua thread khi bật gthread).

Chỉ dùng cho ĐỌC — mọi ghi luôn đi qua ORM/repository nên không có rủi ro
đọc cũ ghi mới ở tầng dữ liệu (chỉ tồn tại độ trễ <= 1 request sau khi có
thay đổi, và chỉ trong cùng process khi counter chưa tăng).
"""
import threading
from typing import Optional

from core.algorithms.trie_search import PrefixSearchTrie

_lock = threading.Lock()
_trie: Optional[PrefixSearchTrie] = None
_version: int = 0
_built_at_version: int = -1


def invalidate(**kwargs) -> None:
    """Tăng version counter — Trie sẽ được dựng lại ở lần tra cứu kế tiếp.

    Chấp nhận **kwargs để dùng trực tiếp làm signal receiver (post_save/
    post_delete gửi sender/instance/raw/using...).
    """
    global _version
    with _lock:
        _version += 1


def get_trie() -> PrefixSearchTrie:
    """Trả về Trie cache; dựng lại lười nếu dữ liệu đã đổi (O(L) tra cứu)."""
    global _trie, _built_at_version
    with _lock:
        if _trie is None or _built_at_version != _version:
            _trie = _build()
            _built_at_version = _version
        return _trie


def _build() -> PrefixSearchTrie:
    """Dựng Trie từ toàn bộ hồ sơ thành viên (khóa: họ tên + MSSV, bỏ dấu)."""
    from apps.members.repositories import DjangoMemberRepository  # noqa: PLC0415

    trie = PrefixSearchTrie()
    for profile in DjangoMemberRepository().iter_search_index_profiles():
        mssv = profile.user.mssv or ""
        words = {profile.ho_ten, mssv}
        trie.insert_multi([w for w in words if w], profile.pk)
    return trie

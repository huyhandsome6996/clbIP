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

QA-Audit đợt 2 — counter dùng chung đa worker (thiết kế như
apps/documents/search_index.py — xem docstring module đó cho đầy đủ lý do):
    - Counter lưu trong CACHE DÙNG CHUNG (DatabaseCache/Redis); sau `incr`
      phải `touch(timeout=None)` vì DatabaseCache.incr làm mất never-expire.
    - Ảnh trạng thái = (shared|None, local): rebuild khi BẤT KỶ thành phần
      đổi — không dùng max() để tránh mask invalidation chéo worker.
    - Cache hỏng → fallback counter trong process (hành vi cũ) — request
      không bao giờ lỗi vì hết cache.

Chỉ dùng cho ĐỌC — mọi ghi luôn đi qua ORM/repository nên không có rủi ro
đọc cũ ghi mới ở tầng dữ liệu (độ trễ tối đa = 1 request sau khi có thay
đổi, và chỉ khi cache dùng chung cũng không khả dụng).
"""
import threading
from typing import Optional, Tuple

from core.algorithms.trie_search import PrefixSearchTrie

_lock = threading.Lock()
_trie: Optional[PrefixSearchTrie] = None
_built_at: Tuple[Optional[int], int] = ()  # ảnh (shared|None, local) lúc dựng
_version: int = 0  # fallback trong process khi cache dùng chung không khả dụng

_VERSION_CACHE_KEY = "trie_version:members"


def _read_shared_version() -> Optional[int]:
    """Đọc counter dùng chung từ cache — None nếu cache hỏng hoặc chưa có key."""
    from django.core.cache import cache  # noqa: PLC0415

    try:
        value = cache.get(_VERSION_CACHE_KEY)
    except Exception:  # noqa: BLE001 — cache hỏng không được hỏng request
        return None
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _bump_shared_version() -> None:
    """Tăng counter dùng chung trong cache — mọi worker thấy và dựng lại.

    ⚠️ Chỉ gọi bên trong `invalidate()` khi đang giữ `_lock`. Sau `incr`
    phải `touch(None)` khôi phục never-expire (DatabaseCache.incr làm mất).
    Key chưa có → `ValueError` → `add`.
    """
    from django.core.cache import cache  # noqa: PLC0415

    try:
        try:
            cache.incr(_VERSION_CACHE_KEY)
            cache.touch(_VERSION_CACHE_KEY, timeout=None)
        except ValueError:
            cache.add(_VERSION_CACHE_KEY, _version + 1, timeout=None)
    except Exception:  # noqa: BLE001 — hết cache/DB hỏng → chỉ còn counter local
        pass


def _version_snapshot() -> Tuple[Optional[int], int]:
    """Ảnh trạng thái dữ liệu hiện tại: (shared|None, local) — xem docstring module."""
    return (_read_shared_version(), _version)


def invalidate(**kwargs) -> None:
    """Tăng version counter — Trie sẽ được dựng lại ở lần tra cứu kế tiếp.

    Chấp nhận **kwargs để dùng trực tiếp làm signal receiver (post_save/
    post_delete gửi sender/instance/raw/using...).
    Tăng cả counter local (fallback) lẫn counter dùng chung (đa worker).
    """
    global _version
    with _lock:
        _version += 1
        _bump_shared_version()


def get_trie() -> PrefixSearchTrie:
    """Trả về Trie cache; dựng lại lười nếu dữ liệu đã đổi (O(L) tra cứu)."""
    global _trie, _built_at
    with _lock:
        snapshot = _version_snapshot()
        if _trie is None or _built_at != snapshot:
            _trie = _build()
            _built_at = snapshot
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

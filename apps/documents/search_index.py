"""
Cache theo process cho PrefixSearchTrie tài liệu (QA-Audit nhóm 5)
===================================================================
Tương tự apps/members/search_index.py — nhưng có 2 vùng Trie theo phạm vi:
    - Trie PUBLIC (cho thành viên thường): chỉ index tài liệu PUBLIC_MEMBER.
    - Trie FULL (cho BCN/ADMIN): index toàn bộ kho.

QA-Audit đợt 2 — 2 sửa chữa:
    1. `_built_at` tách theo SCOPE (dict): trước đây 2 scope dùng chung 1
       biến `_built_at_version` — khi tài liệu đổi rồi member tìm TRƯỚC,
       scope PUBLIC dựng lại và ghi version mới, khiến scope FULL của BCN
       bị coi là "còn mới" dù thực tế đã cũ (đã tái hiện: mong đợi full v2,
       nhận full v1).
    2. Version counter lưu trong CACHE DÙNG CHUNG (DatabaseCache/Redis —
       đã cấu hình ở settings): Procfile chạy nhiều worker gunicorn, trước
       đây `invalidate()` chỉ tăng biến trong process nhận ghi — các worker
       khác giữ index cũ đến khi restart.

Thiết kế đa worker (theo phản biện review đợt 2):
    - Trạng thái "đã dựng" của mỗi scope là ẢNH (snapshot) = (shared, local):
      rebuild khi BẤT KỶ thành phần nào đổi. So sánh max(shared, local) bị
      từ chối vì 2 dãy counter không so sánh được chéo process — worker có
      watermark local cao sẽ MASK invalidation của worker khác sau khi key
      cache bị reset; ảnh (shared, local) không bao giờ mask: bump của ai
      cũng làm snapshot lệch (bù lại có thể rebuild thừa 1 lần sau khi cache
      chết rồi sống lại — chấp nhận được, luôn đúng).
    - Sau `incr` phải `touch(timeout=None)`: DatabaseCache.incr của Django
      là get+set KHÔNG truyền timeout → TTL về default 300s, key counter
      chết sau 5 phút → mất đa worker. `touch(None)` khôi phục never-expire
      (Redis: PERSIST; DatabaseCache: expires=9999-12-31).
    - Cache hỏng (hết DB/Redis) → fallback counter trong process (hành vi
      cũ) — request KHÔNG BAO GIỜ lỗi vì hết cache.
    - Đã biết giới hạn (chấp nhận): incr trên DatabaseCache không nguyên tử
      tuyệt đối (get+set) — 2 worker bump đồng thời có thể gộp thành 1 bump;
      post_save bắn trước commit → worker khác có thể build nhầm dữ liệu cũ
      (cửa sổ cực nhỏ, tồn tại từ bản cũ; bump kế tiếp sẽ tự sửa).
"""
import threading
from typing import Dict, Optional, Tuple

from core.algorithms.trie_search import PrefixSearchTrie

_lock = threading.Lock()
_tries: Dict[str, PrefixSearchTrie] = {}
# scope → ảnh (shared_version|None, local_version) LÚC DỰNG (sửa P2-1: theo scope)
_built_at: Dict[str, Tuple[Optional[int], int]] = {}
_version: int = 0  # fallback trong process khi cache dùng chung không khả dụng

_VERSION_CACHE_KEY = "trie_version:documents"

SCOPE_PUBLIC = "public"   # thành viên thường — chỉ tài liệu PUBLIC_MEMBER
SCOPE_FULL = "full"       # BCN/ADMIN — toàn bộ kho


def _read_shared_version() -> Optional[int]:
    """Đọc counter dùng chung từ cache — None nếu cache hỏng hoặc chưa có key.

    Import cục bộ: tránh binding sớm vào connection cache khi app khởi động
    (override_settings trong test phải có hiệu lực).
    """
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

    ⚠️ Chỉ gọi bên trong `invalidate()` khi đang giữ `_lock` (đọc `_version`
    an toàn). `incr` nguyên tử trên Redis; DatabaseCache là get+set — lost
    update giữa 2 worker chỉ làm gộp 2 bump thành 1 (bump kế tiếp tự sửa,
    chấp nhận được cho invalidation token). Sau incr phải `touch(None)` để
    khôi phục never-expire mà DatabaseCache.incr làm mất (về default 300s).
    Key chưa có → `ValueError` → `add` (đua giữa 2 worker chỉ làm người thua
    bỏ qua lượt add đầu).
    """
    from django.core.cache import cache  # noqa: PLC0415

    try:
        try:
            cache.incr(_VERSION_CACHE_KEY)
            cache.touch(_VERSION_CACHE_KEY, timeout=None)  # giữ never-expire
        except ValueError:
            cache.add(_VERSION_CACHE_KEY, _version + 1, timeout=None)
    except Exception:  # noqa: BLE001 — hết cache/DB hỏng → chỉ còn counter local
        pass


def _version_snapshot() -> Tuple[Optional[int], int]:
    """Ảnh trạng thái dữ liệu hiện tại: (shared|None, local).

    So sánh CẢ HAI thành phần (không dùng max — xem docstring module):
    worker khác bump shared, hoặc chính process này ghi dữ liệu (local tăng
    nhưng shared bump thất bại) → ảnh lệch → rebuild đúng trong mọi trường
    hợp, không mask bump của ai.
    """
    return (_read_shared_version(), _version)


def invalidate(**kwargs) -> None:
    """Đánh dấu dữ liệu đã đổi — các Trie sẽ được dựng lại ở lần tra cứu kế tiếp.

    Chấp nhận **kwargs để dùng trực tiếp làm signal receiver (post_save/
    post_delete gửi sender/instance/raw/using...).
    Tăng cả counter local (fallback khi cache hỏng) lẫn counter dùng chung
    (đa worker).
    """
    global _version
    with _lock:
        _version += 1
        _bump_shared_version()


def get_trie(scope: str = SCOPE_PUBLIC) -> PrefixSearchTrie:
    """Trả về Trie theo phạm vi; dựng lại lười nếu dữ liệu đã đổi.

    So sánh `_built_at[scope]` (ảnh lúc dựng scope này) với ảnh hiện tại —
    KHÔNG dùng chung 1 biến cho cả 2 scope (sửa QA-Audit P2-1).
    """
    global _tries, _built_at
    if scope not in (SCOPE_PUBLIC, SCOPE_FULL):
        scope = SCOPE_PUBLIC
    with _lock:
        snapshot = _version_snapshot()
        if _built_at.get(scope) != snapshot or scope not in _tries:
            _tries[scope] = _build(scope)
            _built_at[scope] = snapshot
        return _tries[scope]


def _build(scope: str) -> PrefixSearchTrie:
    """Dựng Trie từ kho tài liệu theo phạm vi (tiêu đề + từng từ + tags)."""
    from typing import List  # noqa: PLC0415

    from apps.documents.models import Document  # noqa: PLC0415
    from apps.documents.repositories import DjangoDocumentRepository  # noqa: PLC0415

    if scope == SCOPE_FULL:
        scope_filter = None  # toàn bộ kho
    else:
        scope_filter = {"pham_vi": Document.PhamVi.PUBLIC_MEMBER}

    trie = PrefixSearchTrie()
    for doc in DjangoDocumentRepository().iter_indexable_documents(scope_filter):
        aliases: List[str] = [doc.tieu_de, *doc.tieu_de.split()]
        aliases += [tag.strip() for tag in (doc.tags or "").split(",") if tag.strip()]
        trie.insert_multi(aliases, doc.pk)
    return trie

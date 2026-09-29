"""
Cache theo process cho PrefixSearchTrie tài liệu (QA-Audit nhóm 5)
===================================================================
Tương tự apps/members/search_index.py — nhưng có 2 vùng Trie theo phạm vi:
    - Trie PUBLIC (cho thành viên thường): chỉ index tài liệu PUBLIC_MEMBER.
    - Trie FULL (cho BCN/ADMIN): index toàn bộ kho.
Cả hai dùng chung 1 version counter — mọi post_save/post_delete của Document
đều vô hiệu hóa, lần tìm kiếm kế tiếp dựng lại lười vùng cần dùng.
"""
import threading
from typing import Dict, Optional

from core.algorithms.trie_search import PrefixSearchTrie

_lock = threading.Lock()
_tries: Dict[str, PrefixSearchTrie] = {}
_version: int = 0
_built_at_version: int = -1

SCOPE_PUBLIC = "public"   # thành viên thường — chỉ tài liệu PUBLIC_MEMBER
SCOPE_FULL = "full"       # BCN/ADMIN — toàn bộ kho


def invalidate(**kwargs) -> None:
    """Tăng version counter — các Trie sẽ được dựng lại ở lần tra cứu kế tiếp.

    Chấp nhận **kwargs để dùng trực tiếp làm signal receiver (post_save/
    post_delete gửi sender/instance/raw/using...).
    """
    global _version
    with _lock:
        _version += 1


def get_trie(scope: str = SCOPE_PUBLIC) -> PrefixSearchTrie:
    """Trả về Trie theo phạm vi; dựng lại lười nếu dữ liệu đã đổi."""
    global _tries, _built_at_version
    if scope not in (SCOPE_PUBLIC, SCOPE_FULL):
        scope = SCOPE_PUBLIC
    with _lock:
        if _built_at_version != _version or scope not in _tries:
            _tries[scope] = _build(scope)
            _built_at_version = _version
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

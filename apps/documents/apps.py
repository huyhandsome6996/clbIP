from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"
    verbose_name = "Documents"

    def ready(self) -> None:
        """Kết nối signals vô hiệu hóa Trie tìm kiếm (QA-Audit nhóm 5)."""
        from django.db.models.signals import post_delete, post_save

        from apps.documents.models import Document
        from apps.documents.search_index import invalidate as invalidate_doc_trie

        post_save.connect(invalidate_doc_trie, sender=Document, dispatch_uid="trie_doc_save")
        post_delete.connect(invalidate_doc_trie, sender=Document, dispatch_uid="trie_doc_del")

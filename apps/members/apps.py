from django.apps import AppConfig


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.members"
    verbose_name = "Members"

    def ready(self) -> None:
        """Kết nối signals vô hiệu hóa Trie tìm kiếm (QA-Audit nhóm 5)."""
        from django.db.models.signals import post_delete, post_save

        from apps.authentication.models import User
        from apps.members.models import MemberProfile
        from apps.members.search_index import invalidate as invalidate_member_trie

        # mssv sống trên User → cả User lẫn MemberProfile đều phải invalidate
        post_save.connect(invalidate_member_trie, sender=MemberProfile, dispatch_uid="trie_member_save")
        post_delete.connect(invalidate_member_trie, sender=MemberProfile, dispatch_uid="trie_member_del")
        post_save.connect(invalidate_member_trie, sender=User, dispatch_uid="trie_user_save")
        post_delete.connect(invalidate_member_trie, sender=User, dispatch_uid="trie_user_del")

"""Seed the 'Doctors' group (issue #15 acceptance criterion: a doctor-facing
summary must be "viewable by a doctor-role user") with the built-in
`view_chatsession` permission Django already generates for the `ChatSession`
model -- mirrors `review_portal`'s `0003_seed_reviewers_group.py` exactly.

Reversible: removing the group on a rollback doesn't touch ChatSession rows.
"""
from django.apps import apps as live_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

DOCTORS_GROUP = "Doctors"
PERMISSION_CODENAMES = ["view_chatsession"]


def create_doctors_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ChatSession = apps.get_model("chat_intake", "ChatSession")
    content_type = ContentType.objects.get_for_model(ChatSession)

    # Default model permissions are normally created by a post_migrate
    # signal handler that only fires after the *entire* `migrate` run
    # finishes -- not incrementally after each migration. This migration
    # needs `view_chatsession` right now, so create it explicitly against
    # the historical model state (Django's documented workaround for a data
    # migration that depends on default permissions).
    create_permissions(live_apps.get_app_config("chat_intake"), apps=apps, verbosity=0)

    group, _ = Group.objects.get_or_create(name=DOCTORS_GROUP)
    permissions = Permission.objects.filter(
        content_type=content_type, codename__in=PERMISSION_CODENAMES
    )
    group.permissions.set(permissions)


def delete_doctors_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=DOCTORS_GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("chat_intake", "0003_chatsession_summary_text"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_doctors_group, delete_doctors_group),
    ]

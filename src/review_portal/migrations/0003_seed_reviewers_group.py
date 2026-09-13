"""Seed the 'Reviewers' group (issue #7 acceptance criterion: "Reviewer
role/permission groups are ported from clinical-ai-review-platform" — that
repo never got past planning this in its README/docs/architecture.md, so
there's no code to port; this is the real implementation) with the
built-in `change_reviewitem`/`view_reviewitem` permissions Django already
generates for the `ReviewItem` model. Anyone in this group can decide
(accept/reject) an item; everyone else gets a 403 from the decide view.

Reversible: removing the group on a rollback doesn't touch ReviewItem rows.
"""
from django.apps import apps as live_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations


REVIEWERS_GROUP = "Reviewers"
PERMISSION_CODENAMES = ["change_reviewitem", "view_reviewitem"]


def create_reviewers_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ReviewItem = apps.get_model("review_portal", "ReviewItem")
    content_type = ContentType.objects.get_for_model(ReviewItem)

    # Default model permissions (add/change/delete/view_reviewitem) are
    # normally created by a post_migrate signal handler that only fires
    # after the *entire* `migrate` run finishes -- not incrementally after
    # each migration. This migration needs them right now, so create them
    # explicitly against the historical model state (Django's documented
    # workaround for a data migration that depends on default permissions).
    create_permissions(live_apps.get_app_config("review_portal"), apps=apps, verbosity=0)

    group, _ = Group.objects.get_or_create(name=REVIEWERS_GROUP)
    permissions = Permission.objects.filter(
        content_type=content_type, codename__in=PERMISSION_CODENAMES
    )
    group.permissions.set(permissions)


def delete_reviewers_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=REVIEWERS_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("review_portal", "0002_reviewitem_error_category"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_reviewers_group, delete_reviewers_group),
    ]

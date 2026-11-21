"""The portal now has a single evaluation: the Pre Assessment.

Deletes Session 1-5 and Post Session (with their questions and attempts) and
renames "Pre Session Evaluation" to "Pre Assessment". Reversing recreates the
removed evaluations empty (deleted questions/attempts cannot be restored).
"""

from django.db import migrations

REMOVED = [
    (2, "session-1", "Session 1 Evaluation"),
    (3, "session-2", "Session 2 Evaluation"),
    (4, "session-3", "Session 3 Evaluation"),
    (5, "session-4", "Session 4 Evaluation"),
    (6, "session-5", "Session 5 Evaluation"),
    (7, "post-session", "Post Session Evaluation"),
]


def keep_only_pre(apps, schema_editor):
    Evaluation = apps.get_model("portal", "Evaluation")
    Evaluation.objects.filter(slug__in=[slug for _, slug, _ in REMOVED]).delete()
    Evaluation.objects.filter(slug="pre-session").update(title="Pre Assessment")


def restore(apps, schema_editor):
    Evaluation = apps.get_model("portal", "Evaluation")
    Evaluation.objects.filter(slug="pre-session").update(title="Pre Session Evaluation")
    for order, slug, title in REMOVED:
        Evaluation.objects.get_or_create(slug=slug, defaults={"title": title, "order": order})


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0004_portalprofile_certificate_enabled"),
    ]

    operations = [
        migrations.RunPython(keep_only_pre, restore),
    ]

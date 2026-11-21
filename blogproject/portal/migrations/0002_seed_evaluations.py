"""Creates the 7 fixed evaluations, in the order users unlock them."""

from django.db import migrations

EVALUATIONS = [
    (1, "pre-session", "Pre Session Evaluation"),
    (2, "session-1", "Session 1 Evaluation"),
    (3, "session-2", "Session 2 Evaluation"),
    (4, "session-3", "Session 3 Evaluation"),
    (5, "session-4", "Session 4 Evaluation"),
    (6, "session-5", "Session 5 Evaluation"),
    (7, "post-session", "Post Session Evaluation"),
]


def create_evaluations(apps, schema_editor):
    Evaluation = apps.get_model("portal", "Evaluation")
    for order, slug, title in EVALUATIONS:
        Evaluation.objects.update_or_create(slug=slug, defaults={"order": order, "title": title})


def remove_evaluations(apps, schema_editor):
    Evaluation = apps.get_model("portal", "Evaluation")
    Evaluation.objects.filter(slug__in=[slug for _, slug, _ in EVALUATIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_evaluations, remove_evaluations),
    ]

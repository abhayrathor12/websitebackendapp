"""Stored certificate ID per participant (random, e.g. TVA-MC26-7K3F9Q).
Existing participants get one here."""

import secrets

from django.db import migrations, models

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # same as portal/certificate.py


def new_id():
    return "TVA-MC26-" + "".join(secrets.choice(ALPHABET) for _ in range(6))


def fill_ids(apps, schema_editor):
    PortalProfile = apps.get_model("portal", "PortalProfile")
    used = set()
    for profile in PortalProfile.objects.all():
        cert_id = new_id()
        while cert_id in used:
            cert_id = new_id()
        used.add(cert_id)
        profile.certificate_id = cert_id
        profile.save(update_fields=["certificate_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0006_knowledgecheck"),
    ]

    operations = [
        migrations.AddField(
            model_name="portalprofile",
            name="certificate_id",
            field=models.CharField(default="", editable=False, max_length=20),
            preserve_default=False,
        ),
        migrations.RunPython(fill_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="portalprofile",
            name="certificate_id",
            field=models.CharField(editable=False, max_length=20, unique=True),
        ),
    ]

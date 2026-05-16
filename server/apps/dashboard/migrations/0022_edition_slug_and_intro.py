# Add a URL slug + a rich-text registration intro to Edition.
#
# The slug is added straight away as unique+nullable (a unique index over
# all-NULL existing rows is fine in Postgres), then backfilled with unique
# slugs derived from the edition name, then only flipped to NOT NULL.
#
# Note: do NOT add it first as a plain (db_index) SlugField and then
# AlterField to unique=True — on Postgres that makes the schema editor
# create the varchar_pattern_ops "<col>_like" index twice within the same
# migration ("relation ..._like already exists"), which crash-loops the
# container via the entrypoint migrate. Creating it unique up-front creates
# every index exactly once; the final AlterField only changes NULL→NOT NULL
# (no index churn).

from django.db import migrations, models
from django.utils.text import slugify


def backfill_edition_slugs(apps, schema_editor):
    Edition = apps.get_model("dashboard", "Edition")
    used = set()
    for ed in Edition.objects.order_by("pk"):
        base = slugify(ed.name) or "editie"
        slug = base
        n = 2
        while (
            slug in used
            or Edition.objects.exclude(pk=ed.pk).filter(slug=slug).exists()
        ):
            slug = f"{base}-{n}"
            n += 1
        ed.slug = slug
        used.add(slug)
        ed.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0021_skip_location_check'),
    ]

    operations = [
        migrations.AddField(
            model_name='edition',
            name='slug',
            field=models.SlugField(max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='edition',
            name='registration_intro',
            field=models.TextField(
                blank=True,
                default='',
                help_text=(
                    'Rich-text intro shown on the public registration page. '
                    'Sanitised server-side before storing.'
                ),
            ),
        ),
        migrations.RunPython(
            backfill_edition_slugs,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='edition',
            name='slug',
            field=models.SlugField(
                max_length=255,
                unique=True,
                blank=True,
                help_text=(
                    'Used in the public registration URL. Leave blank to '
                    'auto-generate from the name.'
                ),
            ),
        ),
    ]

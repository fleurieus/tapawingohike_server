# Replace the gallery-level `gallery_show_immediately` flag with a
# per-destination `skip_location_check`. The old flag only worked when the
# gallery had a destination and was effectively a "treat this destination as
# reached without GPS" — which is a property of the destination, not the
# gallery. The new flag generalises to any routepart type and composes with
# `confirm_by_user` (tap-to-continue vs auto-advance).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0020_add_gallery_show_immediately'),
    ]

    operations = [
        migrations.AddField(
            model_name='destination',
            name='skip_location_check',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Skip the GPS-radius check: the app treats this destination "
                    "as reached immediately after the previous routepart "
                    "completes. Combine with 'confirm by user' for a "
                    "tap-to-continue screen, or leave that off to auto-advance. "
                    "Use for in-between info/gallery screens."
                ),
            ),
        ),
        migrations.RemoveField(
            model_name='routepart',
            name='gallery_show_immediately',
        ),
        migrations.RemoveField(
            model_name='teamroutepart',
            name='gallery_show_immediately',
        ),
    ]

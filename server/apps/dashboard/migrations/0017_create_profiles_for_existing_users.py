from django.db import migrations


def create_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("dashboard", "UserProfile")
    for user in User.objects.all():
        UserProfile.objects.get_or_create(user=user)


def remove_profiles(apps, schema_editor):
    UserProfile = apps.get_model("dashboard", "UserProfile")
    UserProfile.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0016_add_user_profile"),
    ]

    operations = [
        migrations.RunPython(create_profiles, remove_profiles),
    ]

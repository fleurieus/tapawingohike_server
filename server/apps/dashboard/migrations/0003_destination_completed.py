# Generated by Django 4.2.1 on 2023-08-02 10:11

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0002_teamroutepart_completed"),
    ]

    operations = [
        migrations.AddField(
            model_name="destination",
            name="completed",
            field=models.BooleanField(default=False),
        ),
    ]

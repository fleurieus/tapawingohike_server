from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0013_add_messaging_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="image",
            field=models.ImageField(
                blank=True,
                help_text="Optional image attachment (max 5 MB, JPG/PNG)",
                null=True,
                upload_to="messages/",
            ),
        ),
        migrations.AlterField(
            model_name="message",
            name="text",
            field=models.TextField(blank=True, default=""),
        ),
    ]

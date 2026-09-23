import uuid

from django.db import migrations, models
from django.utils import timezone


def populate_usernames(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    used = set(User.objects.exclude(username__isnull=True).values_list("username", flat=True))
    for user in User.objects.order_by("created_at"):
        base = (user.email.split("@", 1)[0] or "user")[:140]
        candidate = base
        suffix = 1
        while candidate in used:
            suffix += 1
            candidate = f"{base[:140-len(str(suffix))]}-{suffix}"
        user.username = candidate
        user.save(update_fields=["username"])
        used.add(candidate)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.AddField(model_name="user", name="username", field=models.CharField(max_length=150, null=True)),
        migrations.AddField(
            model_name="user",
            name="date_joined",
            field=models.DateTimeField(auto_now_add=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(populate_usernames, migrations.RunPython.noop),
        migrations.AlterField(model_name="user", name="username", field=models.CharField(max_length=150, unique=True)),
        migrations.RemoveField(model_name="user", name="roles"),
        migrations.RemoveField(model_name="user", name="moodle_user_id"),
        migrations.DeleteModel(name="UserRole"),
        migrations.DeleteModel(name="Role"),
        migrations.AlterModelOptions(
            name="user",
            options={
                "ordering": ["email"],
                "permissions": [
                    ("manage_users", "Can manage users"),
                    ("manage_permissions", "Can manage groups and permissions"),
                    ("bulk_import_students", "Can bulk import students"),
                ],
            },
        ),
    ]

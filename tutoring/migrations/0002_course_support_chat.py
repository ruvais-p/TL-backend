import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0002_migrate_legacy_enrollments"),
        ("tutoring", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseSupportConversation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("CLOSED", "Closed")], db_index=True, default="OPEN", max_length=12)),
                ("last_sequence", models.PositiveBigIntegerField(default=0)),
                ("last_message_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("course_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="support_conversations", to="curriculum.courseversion")),
                ("opened_from_enrollment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="support_conversations_opened", to="students.enrollment")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="course_support_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-last_message_at", "-created_at"],
                "permissions": [
                    ("reply_to_assigned_course_support_chats", "Can reply to assigned course support chats"),
                    ("view_all_course_support_chats", "Can view all course support chats"),
                    ("close_course_support_chats", "Can close course support chats"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="coursesupportconversation",
            constraint=models.UniqueConstraint(fields=("student", "course_version"), name="unique_student_course_support_conversation"),
        ),
        migrations.AddIndex(model_name="coursesupportconversation", index=models.Index(fields=["student", "course_version"], name="support_conv_student_ver_idx")),
        migrations.AddIndex(model_name="coursesupportconversation", index=models.Index(fields=["status", "last_message_at"], name="support_conv_status_recent_idx")),
        migrations.CreateModel(
            name="CourseSupportMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sender_role", models.CharField(choices=[("STUDENT", "Student"), ("TEACHER", "Teacher"), ("ACADEMIC_MANAGER", "Academic manager"), ("ADMIN", "Administrator")], max_length=24)),
                ("sequence", models.PositiveBigIntegerField()),
                ("client_message_id", models.UUIDField()),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="support_messages", to="tutoring.coursesupportconversation")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="course_support_messages", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["sequence"]},
        ),
        migrations.AddConstraint(model_name="coursesupportmessage", constraint=models.UniqueConstraint(fields=("conversation", "sequence"), name="unique_support_message_sequence")),
        migrations.AddConstraint(model_name="coursesupportmessage", constraint=models.UniqueConstraint(fields=("sender", "client_message_id"), name="unique_support_sender_client_message")),
        migrations.AddIndex(model_name="coursesupportmessage", index=models.Index(fields=["conversation", "sequence"], name="support_msg_conv_seq_idx")),
        migrations.CreateModel(
            name="CourseSupportReadState",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("last_read_sequence", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="read_states", to="tutoring.coursesupportconversation")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="course_support_read_states", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="coursesupportreadstate", constraint=models.UniqueConstraint(fields=("conversation", "user"), name="unique_support_read_state")),
        migrations.AddIndex(model_name="coursesupportreadstate", index=models.Index(fields=["user", "conversation"], name="support_read_user_conv_idx")),
        migrations.CreateModel(
            name="CourseSupportSocketTicket",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("portal", models.CharField(choices=[("staff", "Staff"), ("learner", "Learner")], max_length=12)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="course_support_socket_tickets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="coursesupportsocketticket", index=models.Index(fields=["expires_at", "consumed_at"], name="support_ticket_expiry_idx")),
    ]

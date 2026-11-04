from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tutoring.models import CourseChatSession
from tutoring.purge import delete_in_batches


class Command(BaseCommand):
    help = "Delete course chatbot sessions and messages older than the configured retention window."

    def handle(self, *args, **options):
        retention_days = settings.COURSE_CHAT_RETENTION_DAYS
        if retention_days < 1:
            raise CommandError("COURSE_CHAT_RETENTION_DAYS must be at least 1.")
        cutoff = timezone.now() - timedelta(days=retention_days)
        sessions = CourseChatSession.objects.filter(updated_at__lt=cutoff)
        count = delete_in_batches(sessions)
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} expired course chat sessions."))

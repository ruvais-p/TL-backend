from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from tutoring.models import CourseSupportConversation, CourseSupportSocketTicket


class Command(BaseCommand):
    help = "Delete expired course-support conversations and stale single-use socket tickets."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        retention_days = settings.COURSE_SUPPORT_CHAT_RETENTION_DAYS
        ticket_cleanup_hours = settings.COURSE_SUPPORT_CHAT_TICKET_CLEANUP_HOURS
        if retention_days < 1:
            raise CommandError("COURSE_SUPPORT_CHAT_RETENTION_DAYS must be at least 1.")
        if ticket_cleanup_hours < 0:
            raise CommandError("COURSE_SUPPORT_CHAT_TICKET_CLEANUP_HOURS cannot be negative.")

        now = timezone.now()
        conversation_cutoff = now - timedelta(days=retention_days)
        ticket_cutoff = now - timedelta(hours=ticket_cleanup_hours)
        conversations = CourseSupportConversation.objects.filter(
            Q(last_message_at__lt=conversation_cutoff)
            | Q(last_message_at__isnull=True, updated_at__lt=conversation_cutoff)
        )
        tickets = CourseSupportSocketTicket.objects.filter(
            Q(expires_at__lt=now) | Q(consumed_at__isnull=False, consumed_at__lt=ticket_cutoff)
        )
        conversation_count = conversations.count()
        ticket_count = tickets.count()

        if not options["dry_run"]:
            conversations.delete()
            tickets.delete()

        action = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(self.style.SUCCESS(
            f"{action} {conversation_count} expired support conversations and {ticket_count} stale socket tickets."
        ))

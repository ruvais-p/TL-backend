import hashlib
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import CourseSupportSocketTicket
from .services import support_socket_portal_allowed


def _consume_ticket_sync(raw_token):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with transaction.atomic():
        ticket = CourseSupportSocketTicket.objects.select_for_update().select_related("user").filter(
            token_hash=token_hash,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
            user__is_active=True,
        ).first()
        if ticket is None or not support_socket_portal_allowed(
            user=ticket.user,
            portal=ticket.portal,
        ):
            return None
        ticket.consumed_at = timezone.now()
        ticket.save(update_fields=["consumed_at"])
        return ticket.user, ticket.portal


_consume_ticket = database_sync_to_async(_consume_ticket_sync)


class SupportSocketTicketMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not settings.COURSE_SUPPORT_CHAT_ENABLED:
            await send({"type": "websocket.close", "code": 4403})
            return
        try:
            values = parse_qs(scope.get("query_string", b"").decode("ascii"), strict_parsing=True)
            tokens = values.get("ticket", [])
            raw_token = tokens[0] if len(tokens) == 1 and tokens[0] else None
        except (UnicodeDecodeError, ValueError):
            raw_token = None
        identity = await _consume_ticket(raw_token) if raw_token else None
        if identity is None:
            await send({"type": "websocket.close", "code": 4401})
            return
        scope = dict(scope)
        scope["user"], scope["support_portal"] = identity
        await self.app(scope, receive, send)

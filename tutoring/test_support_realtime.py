import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

from channels.security.websocket import OriginValidator
from channels.layers import InMemoryChannelLayer, channel_layers
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.constants import GroupName
from accounts.models import User
from .middleware import SupportSocketTicketMiddleware, _consume_ticket_sync
from .models import CourseSupportSocketTicket
from .routing import websocket_urlpatterns
from .services import issue_support_socket_ticket
from .consumers import CourseSupportConsumer, _claim_connection, _release_connection


TEST_CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


class ProtocolHarnessConsumer(CourseSupportConsumer):
    async def connect(self):
        self.connection_claimed = False
        await self.accept()

    async def disconnect(self, close_code):
        pass


@override_settings(
    COURSE_SUPPORT_CHAT_ENABLED=True,
    COURSE_SUPPORT_CHAT_ALLOWED_ORIGINS=["http://localhost:8080"],
    CHANNEL_LAYERS=TEST_CHANNEL_LAYERS,
)
class CourseSupportConnectionTests(TestCase):
    def setUp(self):
        channel_layers.backends = {}
        call_command("setup_groups", verbosity=0)
        self.student = User.objects.create_user(email="socket-student@example.com", password="pass12345")
        self.student.groups.add(self.group(GroupName.STUDENT))
        self.accepted_scopes = []

        async def terminal(scope, receive, send):
            await receive()
            self.accepted_scopes.append(scope)
            await send({"type": "websocket.accept"})

        self.test_application = SupportSocketTicketMiddleware(terminal)

    @staticmethod
    def group(name):
        from django.contrib.auth.models import Group

        return Group.objects.get(name=name)

    def communicator(self, raw_ticket, origin=b"http://localhost:8080"):
        return WebsocketCommunicator(
            self.test_application,
            f"/ws/course-support/?ticket={raw_ticket}",
            headers=[(b"origin", origin), (b"host", b"localhost")],
        )

    def test_valid_ticket_connects_once_and_is_bound_to_user(self):
        _ticket, raw_token = issue_support_socket_ticket(user=self.student, portal="learner")

        async def scenario():
            first = self.communicator(raw_token)
            connected, _ = await first.connect(timeout=5)
            self.assertTrue(connected)

        with patch(
            "tutoring.middleware._consume_ticket",
            new=AsyncMock(return_value=(self.student, "learner")),
        ), patch(
            "tutoring.consumers._claim_connection_async",
            new=AsyncMock(return_value=True),
        ), patch(
            "tutoring.consumers._release_connection_async",
            new=AsyncMock(),
        ):
            asyncio.run(scenario())
        self.assertEqual(self.accepted_scopes[0]["user"], self.student)
        self.assertEqual(self.accepted_scopes[0]["support_portal"], "learner")

    def test_asgi_route_matches_only_the_support_socket_path(self):
        route = websocket_urlpatterns[0].pattern
        self.assertIsNotNone(route.match("ws/course-support/"))
        self.assertIsNone(route.match("ws/other/"))

    def test_ticket_is_consumed_once_and_bound_to_issuing_portal(self):
        ticket, raw_token = issue_support_socket_ticket(user=self.student, portal="learner")
        self.assertEqual(_consume_ticket_sync(raw_token), (self.student, "learner"))
        self.assertIsNone(_consume_ticket_sync(raw_token))
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.consumed_at)

    def test_expired_ticket_is_rejected(self):
        ticket, raw_token = issue_support_socket_ticket(user=self.student, portal="learner")
        CourseSupportSocketTicket.objects.filter(pk=ticket.pk).update(expires_at=timezone.now())

        self.assertIsNone(_consume_ticket_sync(raw_token))

    def test_staff_ticket_is_rejected_if_chat_permission_is_revoked_before_connect(self):
        from django.contrib.auth.models import Permission

        teacher = User.objects.create_user(email="socket-teacher@example.com", password="pass12345")
        teacher_group = self.group(GroupName.TEACHER)
        teacher.groups.add(teacher_group)
        ticket, raw_token = issue_support_socket_ticket(user=teacher, portal="staff")
        permission = Permission.objects.get(
            content_type__app_label="tutoring",
            codename="reply_to_assigned_course_support_chats",
        )
        teacher_group.permissions.remove(permission)

        self.assertIsNone(_consume_ticket_sync(raw_token))
        ticket.refresh_from_db()
        self.assertIsNone(ticket.consumed_at)

    def test_two_connections_for_one_user_receive_the_same_event(self):
        payload = {"v": 1, "type": "conversation.updated", "conversation": {"id": "conversation"}}

        async def scenario():
            layer = InMemoryChannelLayer()
            first = await layer.new_channel()
            second = await layer.new_channel()
            group = f"course_support.user.{self.student.id}"
            await layer.group_add(group, first)
            await layer.group_add(group, second)
            event = {"type": "support.event", "payload": payload}
            await layer.group_send(group, event)
            self.assertEqual(await layer.receive(first), event)
            self.assertEqual(await layer.receive(second), event)

        asyncio.run(scenario())

    @override_settings(COURSE_SUPPORT_CHAT_ENABLED=False)
    def test_disabled_feature_rejects_connection_without_consuming_ticket(self):
        with self.settings(COURSE_SUPPORT_CHAT_ENABLED=True):
            ticket, raw_token = issue_support_socket_ticket(user=self.student, portal="learner")

        async def scenario():
            communicator = self.communicator(raw_token)
            connected, close_code = await communicator.connect(timeout=5)
            self.assertFalse(connected)
            self.assertEqual(close_code, 4403)

        asyncio.run(scenario())
        ticket.refresh_from_db()
        self.assertIsNone(ticket.consumed_at)


class CourseSupportOriginTests(SimpleTestCase):
    def test_explicit_origin_allowlist_rejects_untrusted_origins(self):
        validator = OriginValidator(lambda scope, receive, send: None, ["https://learn.example"])
        self.assertTrue(validator.valid_origin(urlparse("https://learn.example")))
        self.assertFalse(validator.valid_origin(urlparse("https://evil.example")))
        self.assertFalse(validator.valid_origin(None))


@override_settings(
    CHANNEL_LAYERS=TEST_CHANNEL_LAYERS,
    COURSE_SUPPORT_CHAT_CONNECTION_RATE="20/min",
    COURSE_SUPPORT_CHAT_MAX_CONNECTIONS_PER_USER=5,
    COURSE_SUPPORT_CHAT_SEND_RATE="20/min",
    COURSE_SUPPORT_CHAT_EVENT_MAX_BYTES=2048,
)
class CourseSupportProtocolTests(TestCase):
    def setUp(self):
        channel_layers.backends = {}
        cache.clear()
        self.user = SimpleNamespace(pk=uuid.uuid4())
        self.consumer = CourseSupportConsumer()
        self.consumer.scope = {"user": self.user, "support_portal": "learner"}
        self.consumer.send_json = AsyncMock()

    def test_message_send_returns_durable_acknowledgement(self):
        conversation_id = uuid.uuid4()
        client_message_id = uuid.uuid4()
        message = {
            "id": str(uuid.uuid4()),
            "conversation": str(conversation_id),
            "sequence": 1,
            "client_message_id": str(client_message_id),
            "content": "Question",
        }

        async def scenario():
            await self.consumer.receive_json({
                "v": 1,
                "request_id": "request-1",
                "type": "message.send",
                "conversation_id": str(conversation_id),
                "client_message_id": str(client_message_id),
                "content": "Question",
            })
            response = self.consumer.send_json.await_args.args[0]
            self.assertEqual(response["type"], "message.accepted")
            self.assertTrue(response["created"])
            self.assertEqual(response["message"], message)

        with patch("tutoring.consumers._send_message", new=AsyncMock(return_value=(message, True))):
            with (
                patch("tutoring.consumers._claim_connection_async", new=AsyncMock(return_value=True)),
                patch("tutoring.consumers._release_connection_async", new=AsyncMock()),
                patch("tutoring.consumers._allow_rate_async", new=AsyncMock(return_value=True)),
            ):
                asyncio.run(scenario())

    def test_unknown_version_binary_and_oversized_frames_return_structured_errors(self):
        async def scenario():
            await self.consumer.receive_json({"v": 2, "request_id": "version", "type": "message.send"})
            self.assertEqual(self.consumer.send_json.await_args.args[0]["error"]["code"], "UNSUPPORTED_VERSION")
            await self.consumer.receive(bytes_data=b"binary")
            self.assertEqual(self.consumer.send_json.await_args.args[0]["error"]["code"], "BINARY_NOT_SUPPORTED")
            await self.consumer.receive(text_data="x" * 2049)
            self.assertEqual(self.consumer.send_json.await_args.args[0]["error"]["code"], "FRAME_TOO_LARGE")

        with (
            patch("tutoring.consumers._claim_connection_async", new=AsyncMock(return_value=True)),
            patch("tutoring.consumers._release_connection_async", new=AsyncMock()),
        ):
            asyncio.run(scenario())

    def test_rejection_logs_exclude_event_content_and_credentials(self):
        async def scenario():
            await self.consumer.receive_json({
                "v": 1,
                "request_id": "safe-request-id",
                "type": "unsupported.command",
                "content": "do-not-log-this-message",
                "ticket": "do-not-log-this-ticket",
            })

        with self.assertLogs("tutoring.consumers", level="INFO") as captured:
            asyncio.run(scenario())
        logs = "\n".join(captured.output)
        self.assertIn("UNKNOWN_TYPE", logs)
        self.assertNotIn("do-not-log-this-message", logs)
        self.assertNotIn("do-not-log-this-ticket", logs)

    def test_read_and_close_commands_are_acknowledged(self):
        conversation_id = uuid.uuid4()
        conversation = {"id": str(conversation_id), "status": "CLOSED", "last_sequence": 4}

        async def scenario():
            await self.consumer.receive_json({
                "v": 1,
                "request_id": "read",
                "type": "conversation.read",
                "conversation_id": str(conversation_id),
                "sequence": 4,
            })
            self.assertEqual(self.consumer.send_json.await_args.args[0]["type"], "conversation.read.accepted")
            await self.consumer.receive_json({
                "v": 1,
                "request_id": "close",
                "type": "conversation.close",
                "conversation_id": str(conversation_id),
            })
            self.assertEqual(self.consumer.send_json.await_args.args[0]["type"], "conversation.close.accepted")

        with (
            patch("tutoring.consumers._mark_read", new=AsyncMock(return_value=4)),
            patch("tutoring.consumers._close_conversation", new=AsyncMock(return_value=conversation)),
            patch("tutoring.consumers._claim_connection_async", new=AsyncMock(return_value=True)),
            patch("tutoring.consumers._release_connection_async", new=AsyncMock()),
        ):
            asyncio.run(scenario())

    @override_settings(COURSE_SUPPORT_CHAT_SEND_RATE="1/min")
    def test_send_rate_limit_rejects_without_persistence(self):
        message = {"id": str(uuid.uuid4())}
        command = {
            "v": 1,
            "type": "message.send",
            "conversation_id": str(uuid.uuid4()),
            "client_message_id": str(uuid.uuid4()),
            "content": "Question",
        }

        async def scenario():
            await self.consumer.receive_json({**command, "request_id": "first"})
            self.assertEqual(self.consumer.send_json.await_args.args[0]["type"], "message.accepted")
            await self.consumer.receive_json({**command, "request_id": "second"})
            self.assertEqual(self.consumer.send_json.await_args.args[0]["error"]["code"], "RATE_LIMITED")

        mocked = AsyncMock(return_value=(message, True))
        with (
            patch("tutoring.consumers._send_message", new=mocked),
            patch("tutoring.consumers._claim_connection_async", new=AsyncMock(return_value=True)),
            patch("tutoring.consumers._release_connection_async", new=AsyncMock()),
            patch("tutoring.consumers._allow_rate_async", new=AsyncMock(side_effect=[True, False])),
        ):
            asyncio.run(scenario())
        self.assertEqual(mocked.await_count, 1)

    @override_settings(COURSE_SUPPORT_CHAT_MAX_CONNECTIONS_PER_USER=1)
    def test_active_connection_limit_rejects_extra_socket(self):
        self.assertTrue(_claim_connection(self.user.pk))
        self.assertFalse(_claim_connection(self.user.pk))
        _release_connection(self.user.pk)
        self.assertTrue(_claim_connection(self.user.pk))
        _release_connection(self.user.pk)

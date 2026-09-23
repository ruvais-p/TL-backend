import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.admission import portal_admission
from accounts.constants import GroupName
from accounts.models import User
from curriculum.models import Course, CourseVersion, Program, PublishStatus
from students.models import CourseAssignment, Enrollment, StudentGroup, StudentGroupMember

from .models import (
    CourseSupportConversation,
    CourseSupportMessage,
    CourseSupportReadState,
    CourseSupportSocketTicket,
)
from .selectors import (
    can_read_support_conversation,
    can_send_support_message,
    support_recipient_user_ids,
    visible_support_conversations,
)
from .services import (
    SupportChatAccessError,
    SupportChatConflictError,
    SupportChatValidationError,
    advance_support_read_state,
    close_support_conversation,
    current_support_recipient_user_ids,
    get_or_create_support_conversation,
    send_support_message,
)


class CourseSupportFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)
        cls.student = User.objects.create_user(email="support-student@example.com", password="pass12345")
        cls.other_student = User.objects.create_user(email="support-other@example.com", password="pass12345")
        cls.teacher = User.objects.create_user(email="support-teacher@example.com", password="pass12345")
        cls.other_teacher = User.objects.create_user(email="support-other-teacher@example.com", password="pass12345")
        cls.manager = User.objects.create_user(email="support-manager@example.com", password="pass12345")
        cls.admin = User.objects.create_user(email="support-admin@example.com", password="pass12345")
        cls.student.groups.add(cls.group(GroupName.STUDENT))
        cls.other_student.groups.add(cls.group(GroupName.STUDENT))
        cls.teacher.groups.add(cls.group(GroupName.TEACHER))
        cls.other_teacher.groups.add(cls.group(GroupName.TEACHER))
        cls.manager.groups.add(cls.group(GroupName.ACADEMIC_MANAGER))
        cls.admin.groups.add(cls.group(GroupName.ADMIN))

        cls.program = Program.objects.create(name="Support Program", code="support-program", status=PublishStatus.PUBLISHED)
        cls.course = Course.objects.create(program=cls.program, name="Algebra", code="support-algebra", status=PublishStatus.PUBLISHED)
        cls.version = CourseVersion.objects.create(course=cls.course, version_number=1, name="Published", status=PublishStatus.PUBLISHED)
        cls.other_course = Course.objects.create(program=cls.program, name="Science", code="support-science", status=PublishStatus.PUBLISHED)
        cls.other_version = CourseVersion.objects.create(course=cls.other_course, version_number=1, name="Published", status=PublishStatus.PUBLISHED)
        cls.group_row = StudentGroup.objects.create(name="Support 9A", code="SUPPORT-9A", academic_year=2026, teacher=cls.teacher)
        StudentGroupMember.objects.create(student_group=cls.group_row, student=cls.student)
        cls.enrollment = Enrollment.objects.create(student=cls.student, course=cls.course, course_version=cls.version)
        cls.other_enrollment = Enrollment.objects.create(student=cls.other_student, course=cls.course, course_version=cls.version)
        cls.assignment = CourseAssignment.objects.create(
            course=cls.course,
            course_version=cls.version,
            student_group=cls.group_row,
            assigned_by=cls.manager,
        )
        cls.conversation = CourseSupportConversation.objects.create(
            student=cls.student,
            course_version=cls.version,
            opened_from_enrollment=cls.enrollment,
        )

    @classmethod
    def group(cls, name):
        from django.contrib.auth.models import Group

        return Group.objects.get(name=name)


class CourseSupportModelTests(CourseSupportFixture):
    def test_conversation_is_unique_per_student_and_version(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseSupportConversation.objects.create(
                student=self.student,
                course_version=self.version,
                opened_from_enrollment=self.enrollment,
            )

    def test_messages_are_sequence_ordered_and_client_id_is_idempotency_key(self):
        second = CourseSupportMessage.objects.create(
            conversation=self.conversation,
            sender=self.student,
            sender_role=CourseSupportMessage.SenderRole.STUDENT,
            sequence=2,
            client_message_id=uuid.uuid4(),
            content="Second",
        )
        first_client_id = uuid.uuid4()
        first = CourseSupportMessage.objects.create(
            conversation=self.conversation,
            sender=self.student,
            sender_role=CourseSupportMessage.SenderRole.STUDENT,
            sequence=1,
            client_message_id=first_client_id,
            content="First",
        )
        self.assertEqual(list(self.conversation.support_messages.all()), [first, second])
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseSupportMessage.objects.create(
                conversation=self.conversation,
                sender=self.student,
                sender_role=CourseSupportMessage.SenderRole.STUDENT,
                sequence=3,
                client_message_id=first_client_id,
                content="Duplicate",
            )

    def test_read_state_is_unique_per_user_and_conversation(self):
        CourseSupportReadState.objects.create(conversation=self.conversation, user=self.student)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseSupportReadState.objects.create(conversation=self.conversation, user=self.student)

    def test_socket_ticket_hash_is_unique(self):
        from django.utils import timezone

        CourseSupportSocketTicket.objects.create(
            token_hash="a" * 64,
            user=self.student,
            portal=CourseSupportSocketTicket.Portal.LEARNER,
            expires_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseSupportSocketTicket.objects.create(
                token_hash="a" * 64,
                user=self.student,
                portal=CourseSupportSocketTicket.Portal.LEARNER,
                expires_at=timezone.now(),
            )


class CourseSupportAccessTests(CourseSupportFixture):
    def test_teacher_staff_admission_is_permission_scoped(self):
        self.assertTrue(portal_admission(self.teacher, "staff").allowed)
        self.assertTrue(self.teacher.has_perm("tutoring.reply_to_assigned_course_support_chats"))
        self.assertTrue(self.teacher.has_perm("tutoring.close_course_support_chats"))
        self.assertFalse(self.teacher.has_perm("tutoring.view_all_course_support_chats"))

    def test_matching_teacher_student_and_manager_can_read(self):
        self.assertTrue(can_read_support_conversation(user=self.student, conversation=self.conversation))
        self.assertTrue(can_read_support_conversation(user=self.teacher, conversation=self.conversation))
        self.assertTrue(can_read_support_conversation(user=self.manager, conversation=self.conversation))
        self.assertFalse(can_read_support_conversation(user=self.other_teacher, conversation=self.conversation))
        self.assertFalse(can_read_support_conversation(user=self.admin, conversation=self.conversation))

    def test_teacher_access_requires_matching_active_course_assignment(self):
        unrelated_enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.other_course,
            course_version=self.other_version,
        )
        unrelated = CourseSupportConversation.objects.create(
            student=self.student,
            course_version=self.other_version,
            opened_from_enrollment=unrelated_enrollment,
        )
        self.assertFalse(can_read_support_conversation(user=self.teacher, conversation=unrelated))
        self.assignment.status = CourseAssignment.Status.CANCELLED
        self.assignment.save(update_fields=["status"])
        self.assertFalse(can_read_support_conversation(user=self.teacher, conversation=self.conversation))

    def test_teacher_reassignment_revokes_previous_teacher(self):
        self.group_row.teacher = self.other_teacher
        self.group_row.save(update_fields=["teacher"])
        self.assertFalse(can_read_support_conversation(user=self.teacher, conversation=self.conversation))
        self.assertTrue(can_read_support_conversation(user=self.other_teacher, conversation=self.conversation))

    def test_each_teacher_needs_a_matching_assignment_for_a_multi_group_student(self):
        matching_group = StudentGroup.objects.create(
            name="Support 9B",
            code="SUPPORT-9B",
            academic_year=2026,
            teacher=self.other_teacher,
        )
        StudentGroupMember.objects.create(student_group=matching_group, student=self.student)
        CourseAssignment.objects.create(
            course=self.course,
            course_version=self.version,
            student_group=matching_group,
            assigned_by=self.manager,
        )
        self.assertTrue(can_read_support_conversation(user=self.teacher, conversation=self.conversation))
        self.assertTrue(can_read_support_conversation(user=self.other_teacher, conversation=self.conversation))

        self.assignment.status = CourseAssignment.Status.CANCELLED
        self.assignment.save(update_fields=["status"])
        self.assertFalse(can_read_support_conversation(user=self.teacher, conversation=self.conversation))
        self.assertTrue(can_read_support_conversation(user=self.other_teacher, conversation=self.conversation))

    def test_inactive_group_does_not_grant_teacher_access(self):
        self.group_row.status = StudentGroup.Status.INACTIVE
        self.group_row.save(update_fields=["status"])
        self.assertFalse(can_read_support_conversation(user=self.teacher, conversation=self.conversation))

    def test_student_send_requires_current_enrollment_but_read_does_not(self):
        self.assertTrue(can_send_support_message(user=self.student, conversation=self.conversation))
        self.enrollment.status = Enrollment.Status.EXPIRED
        self.enrollment.save(update_fields=["status"])
        self.assertTrue(can_read_support_conversation(user=self.student, conversation=self.conversation))
        self.assertFalse(can_send_support_message(user=self.student, conversation=self.conversation))

    def test_visible_queryset_and_recipient_resolution_are_scoped(self):
        other = CourseSupportConversation.objects.create(
            student=self.other_student,
            course_version=self.version,
            opened_from_enrollment=self.other_enrollment,
        )
        self.assertEqual(list(visible_support_conversations(self.teacher)), [self.conversation])
        self.assertCountEqual(visible_support_conversations(self.manager), [self.conversation, other])
        recipients = support_recipient_user_ids(self.conversation)
        self.assertIn(self.student.id, recipients)
        self.assertIn(self.teacher.id, recipients)
        self.assertIn(self.manager.id, recipients)
        self.assertNotIn(self.other_teacher.id, recipients)
        self.assertNotIn(self.admin.id, recipients)

    def test_recipient_resolution_excludes_inactive_or_permissionless_teachers(self):
        self.teacher.is_active = False
        self.teacher.save(update_fields=["is_active"])
        self.assertNotIn(self.teacher.id, support_recipient_user_ids(self.conversation))

        self.teacher.is_active = True
        self.teacher.save(update_fields=["is_active"])
        self.group(GroupName.TEACHER).permissions.clear()
        self.assertNotIn(self.teacher.id, support_recipient_user_ids(self.conversation))


class CourseSupportServiceTests(CourseSupportFixture):
    def test_conversation_creation_is_idempotent_and_uses_enrollment_version(self):
        self.conversation.delete()
        first, created = get_or_create_support_conversation(student=self.student, course_id=self.course.id)
        second, created_again = get_or_create_support_conversation(student=self.student, course_id=self.course.id)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, second)
        self.assertEqual(first.course_version, self.enrollment.course_version)
        self.assertEqual(first.opened_from_enrollment, self.enrollment)

    def test_conversation_creation_rejects_inaccessible_course(self):
        with self.assertRaises(SupportChatAccessError):
            get_or_create_support_conversation(student=self.student, course_id=self.other_course.id)

    def test_message_send_is_ordered_idempotent_and_normalized(self):
        client_id = uuid.uuid4()
        first = send_support_message(
            actor=self.student,
            conversation_id=self.conversation.id,
            client_message_id=client_id,
            content="  First question  ",
        )
        duplicate = send_support_message(
            actor=self.student,
            conversation_id=self.conversation.id,
            client_message_id=client_id,
            content="Ignored retry body",
        )
        second = send_support_message(
            actor=self.teacher,
            conversation_id=self.conversation.id,
            client_message_id=uuid.uuid4(),
            content="A reply",
        )
        self.assertTrue(first.created)
        self.assertFalse(duplicate.created)
        self.assertEqual(first.message, duplicate.message)
        self.assertEqual(first.message.content, "First question")
        self.assertEqual([first.message.sequence, second.message.sequence], [1, 2])
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.last_sequence, 2)
        self.assertEqual(self.conversation.last_message_at, second.message.created_at)

    def test_client_message_id_cannot_be_reused_for_another_conversation(self):
        other = CourseSupportConversation.objects.create(
            student=self.other_student,
            course_version=self.version,
            opened_from_enrollment=self.other_enrollment,
        )
        client_id = uuid.uuid4()
        send_support_message(
            actor=self.manager,
            conversation_id=self.conversation.id,
            client_message_id=client_id,
            content="First",
        )
        with self.assertRaises(SupportChatConflictError):
            send_support_message(
                actor=self.manager,
                conversation_id=other.id,
                client_message_id=client_id,
                content="Second",
            )

    def test_read_state_only_advances_and_rejects_unknown_sequence(self):
        sent = send_support_message(
            actor=self.student,
            conversation_id=self.conversation.id,
            client_message_id=uuid.uuid4(),
            content="Question",
        )
        state = advance_support_read_state(
            actor=self.teacher,
            conversation_id=self.conversation.id,
            sequence=sent.message.sequence,
        )
        stale = advance_support_read_state(
            actor=self.teacher,
            conversation_id=self.conversation.id,
            sequence=0,
        )
        self.assertEqual(state.last_read_sequence, 1)
        self.assertEqual(stale.last_read_sequence, 1)
        with self.assertRaises(SupportChatValidationError):
            advance_support_read_state(
                actor=self.teacher,
                conversation_id=self.conversation.id,
                sequence=2,
            )

    def test_staff_close_and_eligible_learner_send_reopens(self):
        closed = close_support_conversation(actor=self.teacher, conversation_id=self.conversation.id)
        self.assertEqual(closed.status, CourseSupportConversation.Status.CLOSED)
        with self.assertRaises(SupportChatConflictError):
            send_support_message(
                actor=self.teacher,
                conversation_id=self.conversation.id,
                client_message_id=uuid.uuid4(),
                content="Cannot reply while closed",
            )
        send_support_message(
            actor=self.student,
            conversation_id=self.conversation.id,
            client_message_id=uuid.uuid4(),
            content="Reopen",
        )
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.status, CourseSupportConversation.Status.OPEN)

    def test_revoked_user_cannot_send_or_close(self):
        self.assignment.status = CourseAssignment.Status.CANCELLED
        self.assignment.save(update_fields=["status"])
        with self.assertRaises(SupportChatAccessError):
            send_support_message(
                actor=self.teacher,
                conversation_id=self.conversation.id,
                client_message_id=uuid.uuid4(),
                content="Blocked",
            )
        with self.assertRaises(SupportChatAccessError):
            close_support_conversation(actor=self.teacher, conversation_id=self.conversation.id)

    def test_current_recipient_resolution_tracks_responsibility(self):
        self.assertIn(self.teacher.id, current_support_recipient_user_ids(conversation=self.conversation))
        self.group_row.teacher = self.other_teacher
        self.group_row.save(update_fields=["teacher"])
        recipients = current_support_recipient_user_ids(conversation=self.conversation)
        self.assertNotIn(self.teacher.id, recipients)
        self.assertIn(self.other_teacher.id, recipients)


@override_settings(
    COURSE_SUPPORT_CHAT_ENABLED=True,
    COURSE_SUPPORT_CHAT_TICKET_TTL_SECONDS=30,
    COURSE_SUPPORT_CHAT_WEBSOCKET_URL="ws://testserver/ws/course-support/",
)
class CourseSupportApiTests(CourseSupportFixture):
    def setUp(self):
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def test_learner_availability_and_idempotent_creation(self):
        self.conversation.delete()
        self.authenticate(self.student)
        url = reverse("course-support-conversation", args=[self.course.id])
        available = self.client.get(url)
        self.assertEqual(available.status_code, 200)
        self.assertTrue(available.data["available"])
        self.assertIsNone(available.data["conversation"])

        created = self.client.post(url, {}, format="json")
        existing = self.client.post(url, {}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(existing.status_code, 200)
        self.assertEqual(created.data["id"], existing.data["id"])

    def test_learner_can_recover_owned_history_after_enrollment_expires(self):
        send_support_message(
            actor=self.student,
            conversation_id=self.conversation.id,
            client_message_id=uuid.uuid4(),
            content="Stored history",
        )
        self.enrollment.status = Enrollment.Status.EXPIRED
        self.enrollment.save(update_fields=["status"])
        self.authenticate(self.student)

        availability = self.client.get(reverse("course-support-conversation", args=[self.course.id]))
        history = self.client.get(reverse("course-support-messages", args=[self.conversation.id]))
        self.assertFalse(availability.data["available"])
        self.assertEqual(availability.data["conversation"]["id"], str(self.conversation.id))
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["results"][0]["content"], "Stored history")

    def test_message_history_is_authorization_scoped_and_sequence_bounded(self):
        for index in range(3):
            send_support_message(
                actor=self.student,
                conversation_id=self.conversation.id,
                client_message_id=uuid.uuid4(),
                content=f"Question {index}",
            )
        self.authenticate(self.teacher)
        url = reverse("course-support-messages", args=[self.conversation.id])
        response = self.client.get(url, {"after_sequence": 1, "limit": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["sequence"] for row in response.data["results"]], [2])
        self.assertTrue(response.data["has_more"])

        self.authenticate(self.other_teacher)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_staff_inbox_is_scoped_and_rejects_ordinary_admin(self):
        other = CourseSupportConversation.objects.create(
            student=self.other_student,
            course_version=self.version,
            opened_from_enrollment=self.other_enrollment,
        )
        self.authenticate(self.teacher)
        response = self.client.get(reverse("course-support-conversations"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [str(self.conversation.id)])

        self.authenticate(self.manager)
        response = self.client.get(reverse("course-support-conversations"))
        self.assertCountEqual([row["id"] for row in response.data["results"]], [str(self.conversation.id), str(other.id)])

        self.authenticate(self.admin)
        self.assertEqual(self.client.get(reverse("course-support-conversations")).status_code, 403)

    def test_read_and_close_endpoints_apply_current_authorization(self):
        sent = send_support_message(
            actor=self.student,
            conversation_id=self.conversation.id,
            client_message_id=uuid.uuid4(),
            content="Question",
        )
        self.authenticate(self.teacher)
        read = self.client.post(
            reverse("course-support-read", args=[self.conversation.id]),
            {"sequence": sent.message.sequence},
            format="json",
        )
        closed = self.client.post(reverse("course-support-close", args=[self.conversation.id]), {}, format="json")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.data["sequence"], 1)
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data["status"], CourseSupportConversation.Status.CLOSED)

        self.authenticate(self.student)
        self.assertEqual(
            self.client.post(reverse("course-support-close", args=[self.conversation.id]), {}, format="json").status_code,
            404,
        )

    def test_socket_ticket_is_portal_scoped_and_only_hash_is_stored(self):
        self.authenticate(self.student)
        url = reverse("course-support-socket-ticket")
        response = self.client.post(url, {"portal": "learner"}, format="json")
        self.assertEqual(response.status_code, 201)
        ticket = CourseSupportSocketTicket.objects.get()
        self.assertNotEqual(ticket.token_hash, response.data["ticket"])
        self.assertEqual(ticket.portal, CourseSupportSocketTicket.Portal.LEARNER)
        self.assertEqual(response.data["websocket_url"], "ws://testserver/ws/course-support/")
        self.assertEqual(self.client.post(url, {"portal": "staff"}, format="json").status_code, 403)

        self.authenticate(self.admin)
        self.assertEqual(self.client.post(url, {"portal": "staff"}, format="json").status_code, 403)
        self.authenticate(self.manager)
        self.assertEqual(self.client.post(url, {"portal": "staff"}, format="json").status_code, 201)

    @override_settings(COURSE_SUPPORT_CHAT_ENABLED=False)
    def test_feature_disabled_hides_support_endpoints(self):
        self.authenticate(self.student)
        self.assertEqual(
            self.client.get(reverse("course-support-conversation", args=[self.course.id])).status_code,
            404,
        )


class CourseSupportEventTests(CourseSupportFixture):
    def test_created_message_is_published_only_after_commit(self):
        with patch("tutoring.events._send_to_user_ids") as deliver:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                result = send_support_message(
                    actor=self.student,
                    conversation_id=self.conversation.id,
                    client_message_id=uuid.uuid4(),
                    content="Private question body",
                )
                self.assertFalse(deliver.called)
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()

        recipient_ids, payload = deliver.call_args.args
        self.assertIn(self.student.id, recipient_ids)
        self.assertIn(self.teacher.id, recipient_ids)
        self.assertIn(self.manager.id, recipient_ids)
        self.assertEqual(payload["type"], "message.created")
        self.assertEqual(payload["message"]["id"], str(result.message.id))

    def test_duplicate_retry_does_not_publish_a_second_event(self):
        client_message_id = uuid.uuid4()
        with self.captureOnCommitCallbacks(execute=True):
            first = send_support_message(
                actor=self.student,
                conversation_id=self.conversation.id,
                client_message_id=client_message_id,
                content="Question",
            )
        with patch("tutoring.events._send_to_user_ids") as deliver:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                duplicate = send_support_message(
                    actor=self.student,
                    conversation_id=self.conversation.id,
                    client_message_id=client_message_id,
                    content="Question retry",
                )
        self.assertEqual(first.message, duplicate.message)
        self.assertFalse(duplicate.created)
        self.assertEqual(callbacks, [])
        deliver.assert_not_called()

    def test_post_commit_recipient_resolution_uses_current_assignment(self):
        with patch("tutoring.events._send_to_user_ids") as deliver:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                send_support_message(
                    actor=self.student,
                    conversation_id=self.conversation.id,
                    client_message_id=uuid.uuid4(),
                    content="Question",
                )
            self.group_row.teacher = self.other_teacher
            self.group_row.save(update_fields=["teacher"])
            callbacks[0]()

        recipient_ids = deliver.call_args.args[0]
        self.assertNotIn(self.teacher.id, recipient_ids)
        self.assertIn(self.other_teacher.id, recipient_ids)


class CourseSupportRetentionTests(CourseSupportFixture):
    @override_settings(
        COURSE_SUPPORT_CHAT_RETENTION_DAYS=30,
        COURSE_SUPPORT_CHAT_TICKET_CLEANUP_HOURS=1,
    )
    def test_cleanup_removes_only_expired_support_data_and_stale_tickets(self):
        recent = CourseSupportConversation.objects.create(
            student=self.other_student,
            course_version=self.version,
            opened_from_enrollment=self.other_enrollment,
        )
        old_time = timezone.now() - timedelta(days=31)
        CourseSupportConversation.objects.filter(pk=self.conversation.pk).update(
            last_message_at=old_time,
            updated_at=old_time,
        )
        stale_ticket = CourseSupportSocketTicket.objects.create(
            token_hash="b" * 64,
            user=self.student,
            portal=CourseSupportSocketTicket.Portal.LEARNER,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        live_ticket = CourseSupportSocketTicket.objects.create(
            token_hash="c" * 64,
            user=self.student,
            portal=CourseSupportSocketTicket.Portal.LEARNER,
            expires_at=timezone.now() + timedelta(seconds=30),
        )

        output = StringIO()
        call_command("purge_course_support_chat", stdout=output)

        self.assertFalse(CourseSupportConversation.objects.filter(pk=self.conversation.pk).exists())
        self.assertTrue(CourseSupportConversation.objects.filter(pk=recent.pk).exists())
        self.assertFalse(CourseSupportSocketTicket.objects.filter(pk=stale_ticket.pk).exists())
        self.assertTrue(CourseSupportSocketTicket.objects.filter(pk=live_ticket.pk).exists())
        self.assertIn("Deleted 1 expired support conversations and 1 stale socket tickets", output.getvalue())

    @override_settings(
        COURSE_SUPPORT_CHAT_RETENTION_DAYS=30,
        COURSE_SUPPORT_CHAT_TICKET_CLEANUP_HOURS=1,
    )
    def test_cleanup_dry_run_does_not_delete(self):
        old_time = timezone.now() - timedelta(days=31)
        CourseSupportConversation.objects.filter(pk=self.conversation.pk).update(
            last_message_at=old_time,
            updated_at=old_time,
        )
        call_command("purge_course_support_chat", dry_run=True, verbosity=0)
        self.assertTrue(CourseSupportConversation.objects.filter(pk=self.conversation.pk).exists())

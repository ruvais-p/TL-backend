from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.constants import GroupName
from accounts.models import User
from content.models import ActivityContent, Experiment
from media_library.models import MediaAsset
from students.models import Enrollment

from .models import Chapter, Course, CourseVersion, LearningActivity, Program, PublishStatus, Subtopic
from .services import duplicate_course, publish_course_version, reorder_activities


class CurriculumFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)
        cls.academic = User.objects.create_user(email="academic@example.com", username="academic", password="StrongPass123!")
        cls.academic.groups.add(Group.objects.get(name=GroupName.ACADEMIC_MANAGER))
        cls.content_manager = User.objects.create_user(email="content@example.com", username="content", password="StrongPass123!")
        cls.content_manager.groups.add(Group.objects.get(name=GroupName.CONTENT_MANAGER))
        cls.student = User.objects.create_user(email="student2@example.com", username="student2", password="StrongPass123!")
        cls.student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        cls.other_student = User.objects.create_user(email="other@example.com", username="other", password="StrongPass123!")
        cls.other_student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        cls.program = Program.objects.create(name="Grade 9 Mathematics", code="g9-math", grade="9", status=PublishStatus.PUBLISHED, created_by=cls.academic)
        cls.course = Course.objects.create(program=cls.program, name="Mathematics", code="math-9", status=PublishStatus.DRAFT, created_by=cls.academic, updated_by=cls.academic)
        cls.version = CourseVersion.objects.create(course=cls.course, version_number=2026, name="2026", status=PublishStatus.DRAFT, created_by=cls.academic)
        cls.chapter = Chapter.objects.create(course_version=cls.version, title="Algebra", slug="algebra", chapter_number=1, display_order=0, status=PublishStatus.PUBLISHED)
        cls.subtopic = Subtopic.objects.create(chapter=cls.chapter, title="Variables", slug="variables", display_order=0, status=PublishStatus.PUBLISHED)
        cls.activity = LearningActivity.objects.create(subtopic=cls.subtopic, activity_type=LearningActivity.ActivityType.CONCEPT_VIDEO, title="Variables video", display_order=0, status=PublishStatus.PUBLISHED, created_by=cls.academic, updated_by=cls.academic)


class CurriculumModelAndServiceTests(CurriculumFixtureMixin, TestCase):
    def test_course_code_is_globally_unique(self):
        second_program = Program.objects.create(name="Second", code="second")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Course.objects.create(program=second_program, name="Duplicate", code=self.course.code)

    def test_version_number_is_unique_per_course(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseVersion.objects.create(course=self.course, version_number=2026, name="Duplicate")

    def test_publish_course_version_sets_timestamp_and_course_status(self):
        published = publish_course_version(actor=self.academic, version=self.version)
        self.course.refresh_from_db()
        self.assertEqual(published.status, PublishStatus.PUBLISHED)
        self.assertIsNotNone(published.published_at)
        self.assertEqual(self.course.status, PublishStatus.PUBLISHED)

    def test_content_manager_cannot_publish(self):
        with self.assertRaises(PermissionDenied):
            publish_course_version(actor=self.content_manager, version=self.version)

    def test_duplicate_course_clones_hierarchy_as_draft(self):
        clone = duplicate_course(actor=self.academic, course=self.course, code="math-9-copy")
        self.assertEqual(clone.status, PublishStatus.DRAFT)
        self.assertEqual(clone.versions.count(), 1)
        self.assertEqual(clone.versions.get().chapters.get().subtopics.get().activities.count(), 1)
        self.assertEqual(clone.versions.get().chapters.get().status, PublishStatus.DRAFT)

    def test_reorder_activities_requires_complete_exact_set(self):
        second = LearningActivity.objects.create(subtopic=self.subtopic, activity_type=LearningActivity.ActivityType.HOMEWORK, title="Homework", display_order=1)
        with self.assertRaises(ValidationError):
            reorder_activities(actor=self.academic, subtopic=self.subtopic, ordered_ids=[second.id])
        reorder_activities(actor=self.academic, subtopic=self.subtopic, ordered_ids=[second.id, self.activity.id])
        self.activity.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((second.display_order, self.activity.display_order), (0, 1))


class CurriculumApiTests(CurriculumFixtureMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    def publish_tree(self):
        self.course.status = PublishStatus.PUBLISHED
        self.course.save(update_fields=["status"])
        self.version.status = PublishStatus.PUBLISHED
        self.version.save(update_fields=["status"])

    def test_academic_manager_can_create_program(self):
        self.client.force_authenticate(self.academic)
        response = self.client.post(reverse("program-list"), {
            "name": "Science", "code": "science", "description": "Science program",
            "grade": "9", "status": PublishStatus.DRAFT,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"], self.academic.id)

    def test_academic_manager_can_create_course_with_thumbnail(self):
        thumbnail = MediaAsset.objects.create(
            file_name="science-cover.webp",
            file_type="IMAGE",
            mime_type="image/webp",
            file_size=1024,
            storage_path="course-thumbnails/science-cover.webp",
            status=MediaAsset.Status.READY,
            uploaded_by=self.academic,
        )
        self.client.force_authenticate(self.academic)

        response = self.client.post(reverse("course-list"), {
            "program": str(self.program.id),
            "name": "Science",
            "code": "science-with-thumbnail",
            "description": "Science course",
            "thumbnail": str(thumbnail.id),
            "status": PublishStatus.DRAFT,
            "display_order": 2,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["thumbnail"], thumbnail.id)
        self.assertEqual(Course.objects.get(pk=response.data["id"]).thumbnail, thumbnail)

    def test_content_manager_cannot_publish_course_api(self):
        self.client.force_authenticate(self.content_manager)
        response = self.client.post(reverse("course-publish", args=[self.course.id]), {"version_id": str(self.version.id)}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_content_manager_can_reorder_activities_api(self):
        second = LearningActivity.objects.create(
            subtopic=self.subtopic,
            activity_type=LearningActivity.ActivityType.HOMEWORK,
            title="Homework",
            display_order=1,
        )
        self.client.force_authenticate(self.content_manager)

        response = self.client.post(
            reverse("subtopic-reorder-activities", args=[self.subtopic.id]),
            {"ids": [str(second.id), str(self.activity.id)]},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.activity.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((second.display_order, self.activity.display_order), (0, 1))

    def test_activity_representation_includes_nullable_content_record(self):
        self.client.force_authenticate(self.academic)
        response = self.client.get(reverse("activity-detail", args=[self.activity.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["content_record"])
        self.assertIsNone(response.data["content"])

        content = ActivityContent.objects.create(
            activity=self.activity,
            content_type="application/vnd.tella.overview+json",
            content={"blocks": [{"type": "text", "value": "Hello"}]},
        )
        response = self.client.get(reverse("activity-detail", args=[self.activity.id]))
        self.assertEqual(response.data["content"], content.content)
        self.assertEqual(response.data["content_record"]["id"], str(content.id))
        self.assertEqual(response.data["content_record"]["content_type"], content.content_type)

    def test_activity_representation_includes_admin_authored_experiment(self):
        activity = LearningActivity.objects.create(
            subtopic=self.subtopic,
            activity_type=LearningActivity.ActivityType.EXPERIMENT,
            title="Dynamic experiment",
            display_order=1,
            status=PublishStatus.PUBLISHED,
        )
        configuration = {
            "schema_version": 1,
            "renderer": "placeholder",
            "renderer_config": {"message": "Admin supplied"},
        }
        experiment = Experiment.objects.create(
            activity=activity,
            experiment_type=Experiment.ExperimentType.SIMULATION,
            instructions="Admin supplied instructions",
            configuration=configuration,
        )
        self.client.force_authenticate(self.academic)

        response = self.client.get(reverse("activity-detail", args=[activity.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["experiment"]["id"], str(experiment.id))
        self.assertEqual(response.data["experiment"]["configuration"], configuration)

    def test_enrolled_student_receives_experiment_definition(self):
        self.publish_tree()
        self.activity.activity_type = LearningActivity.ActivityType.EXPERIMENT
        self.activity.save(update_fields=["activity_type"])
        configuration = {"schema_version": 1, "renderer": "placeholder"}
        Experiment.objects.create(
            activity=self.activity,
            experiment_type=Experiment.ExperimentType.SIMULATION,
            instructions="Admin supplied instructions",
            configuration=configuration,
        )
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        self.client.force_authenticate(self.student)

        response = self.client.get(reverse("activity-detail", args=[self.activity.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["experiment"]["configuration"], configuration)

    def test_nested_course_content_prefetch_has_constant_query_cost(self):
        ActivityContent.objects.create(activity=self.activity, content={"value": 1})
        second = LearningActivity.objects.create(
            subtopic=self.subtopic, activity_type=LearningActivity.ActivityType.EXPERIMENT,
            title="Reading", display_order=1, created_by=self.academic, updated_by=self.academic,
        )
        ActivityContent.objects.create(activity=second, content={"value": 2})
        Experiment.objects.create(
            activity=second,
            experiment_type=Experiment.ExperimentType.SIMULATION,
            instructions="Admin supplied",
            configuration={"schema_version": 1, "renderer": "placeholder"},
        )
        self.client.force_authenticate(self.academic)
        with self.assertNumQueries(9):
            response = self.client.get(reverse("course-detail", args=[self.course.id]))
            self.assertEqual(response.status_code, 200)
            records = response.data["versions"][0]["chapters"][0]["subtopics"][0]["activities"]
            self.assertEqual([row["content_record"]["content"]["value"] for row in records], [1, 2])
            self.assertEqual(records[1]["experiment"]["configuration"]["renderer"], "placeholder")

    def test_student_can_only_see_enrolled_published_course(self):
        self.publish_tree()
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        hidden = Course.objects.create(program=self.program, name="Hidden", code="hidden", status=PublishStatus.PUBLISHED)
        CourseVersion.objects.create(course=hidden, version_number=2026, name="2026", status=PublishStatus.PUBLISHED)
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("course-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [str(self.course.id)])

    def test_student_cannot_access_unenrolled_course(self):
        self.publish_tree()
        self.client.force_authenticate(self.other_student)
        self.assertEqual(self.client.get(reverse("course-detail", args=[self.course.id])).status_code, 404)

    def test_student_cannot_access_draft_chapter(self):
        self.publish_tree()
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        draft = Chapter.objects.create(course_version=self.version, title="Draft", slug="draft", chapter_number=2, display_order=1, status=PublishStatus.DRAFT)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(reverse("chapter-detail", args=[draft.id])).status_code, 404)
        response = self.client.get(reverse("course-chapters", args=[self.course.id]))
        self.assertEqual([item["id"] for item in response.data], [str(self.chapter.id)])

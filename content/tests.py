import json
import uuid
import tempfile
from pathlib import Path

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.constants import GroupName
from accounts.models import User
from curriculum.models import Chapter, Course, CourseVersion, LearningActivity, Program, PublishStatus, Subtopic
from media_library.models import MediaAsset
from students.models import Enrollment

from .models import ActivityContent, Experiment, PracticeItem, PracticeSet, Video
from .services import create_experiment, create_video, reorder_practice_items


def multivariable_demo_configuration():
    definition = Path(__file__).resolve().parent / "demo" / "multivariable_profit_workspace.json"
    return json.loads(definition.read_text(encoding="utf-8"))


class ContentFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)
        cls.manager = User.objects.create_user(email="phase3-content@example.com", username="phase3-content", password="pass")
        cls.manager.groups.add(Group.objects.get(name=GroupName.CONTENT_MANAGER))
        cls.student = User.objects.create_user(email="phase3-student@example.com", username="phase3-student", password="pass")
        cls.student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        cls.program = Program.objects.create(name="Program", code="phase3-program", status=PublishStatus.PUBLISHED)
        cls.course = Course.objects.create(program=cls.program, name="Course", code="phase3-course", status=PublishStatus.PUBLISHED)
        cls.version = CourseVersion.objects.create(course=cls.course, version_number=2026, name="2026", status=PublishStatus.PUBLISHED)
        cls.chapter = Chapter.objects.create(course_version=cls.version, title="Chapter", slug="phase3-chapter", chapter_number=1, status=PublishStatus.PUBLISHED)
        cls.subtopic = Subtopic.objects.create(chapter=cls.chapter, title="Subtopic", slug="phase3-subtopic", status=PublishStatus.PUBLISHED)
        cls.video_activity = LearningActivity.objects.create(subtopic=cls.subtopic, activity_type=LearningActivity.ActivityType.CONCEPT_VIDEO, title="Video", display_order=0, status=PublishStatus.PUBLISHED)
        cls.practice_activity = LearningActivity.objects.create(subtopic=cls.subtopic, activity_type=LearningActivity.ActivityType.OBSERVE_LEARN_PRACTICE, title="Practice", display_order=1, status=PublishStatus.PUBLISHED)
        cls.experiment_activity = LearningActivity.objects.create(subtopic=cls.subtopic, activity_type=LearningActivity.ActivityType.EXPERIMENT, title="Experiment", display_order=2, status=PublishStatus.PUBLISHED)
        cls.media = MediaAsset.objects.create(file_name="lesson.mp4", file_type="VIDEO", mime_type="video/mp4", file_size=1024, storage_path="courses/lesson.mp4", status=MediaAsset.Status.READY, uploaded_by=cls.manager)
        cls.video = Video.objects.create(activity=cls.video_activity, media_asset=cls.media, title="Lesson", duration_seconds=120)


class ContentModelServiceTests(ContentFixtureMixin, TestCase):
    def test_video_default_completion_is_ninety_percent(self):
        self.assertEqual(self.video.completion_percentage, 90)

    def test_video_requires_video_activity_type(self):
        with self.assertRaises(ValidationError):
            create_video(actor=self.manager, activity=self.experiment_activity, media_asset=self.media, title="Wrong", duration_seconds=20)

    def test_experiment_requires_compatible_activity_type(self):
        with self.assertRaises(ValidationError):
            create_experiment(actor=self.manager, activity=self.video_activity, experiment_type=Experiment.ExperimentType.EMBEDDED, instructions="Do it")

    def test_practice_item_database_constraint_matches_type(self):
        practice_set = PracticeSet.objects.create(activity=self.practice_activity, title="Set")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PracticeItem.objects.create(practice_set=practice_set, item_type=PracticeItem.ItemType.VIDEO, display_order=0)

    def test_practice_item_sequence_reorders_safely(self):
        practice_set = PracticeSet.objects.create(activity=self.practice_activity, title="Set")
        first = PracticeItem.objects.create(practice_set=practice_set, item_type=PracticeItem.ItemType.VIDEO, video=self.video, display_order=0)
        second = PracticeItem.objects.create(practice_set=practice_set, item_type=PracticeItem.ItemType.QUESTION, question_reference=uuid.uuid4(), display_order=1)
        reorder_practice_items(actor=self.manager, practice_set=practice_set, ordered_ids=[second.id, first.id])
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((second.display_order, first.display_order), (0, 1))

    def test_activity_content_stores_flexible_json(self):
        record = ActivityContent.objects.create(activity=self.experiment_activity, content_type="application/vnd.tella.overview+json", content={"blocks": [{"type": "text"}]})
        self.assertEqual(record.content["blocks"][0]["type"], "text")


class ContentApiTests(ContentFixtureMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_content_manager_can_create_media_metadata(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("media-asset-list"), {
            "file_name": "second.mp4", "file_type": "VIDEO", "mime_type": "video/mp4",
            "file_size": 2048, "storage_path": "courses/second.mp4", "status": "READY",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["uploaded_by"], self.manager.id)

    def test_content_manager_can_upload_media_and_receive_a_playable_url(self):
        self.client.force_authenticate(self.manager)
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("media-asset-list"), {
                "upload": SimpleUploadedFile("lesson video.mp4", b"demo-video-bytes", content_type="video/mp4"),
                "duration_seconds": 42,
                "storage_path": "untrusted/override.mp4",
                "file_type": "DOCUMENT",
                "status": "FAILED",
            }, format="multipart")

            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["file_name"], "lesson video.mp4")
            self.assertEqual(response.data["file_type"], "VIDEO")
            self.assertEqual(response.data["mime_type"], "video/mp4")
            self.assertEqual(response.data["status"], "READY")
            self.assertTrue(response.data["storage_path"].startswith("uploads/"))
            self.assertIn("/media/uploads/", response.data["public_url"])
            self.assertTrue(Path(media_root, response.data["storage_path"]).is_file())

    def test_content_manager_can_create_and_patch_activity_content(self):
        self.client.force_authenticate(self.manager)
        created = self.client.post(reverse("activity-content-list"), {
            "activity": str(self.experiment_activity.id),
            "content_type": "application/vnd.tella.overview+json",
            "content": {"title": "Overview", "extra": {"preserved": True}},
        }, format="json")
        self.assertEqual(created.status_code, 201)
        updated = self.client.patch(reverse("activity-content-detail", args=[created.data["id"]]), {
            "content": {"title": "Updated", "extra": {"preserved": True}},
        }, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["content"]["title"], "Updated")
        self.assertTrue(updated.data["content"]["extra"]["preserved"])

    def test_experiment_definition_round_trips_extension_fields(self):
        self.client.force_authenticate(self.manager)
        configuration = {
            "schema_version": 1,
            "renderer": "geogebra",
            "renderer_config": {
                "material_id": "admin-supplied-material",
                "app_name": "graphing",
                "parameters": {"showToolBar": False},
            },
            "tracking": {
                "watch_objects": ["x", "y"],
                "completion": {"object": "done", "operator": "equals", "value": 1},
            },
            "future_extension": {"preserved": True},
        }

        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.EMBEDDED,
            "instructions": "Follow the admin-authored instructions.",
            "configuration": configuration,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["configuration"], configuration)

    def test_geogebra_definition_requires_material_or_supported_workspace(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.EMBEDDED,
            "instructions": "Instructions",
            "configuration": {
                "schema_version": 1,
                "renderer": "geogebra",
                "renderer_config": {},
            },
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("material_id", str(response.data["configuration"][0]))

    def test_content_manager_can_post_graphspace_experiment(self):
        self.client.force_authenticate(self.manager)
        configuration = {
            "schema_version": 1,
            "renderer": "graphspace",
            "renderer_config": {
                "path": "/graphspace/index_3.html",
                "heading": "Agent decision surface",
                "message": "Graph value and autonomy against risk.",
            },
        }

        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.HTML_INTERACTIVE,
            "instructions": "Explore the decision surface.",
            "configuration": configuration,
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["configuration"], configuration)

    def test_graphspace_definition_rejects_an_untrusted_launch_path(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.HTML_INTERACTIVE,
            "instructions": "Explore the decision surface.",
            "configuration": {
                "schema_version": 1,
                "renderer": "graphspace",
                "renderer_config": {
                    "path": "https://untrusted.example/graphspace",
                    "heading": "Agent decision surface",
                    "message": "Graph value and autonomy against risk.",
                },
            },
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("/graphspace/index_3.html", str(response.data["configuration"][0]))

    def test_content_manager_can_post_data_driven_lpp_workspace(self):
        self.client.force_authenticate(self.manager)
        configuration = {
            "schema_version": 1,
            "renderer": "geogebra",
            "renderer_config": {
                "app_name": "graphing",
                "workspace": {
                    "type": "linear_programming",
                    "title": "LP model formulation",
                    "problem_statement": "Choose a profitable production mix.",
                    "axis_variables": ["x1", "x2"],
                    "variables": [
                        {"id": "x1", "label": "Product A", "symbol": "x1", "unit": "units", "min": 20, "max": 50, "initial": 20, "step": 1},
                        {"id": "x2", "label": "Product B", "symbol": "x2", "unit": "units", "min": 0, "max": 25, "initial": 5, "step": 1},
                        {"id": "x3", "label": "Product C", "symbol": "x3", "unit": "units", "min": 0, "max": 30, "initial": 10, "step": 1},
                    ],
                    "objective": {
                        "label": "Profit", "sense": "maximize", "currency": "₹",
                        "coefficients": {"x1": 12, "x2": 20, "x3": 45},
                    },
                    "constraints": [
                        {"id": "labour", "label": "Assembly time", "coefficients": {"x1": 0.8, "x2": 1.7, "x3": 2.5}, "operator": "<=", "rhs": 100},
                        {"id": "commitment", "label": "Combined commitment", "coefficients": {"x1": 0, "x2": 1, "x3": 1}, "operator": ">=", "rhs": 15},
                    ],
                },
            },
        }

        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.EMBEDDED,
            "instructions": "Change the values and calculate the feasible region.",
            "configuration": configuration,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["configuration"], configuration)

    def test_content_manager_can_post_data_driven_multivariable_workspace(self):
        self.client.force_authenticate(self.manager)
        configuration = multivariable_demo_configuration()

        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.SIMULATION,
            "instructions": "Explore the profit hill and explain your recommendation.",
            "configuration": configuration,
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["configuration"]["renderer_config"]["workspace"]["type"],
            "multivariable_profit",
        )
        self.assertEqual(
            response.data["configuration"]["renderer_config"]["workspace"]["steps"][1]["kind"],
            "slope",
        )

    def test_multivariable_workspace_rejects_a_model_without_one_peak(self):
        self.client.force_authenticate(self.manager)
        configuration = multivariable_demo_configuration()
        configuration["renderer_config"]["workspace"]["cross_effect"] = 1

        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.SIMULATION,
            "instructions": "Instructions",
            "configuration": configuration,
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("concave profit hill", str(response.data["configuration"][0]))

    def test_lpp_workspace_rejects_missing_coefficients(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.EMBEDDED,
            "instructions": "Instructions",
            "configuration": {
                "schema_version": 1,
                "renderer": "geogebra",
                "renderer_config": {
                    "workspace": {
                        "type": "linear_programming",
                        "axis_variables": ["x1", "x2"],
                        "variables": [
                            {"id": "x1", "min": 0, "max": 10, "initial": 0},
                            {"id": "x2", "min": 0, "max": 10, "initial": 0},
                        ],
                        "objective": {"sense": "maximize", "coefficients": {"x1": 1}},
                        "constraints": [
                            {"id": "capacity", "coefficients": {"x1": 1, "x2": 1}, "operator": "<=", "rhs": 10},
                        ],
                    },
                },
            },
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("every variable", str(response.data["configuration"][0]))

    def test_experiment_definition_rejects_non_string_renderer(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.EMBEDDED,
            "instructions": "Instructions",
            "configuration": {"schema_version": 1, "renderer": {"unexpected": True}},
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("renderer", str(response.data["configuration"][0]))

    def test_legacy_question_configuration_remains_valid(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("experiment-list"), {
            "activity": str(self.experiment_activity.id),
            "experiment_type": Experiment.ExperimentType.QUESTION_BASED,
            "instructions": "Instructions",
            "configuration": {"response_fields": [{"key": "answer"}]},
        }, format="json")

        self.assertEqual(response.status_code, 201)

    def test_student_cannot_create_or_patch_activity_content(self):
        record = ActivityContent.objects.create(activity=self.experiment_activity, content={"title": "Original"})
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        self.client.force_authenticate(self.student)
        created = self.client.post(reverse("activity-content-list"), {
            "activity": str(self.practice_activity.id), "content": {},
        }, format="json")
        updated = self.client.patch(reverse("activity-content-detail", args=[record.id]), {
            "content": {"title": "No"},
        }, format="json")
        self.assertEqual(created.status_code, 403)
        self.assertEqual(updated.status_code, 403)

    def test_student_reads_video_for_enrolled_published_course(self):
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("video-detail", args=[self.video.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["media_asset"], self.media.id)

    def test_student_cannot_read_video_without_enrollment(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(reverse("video-detail", args=[self.video.id])).status_code, 404)

    def test_student_media_list_only_contains_accessible_assets(self):
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        MediaAsset.objects.create(file_name="private.mp4", file_type="VIDEO", mime_type="video/mp4", storage_path="private/private.mp4", status="READY")
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("media-asset-list"))
        self.assertEqual([row["id"] for row in response.data], [str(self.media.id)])

    def test_student_cannot_create_video(self):
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        self.client.force_authenticate(self.student)
        response = self.client.post(reverse("video-list"), {
            "activity": str(self.video_activity.id), "media_asset": str(self.media.id),
            "title": "No", "duration_seconds": 10,
        }, format="json")
        self.assertEqual(response.status_code, 403)

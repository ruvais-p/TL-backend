import json
from pathlib import Path

from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import User
from content.experiment_definitions import validate_experiment_configuration
from content.models import ActivityContent, Experiment, Video
from curriculum.models import Chapter, Course, CourseVersion, LearningActivity, Program, PublishStatus, Subtopic
from media_library.models import MediaAsset
from students.models import Enrollment


LPP_DEFINITION = Path(__file__).resolve().parents[3] / "content" / "demo" / "lpp_workspace.json"
MULTIVARIABLE_DEFINITION = (
    Path(__file__).resolve().parents[3] / "content" / "demo" / "multivariable_profit_workspace.json"
)


class Command(BaseCommand):
    help = "Publish the two demo learning streams and attach local lesson videos without embedding lesson data in a renderer."

    def add_arguments(self, parser):
        parser.add_argument("--lpp-video", type=Path, help="Path to the Linear Programming lesson MP4.")
        parser.add_argument("--multivariable-video", type=Path, help="Path to the Multivariable Calculus lesson MP4.")

    @staticmethod
    def _required_user(email):
        user = User.objects.filter(email=email).first()
        if not user:
            raise CommandError(f"Missing demo user {email}. Run setup_groups and seed_workshop first.")
        return user

    def _media(self, source, storage_path, owner, duration):
        existing = MediaAsset.objects.filter(storage_path=storage_path).first()
        if source is None:
            if existing and default_storage.exists(storage_path):
                return existing
            self.stdout.write(self.style.WARNING(f"Video not attached because no path was supplied for {storage_path}."))
            return None
        source = source.expanduser().resolve()
        if not source.is_file():
            raise CommandError(f"Video file was not found: {source}")

        if default_storage.exists(storage_path) and default_storage.size(storage_path) != source.stat().st_size:
            default_storage.delete(storage_path)
        if not default_storage.exists(storage_path):
            with source.open("rb") as stream:
                saved_path = default_storage.save(storage_path, File(stream, name=source.name))
            if saved_path != storage_path:
                raise CommandError(f"Storage could not reserve the expected demo path: {storage_path}")

        media, _ = MediaAsset.objects.update_or_create(
            storage_path=storage_path,
            defaults={
                "file_name": source.name,
                "file_type": "VIDEO",
                "mime_type": "video/mp4",
                "file_size": source.stat().st_size,
                "duration_seconds": duration,
                "uploaded_by": owner,
                "status": MediaAsset.Status.READY,
            },
        )
        return media

    @staticmethod
    def _chapter(version, *, slug, legacy_slug=None, **values):
        chapter = version.chapters.filter(slug=slug).first()
        if chapter is None and legacy_slug:
            chapter = version.chapters.filter(slug=legacy_slug).first()
        if chapter is None:
            chapter = Chapter(course_version=version, slug=slug)
        chapter.slug = slug
        for field, value in values.items():
            setattr(chapter, field, value)
        chapter.save()
        return chapter

    @staticmethod
    def _subtopic(chapter, *, slug, legacy_slug=None, **values):
        subtopic = chapter.subtopics.filter(slug=slug).first()
        if subtopic is None and legacy_slug:
            subtopic = chapter.subtopics.filter(slug=legacy_slug).first()
        if subtopic is None:
            subtopic = Subtopic(chapter=chapter, slug=slug)
        subtopic.slug = slug
        for field, value in values.items():
            setattr(subtopic, field, value)
        subtopic.save()
        return subtopic

    @staticmethod
    def _activity(subtopic, order, manager, **values):
        activity = subtopic.activities.filter(display_order=order).first()
        if activity is None:
            activity = LearningActivity(subtopic=subtopic, display_order=order, created_by=manager)
        for field, value in values.items():
            setattr(activity, field, value)
        activity.updated_by = manager
        activity.save()
        return activity

    @transaction.atomic
    def handle(self, *args, **options):
        admin = self._required_user("admin@example.com")
        manager = self._required_user("content@example.com")
        student = self._required_user("student@example.com")
        if not LPP_DEFINITION.is_file():
            raise CommandError(f"LPP definition is missing: {LPP_DEFINITION}")
        if not MULTIVARIABLE_DEFINITION.is_file():
            raise CommandError(f"Multivariable definition is missing: {MULTIVARIABLE_DEFINITION}")
        lpp_configuration = validate_experiment_configuration(json.loads(LPP_DEFINITION.read_text(encoding="utf-8")))
        multivariable_configuration = validate_experiment_configuration(
            json.loads(MULTIVARIABLE_DEFINITION.read_text(encoding="utf-8"))
        )

        program, _ = Program.objects.update_or_create(
            code="business-mathematics-skill-path",
            defaults={
                "name": "Business Mathematics Skill Path",
                "description": "Curriculum-aligned mathematics skill enhancement through modelling and learning by doing.",
                "grade": "University",
                "status": PublishStatus.PUBLISHED,
                "created_by": admin,
            },
        )
        course, _ = Course.objects.update_or_create(
            code="multivariable-modelling-workshop",
            defaults={
                "program": program,
                "name": "Business Mathematics for Management Students",
                "description": "Applied mathematics lessons with video, interactive GeoGebra experiments, and business decision contexts.",
                "status": PublishStatus.PUBLISHED,
                "display_order": 1,
                "created_by": admin,
                "updated_by": manager,
            },
        )
        version, _ = CourseVersion.objects.update_or_create(
            course=course,
            version_number=1,
            defaults={
                "name": "2026 Demo Edition",
                "status": PublishStatus.PUBLISHED,
                "published_at": timezone.now(),
                "created_by": admin,
            },
        )

        version.chapters.update(chapter_number=F("chapter_number") + 100, display_order=F("display_order") + 100)
        lpp_chapter = self._chapter(
            version,
            slug="linear-programming",
            title="Linear Programming (LPP)",
            description="Formulate a business production problem, inspect its feasible region, and test the optimal allocation.",
            chapter_number=1,
            estimated_minutes=35,
            is_required=True,
            status=PublishStatus.PUBLISHED,
            display_order=1,
            completion_rule={"required_subtopics": True},
        )
        multivariable_chapter = self._chapter(
            version,
            slug="multivariable-calculus",
            legacy_slug="profit-landscape",
            title="Multivariable Calculus",
            description="Use multivariable models to understand how business outcomes change across two or more inputs.",
            chapter_number=2,
            estimated_minutes=35,
            is_required=True,
            status=PublishStatus.PUBLISHED,
            display_order=2,
            completion_rule={"required_subtopics": True},
        )
        version.chapters.exclude(id__in=[lpp_chapter.id, multivariable_chapter.id]).update(status=PublishStatus.ARCHIVED)

        lpp_subtopic = self._subtopic(
            lpp_chapter,
            slug="production-mix-model",
            title="Production mix model",
            description="Translate capacities, commitments, and profit contributions into a linear program.",
            learning_objectives=[
                "Formulate an objective function and business constraints",
                "Identify the feasible region for a two-dimensional slice",
                "Compare feasible vertices to find an optimal product mix",
            ],
            estimated_minutes=35,
            display_order=1,
            is_required=True,
            status=PublishStatus.PUBLISHED,
        )
        multivariable_subtopic = self._subtopic(
            multivariable_chapter,
            slug="business-applications",
            legacy_slug="hold-one-input-still",
            title="Business applications of multivariable calculus",
            description="Connect partial change, surfaces, and constrained decisions to management applications.",
            learning_objectives=[
                "Interpret a business response surface",
                "Explain how one input changes an outcome while other inputs are held fixed",
            ],
            estimated_minutes=35,
            display_order=1,
            is_required=True,
            status=PublishStatus.PUBLISHED,
        )
        lpp_chapter.subtopics.exclude(id=lpp_subtopic.id).update(status=PublishStatus.ARCHIVED)
        multivariable_chapter.subtopics.exclude(id=multivariable_subtopic.id).update(status=PublishStatus.ARCHIVED)

        lpp_media = self._media(options.get("lpp_video"), "demo/business-mathematics/lpp2.mp4", manager, 139)
        multivariable_media = self._media(
            options.get("multivariable_video"),
            "demo/business-mathematics/multivariable-calculus.mp4",
            manager,
            286,
        )

        lpp_video_activity = self._activity(
            lpp_subtopic,
            0,
            manager,
            activity_type=LearningActivity.ActivityType.CONCEPT_VIDEO,
            title="Lesson: Linear Programming for Business Decisions",
            description="Watch the lesson before experimenting with the production-mix model.",
            is_required=True,
            estimated_minutes=3,
            completion_rule={"watch_percentage": 90},
            status=PublishStatus.PUBLISHED if lpp_media else PublishStatus.DRAFT,
        )
        if lpp_media:
            Video.objects.update_or_create(
                activity=lpp_video_activity,
                defaults={
                    "media_asset": lpp_media,
                    "title": "Linear Programming for Business Decisions",
                    "description": "A concise introduction to LPP formulation and business constraints.",
                    "duration_seconds": 139,
                    "completion_percentage": 90,
                },
            )

        lpp_workshop_activity = self._activity(
            lpp_subtopic,
            1,
            manager,
            activity_type=LearningActivity.ActivityType.INTERACTIVE_WORKSHOP,
            title="Workshop: Build and optimise the LPP model",
            description="Change product limits, resource use, and contribution values; then rebuild the feasible region in GeoGebra.",
            is_required=True,
            estimated_minutes=25,
            completion_rule={"calculate_feasible_region": True},
            status=PublishStatus.PUBLISHED,
        )
        Experiment.objects.update_or_create(
            activity=lpp_workshop_activity,
            defaults={
                "experiment_type": Experiment.ExperimentType.SIMULATION,
                "instructions": "Move the Product C slider, edit assumptions if needed, then select Calculate & plot. Compare every feasible vertex and explain why the highlighted allocation is optimal.",
                "configuration": lpp_configuration,
            },
        )
        ActivityContent.objects.update_or_create(
            activity=lpp_workshop_activity,
            defaults={
                "content_type": "application/vnd.tella.workshop-intro+json",
                "content": {
                    "blocks": [
                        {
                            "type": "tip",
                            "heading": "Learning by doing",
                            "body": "The graph is generated from the current values. Change one assumption at a time and use the result table to explain what changed.",
                        }
                    ]
                },
            },
        )

        multivariable_video_activity = self._activity(
            multivariable_subtopic,
            0,
            manager,
            activity_type=LearningActivity.ActivityType.CONCEPT_VIDEO,
            title="Lesson: Multivariable Calculus Applications",
            description="Watch how multivariable calculus supports business analysis and decisions.",
            is_required=True,
            estimated_minutes=5,
            completion_rule={"watch_percentage": 90},
            status=PublishStatus.PUBLISHED if multivariable_media else PublishStatus.DRAFT,
        )
        if multivariable_media:
            Video.objects.update_or_create(
                activity=multivariable_video_activity,
                defaults={
                    "media_asset": multivariable_media,
                    "title": "Multivariable Calculus Applications",
                    "description": "Applications of multivariable calculus in management contexts.",
                    "duration_seconds": 286,
                    "completion_percentage": 90,
                },
            )

        multivariable_workshop = self._activity(
            multivariable_subtopic,
            1,
            manager,
            activity_type=LearningActivity.ActivityType.INTERACTIVE_WORKSHOP,
            title="Workshop: Climb the profit hill",
            description="Explore a two-product profit surface, interpret partial change, and use the gradient to improve a production decision.",
            is_required=True,
            estimated_minutes=25,
            completion_rule={"complete_guided_workshop": True},
            status=PublishStatus.PUBLISHED,
        )
        Experiment.objects.update_or_create(
            activity=multivariable_workshop,
            defaults={
                "experiment_type": Experiment.ExperimentType.SIMULATION,
                "instructions": "Complete the five guided stages. Change production quantities, read the partial slopes, follow the gradient toward the peak, and justify your recommendation.",
                "configuration": multivariable_configuration,
            },
        )
        ActivityContent.objects.update_or_create(
            activity=multivariable_workshop,
            defaults={
                "content_type": "application/vnd.tella.workshop-intro+json",
                "content": {
                    "blocks": [
                        {
                            "type": "tip",
                            "heading": "The lesson is data-driven",
                            "body": "The business values, stage instructions, and questions below were published by a content manager. GeoGebra builds the mathematical scene from that definition.",
                        }
                    ]
                },
            },
        )

        ai_course = Course.objects.filter(code="ai-agents-for-managers").first()
        if ai_course is None:
            call_command("seed_ai_management", verbosity=0)
            ai_course = Course.objects.get(code="ai-agents-for-managers")
        ai_course.name = "AI for Business Management"
        ai_course.description = "Practical AI skills for selecting, governing, and piloting AI workflows in business management."
        ai_course.status = PublishStatus.PUBLISHED
        ai_course.updated_by = manager
        ai_course.save(update_fields=["name", "description", "status", "updated_by", "updated_at"])
        ai_version = ai_course.versions.filter(status=PublishStatus.PUBLISHED).order_by("-version_number").first()
        if ai_version is None:
            raise CommandError("AI for Business Management has no published course version.")

        for assigned_course, assigned_version in ((course, version), (ai_course, ai_version)):
            Enrollment.objects.update_or_create(
                student=student,
                course=assigned_course,
                defaults={"course_version": assigned_version, "status": Enrollment.Status.ACTIVE},
            )

        self.stdout.write(self.style.SUCCESS("Published the Business Mathematics and AI for Business Management demo streams."))
        self.stdout.write(f"Business Mathematics course: {course.id}")
        self.stdout.write(f"LPP workshop activity: {lpp_workshop_activity.id}")
        self.stdout.write(f"Multivariable workshop activity: {multivariable_workshop.id}")
        self.stdout.write(f"Student enrollments: {Enrollment.objects.filter(student=student, status=Enrollment.Status.ACTIVE).count()}")

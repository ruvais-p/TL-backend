from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from accounts.constants import GroupName
from accounts.models import User
from curriculum.models import (
    Chapter,
    Course,
    CourseVersion,
    LearningActivity,
    Program,
    Subtopic,
)
from progress.models import CareerOpportunity
from students.models import Enrollment
from workshops.math import SAMPLE_BAKERY
from workshops.models import WorkshopConfig, WorkshopModel


class Command(BaseCommand):
    help = "Seed roles, demo users, and the bakery multivariable workshop."

    @staticmethod
    def configure_demo_user(user, password, *, is_staff=False, is_superuser=False):
        update_fields = []
        if not user.check_password(password):
            user.set_password(password)
            update_fields.append("password")
        if user.is_staff != is_staff:
            user.is_staff = is_staff
            update_fields.append("is_staff")
        if user.is_superuser != is_superuser:
            user.is_superuser = is_superuser
            update_fields.append("is_superuser")
        if update_fields:
            user.save(update_fields=update_fields)

    @transaction.atomic
    def handle(self, *args, **options):
        groups = {name: Group.objects.get_or_create(name=name)[0] for name in GroupName.values}

        admin, _ = User.objects.get_or_create(
            email="admin@example.com",
            defaults={
                "username": "admin",
                "first_name": "Tella",
                "last_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        self.configure_demo_user(admin, "Admin123!", is_staff=True, is_superuser=True)
        admin.groups.set([groups[GroupName.SUPER_ADMIN], groups[GroupName.ADMIN]])

        manager, _ = User.objects.get_or_create(
            email="content@example.com",
            defaults={
                "username": "content-manager",
                "first_name": "Content",
                "last_name": "Manager",
                "is_staff": True,
            },
        )
        self.configure_demo_user(manager, "Content123!", is_staff=True)
        manager.groups.set([groups[GroupName.CONTENT_MANAGER]])

        student, _ = User.objects.get_or_create(
            email="student@example.com",
            defaults={
                "username": "student",
                "first_name": "Demo",
                "last_name": "Student",
            },
        )
        self.configure_demo_user(student, "Student123!")
        student.groups.set([groups[GroupName.STUDENT]])

        program, _ = Program.objects.get_or_create(
            code="business-mathematics-skill-path",
            defaults={
                "name": "Business Mathematics Skill Path",
                "description": "Applied modelling for business decisions.",
                "status": "PUBLISHED",
            },
        )
        program.status = "PUBLISHED"
        program.save()

        course, _ = Course.objects.get_or_create(
            program=program,
            code="multivariable-modelling-workshop",
            defaults={
                "name": "Multivariable Modelling Workshop",
                "description": "Interactive profit landscape workshop.",
                "status": "PUBLISHED",
            },
        )
        course.status = "PUBLISHED"
        course.save()

        version, _ = CourseVersion.objects.get_or_create(
            course=course,
            version_number=1,
            defaults={"name": "2026", "status": "PUBLISHED"},
        )
        version.status = "PUBLISHED"
        version.save()

        chapter, _ = Chapter.objects.get_or_create(
            course_version=version,
            title="Profit landscape",
            slug="profit-landscape",
            defaults={"chapter_number": 1, "display_order": 1, "status": "PUBLISHED"},
        )
        subtopic, _ = Subtopic.objects.get_or_create(
            chapter=chapter,
            title="Hold one input still",
            slug="hold-one-input-still",
            defaults={"display_order": 1, "status": "PUBLISHED"},
        )
        activity, _ = LearningActivity.objects.get_or_create(
            subtopic=subtopic,
            title="Bakery profit landscape",
            defaults={
                "activity_type": LearningActivity.ActivityType.INTERACTIVE_WORKSHOP,
                "display_order": 1,
                "status": "PUBLISHED",
            },
        )
        activity.activity_type = LearningActivity.ActivityType.INTERACTIVE_WORKSHOP
        activity.status = "PUBLISHED"
        activity.save()

        sample = SAMPLE_BAKERY
        config, _ = WorkshopConfig.objects.update_or_create(
            activity=activity,
            defaults={
                "name": sample["name"],
                "price1": sample["price1"],
                "price_drop1": sample["priceDrop1"],
                "cost1": sample["cost1"],
                "price2": sample["price2"],
                "price_drop2": sample["priceDrop2"],
                "cost2": sample["cost2"],
                "congestion": sample["congestion"],
                "fixed_cost": sample["fixedCost"],
                "current_x": sample["currentX"],
                "current_y": sample["currentY"],
                "product1_label": sample["labels"]["product1"],
                "product2_label": sample["labels"]["product2"],
                "unit1": sample["labels"]["unit1"],
                "unit2": sample["labels"]["unit2"],
                "currency": sample["labels"]["currency"],
            },
        )

        WorkshopModel.objects.update_or_create(
            activity=activity,
            user=None,
            name=sample["name"],
            defaults={"config": sample},
        )

        enrollment = Enrollment.objects.filter(
            student=student,
            course=course,
            status=Enrollment.Status.ACTIVE,
        ).first()
        if enrollment:
            if enrollment.course_version_id != version.id:
                enrollment.course_version = version
                enrollment.save(update_fields=["course_version", "updated_at"])
        else:
            Enrollment.objects.create(student=student, course=course, course_version=version)

        CareerOpportunity.objects.update_or_create(
            title="Bakery operations internship",
            defaults={
                "kind": "internship",
                "legacy_kind": "internship",
                "company_name": "Tella Foods",
                "summary": "Apply modelling skills to a live production plan.",
                "description_markdown": (
                    "## About the internship\n\nApply optimisation skills to a live "
                    "production plan with an experienced operations team."
                ),
                "employment_type": CareerOpportunity.EmploymentType.INTERNSHIP,
                "workplace_mode": CareerOpportunity.WorkplaceMode.REMOTE,
                "remote_region": "India",
                "compensation_disclosure": CareerOpportunity.CompensationDisclosure.PAID,
                "compensation_currency": "INR",
                "compensation_min": 20000,
                "compensation_max": 30000,
                "compensation_pay_period": CareerOpportunity.PayPeriod.MONTH,
                "application_deadline": timezone.now() + timedelta(days=21),
                "application_mode": CareerOpportunity.ApplicationMode.EXTERNAL,
                "application_url": "https://example.com/internships",
                "url": "https://example.com/internships",
                "lifecycle_status": CareerOpportunity.LifecycleStatus.PUBLISHED,
                "is_published": True,
            },
        )
        CareerOpportunity.objects.update_or_create(
            title="Earn-while-you-learn: retail analytics",
            defaults={
                "kind": "earn_while_learn",
                "legacy_kind": "earn_while_learn",
                "company_name": "Northstar Retail",
                "summary": "Paid project work with partner firms.",
                "description_markdown": (
                    "## Project placement\n\nUse course insights to support a retail "
                    "analytics team."
                ),
                "employment_type": CareerOpportunity.EmploymentType.PROJECT,
                "workplace_mode": CareerOpportunity.WorkplaceMode.HYBRID,
                "physical_location": "Bengaluru, Karnataka",
                "compensation_disclosure": CareerOpportunity.CompensationDisclosure.UNPAID,
                "application_deadline": timezone.now() + timedelta(days=35),
                "application_mode": CareerOpportunity.ApplicationMode.INTERNAL,
                "cover_note_required": True,
                "resume_required": True,
                "lifecycle_status": CareerOpportunity.LifecycleStatus.PUBLISHED,
                "is_published": True,
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Seeded workshop activity {activity.id}"))
        self.stdout.write(f"Course id: {course.id}")
        self.stdout.write("Admin login: admin@example.com / Admin123!")
        self.stdout.write("Content manager login: content@example.com / Content123!")
        self.stdout.write("Student login: student@example.com / Student123!")

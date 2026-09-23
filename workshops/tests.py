from django.test import SimpleTestCase, TestCase
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from django.contrib.auth.models import Group
from accounts.constants import GroupName
from accounts.models import User
from students.models import Enrollment
from curriculum.models import (
    Chapter,
    Course,
    CourseVersion,
    LearningActivity,
    Program,
    Subtopic,
)
from workshops.math import (
    NO_PEAK_MESSAGE,
    SAMPLE_BAKERY,
    best_combination,
    coefficients,
    cost_of_being_off,
    monthly_gain,
    profit,
    slope_x,
    slope_y,
    validate_config,
)
from workshops.models import WorkshopConfig, WorkshopModel


class MathLayerTests(SimpleTestCase):
    def test_sample_coefficients(self):
        c = coefficients(SAMPLE_BAKERY)
        self.assertAlmostEqual(c["A"], 17.5, places=6)
        self.assertAlmostEqual(c["B"], 0.05, places=6)
        self.assertAlmostEqual(c["C"], 11.5, places=6)
        self.assertAlmostEqual(c["D"], 0.02, places=6)
        self.assertAlmostEqual(c["E"], 0.01, places=6)
        self.assertAlmostEqual(c["F"], 1000, places=6)

    def test_sample_profit_and_slopes(self):
        self.assertAlmostEqual(profit(200, 150, SAMPLE_BAKERY), 1475, delta=0.01)
        self.assertAlmostEqual(slope_x(200, 150, SAMPLE_BAKERY), -4.00, delta=0.01)
        self.assertAlmostEqual(slope_y(200, 150, SAMPLE_BAKERY), 3.50, delta=0.01)

    def test_sample_best_combination(self):
        peak = best_combination(SAMPLE_BAKERY)
        self.assertAlmostEqual(peak["den"], 0.0039, places=6)
        self.assertAlmostEqual(peak["bestX"], 150, delta=0.01)
        self.assertAlmostEqual(peak["bestY"], 250, delta=0.01)
        self.assertAlmostEqual(profit(150, 250, SAMPLE_BAKERY), 1750, delta=0.01)
        self.assertAlmostEqual(slope_x(150, 250, SAMPLE_BAKERY), 0, delta=0.01)
        self.assertAlmostEqual(slope_y(150, 250, SAMPLE_BAKERY), 0, delta=0.01)

    def test_monthly_gain_and_cost_of_being_off(self):
        self.assertEqual(monthly_gain(1750, 1475), 8250)
        self.assertAlmostEqual(cost_of_being_off(10, SAMPLE_BAKERY), 5, delta=0.01)
        self.assertAlmostEqual(cost_of_being_off(50, SAMPLE_BAKERY), 125, delta=0.01)

    def test_den_guard(self):
        bad = dict(SAMPLE_BAKERY)
        bad["congestion"] = 1
        peak = best_combination(bad)
        self.assertEqual(peak["error"], "NO_PEAK")
        self.assertEqual(peak["message"], NO_PEAK_MESSAGE)
        result = validate_config(bad)
        self.assertFalse(result["canPlot"])
        self.assertEqual(result["errors"]["congestion"], NO_PEAK_MESSAGE)

    def test_blank_field_blocks_plot(self):
        incomplete = dict(SAMPLE_BAKERY)
        incomplete["price1"] = None
        result = validate_config(incomplete)
        self.assertFalse(result["canPlot"])
        self.assertEqual(result["errors"]["price1"], "This field is required.")


class WorkshopModelApiTests(TestCase):
    def setUp(self):
        call_command("setup_groups", verbosity=0)
        student_group = Group.objects.get(name=GroupName.STUDENT)
        self.user = User.objects.create_user(email="student@example.com", password="pass12345")
        self.user.groups.add(student_group)
        program = Program.objects.create(
            name="Path", code="path", status="PUBLISHED"
        )
        self.course = Course.objects.create(
            program=program, name="Course", code="course", status="PUBLISHED"
        )
        version = CourseVersion.objects.create(
            course=self.course, version_number=1, name="2026", status="PUBLISHED"
        )
        Enrollment.objects.create(student=self.user, course=self.course, course_version=version)
        chapter = Chapter.objects.create(course_version=version, title="Ch", slug="ch", chapter_number=1, display_order=1, status="PUBLISHED")
        subtopic = Subtopic.objects.create(chapter=chapter, title="St", slug="st", display_order=1, status="PUBLISHED")
        self.activity = LearningActivity.objects.create(
            subtopic=subtopic,
            title="Workshop",
            activity_type=LearningActivity.ActivityType.INTERACTIVE_WORKSHOP,
            status="PUBLISHED",
            display_order=1,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_store_and_retrieve_sample_shape(self):
        url = reverse("workshop-model-list")
        response = self.client.post(
            url,
            {"activity": str(self.activity.id), "name": SAMPLE_BAKERY["name"], "config": SAMPLE_BAKERY},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        saved = WorkshopModel.objects.get(id=response.data["id"])
        self.assertEqual(saved.config["price1"], 30)
        self.assertEqual(saved.config["currentX"], 200)
        self.assertNotIn("profit", saved.config)
        detail = self.client.get(reverse("workshop-model-detail", args=[saved.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["config"]["labels"]["product1"], "Puffs")

    def test_nested_course_payload(self):
        url = reverse("course-detail", args=[self.course.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Course")
        chapters = response.data["published_version"]["chapters"]
        self.assertEqual(chapters[0]["subtopics"][0]["activities"][0]["title"], "Workshop")

    def test_super_admin_can_manage_config_and_review_saved_models(self):
        super_admin = User.objects.create_user(
            email="workshop-admin@example.com", password="StrongPass123!"
        )
        super_admin.groups.add(Group.objects.get(name=GroupName.SUPER_ADMIN))
        client = APIClient()
        client.force_authenticate(super_admin)

        payload = {
            "activity": str(self.activity.id),
            "name": SAMPLE_BAKERY["name"],
            "price1": SAMPLE_BAKERY["price1"],
            "price_drop1": SAMPLE_BAKERY["priceDrop1"],
            "cost1": SAMPLE_BAKERY["cost1"],
            "price2": SAMPLE_BAKERY["price2"],
            "price_drop2": SAMPLE_BAKERY["priceDrop2"],
            "cost2": SAMPLE_BAKERY["cost2"],
            "congestion": SAMPLE_BAKERY["congestion"],
            "fixed_cost": SAMPLE_BAKERY["fixedCost"],
            "current_x": SAMPLE_BAKERY["currentX"],
            "current_y": SAMPLE_BAKERY["currentY"],
        }
        response = client.post("/api/v1/workshop-configs/", payload, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(WorkshopConfig.objects.filter(activity=self.activity).exists())
        self.assertEqual(client.get("/api/v1/staff-workshop-models/").status_code, 200)

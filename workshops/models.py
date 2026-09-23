import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from curriculum.models import LearningActivity
from .math import validate_config


class WorkshopConfig(models.Model):
    """Canonical seven-input configuration attached to an INTERACTIVE_WORKSHOP activity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.OneToOneField(
        LearningActivity,
        on_delete=models.CASCADE,
        related_name="workshop_config",
    )
    name = models.CharField(max_length=200, default="Bakery — March actuals")
    price1 = models.DecimalField(max_digits=12, decimal_places=4)
    price_drop1 = models.DecimalField(max_digits=12, decimal_places=6)
    cost1 = models.DecimalField(max_digits=12, decimal_places=4)
    price2 = models.DecimalField(max_digits=12, decimal_places=4)
    price_drop2 = models.DecimalField(max_digits=12, decimal_places=6)
    cost2 = models.DecimalField(max_digits=12, decimal_places=4)
    congestion = models.DecimalField(max_digits=12, decimal_places=6)
    fixed_cost = models.DecimalField(max_digits=12, decimal_places=4)
    current_x = models.IntegerField(default=0)
    current_y = models.IntegerField(default=0)
    product1_label = models.CharField(max_length=80, default="Puffs")
    product2_label = models.CharField(max_length=80, default="Tea")
    unit1 = models.CharField(max_length=80, default="puffs per day")
    unit2 = models.CharField(max_length=80, default="teas per day")
    currency = models.CharField(max_length=8, default="₹")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def as_config(self) -> dict:
        return {
            "name": self.name,
            "price1": float(self.price1),
            "priceDrop1": float(self.price_drop1),
            "cost1": float(self.cost1),
            "price2": float(self.price2),
            "priceDrop2": float(self.price_drop2),
            "cost2": float(self.cost2),
            "congestion": float(self.congestion),
            "fixedCost": float(self.fixed_cost),
            "currentX": int(self.current_x),
            "currentY": int(self.current_y),
            "labels": {
                "product1": self.product1_label,
                "product2": self.product2_label,
                "unit1": self.unit1,
                "unit2": self.unit2,
                "currency": self.currency,
            },
        }

    def clean(self):
        result = validate_config(self.as_config())
        if not result["ok"] and "congestion" in result.get("errors", {}):
            raise ValidationError(result["errors"])

    def __str__(self):
        return f"{self.name} ({self.activity.title})"


class WorkshopModel(models.Model):
    """Learner or shared saved business numbers. Never stores computed values."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(
        LearningActivity, on_delete=models.CASCADE, related_name="workshop_models"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workshop_models",
    )
    name = models.CharField(max_length=200)
    config = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def clean(self):
        result = validate_config(self.config or {})
        if result.get("errors"):
            raise ValidationError(result["errors"])

    def __str__(self):
        return self.name

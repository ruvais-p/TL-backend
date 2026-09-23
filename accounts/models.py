import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        ordering = ["email"]
        permissions = [
            ("manage_users", "Can manage users"),
            ("manage_permissions", "Can manage groups and permissions"),
            ("bulk_import_students", "Can bulk import students"),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.username or self.email

    def has_group(self, name: str) -> bool:
        return self.groups.filter(name=name).exists()


class Auth0Identity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="auth0_identities",
    )
    issuer = models.URLField(max_length=500)
    subject = models.CharField(max_length=255)
    email_at_link_time = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_authenticated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["issuer", "subject"]
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "subject"],
                name="unique_auth0_issuer_subject",
            )
        ]
        indexes = [
            models.Index(fields=["user", "issuer"], name="auth0_identity_user_issuer_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.issuer}{self.subject} -> {self.user.email}"

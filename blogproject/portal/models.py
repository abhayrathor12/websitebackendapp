from django.conf import settings
from django.db import models


class PortalProfile(models.Model):
    """A masterclass participant's portal account (login is Django's built-in User)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portal_profile",
    )
    full_name = models.CharField(max_length=255)

    # Both set to True -> the user is deactivated and logged out (Phase 5).
    # Reset to False when the admin activates the user again.
    certificate_downloaded = models.BooleanField(default=False)
    linkedin_downloaded = models.BooleanField(default=False)

    # The admin turns this on per user (Master Portal Users page). Until then the
    # certificate and the LinkedIn guide cannot be downloaded, even after all evaluations.
    certificate_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.user.email}>"


class PasswordResetOTP(models.Model):
    """Forgot password: 6-digit OTP by email (valid 2 minutes). After the OTP is
    verified, a one-time reset token allows setting a new password."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portal_otps",
    )
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    reset_token_hash = models.CharField(max_length=64, blank=True)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user.email} ({self.created_at:%d %b %H:%M})"


class Evaluation(models.Model):
    """Fixed evaluations, created by migrations. Since 0005 there is only one:
    the Pre Assessment (slug "pre-session")."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=100)
    order = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


class Question(models.Model):
    OPTION_CHOICES = [("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")]

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_option = models.CharField(max_length=1, choices=OPTION_CHOICES)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.evaluation.title}: {self.text[:60]}"


class Attempt(models.Model):
    """One submitted evaluation per user (each evaluation can be taken once only)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portal_attempts",
    )
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="attempts"
    )
    answers = models.JSONField(default=dict)  # {"<question_id>": "A"}
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["evaluation__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "evaluation"], name="portal_one_attempt_per_evaluation"
            )
        ]

    def __str__(self):
        return f"{self.user.email} - {self.evaluation.title}: {self.score}/{self.total}"

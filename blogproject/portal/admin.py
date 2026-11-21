from django.contrib import admin

from .models import Attempt, Evaluation, PortalProfile, Question


@admin.register(PortalProfile)
class PortalProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "certificate_downloaded", "linkedin_downloaded", "created_at")
    search_fields = ("full_name", "user__email")


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "slug")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("evaluation", "text", "correct_option", "order")
    list_filter = ("evaluation",)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "evaluation", "score", "total", "submitted_at")
    list_filter = ("evaluation",)

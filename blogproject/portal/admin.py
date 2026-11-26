from django.contrib import admin
from django.utils.html import format_html_join

from . import knowledge_check
from .models import Attempt, Evaluation, KnowledgeCheck, PortalProfile, Question


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


@admin.register(KnowledgeCheck)
class KnowledgeCheckAdmin(admin.ModelAdmin):
    """Answers to the Pre-Masterclass Questions. Select rows and use the action
    "Download selected as CSV (Excel)" to export them."""

    list_display = ("participant", "email", "role", "experience", "ai_ml", "submitted_at")
    search_fields = ("user__email", "user__portal_profile__full_name")
    readonly_fields = ("user", "answers_table", "submitted_at")
    exclude = ("answers",)
    actions = ["export_csv"]
    list_select_related = ("user", "user__portal_profile")

    def has_add_permission(self, request):
        return False  # participants fill it in on the portal

    @admin.display(description="Name")
    def participant(self, obj):
        return knowledge_check.participant_name(obj)

    @admin.display(description="Email", ordering="user__email")
    def email(self, obj):
        return obj.user.email

    @admin.display(description="Role")
    def role(self, obj):
        return obj.answers.get("role_other") or obj.answers.get("role", "")

    @admin.display(description="Experience")
    def experience(self, obj):
        return obj.answers.get("experience", "")

    @admin.display(description="AI/ML level")
    def ai_ml(self, obj):
        return obj.answers.get("ai_ml", "")

    @admin.display(description="Answers")
    def answers_table(self, obj):
        return format_html_join(
            "", '<p style="margin:0 0 10px"><strong>{}</strong><br>{}</p>', knowledge_check.answer_rows(obj)
        )

    @admin.action(description="Download selected as CSV (Excel)")
    def export_csv(self, request, queryset):
        return knowledge_check.csv_response(queryset.select_related("user", "user__portal_profile"))

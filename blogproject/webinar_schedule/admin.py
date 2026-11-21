from django.contrib import admin

from .models import Webinar, WebinarInvite


@admin.register(Webinar)
class WebinarAdmin(admin.ModelAdmin):
    list_display = ("date", "topic", "start_time", "end_time", "join_link")
    readonly_fields = ("meeting_key", "join_link", "start_link", "created_at", "updated_at")


@admin.register(WebinarInvite)
class WebinarInviteAdmin(admin.ModelAdmin):
    list_display = ("registration", "webinar", "meeting_email_sent_at", "portal_email_sent_at")
    list_filter = ("webinar",)
    search_fields = ("registration__email", "registration__name")

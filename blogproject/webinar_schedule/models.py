"""Masterclass webinars (one Zoho meeting per date) and which registrant got which link."""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import models

IST = ZoneInfo("Asia/Kolkata")


class Webinar(models.Model):
    date = models.DateField(unique=True)
    topic = models.CharField(max_length=255)
    agenda = models.TextField(blank=True)
    start_time = models.TimeField(help_text="India time (IST)")
    end_time = models.TimeField(help_text="India time (IST)")

    # Created once in Zoho Meeting when the webinar is scheduled
    meeting_key = models.CharField(max_length=100)
    join_link = models.URLField(max_length=500)
    start_link = models.URLField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.topic} - {self.date:%d %b %Y}"

    @property
    def start_dt(self):
        return datetime.combine(self.date, self.start_time, tzinfo=IST)

    @property
    def end_dt(self):
        return datetime.combine(self.date, self.end_time, tzinfo=IST)

    @property
    def duration_ms(self):
        return int((self.end_dt - self.start_dt).total_seconds() * 1000)

    @property
    def when_text(self):
        """e.g. 'Sat, 21 Nov 2026, 10:00 AM - 05:30 PM (IST)'"""
        return (
            f"{self.date:%a, %d %b %Y}, "
            f"{self.start_dt:%I:%M %p} - {self.end_dt:%I:%M %p} (IST)"
        )


class WebinarInvite(models.Model):
    """Created for every paid Masterclass registration. webinar is empty while
    no upcoming webinar exists; it is filled when the next one is scheduled."""

    registration = models.OneToOneField(
        "blog.MasterClassRegistration",
        on_delete=models.CASCADE,
        related_name="webinar_invite",
    )
    webinar = models.ForeignKey(
        Webinar,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invites",
    )
    meeting_email_sent_at = models.DateTimeField(null=True, blank=True)
    # Added as a participant of the Zoho meeting (Zoho sends the calendar invitation)
    zoho_added_at = models.DateTimeField(null=True, blank=True)
    portal_email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.registration.email} -> {self.webinar or 'waiting'}"

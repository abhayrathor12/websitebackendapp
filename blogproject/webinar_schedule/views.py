"""'Webinar Schedule' page in websitebackend (staff only), mounted at /webinar-schedule/."""

import json
from datetime import date, datetime, time

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from . import zoho
from .models import IST, Webinar
from .services import (
    assign_waiting,
    in_background,
    mark_added_in_zoho,
    notify_update,
    participant_emails,
    resend_pending,
    today_ist,
    waiting_invites,
)


# Registrant count + "Show registrants" list on the page. Hidden for now; set True to show again.
SHOW_REGISTRANTS = False


def _error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _webinar_json(w):
    return {
        "id": w.id,
        "date": w.date.isoformat(),
        "topic": w.topic,
        "agenda": w.agenda,
        "start_time": w.start_time.strftime("%H:%M"),
        "end_time": w.end_time.strftime("%H:%M"),
        "when": w.when_text,
        "join_link": w.join_link,
        "start_link": w.start_link,
        # Link pasted by hand (no Zoho meeting behind it, so no Zoho invites/sync)
        "manual": not w.meeting_key,
        "is_past": w.date < today_ist(),
    }


def _clean(request, instance=None):
    """Validates the form. Returns (data, error_message)."""
    try:
        body = json.loads(request.body or "{}")
    except ValueError:
        return None, "Invalid request."

    topic = str(body.get("topic", "")).strip()
    agenda = str(body.get("agenda", "")).strip()
    if not topic:
        return None, "Please enter the meeting topic."
    if len(topic) > 255:
        return None, "The topic is too long (max 255 characters)."

    # Optional: a meeting link pasted by hand (Zoho, Google Meet, ...). Empty = create it in Zoho.
    join_link = str(body.get("join_link", "")).strip()
    if join_link:
        if len(join_link) > 500:
            return None, "The meeting link is too long (max 500 characters)."
        try:
            URLValidator(schemes=["https"])(join_link)
        except ValidationError:
            return None, "Please enter a valid meeting link starting with https://"

    try:
        day = date.fromisoformat(str(body.get("date", "")))
    except ValueError:
        return None, "Please select a valid date."
    try:
        start = time.fromisoformat(str(body.get("start_time", "")))
        end = time.fromisoformat(str(body.get("end_time", "")))
    except ValueError:
        return None, "Please select the start and end time."

    if end <= start:
        return None, "The end time must be after the start time."
    if day < today_ist():
        return None, "You cannot schedule a webinar on a past date."
    if datetime.combine(day, start, tzinfo=IST) <= datetime.now(IST):
        return None, "The start time has already passed. Please choose a later time."

    clash = Webinar.objects.filter(date=day)
    if instance:
        clash = clash.exclude(pk=instance.pk)
    if clash.exists():
        return None, f"A webinar is already scheduled on {day:%d %b %Y}."

    return {
        "date": day, "topic": topic, "agenda": agenda,
        "start_time": start, "end_time": end, "join_link": join_link,
    }, None


@staff_member_required
def schedule_page(request):
    webinars = Webinar.objects.annotate(
        registrants=Count("invites"),
        not_sent=Count(
            "invites",
            # Zoho invite only counts for meetings created in Zoho (not for pasted links)
            filter=Q(invites__meeting_email_sent_at__isnull=True)
            | (Q(invites__zoho_added_at__isnull=True) & ~Q(meeting_key="")),
        ),
    ).prefetch_related("invites__registration")
    last = Webinar.objects.order_by("-created_at").first()
    return render(
        request,
        "webinar_schedule/schedule.html",
        {
            "webinars": webinars,
            "webinars_json": [_webinar_json(w) for w in webinars],
            "waiting": waiting_invites(),
            "today": today_ist().isoformat(),
            "show_registrants": SHOW_REGISTRANTS,
            "defaults": {
                "topic": last.topic if last else "Smart Manufacturing & AI Masterclass",
                "agenda": last.agenda if last else "",
                "start_time": last.start_time.strftime("%H:%M") if last else "10:00",
                "end_time": last.end_time.strftime("%H:%M") if last else "17:30",
            },
        },
    )


@staff_member_required
@require_POST
def create_webinar(request):
    data, error = _clean(request)
    if error:
        return _error(error)

    join_link = data.pop("join_link")
    webinar = Webinar(**data)
    if join_link:
        # Manual: save the pasted link as it is, Zoho is not contacted
        webinar.meeting_key = ""
        webinar.join_link = join_link
        webinar.start_link = ""
    else:
        try:
            session = zoho.create_meeting(
                webinar.topic, webinar.agenda, webinar.start_dt, webinar.duration_ms
            )
        except zoho.ZohoError as exc:
            return _error(str(exc), status=502)
        webinar.meeting_key = str(session["meetingKey"])
        webinar.join_link = session["joinLink"]
        webinar.start_link = session.get("startLink") or ""
    webinar.save()

    # People who paid while no webinar was scheduled get this link now
    waiting = waiting_invites().count()
    if waiting:
        in_background(assign_waiting, webinar)

    return JsonResponse({"ok": True, "webinar": _webinar_json(webinar), "waiting_sent": waiting})


@staff_member_required
@require_POST
def update_webinar(request, pk):
    webinar = get_object_or_404(Webinar, pk=pk)
    if webinar.date < today_ist():
        return _error("This webinar is already over and cannot be edited.")

    data, error = _clean(request, instance=webinar)
    if error:
        return _error(error)

    join_link = data.pop("join_link")
    if not join_link:
        return _error("Please enter the meeting link.")
    link_changed = join_link != webinar.join_link
    time_changed = (
        data["date"] != webinar.date
        or data["start_time"] != webinar.start_time
        or data["end_time"] != webinar.end_time
    )
    for field, value in data.items():
        setattr(webinar, field, value)
    if link_changed:
        # A different link replaces the Zoho meeting: from now on it is a manual link
        webinar.join_link = join_link
        webinar.meeting_key = ""
        webinar.start_link = ""

    if webinar.meeting_key:
        # Send the full participant list too: Zoho replaces the list on every edit
        participants = participant_emails(webinar)
        try:
            session = zoho.update_meeting(
                webinar.meeting_key, webinar.topic, webinar.agenda, webinar.start_dt, webinar.duration_ms,
                participants=participants or None,
            )
        except zoho.ZohoError as exc:
            return _error(str(exc), status=502)
        if participants:
            mark_added_in_zoho(webinar)
        if session.get("joinLink"):
            webinar.join_link = session["joinLink"]
        if session.get("startLink"):
            webinar.start_link = session["startLink"]
    webinar.save()

    notify = bool(json.loads(request.body).get("notify")) and (time_changed or link_changed)
    notified = webinar.invites.filter(meeting_email_sent_at__isnull=False).count() if notify else 0
    if notified:
        in_background(notify_update, webinar)

    return JsonResponse({"ok": True, "webinar": _webinar_json(webinar), "notified": notified})


@staff_member_required
@require_POST
def resend_webinar_emails(request, pk):
    webinar = get_object_or_404(Webinar, pk=pk)
    pending_filter = Q(meeting_email_sent_at__isnull=True) | Q(portal_email_sent_at__isnull=True)
    if webinar.meeting_key:
        pending_filter |= Q(zoho_added_at__isnull=True)
    pending = webinar.invites.filter(pending_filter).count()
    if pending:
        in_background(resend_pending, webinar)
    return JsonResponse({"ok": True, "pending": pending})


@staff_member_required
@require_POST
def delete_webinar(request, pk):
    """Removes the webinar from the schedule (e.g. a test one). Its registrants
    go back to "waiting" and get the link of the next webinar you schedule.
    The meeting in Zoho itself is not deleted (do that in Zoho if needed)."""
    webinar = get_object_or_404(Webinar, pk=pk)
    moved = webinar.invites.update(webinar=None, meeting_email_sent_at=None, zoho_added_at=None)
    webinar.delete()
    return JsonResponse({"ok": True, "moved_to_waiting": moved})

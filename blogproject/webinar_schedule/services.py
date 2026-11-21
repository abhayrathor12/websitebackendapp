"""Which webinar a registrant gets, adding them to the Zoho meeting (Zoho sends
the calendar invitation), mail 2 (meeting link) and mail 3 (portal link)."""

import threading
from datetime import datetime

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import close_old_connections
from django.template.loader import render_to_string
from django.utils import timezone

from portal.accounts import ensure_portal_account, new_password_if_never_used

from . import zoho
from .models import IST, Webinar, WebinarInvite

DEFAULT_PORTAL_URL = "https://technovizautomation.com/masterportal"


def today_ist():
    return datetime.now(IST).date()


def next_webinar(on_date=None):
    """The webinar on that day or the first one after it (registering on the
    webinar day itself gives that day's link)."""
    on_date = on_date or today_ist()
    return Webinar.objects.filter(date__gte=on_date).order_by("date").first()


def in_background(func, *args):
    """Run in a thread (same approach as the existing registration mail) and
    release the DB connection afterwards."""

    def run():
        try:
            func(*args)
        except Exception as exc:  # never let a mail problem crash the thread silently
            print("❌ Webinar schedule background task failed:", exc)
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True).start()


# ─── Zoho participants (calendar invitation) ──────────────

_zoho_lock = threading.Lock()


def participant_emails(webinar):
    """Every registrant of this webinar (the full list Zoho expects)."""
    emails = webinar.invites.values_list("registration__email", flat=True)
    return sorted({e.strip().lower() for e in emails if e and e.strip()})


def mark_added_in_zoho(webinar):
    webinar.invites.filter(zoho_added_at__isnull=True).update(zoho_added_at=timezone.now())


def sync_zoho_participants(webinar):
    """Adds all registrants of this webinar as participants of its Zoho meeting.
    Zoho emails each NEW participant an invitation that is added to their
    calendar; people already on the list are not invited again.
    Returns True when Zoho accepted the list."""
    with _zoho_lock:  # two registrations at once must not overwrite each other's list
        webinar.refresh_from_db()
        if not webinar.meeting_key:
            return False  # link pasted by hand: there is no Zoho meeting to add people to
        if webinar.date < today_ist():
            return False  # already over, nothing to invite to
        emails = participant_emails(webinar)
        if not emails:
            return True
        try:
            zoho.update_meeting(
                webinar.meeting_key, webinar.topic, webinar.agenda,
                webinar.start_dt, webinar.duration_ms, participants=emails,
            )
        except zoho.ZohoError as exc:
            print("❌ Adding participants to Zoho failed:", webinar, exc)
            return False
        mark_added_in_zoho(webinar)
        return True


# ─── Mails ────────────────────────────────────────────────

def _first_name(name):
    return (name or "").strip().split(" ")[0] or "there"


def _send_designed_mail(subject, text, template, context, to):
    """Designed HTML mail (same look as mail 1, logo embedded) with the plain
    text as fallback for mail apps that block HTML."""
    # Shared branding lives with mail 1 in blog.views (imported here to avoid an import cycle)
    from blog.views import (
        EMAIL_LOGO_CID,
        MASTERCLASS_NAME,
        SITE_URL,
        SUPPORT_EMAIL,
        attach_inline_logo,
    )

    html = render_to_string(template, {
        "masterclass_name": MASTERCLASS_NAME,
        "logo_src": f"cid:{EMAIL_LOGO_CID}",
        "site_url": SITE_URL,
        "support_email": SUPPORT_EMAIL,
        "year": timezone.now().year,
        **context,
    })
    message = EmailMultiAlternatives(subject=subject, body=text, from_email=None, to=to)
    message.attach_alternative(html, "text/html")
    attach_inline_logo(message)
    message.send(fail_silently=False)


def send_meeting_email(invite, updated=False):
    webinar = invite.webinar
    if webinar is None:
        return False
    reg = invite.registration
    subject = (
        f"🔄 Updated: Masterclass joining link - {webinar.date:%a, %d %b %Y}"
        if updated
        else f"🔗 Your Masterclass joining link - {webinar.date:%a, %d %b %Y}"
    )
    intro = (
        "The details of your Masterclass session have been updated. Please note the new details below."
        if updated
        else "Here is your joining link for the Masterclass live session."
    )
    agenda = f"Agenda: {webinar.agenda}\n" if webinar.agenda else ""
    message = (
        f"Hi {reg.name},\n\n"
        f"{intro}\n\n"
        f"Topic: {webinar.topic}\n"
        f"{agenda}"
        f"Date & Time: {webinar.when_text}\n\n"
        f"Join the meeting:\n{webinar.join_link}\n\n"
        + (
            "You will also receive a Zoho Meeting invitation for this session, which adds it "
            "to your calendar.\n\n"
            if webinar.meeting_key else ""
        )
        + f"Please join 10 minutes early and keep this email safe. "
        f"Do not share the link with others.\n\n"
        f"Regards,\n"
        f"Technoviz Automation"
    )
    context = {
        "updated": updated,
        "name": reg.name,
        "first_name": _first_name(reg.name),
        "topic": webinar.topic,
        "agenda": webinar.agenda,
        "date_text": f"{webinar.date:%A, %d %B %Y}",
        "time_text": f"{webinar.start_dt:%I:%M %p} - {webinar.end_dt:%I:%M %p} (IST)",
        "join_link": webinar.join_link,
        "zoho_invite": bool(webinar.meeting_key),
        "steps": [
            ("Join 10 minutes early",
             "Open the link a little before the start time so audio and video are ready."),
            ("Use a laptop or desktop",
             "A stable internet connection and Chrome or Edge give the best experience."),
            ("Keep this link private",
             "The link is for you only. Please do not share it with others."),
        ],
    }
    try:
        _send_designed_mail(subject, message, "emails/masterclass_meeting.html", context, [reg.email])
    except Exception as exc:
        print("❌ Meeting link email failed:", reg.email, exc)
        return False
    invite.meeting_email_sent_at = timezone.now()
    invite.save(update_fields=["meeting_email_sent_at"])
    return True


def send_portal_email(invite, password=None):
    """Mail 3. password is given for a new account (shown in the mail); for an
    existing account they keep their current password."""
    reg = invite.registration
    portal_url = getattr(settings, "MASTERPORTAL_URL", DEFAULT_PORTAL_URL)
    login_email = reg.email.strip().lower()
    if password:
        login = (
            f"Your login details:\n"
            f"Email: {login_email}\n"
            f"Password: {password}\n\n"
            f"You can change this password after logging in (Change Password in the menu).\n"
        )
    else:
        login = (
            f"You already have a portal account. Log in with {login_email} and your existing "
            f"password. If you do not remember it, click \"Forgot password?\" on the login page.\n"
        )
    webinar = invite.webinar
    opening = (
        f"Your evaluations open when your masterclass starts: {webinar.when_text}.\n\n"
        if webinar
        else "Your evaluations open when your masterclass starts. We will email you the masterclass date and joining link.\n\n"
    )
    message = (
        f"Hi {reg.name},\n\n"
        f"Your Masterclass Portal account is ready. In the portal you will take the session "
        f"evaluations, see your marks, and download your certificate after you complete "
        f"all evaluations.\n\n"
        f"Portal link:\n{portal_url}\n\n"
        f"{login}\n"
        f"{opening}"
        f"For any help, contact support@technovizautomation.com.\n\n"
        f"Regards,\n"
        f"Technoviz Automation"
    )
    context = {
        "name": reg.name,
        "first_name": _first_name(reg.name),
        "login_email": login_email,
        "password": password,
        "portal_url": portal_url,
        "opens_text": webinar.when_text if webinar else "",
        "steps": [
            ("Watch the welcome video",
             "Get a quick overview of the masterclass and how the portal works."),
            ("Take the Pre Assessment",
             "It opens when your masterclass starts. Each assessment can be taken only once."),
            ("Check your results",
             "See your marks in My Results right after you submit."),
            ("Download your certificate",
             "After the masterclass, download your certificate and share it on LinkedIn."),
        ],
    }
    try:
        _send_designed_mail(
            "🎓 Your Masterclass Portal access", message,
            "emails/masterclass_portal.html", context, [reg.email],
        )
    except Exception as exc:
        print("❌ Portal email failed:", reg.email, exc)
        return False
    invite.portal_email_sent_at = timezone.now()
    invite.save(update_fields=["portal_email_sent_at"])
    return True


# ─── Flows ────────────────────────────────────────────────

def handle_new_registration(registration):
    """Called after the payment is verified (mail 1 is sent before this).
    Zoho: add them as a participant of the next webinar's meeting (calendar invite).
    Mail 2: meeting link of the next webinar (if one is scheduled).
    Mail 3: portal link."""
    reg_date = timezone.localtime(registration.created_at, IST).date()
    invite, _ = WebinarInvite.objects.get_or_create(
        registration=registration,
        defaults={"webinar": next_webinar(reg_date)},
    )
    # Portal login is created automatically (no registration on the portal)
    _user, password = ensure_portal_account(registration.name, registration.email)
    if invite.webinar and invite.webinar.meeting_key and not invite.zoho_added_at:
        sync_zoho_participants(invite.webinar)
    if invite.webinar and not invite.meeting_email_sent_at:
        send_meeting_email(invite)
    if not invite.portal_email_sent_at:
        send_portal_email(invite, password)
    return invite


def _resend_portal_email(invite):
    user, password = ensure_portal_account(invite.registration.name, invite.registration.email)
    if password is None:
        # The first mail failed, so they never saw their password: issue a new one
        password = new_password_if_never_used(user)
    return send_portal_email(invite, password)


def waiting_invites():
    return WebinarInvite.objects.filter(webinar__isnull=True).select_related("registration")


def assign_waiting(webinar):
    """Registrants who paid while no webinar was scheduled get this one."""
    invites = list(waiting_invites())
    for invite in invites:
        invite.webinar = webinar
        invite.save(update_fields=["webinar"])
    if invites and webinar.meeting_key:
        sync_zoho_participants(webinar)
    for invite in invites:
        send_meeting_email(invite)
    return len(invites)


def resend_pending(webinar):
    """Retry what failed for this webinar's registrants: adding them in Zoho and the mails."""
    sent = 0
    if webinar.meeting_key and webinar.invites.filter(zoho_added_at__isnull=True).exists():
        sync_zoho_participants(webinar)
    for invite in webinar.invites.select_related("registration", "webinar"):
        if not invite.meeting_email_sent_at and send_meeting_email(invite):
            sent += 1
        if not invite.portal_email_sent_at:
            _resend_portal_email(invite)
    return sent


def notify_update(webinar):
    """After the date/time was edited: send the new details to everyone who
    already received this webinar's link."""
    count = 0
    for invite in webinar.invites.select_related("registration", "webinar"):
        if invite.meeting_email_sent_at and send_meeting_email(invite, updated=True):
            count += 1
    return count

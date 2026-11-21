import json
import re
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blog.models import MasterClassRegistration
from portal.accounts import ensure_portal_account

from . import services, zoho
from .models import IST, Webinar, WebinarInvite

FAKE_SESSION = {"meetingKey": "123456789", "joinLink": "https://meeting.zoho.in/join?key=123456789",
                "startLink": "https://meeting.zoho.in/meeting/start?key=123456789"}


def today():
    return datetime.now(IST).date()


def make_webinar(day, **kw):
    return Webinar.objects.create(
        date=day, topic=kw.get("topic", "Masterclass"), agenda="",
        start_time=time(10, 0), end_time=time(17, 30),
        meeting_key=f"k{day:%Y%m%d}", join_link=f"https://meeting.zoho.in/join?key={day:%Y%m%d}",
    )


def make_registration(email="a@example.com", n=1):
    return MasterClassRegistration.objects.create(
        name="Test User", email=email, phone="9999999999", payment_id=f"pay_{n}_{email}",
    )


def run_now(func, *args):
    func(*args)


class NoRealZoho:
    """Registrations now add participants in Zoho: never call the real API in tests."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("webinar_schedule.zoho.update_meeting", return_value={})
        self.zoho_update = patcher.start()
        self.addCleanup(patcher.stop)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AssignmentTests(NoRealZoho, TestCase):
    def test_next_webinar_same_day_counts(self):
        make_webinar(today() + timedelta(days=30))
        same_day = make_webinar(today())
        self.assertEqual(services.next_webinar(today()), same_day)

    def test_after_webinar_day_gets_next_one(self):
        first = make_webinar(today() + timedelta(days=3))
        second = make_webinar(today() + timedelta(days=30))
        self.assertEqual(services.next_webinar(first.date), first)
        self.assertEqual(services.next_webinar(first.date + timedelta(days=1)), second)

    def test_new_registration_gets_meeting_and_portal_mail(self):
        w = make_webinar(today() + timedelta(days=5))
        invite = services.handle_new_registration(make_registration())
        self.assertEqual(invite.webinar, w)
        self.assertIsNotNone(invite.meeting_email_sent_at)
        self.assertIsNotNone(invite.portal_email_sent_at)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn(w.join_link, mail.outbox[0].body)
        self.assertIn("technovizautomation.com/masterportal", mail.outbox[1].body)
        # portal account created automatically, login in the mail
        user = User.objects.get(username="a@example.com")
        self.assertTrue(user.is_active)
        password = re.search(r"Password: (\S+)", mail.outbox[1].body).group(1)
        self.assertTrue(user.check_password(password))

    def test_existing_account_mail_has_no_password(self):
        make_webinar(today() + timedelta(days=5))
        services.handle_new_registration(make_registration())
        services.handle_new_registration(make_registration(n=2))  # pays again
        self.assertEqual(User.objects.filter(email="a@example.com").count(), 1)
        self.assertNotIn("Password:", mail.outbox[-1].body)
        self.assertIn("existing password", mail.outbox[-1].body)

    def test_resend_portal_mail_issues_new_password_if_never_logged_in(self):
        w = make_webinar(today() + timedelta(days=5))
        reg = make_registration()
        user, _ = ensure_portal_account(reg.name, reg.email)
        WebinarInvite.objects.create(registration=reg, webinar=w, meeting_email_sent_at=timezone.now())
        services.resend_pending(w)
        password = re.search(r"Password: (\S+)", mail.outbox[-1].body).group(1)
        user.refresh_from_db()
        self.assertTrue(user.check_password(password))

    def test_no_webinar_waits_then_gets_link_when_created(self):
        invite = services.handle_new_registration(make_registration())
        self.assertIsNone(invite.webinar)
        self.assertEqual(len(mail.outbox), 1)  # portal mail only
        w = make_webinar(today() + timedelta(days=10))
        self.assertEqual(services.assign_waiting(w), 1)
        invite.refresh_from_db()
        self.assertEqual(invite.webinar, w)
        self.assertIsNotNone(invite.meeting_email_sent_at)
        self.assertIn(w.join_link, mail.outbox[-1].body)

    def test_handle_twice_does_not_resend(self):
        make_webinar(today() + timedelta(days=5))
        reg = make_registration()
        services.handle_new_registration(reg)
        services.handle_new_registration(reg)
        self.assertEqual(len(mail.outbox), 2)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@mock.patch("webinar_schedule.views.in_background", side_effect=run_now)
class PageTests(NoRealZoho, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user("admin", "admin@x.com", "pw", is_staff=True)
        self.client.force_login(self.admin)
        self.day = today() + timedelta(days=7)

    def body(self, **kw):
        data = {"date": self.day.isoformat(), "topic": "Smart AI Masterclass", "agenda": "Smart AI",
                "start_time": "10:00", "end_time": "17:30"}
        data.update(kw)
        return json.dumps(data)

    def post(self, url, body):
        return self.client.post(url, body, content_type="application/json")

    def test_page_needs_staff(self, _bg):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("webinar-schedule")).status_code, 302)

    def test_page_loads(self, _bg):
        make_webinar(self.day)
        res = self.client.get(reverse("webinar-schedule"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Webinar Schedule")

    @mock.patch("webinar_schedule.zoho.create_meeting", return_value=FAKE_SESSION)
    def test_create_saves_link_and_sends_to_waiting(self, create, _bg):
        services.handle_new_registration(make_registration())  # waiting
        res = self.post(reverse("webinar-schedule-create"), self.body())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["waiting_sent"], 1)
        w = Webinar.objects.get()
        self.assertEqual(w.join_link, FAKE_SESSION["joinLink"])
        self.assertEqual(w.duration_ms, int(7.5 * 3600 * 1000))
        args = create.call_args.args
        self.assertEqual(args[2], datetime(self.day.year, self.day.month, self.day.day, 10, 0, tzinfo=IST))
        self.assertEqual(args[3], 27000000)
        self.assertEqual(WebinarInvite.objects.get().webinar, w)

    @mock.patch("webinar_schedule.zoho.create_meeting")
    def test_create_validation(self, create, _bg):
        cases = [
            self.body(topic=""),
            self.body(end_time="09:00"),
            self.body(date=(today() - timedelta(days=1)).isoformat()),
        ]
        for body in cases:
            self.assertEqual(self.post(reverse("webinar-schedule-create"), body).status_code, 400)
        make_webinar(self.day)
        self.assertEqual(self.post(reverse("webinar-schedule-create"), self.body()).status_code, 400)
        create.assert_not_called()

    @mock.patch("webinar_schedule.zoho.create_meeting", side_effect=zoho.ZohoError("Zoho down"))
    def test_zoho_error_saves_nothing(self, _create, _bg):
        res = self.post(reverse("webinar-schedule-create"), self.body())
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"], "Zoho down")
        self.assertFalse(Webinar.objects.exists())

    @mock.patch("webinar_schedule.zoho.update_meeting", return_value={})
    def test_edit_time_notifies_registrants(self, update, _bg):
        w = make_webinar(self.day)
        services.handle_new_registration(make_registration())
        mail.outbox.clear()
        res = self.post(reverse("webinar-schedule-update", args=[w.id]),
                        self.body(start_time="11:00", notify=True, join_link=w.join_link))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["notified"], 1)
        w.refresh_from_db()
        self.assertEqual(w.start_time, time(11, 0))
        self.assertEqual(update.call_args.args[0], w.meeting_key)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Updated", mail.outbox[0].subject)

    @mock.patch("webinar_schedule.zoho.update_meeting", return_value={})
    def test_edit_topic_only_sends_nothing(self, _update, _bg):
        w = make_webinar(self.day)
        services.handle_new_registration(make_registration())
        mail.outbox.clear()
        res = self.post(reverse("webinar-schedule-update", args=[w.id]), self.body(topic="New", notify=True, join_link=w.join_link))
        self.assertEqual(res.json()["notified"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_past_webinar_cannot_be_edited(self, _bg):
        w = make_webinar(today() - timedelta(days=2))
        res = self.post(reverse("webinar-schedule-update", args=[w.id]), self.body())
        self.assertEqual(res.status_code, 400)

    def test_resend_failed(self, _bg):
        w = make_webinar(self.day)
        reg = make_registration()
        WebinarInvite.objects.create(registration=reg, webinar=w)
        res = self.post(reverse("webinar-schedule-resend", args=[w.id]), "{}")
        self.assertEqual(res.json()["pending"], 1)
        inv = WebinarInvite.objects.get()
        self.assertIsNotNone(inv.meeting_email_sent_at)
        self.assertIsNotNone(inv.portal_email_sent_at)


class ZohoPayloadTests(TestCase):
    ENV = {"ZOHO_CLIENT_ID": "id", "ZOHO_CLIENT_SECRET": "s", "ZOHO_REFRESH_TOKEN": "r",
           "ZOHO_ZSOID": "60000", "ZOHO_PRESENTER_ID": "777", "ZOHO_ZSOURCE": "src"}

    def test_missing_settings_message(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(zoho.ZohoError, "ZOHO_CLIENT_ID"):
                zoho.create_meeting("t", "a", datetime(2026, 11, 21, 10, 0, tzinfo=IST), 3600000)

    def test_payload_matches_tested_script(self):
        with mock.patch.dict("os.environ", self.ENV):
            p = zoho._payload("Topic", "Agenda", datetime(2026, 11, 21, 15, 0, tzinfo=IST), 3600000)
        self.assertEqual(p, {"session": {
            "topic": "Topic", "agenda": "Agenda", "presenter": 777,
            "startTime": "Nov 21, 2026 03:00 PM", "duration": 3600000, "timezone": "Asia/Calcutta"}})



@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@mock.patch("webinar_schedule.zoho.update_meeting", return_value={})
class ZohoParticipantTests(TestCase):
    def participants(self, update):
        return update.call_args.kwargs["participants"]

    def test_registration_adds_full_list_to_zoho(self, update):
        w = make_webinar(today() + timedelta(days=5))
        services.handle_new_registration(make_registration("First@Example.com", 1))
        self.assertEqual(update.call_args.args[0], w.meeting_key)
        self.assertEqual(self.participants(update), ["first@example.com"])
        invite = services.handle_new_registration(make_registration("second@example.com", 2))
        # Zoho replaces the list, so the earlier registrant must still be in it
        self.assertEqual(self.participants(update), ["first@example.com", "second@example.com"])
        invite.refresh_from_db()
        self.assertIsNotNone(invite.zoho_added_at)
        # our joining-link mail no longer carries an .ics invite (only the embedded logo)
        self.assertFalse(any("calendar" in str(a) for a in mail.outbox[0].attachments))
        self.assertIn("Zoho Meeting invitation", mail.outbox[0].body)
        # mails 2 and 3 are designed HTML (plain text stays as fallback)
        link_html, link_type = mail.outbox[0].alternatives[0]
        self.assertEqual(link_type, "text/html")
        self.assertIn(w.join_link, link_html)
        self.assertIn("Join the Masterclass", link_html)
        portal_html = mail.outbox[1].alternatives[0][0]
        self.assertIn("Your Login Details", portal_html)
        self.assertIn(re.search(r"Password: (\S+)", mail.outbox[1].body).group(1), portal_html)

    def test_zoho_failure_still_sends_mails_and_can_retry(self, update):
        w = make_webinar(today() + timedelta(days=5))
        update.side_effect = zoho.ZohoError("Zoho down")
        invite = services.handle_new_registration(make_registration())
        invite.refresh_from_db()
        self.assertIsNone(invite.zoho_added_at)
        self.assertEqual(len(mail.outbox), 2)  # link + portal mail still sent
        update.side_effect = None
        services.resend_pending(w)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.zoho_added_at)

    def test_waiting_registrants_added_when_webinar_created(self, update):
        services.handle_new_registration(make_registration("a@example.com", 1))
        services.handle_new_registration(make_registration("b@example.com", 2))
        update.assert_not_called()  # no webinar yet
        w = make_webinar(today() + timedelta(days=5))
        services.assign_waiting(w)
        self.assertEqual(update.call_count, 1)  # one call with the whole list
        self.assertEqual(self.participants(update), ["a@example.com", "b@example.com"])
        self.assertFalse(WebinarInvite.objects.filter(zoho_added_at__isnull=True).exists())

    def test_past_webinar_is_not_synced(self, update):
        w = make_webinar(today() - timedelta(days=1))
        WebinarInvite.objects.create(registration=make_registration(), webinar=w)
        self.assertFalse(services.sync_zoho_participants(w))
        update.assert_not_called()

    def test_payload_participants(self, _update):
        with mock.patch.dict("os.environ", {k: "1" for k in zoho.REQUIRED}):
            no_list = zoho._payload("T", "", datetime(2026, 12, 1, 10, tzinfo=IST), 1000)
            with_list = zoho._payload("T", "", datetime(2026, 12, 1, 10, tzinfo=IST), 1000, ["x@y.com"])
        self.assertNotIn("participants", no_list["session"])
        self.assertEqual(with_list["session"]["participants"], [{"email": "x@y.com"}])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@mock.patch("webinar_schedule.views.in_background", side_effect=run_now)
@mock.patch("webinar_schedule.zoho.update_meeting")
@mock.patch("webinar_schedule.zoho.create_meeting")
class ManualLinkTests(TestCase):
    """Free PythonAnywhere cannot reach Zoho Meeting: the admin pastes the link by hand."""

    LINK = "https://meet.zoho.in/abcd-efg-hij"

    def setUp(self):
        self.client.force_login(User.objects.create_user("admin", "a@x.com", "pw", is_staff=True))
        self.day = today() + timedelta(days=10)

    def post(self, url, **kw):
        data = {"date": self.day.isoformat(), "topic": "Masterclass", "agenda": "",
                "start_time": "10:00", "end_time": "17:30"}
        data.update(kw)
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_pasted_link_is_saved_without_zoho_and_sent_to_waiting(self, create, update, _bg):
        services.handle_new_registration(make_registration("w@example.com"))  # paid, no webinar yet
        mail.outbox.clear()
        res = self.post(reverse("webinar-schedule-create"), join_link=self.LINK)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["webinar"]["manual"])
        create.assert_not_called()
        update.assert_not_called()
        w = Webinar.objects.get()
        self.assertEqual((w.join_link, w.meeting_key), (self.LINK, ""))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.LINK, mail.outbox[0].body)
        self.assertNotIn("Zoho Meeting invitation", mail.outbox[0].body)
        self.assertNotIn("Zoho Meeting</strong>", mail.outbox[0].alternatives[0][0])

    def test_new_registrant_gets_manual_link_and_is_not_pending(self, create, update, _bg):
        self.post(reverse("webinar-schedule-create"), join_link=self.LINK)
        services.handle_new_registration(make_registration("n@example.com"))
        update.assert_not_called()
        self.assertIn(self.LINK, mail.outbox[0].body)
        page = self.client.get(reverse("webinar-schedule"))
        self.assertEqual(page.context["webinars"][0].not_sent, 0)

    def test_bad_link_rejected(self, create, update, _bg):
        for link in ("meet.zoho.in/abc", "http://meet.zoho.in/abc", "https://"):
            self.assertEqual(self.post(reverse("webinar-schedule-create"), join_link=link).status_code, 400, link)
        self.assertFalse(Webinar.objects.exists())

    def test_edit_link_notifies_and_skips_zoho(self, create, update, _bg):
        self.post(reverse("webinar-schedule-create"), join_link=self.LINK)
        w = Webinar.objects.get()
        services.handle_new_registration(make_registration("e@example.com"))
        mail.outbox.clear()
        new = "https://meet.google.com/xyz-abcd-efg"
        res = self.post(reverse("webinar-schedule-update", args=[w.id]), join_link=new, notify=True)
        self.assertEqual(res.json()["notified"], 1)
        update.assert_not_called()
        self.assertIn(new, mail.outbox[0].body)
        self.assertIn("Updated", mail.outbox[0].subject)

    def test_edit_needs_link(self, create, update, _bg):
        self.post(reverse("webinar-schedule-create"), join_link=self.LINK)
        w = Webinar.objects.get()
        res = self.post(reverse("webinar-schedule-update", args=[w.id]), join_link="")
        self.assertEqual(res.status_code, 400)

    def test_replacing_zoho_link_makes_it_manual(self, create, update, _bg):
        w = make_webinar(self.day)  # created in Zoho (has a meeting key)
        res = self.post(reverse("webinar-schedule-update", args=[w.id]), join_link=self.LINK)
        self.assertEqual(res.status_code, 200, res.content)
        update.assert_not_called()
        w.refresh_from_db()
        self.assertEqual((w.join_link, w.meeting_key), (self.LINK, ""))



@mock.patch("webinar_schedule.zoho.update_meeting", return_value={})
class DeleteTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("admin", "a@x.com", "pw", is_staff=True))

    def test_delete_moves_registrants_to_waiting(self, _update):
        w = make_webinar(today() + timedelta(days=5))
        invite = WebinarInvite.objects.create(
            registration=make_registration(), webinar=w,
            meeting_email_sent_at=timezone.now(), zoho_added_at=timezone.now(),
        )
        res = self.client.post(reverse("webinar-schedule-delete", args=[w.id]))
        self.assertEqual(res.json(), {"ok": True, "moved_to_waiting": 1})
        self.assertFalse(Webinar.objects.exists())
        invite.refresh_from_db()
        self.assertIsNone(invite.webinar)
        self.assertIsNone(invite.meeting_email_sent_at)
        self.assertIsNone(invite.zoho_added_at)

    def test_past_webinar_can_be_deleted(self, _update):
        w = make_webinar(today() - timedelta(days=3))
        self.assertEqual(self.client.post(reverse("webinar-schedule-delete", args=[w.id])).status_code, 200)
        self.assertFalse(Webinar.objects.exists())

    def test_delete_needs_staff_and_post(self, _update):
        w = make_webinar(today() + timedelta(days=5))
        self.assertEqual(self.client.get(reverse("webinar-schedule-delete", args=[w.id])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("webinar-schedule-delete", args=[w.id])).status_code, 302)
        self.assertTrue(Webinar.objects.exists())

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from blog.models import MasterClassRegistration

from .accounts import ensure_portal_account, generate_password
from .models import Evaluation, PortalProfile, Question

User = get_user_model()
PASSWORD = "Str0ng-Pass-123"


class PortalPhase1Tests(TestCase):
    """Accounts are created automatically after payment (no registration on the portal)."""

    def setUp(self):
        self.api = APIClient()
        self.user, self.password = ensure_portal_account("Paid User", "Paid@Example.com")

    def login(self, email="paid@example.com", password=None):
        return self.api.post(
            "/api/portal/login/",
            {"email": email, "password": password or self.password},
            format="json",
        )

    def test_only_pre_assessment_left(self):
        self.assertEqual(
            list(Evaluation.objects.values_list("slug", "title")),
            [("pre-session", "Pre Assessment")],
        )

    def test_account_created_active_with_name_password(self):
        self.assertEqual(self.user.username, "paid@example.com")
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.portal_profile.full_name, "Paid User")
        self.assertRegex(self.password, r"^Paid@\d{4}$")

    def test_existing_account_keeps_password(self):
        user, password = ensure_portal_account("Paid User", "PAID@example.com")
        self.assertEqual(user, self.user)
        self.assertIsNone(password)
        self.assertEqual(User.objects.filter(email__iexact="paid@example.com").count(), 1)

    def test_password_generation(self):
        self.assertRegex(generate_password("  rahul kumar "), r"^Rahul@\d{4}$")
        self.assertRegex(generate_password("Dr. A.K. Sharma"), r"^Dr@\d{4}$")
        self.assertRegex(generate_password(""), r"^User@\d{4}$")

    def test_register_endpoint_removed(self):
        res = self.api.post("/api/portal/register/", {}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_login_works_and_sets_last_login(self):
        res = self.login()
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["user"]["is_admin"])
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

        self.api.credentials(HTTP_AUTHORIZATION=f"Token {res.data['token']}")
        me = self.api.get("/api/portal/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], "paid@example.com")

    def test_deactivated_login_refused(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        res = self.login()
        self.assertEqual(res.status_code, 403)
        self.assertIn("not active", res.data["message"])

    def test_wrong_password(self):
        self.assertEqual(self.login(password="wrong").status_code, 400)

    def test_logout_deletes_token(self):
        token = self.login().data["token"]
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.api.post("/api/portal/logout/").status_code, 200)
        self.assertEqual(self.api.get("/api/portal/me/").status_code, 401)

    def test_staff_can_log_in_as_admin(self):
        User.objects.create_user(username="admin", email="admin@x.com", password=PASSWORD, is_staff=True)
        res = self.login(email="admin", password=PASSWORD)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["user"]["is_admin"])

    def test_plain_django_user_has_no_portal_access(self):
        User.objects.create_user(username="other", email="other@x.com", password=PASSWORD)
        self.assertEqual(self.login(email="other", password=PASSWORD).status_code, 403)

    def test_staff_page_activate_and_deactivate(self):
        profile = self.user.portal_profile
        profile.certificate_downloaded = True
        profile.linkedin_downloaded = True
        profile.save()
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        staff = User.objects.create_user(username="admin", password=PASSWORD, is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/portal-users/").status_code, 200)

        res = self.client.post(f"/portal-users/toggle/{profile.id}/", '{"active": true}',
                               content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        profile.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertFalse(profile.certificate_downloaded)
        self.assertFalse(profile.linkedin_downloaded)

        token = self.login().data["token"]
        self.client.post(f"/portal-users/toggle/{profile.id}/", '{"active": false}',
                         content_type="application/json")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(Token.objects.filter(key=token).exists())

    def test_staff_page_requires_staff(self):
        res = self.client.get("/portal-users/")
        self.assertEqual(res.status_code, 302)  # redirected to admin login


QUESTION = {
    "text": "What does OEE stand for?",
    "option_a": "Overall Equipment Effectiveness",
    "option_b": "Operational Energy Efficiency",
    "option_c": "Output Efficiency Estimate",
    "option_d": "Overall Energy Effectiveness",
    "correct_option": "A",
}


class PortalPhase3QuestionTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        staff = User.objects.create_user(username="admin", password=PASSWORD, is_staff=True)
        self.staff_token = Token.objects.create(user=staff).key
        self.url = "/api/portal/admin/evaluations/pre-session/questions/"

    def as_staff(self):
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token}")

    def test_participant_cannot_manage_questions(self):
        user = User.objects.create_user(username="p@x.com", email="p@x.com", password=PASSWORD)
        PortalProfile.objects.create(user=user, full_name="P")
        token = Token.objects.create(user=user).key
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.api.get(self.url).status_code, 403)
        self.assertEqual(self.api.post(self.url, QUESTION, format="json").status_code, 403)

    def test_anonymous_cannot_manage_questions(self):
        self.assertEqual(self.api.get(self.url).status_code, 401)

    def test_create_list_update_delete(self):
        self.as_staff()
        res = self.api.post(self.url, QUESTION, format="json")
        self.assertEqual(res.status_code, 201)
        qid = res.data["id"]
        self.assertEqual(res.data["order"], 1)

        second = self.api.post(self.url, {**QUESTION, "text": "Second?"}, format="json")
        self.assertEqual(second.data["order"], 2)

        listing = self.api.get(self.url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data["questions"]), 2)
        self.assertEqual(listing.data["questions"][0]["correct_option"], "A")
        self.assertEqual(listing.data["evaluation"]["title"], "Pre Assessment")

        upd = self.api.put(
            f"/api/portal/admin/questions/{qid}/",
            {**QUESTION, "correct_option": "C"},
            format="json",
        )
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.data["correct_option"], "C")

        self.assertEqual(self.api.delete(f"/api/portal/admin/questions/{qid}/").status_code, 204)
        self.assertEqual(len(self.api.get(self.url).data["questions"]), 1)

    def test_validation(self):
        self.as_staff()
        res = self.api.post(self.url, {**QUESTION, "option_b": "   "}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Option B", res.data["message"])

        res = self.api.post(self.url, {**QUESTION, "correct_option": "E"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_unknown_evaluation(self):
        self.as_staff()
        res = self.api.get("/api/portal/admin/evaluations/nope/questions/")
        self.assertEqual(res.status_code, 404)


class PortalPhase45ParticipantTests(TestCase):
    """Taking evaluations in order, results, certificate + LinkedIn downloads, auto-deactivation."""

    def setUp(self):
        self.api = APIClient()
        self.user = User.objects.create_user(
            username="p@x.com", email="p@x.com", password=PASSWORD
        )
        self.profile = PortalProfile.objects.create(user=self.user, full_name="Test Participant")
        self.token = Token.objects.create(user=self.user).key
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 2 questions per evaluation; correct answer is always "B"
        for ev in Evaluation.objects.all():
            for n in range(2):
                ev.questions.create(
                    text=f"{ev.slug} Q{n}", option_a="a", option_b="b",
                    option_c="c", option_d="d", correct_option="B", order=n,
                )

    def answers_for(self, slug, choice="B"):
        ev = Evaluation.objects.get(slug=slug)
        return {str(q.id): choice for q in ev.questions.all()}

    def submit(self, slug, answers=None):
        return self.api.post(
            f"/api/portal/evaluations/{slug}/submit/",
            {"answers": answers if answers is not None else self.answers_for(slug)},
            format="json",
        )

    def complete_all(self):
        for ev in Evaluation.objects.all():
            self.assertEqual(self.submit(ev.slug).status_code, 201)

    def test_only_first_evaluation_open_initially(self):
        res = self.api.get("/api/portal/progress/")
        statuses = [e["status"] for e in res.data["evaluations"]]
        self.assertEqual(statuses, ["open"])
        self.assertFalse(res.data["all_done"])

    def test_questions_hide_correct_answer(self):
        res = self.api.get("/api/portal/evaluations/pre-session/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "open")
        self.assertNotIn("correct_option", res.data["questions"][0])
        self.assertNotIn("correct", res.data["questions"][0])

    def test_locked_evaluation_blocked(self):
        # Removed evaluations no longer exist
        self.assertEqual(self.api.get("/api/portal/evaluations/session-1/").status_code, 404)
        res = self.api.post("/api/portal/evaluations/post-session/submit/", {"answers": {}}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_submit_scores_and_unlocks_next(self):
        answers = self.answers_for("pre-session")
        first_id = next(iter(answers))
        answers[first_id] = "A"  # one wrong
        res = self.submit("pre-session", answers)
        self.assertEqual(res.status_code, 201)
        self.assertEqual((res.data["score"], res.data["total"]), (1, 2))
        wrong = [q for q in res.data["questions"] if not q["is_correct"]]
        self.assertEqual(len(wrong), 1)
        self.assertEqual(wrong[0]["selected"], "A")
        self.assertEqual(wrong[0]["correct"], "B")

        statuses = [e["status"] for e in self.api.get("/api/portal/progress/").data["evaluations"]]
        self.assertEqual(statuses, ["done"])

        # Viewing it again shows the saved result
        again = self.api.get("/api/portal/evaluations/pre-session/")
        self.assertEqual(again.data["status"], "done")
        self.assertEqual(again.data["score"], 1)

    def test_submit_only_once(self):
        self.assertEqual(self.submit("pre-session").status_code, 201)
        self.assertEqual(self.submit("pre-session").status_code, 400)

    def test_all_questions_must_be_answered(self):
        answers = self.answers_for("pre-session")
        answers.pop(next(iter(answers)))
        self.assertEqual(self.submit("pre-session", answers).status_code, 400)
        self.assertEqual(self.submit("pre-session", {k: "X" for k in answers}).status_code, 400)

    def test_result_unchanged_after_admin_edits_question(self):
        self.submit("pre-session")
        Question.objects.filter(evaluation__slug="pre-session").update(
            correct_option="C", text="changed"
        )
        res = self.api.get("/api/portal/evaluations/pre-session/")
        self.assertEqual(res.data["score"], 2)
        self.assertTrue(all(q["is_correct"] for q in res.data["questions"]))

    def test_downloads_locked_until_all_done(self):
        self.assertEqual(self.api.get("/api/portal/certificate/").status_code, 403)
        self.assertEqual(self.api.get("/api/portal/linkedin-guide/").status_code, 403)

    def test_downloads_wait_for_admin_certificate_activation(self):
        self.complete_all()
        progress = self.api.get("/api/portal/progress/").data
        self.assertTrue(progress["all_done"])
        self.assertFalse(progress["certificate_enabled"])
        for path in ("/api/portal/certificate/", "/api/portal/linkedin-guide/"):
            res = self.api.get(path)
            self.assertEqual(res.status_code, 403)
            self.assertIn("waiting for approval", res.data["message"])

        # Staff switch on -> download works; switch off -> blocked again
        staff = User.objects.create_user(username="admin", password=PASSWORD, is_staff=True)
        self.client.force_login(staff)
        url = f"/portal-users/certificate/{self.profile.id}/"
        res = self.client.post(url, '{"enabled": true}', content_type="application/json")
        self.assertEqual(res.json(), {"success": True, "enabled": True})
        self.assertTrue(self.api.get("/api/portal/progress/").data["certificate_enabled"])
        self.assertEqual(self.api.get("/api/portal/certificate/").status_code, 200)

        self.client.post(url, '{"enabled": false}', content_type="application/json")
        self.assertEqual(self.api.get("/api/portal/certificate/").status_code, 403)

    def test_certificate_toggle_is_staff_only(self):
        url = f"/portal-users/certificate/{self.profile.id}/"
        self.client.force_login(self.user)
        self.client.post(url, '{"enabled": true}', content_type="application/json")
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.certificate_enabled)

    def test_both_downloads_deactivate_then_reactivate(self):
        self.assertIsNone(self.api.get("/api/portal/progress/").data["certificate"])
        self.complete_all()
        progress = self.api.get("/api/portal/progress/").data
        self.assertTrue(progress["all_done"])
        self.assertEqual(progress["certificate"]["name"], "Test Participant")
        self.assertEqual(progress["certificate"]["certificate_id"], self.profile.certificate_id)
        self.assertTrue(progress["certificate"]["verify_url"].endswith(
            f"/verify-certificate?id={self.profile.certificate_id}"))
        self.assertTrue(set("".join(progress["certificate"]["qr"])) <= {"0", "1"})
        self.profile.certificate_enabled = True
        self.profile.save()

        cert = self.api.get("/api/portal/certificate/")
        self.assertEqual(cert.status_code, 200)
        self.assertEqual(cert["Content-Type"], "application/pdf")
        self.assertTrue(cert.content.startswith(b"%PDF"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)  # only one file so far

        guide = self.api.get("/api/portal/linkedin-guide/")
        self.assertEqual(guide.status_code, 200)
        self.assertTrue(b"".join(guide.streaming_content).startswith(b"%PDF"))

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(self.api.get("/api/portal/progress/").status_code, 401)

        # Admin re-activates: downloads available again, and deactivate again afterwards
        staff = User.objects.create_user(username="admin", password=PASSWORD, is_staff=True)
        self.client.force_login(staff)
        self.client.post(f"/portal-users/toggle/{self.profile.id}/", '{"active": true}',
                         content_type="application/json")
        login = APIClient().post("/api/portal/login/", {"email": "p@x.com", "password": PASSWORD},
                                 format="json")
        self.assertEqual(login.status_code, 200)
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        progress = self.api.get("/api/portal/progress/").data
        self.assertTrue(progress["all_done"])
        self.assertFalse(progress["certificate_downloaded"])

        self.api.get("/api/portal/linkedin-guide/")
        self.api.get("/api/portal/certificate/")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_staff_cannot_use_participant_api(self):
        staff = User.objects.create_user(username="admin", password=PASSWORD, is_staff=True)
        token = Token.objects.create(user=staff).key
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.api.get("/api/portal/progress/").status_code, 403)

    def test_certificate_pdf_builds_with_long_name(self):
        from datetime import date

        from .certificate import build_certificate_pdf

        pdf = build_certificate_pdf("A Very Long Participant Name " * 3, date(2026, 11, 21), "TVA-MC26-00001")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_certificate_id_made_at_registration(self):
        cert_id = self.profile.certificate_id
        self.assertRegex(cert_id, r"^TVA-MC26-[A-HJKMNP-Z2-9]{6}$")
        other = PortalProfile.objects.create(
            user=User.objects.create_user(username="q@x.com", email="q@x.com", password=PASSWORD),
            full_name="Other",
        )
        self.assertNotEqual(other.certificate_id, cert_id)
        self.profile.full_name = "Renamed"
        self.profile.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.certificate_id, cert_id)  # never changes

    def test_verify_certificate(self):
        public = APIClient()  # not logged in
        url = f"/api/portal/verify-certificate/{self.profile.certificate_id}/"

        res = public.get("/api/portal/verify-certificate/TVA-MC26-ZZZZZZ/")
        self.assertEqual((res.status_code, res.data["status"]), (404, "not_found"))

        # ID exists but the certificate is not issued yet: no personal details
        res = public.get(url)
        self.assertEqual(res.data["status"], "not_issued")
        self.assertNotIn("name", res.data)

        self.complete_all()
        self.assertEqual(public.get(url).data["status"], "not_issued")  # admin has not activated

        self.profile.certificate_enabled = True
        self.profile.save()
        # lower case + spaces typed by a visitor still match
        res = public.get(f"/api/portal/verify-certificate/{self.profile.certificate_id.lower()} /")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "verified")
        self.assertEqual(res.data["name"], "Test Participant")
        self.assertEqual(res.data["course"], "Smart Manufacturing & AI Masterclass 2026")
        self.assertNotIn("email", res.data)

        # Still verifiable after the user is deactivated (both downloads done)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(public.get(url).data["status"], "verified")

    def test_certificate_date_is_masterclass_date(self):
        from datetime import date, time

        from webinar_schedule.models import Webinar, WebinarInvite
        from blog.models import MasterClassRegistration

        self.complete_all()  # (evaluations open only once the masterclass starts)
        webinar = Webinar.objects.create(
            date=date(2026, 12, 12), topic="Masterclass", start_time=time(10), end_time=time(17, 30),
            meeting_key="", join_link="https://example.com/j",
        )
        registration = MasterClassRegistration.objects.create(
            name="Test Participant", email="p@x.com", phone="9999999999", payment_id="pay_cert_1"
        )
        WebinarInvite.objects.create(registration=registration, webinar=webinar)
        progress = self.api.get("/api/portal/progress/").data
        self.assertEqual(str(progress["certificate"]["completed_on"]), "2026-12-12")


# ─── Forgot password (OTP), change password, webinar-time lock ───

import re
from datetime import datetime, time, timedelta
from unittest import mock

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from webinar_schedule.models import IST, Webinar, WebinarInvite

from .models import PasswordResetOTP


def run_thread_now(target, args=(), daemon=None, **kw):
    """Replaces threading.Thread so the OTP email is sent synchronously in tests."""
    class T:
        def start(self):
            target(*args)
    return T()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@mock.patch("portal.views.threading.Thread", side_effect=run_thread_now)
class PasswordTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user, self.password = ensure_portal_account("Riya Shah", "riya@example.com")

    def forgot(self, email="riya@example.com"):
        return self.api.post("/api/portal/forgot-password/", {"email": email}, format="json")

    def otp_from_mail(self):
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)

    def verify(self, otp, email="riya@example.com"):
        return self.api.post("/api/portal/verify-otp/", {"email": email, "otp": otp}, format="json")

    def reset(self, token, password="Brand-New-Pass-9", email="riya@example.com"):
        return self.api.post(
            "/api/portal/reset-password/",
            {"email": email, "reset_token": token, "password": password},
            format="json",
        )

    def test_full_reset_flow(self, _t):
        res = self.forgot()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["expires_in"], 120)
        self.assertEqual(len(mail.outbox), 1)
        token = self.verify(self.otp_from_mail()).data["reset_token"]
        self.assertEqual(self.reset(token).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-New-Pass-9"))
        # the reset token works only once
        self.assertEqual(self.reset(token, password="Another-Pass-77").status_code, 400)

    def test_unknown_email_same_answer_no_mail(self, _t):
        res = self.forgot("nobody@example.com")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["message"], self.forgot().data["message"])
        self.assertEqual(len(mail.outbox), 1)  # only the real user got a mail

    def test_otp_expires_after_2_minutes(self, _t):
        self.forgot()
        code = self.otp_from_mail()
        PasswordResetOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        res = self.verify(code)
        self.assertEqual(res.status_code, 400)
        self.assertIn("expired", res.data["message"])

    def test_wrong_otp_attempts_limited(self, _t):
        self.forgot()
        code = self.otp_from_mail()
        wrong = "000000" if code != "000000" else "111111"
        for left in (4, 3, 2, 1):
            res = self.verify(wrong)
            self.assertIn(f"{left} attempt", res.data["message"])
        self.assertIn("Too many", self.verify(wrong).data["message"])
        self.assertIn("Too many", self.verify(code).data["message"])  # even the right one now

    def test_one_otp_per_2_minutes_and_new_one_replaces_old(self, _t):
        self.forgot()
        first = self.otp_from_mail()
        self.forgot()
        self.assertEqual(len(mail.outbox), 1)  # not resent within 2 minutes
        PasswordResetOTP.objects.update(created_at=timezone.now() - timedelta(minutes=3))
        self.forgot()
        self.assertEqual(len(mail.outbox), 2)
        second = self.otp_from_mail()
        if first != second:
            self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)

    def test_weak_new_password_refused(self, _t):
        self.forgot()
        token = self.verify(self.otp_from_mail()).data["reset_token"]
        self.assertEqual(self.reset(token, password="123").status_code, 400)

    def test_reset_logs_out_other_devices(self, _t):
        old = Token.objects.create(user=self.user).key
        self.forgot()
        self.reset(self.verify(self.otp_from_mail()).data["reset_token"])
        self.assertFalse(Token.objects.filter(key=old).exists())

    def test_change_password(self, _t):
        token = Token.objects.create(user=self.user).key
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        url = "/api/portal/change-password/"
        bad = self.api.post(url, {"current_password": "nope", "new_password": "Brand-New-Pass-9"}, format="json")
        self.assertEqual(bad.status_code, 400)
        weak = self.api.post(url, {"current_password": self.password, "new_password": "123"}, format="json")
        self.assertEqual(weak.status_code, 400)
        ok = self.api.post(url, {"current_password": self.password, "new_password": "Brand-New-Pass-9"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-New-Pass-9"))
        self.assertEqual(self.api.get("/api/portal/me/").status_code, 200)  # still logged in

    def test_change_password_needs_login(self, _t):
        self.assertEqual(self.api.post("/api/portal/change-password/", {}, format="json").status_code, 401)


class WebinarLockTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user, _ = ensure_portal_account("Lock User", "lock@example.com")
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.reg = MasterClassRegistration.objects.create(
            name="Lock User", email="Lock@Example.com", phone="9999999999", payment_id="pay_lock"
        )

    def webinar(self, start):
        return Webinar.objects.create(
            date=start.date(), topic="T", start_time=start.time(), end_time=time(23, 59),
            meeting_key="k", join_link="https://meeting.zoho.in/join?key=k",
        )

    def statuses(self):
        res = self.api.get("/api/portal/progress/")
        return res, [e["status"] for e in res.data["evaluations"]]

    def test_old_user_without_webinar_link_is_open(self):
        res, statuses = self.statuses()
        self.assertEqual(statuses[0], "open")
        self.assertFalse(res.data["waiting_for_webinar"])

    def test_locked_before_webinar_start(self):
        start = (datetime.now(IST) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        WebinarInvite.objects.create(registration=self.reg, webinar=self.webinar(start))
        res, statuses = self.statuses()
        self.assertEqual(statuses, ["locked"])
        self.assertTrue(res.data["waiting_for_webinar"])
        self.assertIn("10:00 AM", res.data["schedule_message"])
        ev = self.api.get("/api/portal/evaluations/pre-session/")
        self.assertEqual(ev.status_code, 403)
        self.assertIn("when your masterclass starts", ev.data["message"])

    def test_open_after_webinar_start(self):
        start = (datetime.now(IST) - timedelta(minutes=5)).replace(second=0, microsecond=0)
        WebinarInvite.objects.create(registration=self.reg, webinar=self.webinar(start))
        res, statuses = self.statuses()
        self.assertEqual(statuses, ["open"])
        self.assertFalse(res.data["waiting_for_webinar"])

    def test_waiting_without_webinar_is_locked(self):
        WebinarInvite.objects.create(registration=self.reg, webinar=None)
        res, statuses = self.statuses()
        self.assertEqual(statuses, ["locked"])
        self.assertIsNone(res.data["evaluations_locked_until"])
        self.assertTrue(res.data["waiting_for_webinar"])


# ─── Knowledge Check (Pre-Masterclass Questions) ───

from portal.models import KnowledgeCheck  # noqa: E402

GOOD_ANSWERS = {
    "role": "Automation",
    "experience": "8–15 Years",
    "plc_knowledge": "Intermediate",
    "industrial_data": "Hands-on Experience",
    "ai_ml": "Beginner",
    "genai_tools": "Regularly",
    "rag_agents": "Basic Understanding",
    "ai_usecase": "PoC/Experiment",
    "ai_usecase_details": "Vision inspection of welds",
    "interests": ["Predictive Maintenance", "Generative AI + RAG"],
    "problem": "Unplanned downtime on our press line",
}


class KnowledgeCheckTests(TestCase):
    URL = "/api/portal/knowledge-check/"

    def setUp(self):
        self.api = APIClient()
        self.user, _ = ensure_portal_account("Kc User", "kc@example.com")
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")

    def post(self, **changes):
        answers = {**GOOD_ANSWERS, **changes}
        return self.api.post(self.URL, {"answers": answers}, format="json")

    def test_questions_are_listed_and_always_open(self):
        res = self.api.get(self.URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["questions"]), 10)
        self.assertIsNone(res.data["answers"])

    def test_submit_once_then_locked(self):
        res = self.post()
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["answers"]["role"], "Automation")
        # multi-choice keeps the order of the listed options
        self.assertEqual(res.data["answers"]["interests"], ["Generative AI + RAG", "Predictive Maintenance"])
        res = self.post(role="Quality")
        self.assertEqual(res.status_code, 409)
        self.assertIn("cannot be changed", res.data["message"])
        self.assertEqual(KnowledgeCheck.objects.get(user=self.user).answers["role"], "Automation")
        # the tab stays open: GET still shows the saved answers
        self.assertEqual(self.api.get(self.URL).data["answers"]["role"], "Automation")

    def test_validation(self):
        self.assertEqual(self.post(experience="").status_code, 400)
        self.assertEqual(self.post(experience="99 Years").status_code, 400)
        self.assertEqual(self.post(interests=[]).status_code, 400)
        res = self.post(role="Other", role_other="")
        self.assertEqual(res.status_code, 400)
        self.assertIn("question 1", res.data["message"].lower())
        self.assertEqual(self.post(role="Other", role_other="Plant Head").status_code, 200)
        self.assertFalse(KnowledgeCheck.objects.filter(answers__role="").exists())

    def test_optional_texts_and_hidden_detail_cleared(self):
        res = self.post(problem="", ai_usecase="No", ai_usecase_details="should be dropped")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["answers"]["ai_usecase_details"], "")
        self.assertEqual(res.data["answers"]["problem"], "")

    def test_progress_shows_done_flag(self):
        self.assertFalse(self.api.get("/api/portal/progress/").data["knowledge_check_done"])
        self.post()
        self.assertTrue(self.api.get("/api/portal/progress/").data["knowledge_check_done"])

    def test_needs_participant_login(self):
        self.api.credentials()
        self.assertEqual(self.api.get(self.URL).status_code, 401)
        staff = User.objects.create_user("staffer", "s@x.com", PASSWORD, is_staff=True)
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=staff).key}")
        self.assertEqual(self.api.get(self.URL).status_code, 403)

    def test_admin_csv_export(self):
        self.post(role="Other", role_other="Plant Head")
        admin_user = User.objects.create_superuser("boss", "b@x.com", PASSWORD)
        self.client.force_login(admin_user)
        res = self.client.post(
            "/admin/portal/knowledgecheck/",
            {"action": "export_csv", "_selected_action": [KnowledgeCheck.objects.get().pk]},
        )
        self.assertEqual(res.status_code, 200)
        body = res.content.decode("utf-8-sig")
        self.assertIn("Q1. Your current role/function", body.splitlines()[0])
        self.assertIn("Plant Head", body)
        self.assertIn("Generative AI + RAG, Predictive Maintenance", body)


    def test_answers_on_portal_users_page_and_export(self):
        self.post(role="Other", role_other="Plant Head")
        page_url, export_url = "/portal-users/", "/portal-users/knowledge-check/export/"
        self.assertEqual(self.client.get(export_url).status_code, 302)  # staff only
        self.client.force_login(User.objects.create_user("staff2", "st@x.com", PASSWORD, is_staff=True))
        res = self.client.get(page_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "View answers")
        self.assertContains(res, "Plant Head")
        self.assertEqual(res.context["kc_submitted"], 1)
        csv_body = self.client.get(export_url).content.decode("utf-8-sig")
        self.assertIn("Plant Head", csv_body)
        self.assertIn("Q9. Which areas are you most interested in?", csv_body.splitlines()[0])

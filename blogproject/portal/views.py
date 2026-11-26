"""Master Portal: API for the React portal (/masterportal) and the staff page in websitebackend."""

import hashlib
import json
import secrets
import threading
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Max
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from . import knowledge_check
from .certificate import (
    COURSE,
    ORGANISATION,
    TRAINER,
    build_certificate_pdf,
    normalise_certificate_id,
    qr_matrix,
    verify_url,
)
from .models import Attempt, Evaluation, KnowledgeCheck, PasswordResetOTP, PortalProfile, Question
from .serializers import AdminQuestionSerializer

User = get_user_model()

# The LinkedIn guide is a static PDF. Replace this file to change it (keep the same name).
LINKEDIN_GUIDE_PATH = Path(__file__).resolve().parent / "files" / "linkedin_guide.pdf"
OPTION_KEYS = ("A", "B", "C", "D")


# ─── Helpers ───────────────────────────────────────────────


def user_payload(user):
    profile = getattr(user, "portal_profile", None)
    return {
        "id": user.id,
        "name": profile.full_name if profile else (user.get_full_name() or user.username),
        "email": user.email or user.username,
        "is_admin": user.is_staff,
    }


def find_user(identifier):
    """Participants log in with their email; staff may also use their Django username."""
    identifier = identifier.strip()
    return (
        User.objects.filter(username__iexact=identifier).first()
        or User.objects.filter(email__iexact=identifier).first()
    )


def deactivate_user(user):
    """Deactivate and log out on every device (the login token is deleted)."""
    user.is_active = False
    user.save(update_fields=["is_active"])
    Token.objects.filter(user=user).delete()


class IsPortalUser(BasePermission):
    """Logged in, and either staff (portal admin) or a registered participant."""

    message = "You do not have access to the portal."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or hasattr(user, "portal_profile"))
        )


class PortalAPIView(APIView):
    """Base view for logged-in portal requests (token sent as 'Authorization: Token <key>')."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsPortalUser]


class PublicAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class IsPortalAdmin(BasePermission):
    message = "Only the portal admin can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class PortalAdminAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsPortalAdmin]


class IsParticipant(BasePermission):
    message = "Only participants can do this."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "portal_profile"))


class ParticipantAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsParticipant]


# ─── Auth API ──────────────────────────────────────────────


# Registration was removed: accounts are created automatically after the
# Masterclass payment (portal/accounts.py) and the login is sent by email.


class LoginView(PublicAPIView):
    def post(self, request):
        identifier = request.data.get("email") or ""
        password = request.data.get("password") or ""

        user = find_user(identifier) if identifier else None
        if not user or not user.check_password(password):
            return Response(
                {"message": "Invalid email or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not (user.is_staff or hasattr(user, "portal_profile")):
            return Response(
                {"message": "This account does not have access to the portal."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.is_active:
            return Response(
                {"message": "Your account is not active. Please wait for the admin to activate it."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        update_last_login(None, user)
        return Response({"token": token.key, "user": user_payload(user)})


class LogoutView(PortalAPIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"message": "Logged out."})


class MeView(PortalAPIView):
    def get(self, request):
        return Response(user_payload(request.user))


def password_error(password, user):
    """Django's password rules (min 8 chars, not too common, not all numbers...)."""
    try:
        validate_password(password, user=user)
    except ValidationError as e:
        return " ".join(e.messages)
    return None


class ChangePasswordView(PortalAPIView):
    """Logged-in user changes their password (current password required)."""

    def post(self, request):
        current = request.data.get("current_password") or ""
        new = request.data.get("new_password") or ""
        user = request.user

        if not user.check_password(current):
            return Response(
                {"message": "Your current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST
            )
        if current == new:
            return Response(
                {"message": "The new password must be different from the current one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        error = password_error(new, user)
        if error:
            return Response({"message": error}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new)
        user.save(update_fields=["password"])
        return Response({"message": "Your password has been changed."})


# ─── Forgot password (OTP by email) ───────────────────────

OTP_VALID_SECONDS = 120  # 2 minutes
OTP_MAX_ATTEMPTS = 5
RESET_TOKEN_VALID_SECONDS = 600  # time to type the new password after the OTP
OTP_SENT_MESSAGE = (
    "If this email is registered for the Masterclass portal, an OTP has been sent to it. "
    "The OTP expires in 2 minutes."
)
OTP_INVALID_MESSAGE = "This OTP is incorrect or has expired. Please request a new OTP."


def _hash(value):
    return hashlib.sha256(f"{settings.SECRET_KEY}:{value}".encode()).hexdigest()


def find_participant(email):
    user = find_user(email) if email else None
    return user if user and hasattr(user, "portal_profile") else None


def send_otp_email(email, name, code):
    try:
        send_mail(
            "🔐 Your Masterclass Portal password reset OTP",
            (
                f"Hi {name},\n\n"
                f"Your OTP to reset your Masterclass Portal password is:\n\n"
                f"    {code}\n\n"
                f"This OTP expires in 2 minutes. Do not share it with anyone.\n\n"
                f"If you did not ask to reset your password, you can ignore this email.\n\n"
                f"Regards,\n"
                f"Technoviz Automation"
            ),
            None,
            [email],
            fail_silently=False,
        )
    except Exception as exc:
        print("❌ OTP email failed:", email, exc)


class ForgotPasswordView(PublicAPIView):
    """POST {email}: emails a 6-digit OTP. Same answer whether or not the email
    exists, so the form cannot be used to find out who is registered."""

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        user = find_participant(email)
        if user:
            now = timezone.now()
            recent = user.portal_otps.filter(
                used=False, created_at__gt=now - timedelta(seconds=OTP_VALID_SECONDS)
            ).exists()
            if not recent:  # one OTP per 2 minutes
                user.portal_otps.filter(used=False).update(used=True)
                code = f"{secrets.randbelow(1_000_000):06d}"
                PasswordResetOTP.objects.create(
                    user=user,
                    code_hash=_hash(code),
                    expires_at=now + timedelta(seconds=OTP_VALID_SECONDS),
                )
                threading.Thread(
                    target=send_otp_email,
                    args=(user.email, user.portal_profile.full_name, code),
                    daemon=True,
                ).start()
        return Response({"message": OTP_SENT_MESSAGE, "expires_in": OTP_VALID_SECONDS})


class VerifyOTPView(PublicAPIView):
    """POST {email, otp}: returns a one-time reset_token if the OTP is right."""

    def post(self, request):
        user = find_participant((request.data.get("email") or "").strip())
        code = str(request.data.get("otp") or "").strip()
        otp = user.portal_otps.filter(used=False, verified_at__isnull=True).first() if user else None

        if not otp or otp.expires_at <= timezone.now():
            return Response({"message": OTP_INVALID_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)
        if otp.attempts >= OTP_MAX_ATTEMPTS:
            return Response(
                {"message": "Too many wrong attempts. Please request a new OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not secrets.compare_digest(otp.code_hash, _hash(code)):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            left = OTP_MAX_ATTEMPTS - otp.attempts
            message = (
                f"Incorrect OTP. {left} attempt{'s' if left != 1 else ''} left."
                if left
                else "Too many wrong attempts. Please request a new OTP."
            )
            return Response({"message": message}, status=status.HTTP_400_BAD_REQUEST)

        reset_token = secrets.token_urlsafe(32)
        otp.verified_at = timezone.now()
        otp.reset_token_hash = _hash(reset_token)
        otp.save(update_fields=["verified_at", "reset_token_hash"])
        return Response({"reset_token": reset_token})


class ResetPasswordView(PublicAPIView):
    """POST {email, reset_token, password}: sets the new password (once)."""

    def post(self, request):
        user = find_participant((request.data.get("email") or "").strip())
        token = str(request.data.get("reset_token") or "")
        password = request.data.get("password") or ""

        otp = (
            user.portal_otps.filter(
                used=False,
                verified_at__gt=timezone.now() - timedelta(seconds=RESET_TOKEN_VALID_SECONDS),
                reset_token_hash=_hash(token),
            ).first()
            if user and token
            else None
        )
        if not otp:
            return Response(
                {"message": "Your reset session has expired. Please start again with Forgot password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        error = password_error(password, user)
        if error:
            return Response({"message": error}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=["password"])
        user.portal_otps.filter(used=False).update(used=True)
        Token.objects.filter(user=user).delete()  # log out other devices
        return Response({"message": "Your password has been changed. Please log in with your new password."})


# ─── Participant: progress, evaluations, results ───────────


def evaluation_schedule(user):
    """When the evaluations open for this user, from their webinar.

    Returns None when there is no time restriction (staff, and users whose
    payment is not linked to a webinar - e.g. registered before the Webinar
    Schedule existed). Otherwise {"opens_at": datetime or None (no webinar yet),
    "is_open": bool}. The newest payment decides.
    """
    if user.is_staff:
        return None
    from webinar_schedule.models import WebinarInvite

    invite = (
        WebinarInvite.objects.filter(registration__email__iexact=user.email)
        .select_related("webinar")
        .order_by("-registration__created_at")
        .first()
    )
    if invite is None:
        return None
    opens_at = invite.webinar.start_dt if invite.webinar else None
    return {"opens_at": opens_at, "is_open": bool(opens_at and timezone.now() >= opens_at)}


def schedule_locked_message(schedule):
    if schedule["opens_at"] is None:
        return (
            "Your evaluations open when your masterclass starts. You will receive the masterclass "
            "date and joining link by email."
        )
    opens = schedule["opens_at"]
    return (
        f"Your evaluations open on {opens:%a, %d %b %Y} at {opens:%I:%M %p} (IST), "
        f"when your masterclass starts."
    )


def locked_message(user):
    schedule = evaluation_schedule(user)
    if schedule and not schedule["is_open"]:
        return schedule_locked_message(schedule)
    return "Complete the previous evaluation to unlock this one."


def evaluation_progress(user, schedule=None):
    """Status of every evaluation for this user: done / open / locked (in order)."""
    evaluations = Evaluation.objects.annotate(question_count=Count("questions")).order_by("order")
    attempts = {a.evaluation_id: a for a in Attempt.objects.filter(user=user)}
    if schedule is None:
        schedule = evaluation_schedule(user)
    webinar_started = schedule is None or schedule["is_open"]

    items = []
    previous_all_done = True
    for ev in evaluations:
        attempt = attempts.get(ev.id)
        if attempt:
            state = "done"
        elif not webinar_started:
            state = "locked"
        elif previous_all_done:
            state = "open"
        else:
            state = "locked"
        items.append(
            {
                "slug": ev.slug,
                "title": ev.title,
                "order": ev.order,
                "status": state,
                "question_count": ev.question_count,
                "score": attempt.score if attempt else None,
                "total": attempt.total if attempt else None,
                "submitted_at": attempt.submitted_at if attempt else None,
            }
        )
        previous_all_done = previous_all_done and attempt is not None
    return items


def all_evaluations_done(user):
    total = Evaluation.objects.count()
    return total > 0 and Attempt.objects.filter(user=user).count() >= total


def result_payload(evaluation, attempt):
    questions = []
    for item in attempt.answers:
        questions.append({**item, "is_correct": item["selected"] == item["correct"]})
    return {
        "evaluation": {"slug": evaluation.slug, "title": evaluation.title},
        "status": "done",
        "score": attempt.score,
        "total": attempt.total,
        "submitted_at": attempt.submitted_at,
        "questions": questions,
    }


def get_evaluation_for(user, slug):
    """Returns (evaluation, status) or raises 404."""
    evaluation = get_object_or_404(Evaluation, slug=slug)
    state = next(i["status"] for i in evaluation_progress(user) if i["slug"] == slug)
    return evaluation, state


def completion_date(user):
    """Date printed on the certificate: the day of the user's masterclass. Falls back to
    the date of their last submitted evaluation when no masterclass is assigned."""
    invite = masterclass_invite(user)
    if invite is not None:
        return invite.webinar.date
    last_attempt = Attempt.objects.filter(user=user).order_by("-submitted_at").first()
    return timezone.localtime(last_attempt.submitted_at if last_attempt else timezone.now()).date()


def certificate_issued(profile):
    """The certificate counts as issued once all evaluations are done and the admin activated it."""
    return profile.certificate_enabled and all_evaluations_done(profile.user)


class KnowledgeCheckView(ParticipantAPIView):
    """Pre-Masterclass Questions. The tab is always open: GET shows the questions
    (and the answers once submitted). POST submits them - only once, the answers
    cannot be changed afterwards."""

    def payload(self, user):
        check = KnowledgeCheck.objects.filter(user=user).first()
        return {
            "questions": knowledge_check.QUESTIONS,
            "answers": check.answers if check else None,
            "submitted_at": check.submitted_at if check else None,
            "updated_at": check.updated_at if check else None,
            "masterclass_when": masterclass_when(user),
        }

    def get(self, request):
        return Response(self.payload(request.user))

    def post(self, request):
        answers, error = knowledge_check.clean_answers(request.data.get("answers"))
        if error:
            return Response({"message": error}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                _check, created = KnowledgeCheck.objects.get_or_create(
                    user=request.user, defaults={"answers": answers}
                )
        except IntegrityError:  # submitted at the same moment in another tab
            created = False
        if not created:
            return Response(
                {"message": "You have already submitted your answers. They cannot be changed."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.payload(request.user))


def masterclass_invite(user):
    """The user's latest masterclass assignment (WebinarInvite with a webinar), or None."""
    from webinar_schedule.models import WebinarInvite

    if not user.email:
        return None
    return (
        WebinarInvite.objects.filter(registration__email__iexact=user.email, webinar__isnull=False)
        .select_related("webinar")
        .order_by("-registration__created_at")
        .first()
    )


def masterclass_when(user):
    """e.g. 'Sat, 12 Dec 2026 at 10:00 AM IST' for the user's masterclass, or None."""
    invite = masterclass_invite(user)
    if invite is None:
        return None
    return f"{invite.webinar.start_dt:%a, %d %b %Y} at {invite.webinar.start_dt:%I:%M %p} IST"


class ProgressView(ParticipantAPIView):
    def get(self, request):
        user = request.user
        profile = user.portal_profile
        schedule = evaluation_schedule(user)
        items = evaluation_progress(user, schedule)
        all_done = bool(items) and all(i["status"] == "done" for i in items)
        waiting = bool(schedule and not schedule["is_open"])
        return Response(
            {
                "evaluations": items,
                # Evaluations open when the user's webinar starts
                "evaluations_locked_until": schedule["opens_at"] if waiting else None,
                "waiting_for_webinar": waiting,
                "schedule_message": schedule_locked_message(schedule) if waiting else None,
                "all_done": all_done,
                "knowledge_check_done": KnowledgeCheck.objects.filter(user=user).exists(),
                "certificate_enabled": profile.certificate_enabled,
                "certificate_downloaded": profile.certificate_downloaded,
                "linkedin_downloaded": profile.linkedin_downloaded,
                # Details for the on-screen certificate preview
                "certificate": {
                    "name": profile.full_name,
                    "completed_on": completion_date(user),
                    "certificate_id": profile.certificate_id,
                    "verify_url": verify_url(profile.certificate_id),
                    # QR code rows ("1" = dark), drawn by the on-screen preview
                    "qr": qr_matrix(verify_url(profile.certificate_id)),
                }
                if all_done
                else None,
            }
        )


class EvaluationView(ParticipantAPIView):
    """GET: questions to answer (no correct answers), or the result if already submitted."""

    def get(self, request, slug):
        evaluation, state = get_evaluation_for(request.user, slug)

        if state == "locked":
            return Response(
                {"message": locked_message(request.user)},
                status=status.HTTP_403_FORBIDDEN,
            )

        if state == "done":
            attempt = Attempt.objects.get(user=request.user, evaluation=evaluation)
            return Response(result_payload(evaluation, attempt))

        return Response(
            {
                "evaluation": {"slug": evaluation.slug, "title": evaluation.title},
                "status": "open",
                "questions": [
                    {
                        "id": q.id,
                        "text": q.text,
                        "options": {
                            "A": q.option_a,
                            "B": q.option_b,
                            "C": q.option_c,
                            "D": q.option_d,
                        },
                    }
                    for q in evaluation.questions.all()
                ],
            }
        )


class SubmitEvaluationView(ParticipantAPIView):
    """POST {"answers": {"<question_id>": "A"}} — once only. Returns the result."""

    def post(self, request, slug):
        evaluation, state = get_evaluation_for(request.user, slug)

        if state == "locked":
            return Response(
                {"message": locked_message(request.user)},
                status=status.HTTP_403_FORBIDDEN,
            )
        if state == "done":
            return Response(
                {"message": "You have already submitted this evaluation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        answers = request.data.get("answers")
        if not isinstance(answers, dict):
            return Response({"message": "Invalid answers."}, status=status.HTTP_400_BAD_REQUEST)

        questions = list(evaluation.questions.all())
        if not questions:
            return Response(
                {"message": "This evaluation has no questions yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Snapshot of each question, so results stay the same if the admin edits questions later
        snapshot = []
        score = 0
        for q in questions:
            selected = str(answers.get(str(q.id)) or "").strip().upper()
            if selected not in OPTION_KEYS:
                return Response(
                    {"message": "Please answer all questions before submitting."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if selected == q.correct_option:
                score += 1
            snapshot.append(
                {
                    "id": q.id,
                    "text": q.text,
                    "options": {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d},
                    "correct": q.correct_option,
                    "selected": selected,
                }
            )

        try:
            with transaction.atomic():
                attempt = Attempt.objects.create(
                    user=request.user,
                    evaluation=evaluation,
                    answers=snapshot,
                    score=score,
                    total=len(questions),
                )
        except IntegrityError:  # double click / two tabs
            return Response(
                {"message": "You have already submitted this evaluation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(result_payload(evaluation, attempt), status=status.HTTP_201_CREATED)


# ─── Participant: certificate + LinkedIn guide ─────────────


def record_download(profile, field):
    """Mark a download; after both files are downloaded the user is deactivated and logged out."""
    setattr(profile, field, True)
    profile.save(update_fields=[field])
    if profile.certificate_downloaded and profile.linkedin_downloaded:
        deactivate_user(profile.user)


CERTIFICATE_WAITING_MESSAGE = (
    "Your certificate is waiting for approval from the Technoviz team. "
    "You will be able to download it once it is activated."
)


def downloads_blocked(user):
    """403 response if the user may not download yet, else None."""
    if not all_evaluations_done(user):
        message = "Complete all evaluations to unlock your certificate."
    elif not user.portal_profile.certificate_enabled:
        message = CERTIFICATE_WAITING_MESSAGE
    else:
        return None
    return Response({"message": message}, status=status.HTTP_403_FORBIDDEN)


class CertificateDownloadView(ParticipantAPIView):
    def get(self, request):
        user = request.user
        blocked = downloads_blocked(user)
        if blocked:
            return blocked

        profile = user.portal_profile
        pdf = build_certificate_pdf(profile.full_name, completion_date(user), profile.certificate_id)

        record_download(profile, "certificate_downloaded")

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="Masterclass-Certificate.pdf"'
        return response


class LinkedInGuideDownloadView(ParticipantAPIView):
    def get(self, request):
        user = request.user
        blocked = downloads_blocked(user)
        if blocked:
            return blocked
        if not LINKEDIN_GUIDE_PATH.exists():
            return Response(
                {"message": "The LinkedIn guide is not available yet. Please contact the admin."},
                status=status.HTTP_404_NOT_FOUND,
            )

        record_download(user.portal_profile, "linkedin_downloaded")

        return FileResponse(
            open(LINKEDIN_GUIDE_PATH, "rb"),
            as_attachment=True,
            filename="How-to-Share-on-LinkedIn.pdf",
            content_type="application/pdf",
        )


# ─── Public: certificate verification (website /verify-certificate) ───


class VerifyCertificateView(PublicAPIView):
    """GET /api/portal/verify-certificate/<id>/ - anyone can check a certificate ID.
    Returns only public details (no email/phone/answers)."""

    def get(self, request, cert_id):
        cert_id = normalise_certificate_id(cert_id)
        profile = (
            PortalProfile.objects.select_related("user").filter(certificate_id=cert_id).first()
            if cert_id
            else None
        )
        if profile is None:
            return Response(
                {"status": "not_found", "message": "No certificate was found with this ID."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not certificate_issued(profile):
            # The ID exists (made at registration) but the certificate is not issued yet
            return Response(
                {
                    "status": "not_issued",
                    "certificate_id": profile.certificate_id,
                    "message": "This certificate has not been issued yet.",
                }
            )
        return Response(
            {
                "status": "verified",
                "certificate_id": profile.certificate_id,
                "name": profile.full_name,
                "course": COURSE,
                "format": "Full-Day Masterclass",
                "completed_on": completion_date(profile.user),
                "issued_by": ORGANISATION,
                "trainer": TRAINER,
            }
        )


# ─── Admin: question manager API ───────────────────────────


FIELD_LABELS = {
    "text": "Question",
    "option_a": "Option A",
    "option_b": "Option B",
    "option_c": "Option C",
    "option_d": "Option D",
    "correct_option": "Correct option",
}


def first_error(errors):
    """Turn DRF serializer errors into one readable message, e.g. 'Option B: may not be blank.'"""
    for field, value in errors.items():
        message = str(value[0]) if isinstance(value, list) and value else str(value)
        if field in FIELD_LABELS and not message.startswith(FIELD_LABELS[field]):
            message = f"{FIELD_LABELS[field]}: {message.replace('This field', 'it')}"
        return message
    return "Invalid data."


class AdminQuestionListView(PortalAdminAPIView):
    """GET: all questions of an evaluation. POST: add a question."""

    def get(self, request, slug):
        evaluation = get_object_or_404(Evaluation, slug=slug)
        questions = evaluation.questions.all()
        return Response(
            {
                "evaluation": {"slug": evaluation.slug, "title": evaluation.title},
                "attempts_count": Attempt.objects.filter(evaluation=evaluation).count(),
                "questions": AdminQuestionSerializer(questions, many=True).data,
            }
        )

    def post(self, request, slug):
        evaluation = get_object_or_404(Evaluation, slug=slug)
        serializer = AdminQuestionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"message": first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST
            )
        last = evaluation.questions.aggregate(m=Max("order"))["m"] or 0
        question = serializer.save(evaluation=evaluation, order=last + 1)
        return Response(AdminQuestionSerializer(question).data, status=status.HTTP_201_CREATED)


class AdminQuestionDetailView(PortalAdminAPIView):
    """PUT: edit a question. DELETE: remove it."""

    def put(self, request, pk):
        question = get_object_or_404(Question, pk=pk)
        serializer = AdminQuestionSerializer(question, data=request.data)
        if not serializer.is_valid():
            return Response(
                {"message": first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        get_object_or_404(Question, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Staff page in websitebackend ──────────────────────────


@staff_member_required
def portal_users(request):
    total_evaluations = Evaluation.objects.count()
    profiles = list(
        PortalProfile.objects.select_related("user", "user__knowledge_check")
        .annotate(completed=Count("user__portal_attempts", distinct=True))
        .order_by("-created_at")
    )
    # Knowledge Check answers, shown in a popup per user ("View answers")
    for p in profiles:
        check = getattr(p.user, "knowledge_check", None)
        p.kc_submitted_at = check.submitted_at if check else None
        p.kc_answers = knowledge_check.answer_rows(check) if check else []
    return render(
        request,
        "portal/portal_users.html",
        {
            "profiles": profiles,
            "total_evaluations": total_evaluations,
            "kc_submitted": sum(1 for p in profiles if p.kc_submitted_at),
        },
    )


@staff_member_required
@require_POST
def toggle_certificate(request, pk):
    """Turn certificate (and LinkedIn guide) downloads on or off for one user."""
    profile = get_object_or_404(PortalProfile, pk=pk)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}
    profile.certificate_enabled = bool(data.get("enabled", not profile.certificate_enabled))
    profile.save(update_fields=["certificate_enabled"])
    return JsonResponse({"success": True, "enabled": profile.certificate_enabled})


@staff_member_required
@require_POST
def toggle_portal_user(request, pk):
    profile = get_object_or_404(PortalProfile.objects.select_related("user"), pk=pk)
    user = profile.user

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}
    activate = bool(data.get("active", not user.is_active))

    if activate:
        user.is_active = True
        user.save(update_fields=["is_active"])
        # Re-activated users can download the certificate + LinkedIn PDF again
        profile.certificate_downloaded = False
        profile.linkedin_downloaded = False
        profile.save(update_fields=["certificate_downloaded", "linkedin_downloaded"])
    else:
        deactivate_user(user)

    return JsonResponse({"success": True, "active": user.is_active})


# ─── Knowledge Check answers: CSV download (button on Master Portal Users) ───


@staff_member_required
def knowledge_check_export(request):
    checks = KnowledgeCheck.objects.select_related("user", "user__portal_profile").order_by("-submitted_at")
    return knowledge_check.csv_response(checks)

"""Portal API, mounted at /api/portal/."""

from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="portal-login"),
    path("logout/", views.LogoutView.as_view(), name="portal-logout"),
    path("me/", views.MeView.as_view(), name="portal-me"),
    path("change-password/", views.ChangePasswordView.as_view(), name="portal-change-password"),
    # Forgot password: OTP by email -> verify -> new password
    path("forgot-password/", views.ForgotPasswordView.as_view(), name="portal-forgot-password"),
    path("verify-otp/", views.VerifyOTPView.as_view(), name="portal-verify-otp"),
    path("reset-password/", views.ResetPasswordView.as_view(), name="portal-reset-password"),
    # Participant
    path("progress/", views.ProgressView.as_view(), name="portal-progress"),
    path("knowledge-check/", views.KnowledgeCheckView.as_view(), name="portal-knowledge-check"),
    path("evaluations/<slug:slug>/", views.EvaluationView.as_view(), name="portal-evaluation"),
    path(
        "evaluations/<slug:slug>/submit/",
        views.SubmitEvaluationView.as_view(),
        name="portal-evaluation-submit",
    ),
    path("certificate/", views.CertificateDownloadView.as_view(), name="portal-certificate"),
    path("linkedin-guide/", views.LinkedInGuideDownloadView.as_view(), name="portal-linkedin-guide"),
    path(
        "verify-certificate/<str:cert_id>/",
        views.VerifyCertificateView.as_view(),
        name="portal-verify-certificate",
    ),
    # Admin: question manager
    path(
        "admin/evaluations/<slug:slug>/questions/",
        views.AdminQuestionListView.as_view(),
        name="portal-admin-questions",
    ),
    path(
        "admin/questions/<int:pk>/",
        views.AdminQuestionDetailView.as_view(),
        name="portal-admin-question",
    ),
]

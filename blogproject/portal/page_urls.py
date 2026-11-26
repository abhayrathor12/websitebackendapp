"""Staff pages in websitebackend, mounted at /portal-users/
(Master Portal Users + Knowledge Check answers CSV)."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.portal_users, name="portal-users"),
    path("toggle/<int:pk>/", views.toggle_portal_user, name="portal-user-toggle"),
    path("certificate/<int:pk>/", views.toggle_certificate, name="portal-certificate-toggle"),
    path("knowledge-check/export/", views.knowledge_check_export, name="knowledge-check-export"),
]

"""Staff page in websitebackend, mounted at /webinar-schedule/."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.schedule_page, name="webinar-schedule"),
    path("create/", views.create_webinar, name="webinar-schedule-create"),
    path("<int:pk>/update/", views.update_webinar, name="webinar-schedule-update"),
    path("<int:pk>/resend/", views.resend_webinar_emails, name="webinar-schedule-resend"),
    path("<int:pk>/delete/", views.delete_webinar, name="webinar-schedule-delete"),
]

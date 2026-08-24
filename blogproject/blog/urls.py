from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'blogs', BlogViewSet, basename='blog')
router.register(r'contacts', ContactViewSet, basename='contact')

urlpatterns = [
    path('', include(router.urls)),
    path("con/create/", ContactCreateView.as_view(), name="contact_create"),
    path("webinar/register/", WebinarRegistrationAPIView.as_view(), name="webinar-register"),
    path("webinar/toggle-attended/<int:pk>/", toggle_attended, name="toggle_attended"),
     path(
        "ideathon-registration/",
        IdeathonRegistrationAPIView.as_view(),
        name="ideathon-registration",
    ),
     path("ideathon-list/", ideathon_list, name="ideathon-list"),
path("ideathon/delete/<int:pk>/", delete_ideathon, name="delete-ideathon"),
path("ideathon/delete-multiple/", delete_multiple_ideathon, name="delete-multiple-ideathon"),
 path("create-order/", CreateOrderView.as_view(), name="create-order"),
    path("verify-payment/", VerifyPaymentView.as_view(), name="verify-payment"),
    path("masterclass-list/", masterclass_list, name="masterclass-list"),
path("masterclass/delete/<int:pk>/", delete_masterclass, name="delete-masterclass"),
path("masterclass/delete-multiple/", delete_multiple_masterclass, name="delete-multiple-masterclass"),
]

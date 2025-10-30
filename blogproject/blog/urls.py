from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'blogs', BlogViewSet, basename='blog')
router.register(r'contacts', ContactViewSet, basename='contact')

urlpatterns = [
    path('', include(router.urls)),
    path("con/create/", ContactCreateView.as_view(), name="contact_create"),
 
    
]

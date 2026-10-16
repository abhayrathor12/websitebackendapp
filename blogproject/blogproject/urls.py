"""
URL configuration for blogproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""





from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from blog.views import*
from blog.sitemap import sitemap_xml
urlpatterns = [
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap_xml, name='sitemap'),
    path('api/', include('blog.urls')),
    path('blogpage/', add_blog, name='add_blog'),
    path("", contact_list, name="contact_list"),
    path("webinar_list/", webinar_list, name="webinar_list"),
    path("blogsview/", blog_list, name="blog_list"),
    path("blog/edit/<int:blog_id>/", edit_blog, name="edit_blog"),
    path("blog/delete/<int:blog_id>/", delete_blog, name="delete_blog"),

path("webinar/delete/<int:pk>/", delete_webinar),
path("webinar/delete-multiple/", delete_multiple_webinar),

    
]

# Blog images keep working with DEBUG off. Adding a /media/ static files mapping
# in the PythonAnywhere Web tab is faster and takes over from this automatically.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]


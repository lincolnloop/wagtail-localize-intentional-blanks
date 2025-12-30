"""
URL configuration for tests.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("intentional-blanks/", include("wagtail_localize_intentional_blanks.urls")),
]

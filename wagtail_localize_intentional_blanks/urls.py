"""
URL patterns for the intentional blanks API.
"""

from django.urls import path

from . import views

app_name = "wagtail_localize_intentional_blanks"

urlpatterns = [
    path(
        "translations/<int:translation_id>/segment/<int:segment_id>/do-not-translate/",
        views.mark_segment_do_not_translate_view,
        name="mark_segment_do_not_translate",
    ),
    path(
        "translations/<int:translation_id>/segment/<int:segment_id>/status/",
        views.get_segment_status,
        name="get_segment_status",
    ),
    path(
        "translations/<int:translation_id>/status/",
        views.get_translation_status,
        name="get_translation_status",
    ),
]

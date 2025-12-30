"""
Views for handling AJAX requests from the translation editor.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from wagtail_localize.models import String, StringSegment, StringTranslation, Translation

from .constants import get_setting
from .utils import (
    get_backup_separator,
    is_do_not_translate,
    mark_segment_do_not_translate,
    unmark_segment_do_not_translate,
    validate_configuration,
)

logger = logging.getLogger(__name__)


def check_permission(user):
    """
    Check if user has permission to mark segments as "do not translate".

    Args:
        user: Django User instance

    Raises:
        PermissionDenied if user doesn't have permission
    """
    required_permission = get_setting("REQUIRED_PERMISSION")

    if required_permission is None:
        # No specific permission required
        return True

    if not user.has_perm(required_permission):
        raise PermissionDenied(f"User does not have required permission: {required_permission}")

    return True


@login_required
@require_POST
def mark_segment_do_not_translate_view(request, translation_id, segment_id):
    """
    Mark a translation segment as "do not translate".

    POST params:
        do_not_translate: bool - True to mark as do not translate, False to unmark

    Returns:
        JSON response with success status and source value

    Example AJAX call:
        fetch('/intentional-blanks/translations/123/segment/456/do-not-translate/', {
            method: 'POST',
            headers: {'X-CSRFToken': csrfToken},
            body: new FormData({do_not_translate: 'true'})
        })
    """
    try:
        # Check permissions
        check_permission(request.user)

        # Get objects
        translation = Translation.objects.get(id=translation_id)
        # segment_id is actually the String ID from wagtail-localize's JSON
        string = String.objects.get(id=segment_id)
        segment = StringSegment.objects.get(source=translation.source, string=string)

        # Get action - only accept explicit 'true' or 'false'
        do_not_translate_param = request.POST.get("do_not_translate", "").lower()
        if do_not_translate_param not in ("true", "false"):
            return JsonResponse({"success": False, "error": 'Invalid do_not_translate parameter. Must be "true" or "false".'}, status=400)

        do_not_translate = do_not_translate_param == "true"

        if do_not_translate:
            mark_segment_do_not_translate(translation, segment, user=request.user)
            message = "Segment marked as do not translate"
        else:
            unmark_segment_do_not_translate(translation, segment)
            message = "Segment unmarked, ready for manual translation"

        # Get the source text to display in UI
        source_text = segment.string.data if segment.string else ""

        # Get the translated value (if any) for unmarking
        translated_value = None
        if not do_not_translate:
            try:
                existing_translation = StringTranslation.objects.get(
                    translation_of=segment.string, locale=translation.target_locale, context=segment.context
                )
                validate_configuration()
                marker = get_setting("MARKER")
                backup_separator = get_backup_separator()
                # Make sure it's not the marker or encoded marker format
                if existing_translation.data != marker and not existing_translation.data.startswith(marker + backup_separator):
                    translated_value = existing_translation.data
            except StringTranslation.DoesNotExist:
                pass

        return JsonResponse(
            {
                "success": True,
                "source_value": source_text,
                "translated_value": translated_value,
                "do_not_translate": do_not_translate,
                "message": message,
            }
        )

    except Translation.DoesNotExist:
        return JsonResponse({"success": False, "error": "Translation not found"}, status=404)

    except StringSegment.DoesNotExist:
        return JsonResponse({"success": False, "error": "Segment not found"}, status=404)

    except PermissionDenied as e:
        return JsonResponse({"success": False, "error": str(e)}, status=403)

    except Exception as e:
        # Log the error
        logger.exception("Error in mark_segment_do_not_translate_view")

        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
def get_segment_status(request, translation_id, segment_id):
    """
    Get the current status of a segment (marked as do not translate or not).

    Args:
        translation_id: The Translation ID
        segment_id: The String ID (not StringSegment ID)

    Returns:
        JSON response with status info

    Example:
        GET /intentional-blanks/translations/123/segment/456/status/
    """
    try:
        check_permission(request.user)

        translation = Translation.objects.get(id=translation_id)
        # segment_id is actually the String ID from wagtail-localize's JSON
        string = String.objects.get(id=segment_id)
        segment = StringSegment.objects.get(source=translation.source, string=string)

        try:
            string_translation = StringTranslation.objects.get(
                translation_of=segment.string,  # translation_of expects a String, not StringSegment
                locale=translation.target_locale,
            )
            do_not_translate = is_do_not_translate(string_translation)
            translated_text = string_translation.data if not do_not_translate else None
        except StringTranslation.DoesNotExist:
            do_not_translate = False
            translated_text = None

        source_text = segment.string.data if segment.string else ""

        return JsonResponse({"success": True, "do_not_translate": do_not_translate, "source_text": source_text, "translated_text": translated_text})

    except (Translation.DoesNotExist, StringSegment.DoesNotExist):
        return JsonResponse({"success": False, "error": "Not found"}, status=404)

    except PermissionDenied as e:
        return JsonResponse({"success": False, "error": str(e)}, status=403)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@never_cache
def get_translation_status(request, translation_id):
    """
    Get the status of all segments for a translation in one request.

    Args:
        translation_id: The Translation ID

    Returns:
        JSON response with a mapping of segment IDs to their status

    Example:
        GET /intentional-blanks/translations/123/status/
        Response: {
            "success": true,
            "segments": {
                "456": {"do_not_translate": true, "source_text": "Hello"},
                "457": {"do_not_translate": false, "source_text": "World"}
            }
        }
    """
    try:
        check_permission(request.user)

        translation = Translation.objects.get(id=translation_id)

        print(f"[GET_TRANSLATION_STATUS] translation_id={translation_id}, source={translation.source.id}, target_locale={translation.target_locale}")

        # Get all String IDs for this translation source

        string_ids = list(StringSegment.objects.filter(source=translation.source).values_list("string_id", flat=True))

        print(f"[GET_TRANSLATION_STATUS] Found {len(string_ids)} string_ids: {string_ids}")

        # Get all string translations for these strings that are marked as "do not translate"
        validate_configuration()
        marker = get_setting("MARKER")
        backup_separator = get_backup_separator()
        marked_translations = (
            StringTranslation.objects.filter(locale=translation.target_locale, translation_of_id__in=string_ids)
            .filter(Q(data=marker) | Q(data__startswith=marker + backup_separator))
            .select_related("translation_of")
        )

        print(f"[GET_TRANSLATION_STATUS] Found {marked_translations.count()} marked translations")

        # Build a mapping of string ID -> status
        segments = {}
        for st in marked_translations:
            print(f"[GET_TRANSLATION_STATUS]   Marked segment: string_id={st.translation_of.id}, context='{st.context}', data='{st.data[:50]}...'")
            segments[str(st.translation_of.id)] = {"do_not_translate": True, "source_text": st.translation_of.data}

        print(f"[GET_TRANSLATION_STATUS] Returning {len(segments)} segments: {list(segments.keys())}")

        return JsonResponse({"success": True, "segments": segments})

    except Translation.DoesNotExist:
        return JsonResponse({"success": False, "error": "Translation not found"}, status=404)

    except PermissionDenied as e:
        return JsonResponse({"success": False, "error": str(e)}, status=403)

    except Exception as e:
        logger.exception("Error in get_translation_status")
        return JsonResponse({"success": False, "error": str(e)}, status=400)

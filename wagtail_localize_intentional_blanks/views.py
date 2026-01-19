"""
Views for handling AJAX requests from the translation editor.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from wagtail_localize.models import (
    StringSegment,
    StringTranslation,
    Translation,
)

from .constants import get_setting
from .utils import (
    bulk_mark_segments,
    bulk_unmark_segments,
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
        raise PermissionDenied(
            f"User does not have required permission: {required_permission}"
        )

    return True


@login_required
@require_POST
def mark_segment_do_not_translate_view(request, translation_id, segment_id):
    """
    Mark a translation segment as "do not translate".

    Args:
        translation_id: The Translation ID
        segment_id: The StringSegment ID (not String ID)

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

        # segment_id is the StringSegment ID (matches wagtail-localize's segment.id)
        logger.info(
            f"Marking segment as do not translate: translation_id={translation_id}, segment_id={segment_id}"
        )

        segment = StringSegment.objects.get(id=segment_id, source=translation.source)
        string = segment.string

        if not string:
            logger.error(f"StringSegment {segment_id} has no associated String")
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Segment {segment_id} has no associated String. The translation may be corrupted.",
                },
                status=400,
            )

        # Get action - only accept explicit 'true' or 'false'
        do_not_translate_param = request.POST.get("do_not_translate", "").lower()
        if do_not_translate_param not in ("true", "false"):
            return JsonResponse(
                {
                    "success": False,
                    "error": 'Invalid do_not_translate parameter. Must be "true" or "false".',
                },
                status=400,
            )

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
                    translation_of=segment.string,
                    locale=translation.target_locale,
                    context=segment.context,
                )
                validate_configuration()
                marker = get_setting("MARKER")
                backup_separator = get_backup_separator()
                # Make sure it's not the marker or encoded marker format
                if (
                    existing_translation.data != marker
                    and not existing_translation.data.startswith(
                        marker + backup_separator
                    )
                ):
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
        return JsonResponse(
            {"success": False, "error": "Translation not found"}, status=404
        )

    except StringSegment.DoesNotExist:
        logger.error(
            f"StringSegment {segment_id} does not exist for translation {translation_id}"
        )
        return JsonResponse(
            {
                "success": False,
                "error": f"Segment {segment_id} not found. The translation may need to be re-synced.",
            },
            status=404,
        )

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
        segment_id: The StringSegment ID (not String ID)

    Returns:
        JSON response with status info

    Example:
        GET /intentional-blanks/translations/123/segment/456/status/
    """
    try:
        check_permission(request.user)

        translation = Translation.objects.get(id=translation_id)

        # segment_id is the StringSegment ID (matches wagtail-localize's segment.id)
        segment = StringSegment.objects.get(id=segment_id, source=translation.source)
        string = segment.string

        if not string:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Segment {segment_id} has no associated String.",
                },
                status=400,
            )

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

        return JsonResponse(
            {
                "success": True,
                "do_not_translate": do_not_translate,
                "source_text": source_text,
                "translated_text": translated_text,
            }
        )

    except Translation.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Translation not found"}, status=404
        )

    except StringSegment.DoesNotExist:
        logger.error(
            f"StringSegment {segment_id} does not exist for translation {translation_id}"
        )
        return JsonResponse(
            {
                "success": False,
                "error": f"Segment {segment_id} not found. The translation may need to be re-synced.",
            },
            status=404,
        )

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
        JSON response with a mapping of StringSegment IDs to their status

    Example:
        GET /intentional-blanks/translations/123/status/
        Response: {
            "success": true,
            "segments": {
                "456": {"do_not_translate": true, "source_text": "Hello"},
                "457": {"do_not_translate": false, "source_text": "World"}
            }
        }
        (Keys are StringSegment IDs, not String IDs)
    """
    try:
        check_permission(request.user)

        translation = Translation.objects.get(id=translation_id)

        # Get all string translations for this translation source that are marked as "do not translate"
        validate_configuration()
        marker = get_setting("MARKER")
        backup_separator = get_backup_separator()

        # Get all StringSegments for this source
        all_segments = StringSegment.objects.filter(
            source=translation.source
        ).select_related("string")
        string_ids = list(all_segments.values_list("string_id", flat=True))

        # Get marked translations
        marked_translations = (
            StringTranslation.objects.filter(
                locale=translation.target_locale, translation_of_id__in=string_ids
            )
            .filter(Q(data=marker) | Q(data__startswith=marker + backup_separator))
            .select_related("translation_of")
        )

        # Build a map: String ID -> StringSegment ID
        string_to_segment_map = {seg.string_id: seg.id for seg in all_segments}

        # Build a mapping of StringSegment ID -> status
        segments = {}
        for st in marked_translations:
            string_id = st.translation_of.id
            segment_id = string_to_segment_map.get(string_id)

            if segment_id:
                segments[str(segment_id)] = {
                    "do_not_translate": True,
                    "source_text": st.translation_of.data,
                }

        return JsonResponse({"success": True, "segments": segments})

    except Translation.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Translation not found"}, status=404
        )

    except PermissionDenied as e:
        return JsonResponse({"success": False, "error": str(e)}, status=403)

    except Exception as e:
        logger.exception("Error in get_translation_status")
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def toggle_all_do_not_translate_view(request, translation_id):
    """
    Mark or unmark all translation segments as "do not translate" at once.

    This view uses optimized batch operations to minimize database queries,
    making it performant even for translations with hundreds of segments.

    Args:
        translation_id: The Translation ID

    POST params:
        do_not_translate: string - "true" to mark all, "false" to unmark all

    Returns:
        JSON response with affected segment IDs and counts

    Example AJAX call:
        fetch('/intentional-blanks/translations/123/toggle-all-do-not-translate/', {
            method: 'POST',
            headers: {'X-CSRFToken': csrfToken},
            body: new FormData({do_not_translate: 'true'})
        })
    """
    try:
        # Check permissions
        check_permission(request.user)

        # Get translation object
        translation = Translation.objects.get(id=translation_id)

        # Get action - only accept explicit 'true' or 'false'
        do_not_translate_param = request.POST.get("do_not_translate", "").lower()
        if do_not_translate_param not in ("true", "false"):
            return JsonResponse(
                {
                    "success": False,
                    "error": 'Invalid do_not_translate parameter. Must be "true" or "false".',
                },
                status=400,
            )

        do_not_translate = do_not_translate_param == "true"

        # Get all StringSegments for this translation's source
        # Convert to list to avoid multiple queries
        segments = list(
            StringSegment.objects.filter(source=translation.source).select_related(
                "string"
            )
        )

        if not segments:
            return JsonResponse(
                {
                    "success": False,
                    "error": "No segments found for this translation.",
                },
                status=400,
            )

        # Use optimized batch operations wrapped in a transaction
        with transaction.atomic():
            if do_not_translate:
                # Mark all segments using optimized batch operation
                affected_count = bulk_mark_segments(
                    translation, segments, user=request.user
                )
                segment_ids = [s.id for s in segments]
                segment_data = {}
                message = f"Marked {affected_count} segments"
            else:
                # Unmark all segments using optimized batch operation
                # Returns (affected_count, segment_data) where segment_data includes
                # both translated_value and source_value for each segment
                affected_count, segment_data = bulk_unmark_segments(
                    translation, segments
                )
                segment_ids = list(segment_data.keys())
                message = f"Unmarked {affected_count} segments"

        return JsonResponse(
            {
                "success": True,
                "affected_count": affected_count,
                "segment_ids": segment_ids,
                "segment_data": segment_data,
                "do_not_translate": do_not_translate,
                "message": message,
            }
        )

    except Translation.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Translation not found"}, status=404
        )

    except PermissionDenied as e:
        return JsonResponse({"success": False, "error": str(e)}, status=403)

    except Exception as e:
        # Log the error
        logger.exception("Error in toggle_all_do_not_translate_view")
        return JsonResponse({"success": False, "error": str(e)}, status=400)

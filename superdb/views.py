# superdb/views.py
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.utils import timezone
import json
from .utils import decode_qr_token
from .models import Event, User, Attendance, Penalty
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test

def is_scanner_or_admin(user):
    return user.is_authenticated and (user.is_scanner() or user.is_admin())

@require_POST
@login_required
@user_passes_test(is_scanner_or_admin)
def scan_endpoint(request):
    """
    Expects JSON body: { "token": "<jwt token>" }
    Only scanner-role or admin users can POST to this endpoint.
    """
    try:
        payload = json.loads(request.body)
        token = payload.get('token')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'bad_request'}, status=400)

    data, err = decode_qr_token(token)
    if err:
        return JsonResponse({'ok': False, 'error': 'token_' + err}, status=400)

    event_id = data.get('event')
    user_id = data.get('user')
    now = timezone.now()

    try:
        event = Event.objects.get(pk=event_id)
        user = User.objects.get(pk=user_id)
    except Event.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'no_event'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'no_user'}, status=404)

    # check banned
    if user.penalty_status == 'banned' or not user.is_active_member:
        return JsonResponse({'ok': False, 'error': 'user_banned'}, status=403)

    # Check event time window
    if not (event.start_time <= now <= event.end_time):
        return JsonResponse({'ok': False, 'error': 'outside_event_time', 'now': now.isoformat(), 'start': event.start_time.isoformat(), 'end': event.end_time.isoformat()}, status=400)

    # Prevent overlapping events
    overlapping = Attendance.objects.filter(
        user=user,
        event__start_time__lte=event.end_time,
        event__end_time__gte=event.start_time
    ).exclude(event=event)

    if overlapping.exists():
        # increment penalty count
        user.penalty_count += 1
        if user.penalty_count >= 2:
            user.penalty_status = 'banned'
            user.save()
            Penalty.objects.create(user=user, reason='Auto-ban for multiple overlapping scans', admin=request.user)
            return JsonResponse({'ok': False, 'error': 'banned_due_to_multiple_overlaps', 'penalty_count': user.penalty_count}, status=403)
        else:
            user.penalty_status = 'warned'
            user.save()
            Penalty.objects.create(user=user, reason=f'Warning: overlapping event scanned (count={user.penalty_count})', admin=request.user)
            return JsonResponse({'ok': False, 'error': 'warning_overlapping_scan', 'penalty_count': user.penalty_count}, status=400)

    # Create attendance record (unique)
    try:
        with transaction.atomic():
            attendance, created = Attendance.objects.get_or_create(event=event, user=user, defaults={'scanner': request.user})
            if not created:
                return JsonResponse({'ok': False, 'error': 'already_checked_in'}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'db_error', 'details': str(e)}, status=500)

    return JsonResponse({'ok': True, 'message': 'checked_in', 'user': user.id, 'event': event.id, 'checked_at': attendance.checked_at.isoformat()})

@login_required
@require_GET
def check_status(request):
    event_id = request.GET.get('event_id')
    user_id = request.GET.get('user_id')
    try:
        event = Event.objects.get(pk=event_id)
        user = User.objects.get(pk=user_id)
    except Exception:
        return JsonResponse({'ok': False}, status=400)
    checked = Attendance.objects.filter(event=event, user=user).exists()
    banned = user.penalty_status == 'banned' or not user.is_active_member
    return JsonResponse({'ok': True, 'checked_in': checked, 'banned': banned})
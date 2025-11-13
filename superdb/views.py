# superdb/views.py
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.utils import timezone
import json
from .utils import decode_qr_token
from .models import Event, User, Attendance, Penalty, Graup
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
import pandas as pd
from io import StringIO
import requests
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model

def is_scanner_or_admin(user):
    return user.is_authenticated and (user.role == 'scanner' or user.role == 'admin' or user.role == 'core')

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
        user.penalty_level += 1
        if user.penalty_level >= 2:
            user.penalty_status = 'banned'
            user.save()
            Penalty.objects.create(user=user, reason='Auto-ban for multiple overlapping scans', admin=request.user)
            return JsonResponse({'ok': False, 'error': 'banned_due_to_multiple_overlaps', 'penalty_level': user.penalty_level}, status=403)
        else:
            user.penalty_status = 'warned'
            user.save()
            Penalty.objects.create(user=user, reason=f'Warning: overlapping event scanned (count={user.penalty_level})', admin=request.user)
            return JsonResponse({'ok': False, 'error': 'warning_overlapping_scan', 'penalty_level': user.penalty_level}, status=400)

    # Create attendance record (unique)
    try:
        with transaction.atomic():
            attendance, created = Attendance.objects.get_or_create(event=event, user=user, defaults={'scanner': request.user})
            if not created:
                return JsonResponse({'ok': False, 'error': 'already_checked_in'}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'db_error', 'details': str(e)}, status=500)

    return JsonResponse({'ok': True, 'message': 'checked_in', 'username': user.username, 'eventname': event.title, 'group': user.group.name, 'user': user.id, 'event': event.id, 'checked_at': attendance.checked_at.isoformat()})

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

User = get_user_model()


@csrf_exempt
def parse_import(request):
    import json
    import pandas as pd
    from io import StringIO
    import requests

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method"}, status=400)

    # FILE MODE
    if "file" in request.FILES:
        df = pd.read_excel(request.FILES["file"])

    # URL MODE
    else:
        data = json.loads(request.body)
        url = data.get("url")

        try:
            sheet_id = url.split("/d/")[1].split("/")[0]
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            text = requests.get(csv_url).text
            df = pd.read_csv(StringIO(text))
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    # ✅ columns to help user create reference mapping
    columns = list(df.columns)

    # ✅ rows to use later in finalize
    rows = df.to_dict(orient="records")

    return JsonResponse({
        "success": True,
        "columns": columns,
        "rows": rows
    })

@csrf_exempt
def finalize_import(request):
    import json
    User = get_user_model()

    data = json.loads(request.body)

    rows = data["rows"]
    mode = data["mode"]              # "username" or "firstname_lastname"
    mapping = data["mapping"]
    role = data["role"]
    default_penalty = 0
    default_penalty = "ok"

    count = 0

    for row in rows:
        
        # ✅ MODE A — username directly from spreadsheet
        if mode == "username":
            username = row.get(mapping["username"], "")
            password = row.get(mapping.get("password"), None)

        # ✅ MODE B — build username from firstname + lastname
        else:
            firstname = row.get(mapping["firstname"], "")
            lastname = row.get(mapping["lastname"], "")
            password = row.get(mapping.get("password"), None)

            # ✅ Build username WITHOUT saving firstname/lastname to DB
            username = f"{firstname}_{lastname}".lower().replace(" ", "")

        if not username:
            continue

        user, created = User.objects.update_or_create(
            username=username,
            defaults={
                "role": role,
                "penalty_level": default_penalty,
                "penalty_status": default_penalty2,
            }
        )

        if password:
            user.set_password(password)
            user.save()

        count += 1

    return JsonResponse({"success": True, "count": count})


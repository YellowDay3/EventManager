# views.py
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from superdb.models import User, Event, Penalty, Graup, Attendance, Log
from superdb.utils import make_qr_payload, timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from superdb.forms import AdminUserForm, EventForm, GraupForm
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
import qrcode
from io import BytesIO
import zipfile
from django.utils import timezone
from datetime import timedelta
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from superdb.scheduler import apply_no_show_penalties
import os
import subprocess# You might need to pip install gitpython, or use subprocess

# SECURITY WARNING: Ideally, check for a secret token here!
# [AUTO UPDATE FOR PYTHONANYWHERE!]
@csrf_exempt
def update_server(request):
    if request.method == "POST":
        repo_dir = '/home/robotiqueformation/EventManager'
        
        # 1. Update Code
        os.system(f'cd {repo_dir} && git pull')
        
        # 2. Reload the Server (Touch the WSGI file)
        wsgi_file = '/var/www/robotiqueformation_pythonanywhere_com_wsgi.py'
        os.system(f'touch {wsgi_file}')
        
        return HttpResponse("Updated successfully", status=200)
    return HttpResponse("Wrong method", status=400)

@login_required(login_url='/accounts/login')
def menu(request):
    """
    Central redirect depending on user role.
    """
    user = request.user

    if user.role == 'admin' or user.role == 'core' or user.role == 'moderator':
        return redirect('admin_dashboard')
    elif user.role == 'scanner':
        return redirect('scanner_page')
    elif user.role == 'member':
        return redirect('member_page')

    # Fallback (invalid role)
    logout(request)
    return redirect('/accounts/login')

# Add this view function to your existing views.py
@csrf_exempt
def check_role(request):
    """
    AJAX endpoint to check user role dynamically
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username', '').strip()
            
            if not username:
                return JsonResponse({'role': None})
            
            try:
                user = User.objects.get(username=username)
                return JsonResponse({'role': user.role})
            except User.DoesNotExist:
                return JsonResponse({'role': None})
                
        except json.JSONDecodeError:
            return JsonResponse({'role': None, 'error': 'Invalid JSON'})
    
    return JsonResponse({'role': None, 'error': 'Invalid request method'})

# ---- simple role checks ----
def is_core(user): return user.is_authenticated and user.role == "core"
def is_higheradmin(user): return user.is_authenticated and user.role == "admin" or user.role == "core"
def is_admin(user): return user.is_authenticated and user.role == "admin" or user.role == "moderator" or user.role == "core"
def is_scanner(user): return user.is_authenticated and user.role == "scanner"
def is_member(user): return user.is_authenticated and user.role == "member"

def login_redirect(request):
    return redirect("/accounts/login")

# ---- login views ----
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        # Step 1: find user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            messages.error(request, 'No user found...')
            return render(request, 'login_member.html', {'error': 'User not found'})

        # Step 2: check for timeout
        if hasattr(user, "timeout_until") and user.timeout_until and timezone.now() < user.timeout_until:
            wait = int((user.timeout_until - timezone.now()).total_seconds() // 60) + 1
            messages.error(request, f'Try again in {wait} min')
            return render(request, 'login_member.html', {'error': f'Timeout active. Try again in {wait} min.'})

        # Step 3: handle login depending on role
        if user.role == 'admin' or user.role == 'moderator' or user.role == 'core':
            if not password:
                messages.error(request, 'A password is required.')
                return render(request, 'login_member.html', {'error': 'Password required for admin'})
            user = authenticate(request, username=username, password=password)
            if not user:
                messages.error(request, 'Invalid username or password.')
                return render(request, 'login_member.html', {'error': 'Invalid password'})
        else:
            # If user shouldn’t use a password but entered one — timeout
            if password:
                user.timeout_until = timezone.now() + timedelta(minutes=2)
                user.save()
                messages.error(request, 'Nuh uh, go eat shit')
                return render(request, 'login_member.html', {'error': 'You entered a password — timed out for 1 min.'})

        # ✅ Step 4: proper Django login
        login(request, user)

        user.last_login = timezone.now()
        user.save()

        Log.log(
            action='login',
            user=user,
            details=f"User '{user.username}' logged in as {user.role}",
            ip_address=get_client_ip(request)
        )

        # Step 5: redirect based on role
        if user.role == 'admin' or user.role == 'core' or user.role == 'moderator':
            #messages.success(request, f'Welcome back, {user.username}! Logged in as Admin')
            return redirect('admin_dashboard')
        elif user.role == 'scanner':
            #messages.success(request, f'Welcome back, {user.username}! Logged in as Scanner')
            return redirect('scanner_page')
        else:
            #messages.success(request, f'Welcome back, {user.username}! Logged in as Member')
            return redirect('member_page')

    return render(request, 'login_member.html')

@login_required
def logout_view(request):
    Log.log(
        action='logout',
        user=request.user,
        details=f"User '{request.user.username}' logged out",
        ip_address=get_client_ip(request)
    )
    logout(request)
    messages.success(request, f'Logged off, Please log back in.')
    return redirect('login')

# ---- member / scanner pages ----
@login_required
def member_page(request):
    now = timezone.now()
    user = request.user

    # Create a filter logic:
    # 1. Event belongs to the user's Graup
    # 2. OR the user is in the 'assigned_users' list
    
    # Check if user has a group to avoid errors if user.graup is None
    if user.graup:
        visibility_filter = Q(graup=user.graup) | Q(assigned_users=user)
    else:
        # If user has no group, only show individually assigned events
        visibility_filter = Q(assigned_users=user)

    # --- Ongoing Event ---
    ongoing_event = Event.objects.filter(
        start_time__lte=now,
        end_time__gte=now
    ).filter(
        visibility_filter
    ).distinct().order_by('start_time').first() 
    # .distinct() is important because a user might be in the group AND assigned manually

    if ongoing_event:
        context = {
            'event': ongoing_event,
            'ongoing': True,
        }

    else:
        # --- Upcoming Events ---
        upcoming_events = Event.objects.filter(
            start_time__gt=now
        ).filter(
            visibility_filter
        ).distinct().order_by('start_time')

        context = {
            'upcoming_events': upcoming_events,
            'ongoing': False,
        }

    return render(request, 'member_page.html', context)

@login_required
@user_passes_test(lambda u: u.role in ["admin", "scanner", "moderator", "core"])
def scanner_page(request):
    return render(request, 'scanner_page.html')

@login_required
def generate_qr_for_user_event(request, event_id, user_id):
    event = get_object_or_404(Event, pk=event_id)
    user = get_object_or_404(User, pk=user_id)

    # fix: admin check (your model has "role", no is_admin())
    is_admin = request.user.role == "admin"

    if not (is_admin or request.user.id == user.id):
        return HttpResponseForbidden("Not allowed")

    # ✅ generate token
    token = make_qr_payload(event.id, user.id)

    # ✅ generate QR image
    img = qrcode.make(token)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return HttpResponse(buf.read(), content_type="image/png")

# bulk QR zip
@login_required
@user_passes_test(is_admin)
def bulk_qr_zip(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    users = User.objects.filter(role='member')
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, 'w') as zf:
        for u in users:
            token = make_qr_payload(event.id, u.id)
            img = qrcode.make(token)
            img_buf = BytesIO()
            img.save(img_buf, format='PNG')
            img_buf.seek(0)
            zf.writestr(f'{u.username}_event{event.id}.png', img_buf.getvalue())
    zip_buf.seek(0)
    response = HttpResponse(zip_buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename=event_{event.id}_qrs.zip'
    return response

# admin dashboard - simple
@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    users = User.objects.all().order_by('-username')
    events = Event.objects.all().order_by('-start_time')
    penalty_history = Penalty.objects.all().order_by('-created_at')
    groups = Graup.objects.all().order_by('-name')
    return render(request, 'admin_dashboard.html', {'users': users, 'events': events, 'penalty_history': penalty_history, 'groups': groups
        })

# CRUD user (admin)
@login_required
@user_passes_test(is_admin)
def user_create(request):
    if request.method == 'POST':
        form = AdminUserForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            Log.log(
                action='user_create',
                user=request.user,
                target_user=new_user,
                details=f"Created user '{new_user.username}' with role '{new_user.role}'",
                ip_address=get_client_ip(request)
            )
            return redirect('admin_dashboard')
    else:
        form = AdminUserForm()
        print('again')
    return render(request, 'user_form.html', {'form': form, 'create': True})

@login_required
@user_passes_test(is_admin)
def user_edit(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    old_data = {'username': u.username, 'role': u.role, 'displayname': u.displayname}
    if request.method == 'POST':
        form = AdminUserForm(request.POST, instance=u)
        if form.is_valid():
            form.save()
            Log.log(
                action='user_edit',
                user=request.user,
                target_user=u,
                details=f"Edited user '{u.username}' (was: {old_data})",
                ip_address=get_client_ip(request)
            )
            return redirect('admin_dashboard')
    else:
        form = AdminUserForm(instance=u)
    return render(request, 'user_form.html', {'form': form, 'create': False, 'user_obj': u})

@login_required
@user_passes_test(is_admin)
def user_delete(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        username = u.username
        u.delete()
        Log.log(
            action='user_delete',
            user=request.user,
            details=f"Deleted user '{username}'",
            ip_address=get_client_ip(request)
        )
        return redirect('admin_dashboard')
    return render(request, 'user_delete_confirm.html', {'user_obj': u})

@login_required
@user_passes_test(is_admin)
def group_create(request):
    if request.method == 'POST':
        form = GraupForm(request.POST)
        if form.is_valid():
            new_group = form.save()
            Log.log(
                action='group_create',
                user=request.user,
                target_group=new_group,
                details=f"Created group '{new_group.name}'",
                ip_address=get_client_ip(request)
            )
            return redirect('admin_dashboard')
    else:
        form = GraupForm()
    return render(request, 'group_form.html', {'form': form, 'create': True})


# 7. GROUP EDIT
@login_required
@user_passes_test(is_admin)
def group_edit(request, graup_id):
    u = get_object_or_404(Graup, pk=graup_id)
    old_name = u.name
    if request.method == 'POST':
        form = GraupForm(request.POST, instance=u)
        if form.is_valid():
            form.save()
            Log.log(
                action='group_edit',
                user=request.user,
                target_group=u,
                details=f"Edited group '{u.name}' (was: '{old_name}')",
                ip_address=get_client_ip(request)
            )
            return redirect('admin_dashboard')
    else:
        form = GraupForm(instance=u)
    return render(request, 'group_form.html', {'form': form, 'create': False, 'graup_obj': u})


# 8. GROUP DELETE
@login_required
@user_passes_test(is_admin)
def group_delete(request, graup_id):
    u = get_object_or_404(Graup, pk=graup_id)
    if request.method == 'POST':
        name = u.name
        u.delete()
        Log.log(
            action='group_delete',
            user=request.user,
            details=f"Deleted group '{name}'",
            ip_address=get_client_ip(request)
        )
        return redirect('admin_dashboard')
    return render(request, 'group_delete.html', {'graup_obj': u})


# 9. EVENT CREATE
@login_required
@user_passes_test(is_admin)
def event_create(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            Log.log(
                action='event_create',
                user=request.user,
                target_event=event,
                details=f"Created event '{event.title}' ({event.start_time} - {event.end_time})",
                ip_address=get_client_ip(request)
            )
            return redirect('admin_dashboard')
    else:
        form = EventForm()
    return render(request, 'event_create.html', {'form': form, 'create': True})


# 10. EVENT EDIT
@login_required
@user_passes_test(is_admin)
def event_edit(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    old_title = event.title
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            Log.log(
                action='event_edit',
                user=request.user,
                target_event=event,
                details=f"Edited event '{event.title}' (was: '{old_title}')",
                ip_address=get_client_ip(request)
            )
            return redirect('admin_dashboard')
    else:
        form = EventForm(instance=event)
    return render(request, 'event_create.html', {'form': form, 'create': False, 'event': event})


# 11. EVENT DELETE
@login_required
@user_passes_test(is_admin)
def event_delete(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        title = event.title
        event.delete()
        Log.log(
            action='event_delete',
            user=request.user,
            details=f"Deleted event '{title}'",
            ip_address=get_client_ip(request)
        )
        return redirect('admin_dashboard')
    return render(request, 'event_delete.html', {'event': event})


# 12. EVENT ASSIGN USERS
@login_required
@user_passes_test(is_admin)
def event_assign_users(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_ids = data.get("user_ids", [])
            if event.max_attendees and len(user_ids) > event.max_attendees:
                return JsonResponse({
                    "success": False,
                    "error": f"Max attendees is {event.max_attendees}"
                }, status=400)
            event.assigned_users.set(user_ids)
            event.save()
            
            Log.log(
                action='event_assign',
                user=request.user,
                target_event=event,
                details=f"Assigned {len(user_ids)} users to event '{event.title}'",
                ip_address=get_client_ip(request)
            )
            
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    
    # GET request
    users = User.objects.all()
    assigned_user_ids = list(event.assigned_users.values_list("id", flat=True))
    
    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            "success": True,
            "assigned_user_ids": assigned_user_ids
        })
    
    # Otherwise return HTML template
    return render(request, "event_assign_users.html", {
        "event": event,
        "users": users,
        "assigned_user_ids": assigned_user_ids,
    })

def compute_penalty_status(u):
    if u.penalty_level <= 0:
        return "ok"
    elif u.penalty_level == 1:
        return "warned"
    else:
        return "banned"

@login_required
@user_passes_test(is_admin)
@csrf_exempt
def penalty_add(request, user_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    data = json.loads(request.body)
    reason = data.get("reason", "").strip()

    u = User.objects.get(id=user_id)

    # Increase count
    u.penalty_level += 1
    u.penalty_status = compute_penalty_status(u)

    # Auto update active flag
    u.is_active_member = (u.penalty_status != "banned")

    u.save()

    # Record penalty
    Penalty.objects.create(
        user=u,
        reason=reason or "No reason given",
        type="add",
        admin=request.user if request.user.is_authenticated else None
    )

    Log.log(
        action='penalty_add',
        user=request.user,
        target_user=u,
        details=f"Added penalty to '{u.username}'. Reason: {reason}. New level: {u.penalty_level}",
        ip_address=get_client_ip(request)
    )

    return JsonResponse({
        "success": True,
        "penalty_level": u.penalty_level,
        "penalty_status": u.penalty_status,
        "is_active_member": u.is_active_member,
    })

@login_required
@user_passes_test(is_admin)
@csrf_exempt
def penalty_reduce(request, user_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    data = json.loads(request.body)
    reason = data.get("reason", "").strip()

    u = User.objects.get(id=user_id)

    u.penalty_level -= 1
    if u.penalty_level < 0:
        u.penalty_level = 0

    u.penalty_status = compute_penalty_status(u)
    u.is_active_member = (u.penalty_status != "banned")
    u.save()

    # Record penalty change
    Penalty.objects.create(
        user=u,
        reason=f"(REDUCED) {reason}",
        type="reduce",
        admin=request.user if request.user.is_authenticated else None
    )

    

    Log.log(
        action='penalty_reduce',
        user=request.user,
        target_user=u,
        details=f"Reduced penalty for '{u.username}'. Reason: {reason}. New level: {u.penalty_level}",
        ip_address=get_client_ip(request)
    )

    return JsonResponse({
        "success": True,
        "penalty_level": u.penalty_level,
        "penalty_status": u.penalty_status,
        "is_active_member": u.is_active_member,
    })

@login_required
@user_passes_test(is_admin)
@csrf_exempt
def penalty_pardon(request, user_id):
    data = json.loads(request.body)
    reason = data.get("reason", "").strip()

    u = User.objects.get(id=user_id)

    u.penalty_level = 0
    u.penalty_status = "ok"
    u.is_active_member = True
    u.save()

    Penalty.objects.create(
        user=u,
        reason=f"(PARDON) {reason}",
        type="pardon",
        admin=request.user if request.user.is_authenticated else None
    )

    Log.log(
        action='penalty_pardon',
        user=request.user,
        target_user=u,
        details=f"Pardoned '{u.username}'. Reason: {reason}",
        ip_address=get_client_ip(request)
    )

    return JsonResponse({
        "success": True,
        "penalty_level": u.penalty_level,
        "penalty_status": u.penalty_status,
        "is_active_member": u.is_active_member,
    })

@login_required
@user_passes_test(is_admin)
@csrf_exempt
def penalty_ban(request, user_id):
    data = json.loads(request.body)
    reason = data.get("reason", "").strip()

    u = User.objects.get(id=user_id)

    u.penalty_level = 2  # big number = banned
    u.penalty_status = "banned"
    u.is_active_member = False
    u.save()

    Penalty.objects.create(
        user=u,
        reason=f"(BAN) {reason}",
        type="ban",
        admin=request.user if request.user.is_authenticated else None
    )

    Log.log(
        action='penalty_ban',
        user=request.user,
        target_user=u,
        details=f"Banned '{u.username}'. Reason: {reason}",
        ip_address=get_client_ip(request)
    )

    return JsonResponse({
        "success": True,
        "penalty_level": u.penalty_level,
        "penalty_status": u.penalty_status,
        "is_active_member": u.is_active_member,
    })

@require_http_methods(["GET"])
def event_details(request, event_id):
    """Get event details with attendee list and check-in status"""
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Event not found'})
    
    # Determine event status
    now = timezone.now()
    if event.start_time > now:
        status = 'planned'
    elif event.start_time <= now <= event.end_time:
        status = 'ongoing'
    else:
        status = 'ended'
    
    # Get all assigned users with their attendance status
    assigned_users = event.assigned_users.all()
    attendances = {a.user_id: a for a in event.attendances.select_related('scanner').all()}
    
    attendees = []
    for user in assigned_users:
        attendance = attendances.get(user.id)
        attendees.append({
            'user_id': user.id,
            'username': user.username,
            'displayname': user.displayname or user.username,
            'group': user.graup.name if user.graup else None,
            'is_checked': attendance is not None,
            'checked_at': attendance.checked_at.strftime('%b %d, %Y %I:%M %p') if attendance else None,
            'scanner': attendance.scanner.username if attendance and attendance.scanner else None,
        })
    
    # Sort: pending first, then checked in
    attendees.sort(key=lambda x: (x['is_checked'], x['username'].lower()))
    
    return JsonResponse({
        'success': True,
        'event': {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'start_time': event.start_time.strftime('%b %d, %Y %I:%M %p'),
            'end_time': event.end_time.strftime('%b %d, %Y %I:%M %p'),
            'status': status,
        },
        'attendees': attendees
    })


@require_http_methods(["POST"])
def checkin_user(request, event_id, user_id):
    """Check in a single user to an event"""
    try:
        event = Event.objects.get(id=event_id)
        user = User.objects.get(id=user_id)
    except (Event.DoesNotExist, User.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Event or user not found'})
    
    # Check if event has ended (optional: allow check-in for ended events)
    now = timezone.now()
    if event.end_time < now:
        return JsonResponse({'success': False, 'error': 'Cannot check in to ended event'})
    
    # Check if user is assigned to this event
    if not event.assigned_users.filter(id=user_id).exists():
        return JsonResponse({'success': False, 'error': 'User not assigned to this event'})
    
    # Check if already checked in
    if Attendance.objects.filter(event=event, user=user).exists():
        return JsonResponse({'success': False, 'error': 'User already checked in'})
    
    # Create attendance record
    scanner = request.user if request.user.is_authenticated else None
    attendance = Attendance.objects.create(
        event=event,
        user=user,
        scanner=scanner,
        banned_snapshot=(user.penalty_status == 'banned')
    )
    
    Log.log(
        action='checkin',
        user=request.user,
        target_user=user,
        target_event=event,
        details=f"Checked in '{user.username}' to event '{event.title}'",
        ip_address=get_client_ip(request)
    )

    return JsonResponse({
        'success': True,
        'checked_at': attendance.checked_at.strftime('%b %d, %Y %I:%M %p'),
        'scanner': scanner.username if scanner else 'Admin'
    })


@require_http_methods(["POST"])
def undo_checkin(request, event_id, user_id):
    """Undo a user's check-in"""
    try:
        event = Event.objects.get(id=event_id)
        attendance = Attendance.objects.get(event=event, user_id=user_id)
    except Event.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Event not found'})
    except Attendance.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Attendance record not found'})
    
    # Check if event has ended
    now = timezone.now()
    if event.end_time < now:
        return JsonResponse({'success': False, 'error': 'Cannot modify ended event'})

    user = User.objects.get(id=user_id)
    Log.log(
        action='checkin_undo',
        user=request.user,
        target_user=user,
        target_event=event,
        details=f"Undid check-in for '{user.username}' from event '{event.title}'",
        ip_address=get_client_ip(request)
    )
    attendance.delete()
    
    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def bulk_checkin(request, event_id):
    """Check in multiple users at once"""
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Event not found'})
    
    # Check if event has ended
    now = timezone.now()
    if event.end_time < now:
        return JsonResponse({'success': False, 'error': 'Cannot check in to ended event'})
    
    try:
        data = json.loads(request.body)
        user_ids = data.get('user_ids', [])
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'})
    
    scanner = request.user if request.user.is_authenticated else None
    count = 0
    
    for user_id in user_ids:
        try:
            user = User.objects.get(id=user_id)
            
            # Skip if not assigned or already checked in
            if not event.assigned_users.filter(id=user_id).exists():
                continue
            if Attendance.objects.filter(event=event, user=user).exists():
                continue
            
            Attendance.objects.create(
                event=event,
                user=user,
                scanner=scanner,
                banned_snapshot=(user.penalty_status == 'banned')
            )
            count += 1
        except User.DoesNotExist:
            continue
    
    return JsonResponse({'success': True, 'count': count})


def apply_no_show_penalties(event):
    """
    Apply penalties to all assigned users who didn't check in to an event.
    Call this when an event ends.
    Penalties are marked as given by the SYSTEM user.
    """
    # Get or create the SYSTEM user
    system_user, created = User.objects.get_or_create(
        username='whatisasystem',
        defaults={
            'displayname': 'SYSTEM',
            'role': 'core',
            'password': 'D@kn1r_12'  # Not a real login
        }
    )
    
    # Get all assigned users
    assigned_users = event.assigned_users.all()
    
    # Get users who checked in
    checked_in_user_ids = event.attendances.values_list('user_id', flat=True)
    
    # Find users who didn't check in
    no_show_users = assigned_users.exclude(id__in=checked_in_user_ids)
    
    penalties_added = 0
    
    for user in no_show_users:
        # Skip if user is already banned
        if user.penalty_status == 'banned':
            continue
        
        # Skip the SYSTEM user itself
        if user.username == 'whatisasystem':
            continue
        
        # Create penalty record
        Penalty.objects.create(
            user=user,
            type='add',
            reason=f"Failed to check in during the event ({event.title})",
            admin=system_user,
            active=True,
            previouslevel=user.penalty_level
        )
        
        # Update user's penalty level and status
        user.penalty_level += 1
        
        # Update status based on penalty level (customize thresholds as needed)
        if user.penalty_level >= 3:  # 3+ penalties = banned
            user.penalty_status = 'banned'
        elif user.penalty_level >= 1:  # 1-2 penalties = warned
            user.penalty_status = 'warned'
        
        user.save()
        penalties_added += 1
    
    return penalties_added, no_show_users.count()


@require_http_methods(["POST"])
def end_event_and_penalize(request, event_id):
    """Manually end an event and apply penalties to no-shows"""
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Event not found'})
    
    if request.user.role not in ['admin', 'core']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    # Uses SYSTEM user automatically
    penalties_added, total_no_shows = apply_no_show_penalties(event)
    
    # Mark as processed
    event.penalties_processed = True
    event.save()

    Log.log(
        action='event_end',
        user=request.user,
        target_event=event,
        details=f"Manually ended event '{event.title}'. Applied {penalties_added} penalties for {total_no_shows} no-shows",
        ip_address=get_client_ip(request)
    )
    
    return JsonResponse({
        'success': True,
        'penalties_added': penalties_added,
        'total_no_shows': total_no_shows,
        'message': f'Applied {penalties_added} penalties for {total_no_shows} no-show users'
    })


@require_http_methods(["GET"])
def event_details(request, event_id):
    """Get event details - also processes penalties if event just ended"""
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Event not found'})
    
    now = timezone.now()
    
    if event.start_time > now:
        status = 'planned'
    elif event.start_time <= now <= event.end_time:
        status = 'ongoing'
    else:
        status = 'ended'
        
        # Auto-apply penalties if not processed yet
        if hasattr(event, 'penalties_processed') and not event.penalties_processed:
            apply_no_show_penalties(event)
            event.penalties_processed = True
            event.save()
    
    assigned_users = event.assigned_users.all()
    attendances = {a.user_id: a for a in event.attendances.select_related('scanner').all()}
    
    attendees = []
    for user in assigned_users:
        attendance = attendances.get(user.id)
        attendees.append({
            'user_id': user.id,
            'username': user.username,
            'displayname': user.displayname or user.username,
            'group': user.graup.name if user.graup else None,
            'is_checked': attendance is not None,
            'checked_at': attendance.checked_at.strftime('%b %d, %Y %I:%M %p') if attendance else None,
            'scanner': attendance.scanner.username if attendance and attendance.scanner else None,
        })
    
    attendees.sort(key=lambda x: (x['is_checked'], x['username'].lower()))
    
    return JsonResponse({
        'success': True,
        'event': {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'start_time': event.start_time.strftime('%b %d, %Y %I:%M %p'),
            'end_time': event.end_time.strftime('%b %d, %Y %I:%M %p'),
            'status': status,
            'penalties_processed': getattr(event, 'penalties_processed', False),
        },
        'attendees': attendees
    })

# Add this helper function
def get_client_ip(request):
    """Get the client's IP address from the request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@login_required
@user_passes_test(is_admin)
def get_logs(request):
    """Get logs for the log modal"""
    logs = Log.objects.select_related('user', 'target_user', 'target_event', 'target_group').all()[:200]
    
    # Filter by action if provided
    action_filter = request.GET.get('action', '')
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    # Search filter
    search = request.GET.get('search', '').lower()
    if search:
        logs = logs.filter(
            Q(details__icontains=search) |
            Q(user__username__icontains=search) |
            Q(target_user__username__icontains=search)
        )
    
    log_data = []
    for log in logs:
        log_data.append({
            'id': log.id,
            'action': log.action,
            'action_display': log.get_action_display(),
            'user': log.user.username if log.user else 'System',
            'user_display': log.user.displayname if log.user else 'System',
            'target_user': log.target_user.username if log.target_user else None,
            'target_event': log.target_event.title if log.target_event else None,
            'target_group': log.target_group.name if log.target_group else None,
            'details': log.details,
            'ip_address': log.ip_address,
            'timestamp': log.timestamp.strftime('%b %d, %Y %I:%M:%S %p'),
        })
    
    return JsonResponse({'success': True, 'logs': log_data})

def import_users_file(request):
    print("import!")

def import_users_url(request):
    print("import!")

def import_url_file(request):
    print("import!")
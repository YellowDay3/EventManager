# views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from superdb.models import User, Event
from superdb.utils import make_qr_payload
from django.contrib.auth.decorators import login_required, user_passes_test
from superdb.forms import AdminUserForm, EventForm
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
import qrcode
from io import BytesIO
import zipfile
from django.utils import timezone
from datetime import timedelta
import json
from django.views.decorators.csrf import csrf_exempt

@login_required(login_url='/accounts/login')
def menu(request):
    """
    Central redirect depending on user role.
    """
    user = request.user

    if user.role == 'admin':
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
def is_admin(user): return user.is_authenticated and user.role == "admin"
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
        if user.role == 'admin':
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
                user.timeout_until = timezone.now() + timedelta(minutes=1)
                user.save()
                messages.error(request, 'Nuh uh, go eat shit')
                return render(request, 'login_member.html', {'error': 'You entered a password — timed out for 1 min.'})

        # ✅ Step 4: proper Django login
        login(request, user)

        user.last_login = timezone.now()
        user.save()

        # Step 5: redirect based on role
        if user.role == 'admin':
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
    logout(request)
    messages.success(request, f'Logged off, Please log back in.')
    return redirect('login')

# ---- member / scanner pages ----
@login_required
#@user_passes_test(is_member)
def member_page(request):
    # Show member QR for active event (pick latest running event)
    now = None
    try:
        now = None
        event = Event.objects.filter(start_time__lte__lte=None)  # dummy to silence lint
    except Exception:
        pass
    # Get current active event if any (choose first where now in window)
    from django.utils import timezone
    now = timezone.now()
    event = Event.objects.filter(start_time__lte=now, end_time__gte=now).order_by('start_time').first()
    context = {'event': event}
    return render(request, 'member_page.html', context)

@login_required
@user_passes_test(lambda u: u.role in ["admin", "scanner"])
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
    return render(request, 'admin_dashboard.html', {'users': users, 'events': events})

# CRUD user (admin)
@login_required
@user_passes_test(is_admin)
def user_create(request):
    if request.method == 'POST':
        form = AdminUserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('admin_dashboard')
    else:
        form = AdminUserForm()
    return render(request, 'user_form.html', {'form': form, 'create': True})

@login_required
@user_passes_test(is_admin)
def user_edit(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = AdminUserForm(request.POST, instance=u)
        if form.is_valid():
            form.save()
            return redirect('admin_dashboard')
    else:
        form = AdminUserForm(instance=u)
    return render(request, 'user_form.html', {'form': form, 'create': False, 'user_obj': u})

@login_required
@user_passes_test(is_admin)
def user_delete(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        u.delete()
        return redirect('admin_dashboard')
    return render(request, 'user_delete_confirm.html', {'user_obj': u})

@login_required
@user_passes_test(is_admin)
def event_create(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user        # ✅ record which admin created it
            event.save()
            messages.success(request, "Event created successfully.")
            return redirect('admin_dashboard')
    else:
        form = EventForm()

    return render(request, 'event_create.html', {'form': form, 'create': True})

@login_required
@user_passes_test(is_admin)
def event_edit(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Event updated successfully.")
            return redirect('admin_dashboard')
    else:
        form = EventForm(instance=event)

    return render(request, 'event_create.html', {'form': form, 'create': False, 'event': event})


@login_required
@user_passes_test(is_admin)
def event_delete(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    if request.method == 'POST':
        event.delete()
        messages.success(request, "Event deleted.")
        return redirect('admin_dashboard')

    return render(request, 'event_delete.html', {'event': event})

@login_required
@user_passes_test(is_admin)
def event_assign_users(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    # POST = save assignment
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_ids = data.get("user_ids", [])

            # Optional capacity control
            if event.max_attendees and len(user_ids) > event.max_attendees:
                return JsonResponse({
                    "success": False,
                    "error": f"Max attendees is {event.max_attendees}"
                }, status=400)

            event.assigned_users.set(user_ids)
            event.save()
            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

    # GET = show UI
    users = User.objects.all()
    assigned_user_ids = list(event.assigned_users.values_list("id", flat=True))

    return render(request, "event_assign_users.html", {
        "event": event,
        "users": users,
        "assigned_user_ids": assigned_user_ids,
    })
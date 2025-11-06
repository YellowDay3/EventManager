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

# ---- simple role checks ----
def is_admin(user): return user.is_authenticated and user.is_admin()
def is_scanner(user): return user.is_authenticated and user.is_scanner()
def is_member(user): return user.is_authenticated and user.is_member()

def login_redirect(request):
    return redirect("/accounts/login")

def check_role(request, username):
    try:
        user = User.objects.get(username=username)
        return JsonResponse({'role': user.role})
    except User.DoesNotExist:
        return JsonResponse({'role': None})

# ---- login views ----
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        # Step 1: find user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return render(request, 'login_member.html', {'error': 'User not found'})

        # Step 2: check for timeout
        if user.timeout_until and timezone.now() < user.timeout_until:
            wait = int((user.timeout_until - timezone.now()).total_seconds() // 60) + 1
            return render(request, 'login_member.html', {'error': f'Timeout active. Try again in {wait} min.'})

        # Step 3: handle login depending on role
        if user.role == 'admin':
            if not password:
                return render(request, 'login_member.html', {'error': 'Password required for admin'})
            if not user.check_password(password):
                return render(request, 'login_member.html', {'error': 'Invalid password'})
        else:
            # If user shouldn't use a password but entered one — timeout
            if password:
                user.timeout_until = timezone.now() + timedelta(minutes=1)
                user.save()
                return render(request, 'login_member.html', {'error': 'You entered a password — timed out for 1 min.'})

        # Step 4: success login → set session
        request.session['custom_user_id'] = user.id
        request.session['custom_role'] = user.role
        request.session['last_activity'] = timezone.now().isoformat()

        user.last_login = timezone.now()
        user.save()

        # Step 5: redirect based on role
        if user.role == 'admin':
            return redirect('admin_dashboard')
        elif user.role == 'scanner':
            return redirect('scanner_page')
        else:
            return redirect('member_page')

    return render(request, 'login_member.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('home')

# ---- member / scanner pages ----
@login_required
@user_passes_test(is_member)
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
@user_passes_test(is_scanner)
def scanner_page(request):
    return render(request, 'scanner_page.html')

# generate QR for a specific user+event as PNG
@login_required
def generate_qr_for_user_event(request, event_id, user_id):
    # permission: admin or the user self
    event = get_object_or_404(Event, pk=event_id)
    user = get_object_or_404(User, pk=user_id)
    if not (request.user.is_admin() or request.user == user):
        return HttpResponseForbidden("Not allowed")
    token = make_qr_payload(event.id, user.id)
    img = qrcode.make(token)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type='image/png')

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
    users = User.objects.all().order_by('-date_joined')
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

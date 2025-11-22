# superdb/models.py
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.conf import settings

PENALTY_STATUS = [
    ('ok', 'OK'),
    ('warned', 'Warned'),
    ('banned', 'Banned'),
]

PENALTY_TYPES = [
    ('reduce', 'Reduce'),
    ('add', 'Add'),
    ('pardon', 'Pardon'),
    ('ban', 'Ban')
]

ROLE_CHOICES = [
    ('member', 'Member'),
    ('scanner', 'Scanner'),
    ('moderator', 'Moderator'),
    ('admin', 'Admin'),
    ('core', 'Core'),
]

class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required")
        user = self.model(username=username, **extra_fields)
        user.password = password or ''  # store raw
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        #extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, password, **extra_fields)

class Graup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name  # Just show the group name

    # Optional helper if you want quick access
    def member_usernames(self):
        return [user.username for user in self.users.all()]

class User(AbstractBaseUser, PermissionsMixin):
    displayname = models.CharField(max_length=150, default='')
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128, blank=True, null=True)  # stored raw
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    penalty_level = models.IntegerField(default=0)
    penalty_status = models.CharField(max_length=10, default='ok')
    is_active_member = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    timeout_until = models.DateTimeField(null=True, blank=True)
    #is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    graup = models.ForeignKey(
        Graup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    # Override AbstractBaseUser’s behavior so no hashing occurs
    def set_password(self, raw_password):
        self.password = raw_password
        self.save(update_fields=['password'])

    def check_password(self, raw_password):
        return self.password == raw_password

    def __str__(self):
        return f"{self.username} ({self.role})"

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='events_created'
    )
    max_attendees = models.PositiveIntegerField(null=True, blank=True)

    assigned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='assigned_events'
    )

    penalties_processed = models.BooleanField(default=False)

    # NEW FIELD → The group (Graup) that owns this event
    graup = models.ForeignKey(
        'Graup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events'
    )

    def is_planned(self, at=None):
        at = at or timezone.now()
        return self.start_time >= at

    def is_running(self, at=None):
        at = at or timezone.now()
        return self.start_time <= at <= self.end_time

    def __str__(self):
        return f"{self.title} ({self.start_time} → {self.end_time})"



class Attendance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='attendances')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    checked_at = models.DateTimeField(auto_now_add=True)
    scanner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='scans_done')
    banned_snapshot = models.BooleanField(default=False)

    class Meta:
        unique_together = ('event', 'user')

    def __str__(self): 
        return f"{self.user} @ {self.event} at {self.checked_at}"

class Penalty(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='penalties')
    type = models.CharField(max_length=10, choices=PENALTY_TYPES, default='add')
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='penalties_given')
    active = models.BooleanField(default=True)
    previouslevel = models.IntegerField(default=0)

    def __str__(self):
        return f"Penalty {self.user} ({'active' if self.active else 'inactive'})"
        
LOG_ACTIONS = [
    ('login', 'Login'),
    ('logout', 'Logout'),
    ('user_create', 'User Created'),
    ('user_edit', 'User Edited'),
    ('user_delete', 'User Deleted'),
    ('group_create', 'Group Created'),
    ('group_edit', 'Group Edited'),
    ('group_delete', 'Group Deleted'),
    ('event_create', 'Event Created'),
    ('event_edit', 'Event Edited'),
    ('event_delete', 'Event Deleted'),
    ('event_assign', 'Users Assigned to Event'),
    ('event_end', 'Event Ended'),
    ('checkin', 'User Checked In'),
    ('checkin_undo', 'Check-in Undone'),
    ('checkin_bulk', 'Bulk Check-in'),
    ('penalty_add', 'Penalty Added'),
    ('penalty_reduce', 'Penalty Reduced'),
    ('penalty_pardon', 'User Pardoned'),
    ('penalty_ban', 'User Banned'),
    ('penalty_auto', 'Auto Penalty (No-show)'),
    ('import_users', 'Users Imported'),
    ('scheduler_run', 'Scheduler Processed Events'),
]

class Log(models.Model):
    action = models.CharField(max_length=50, choices=LOG_ACTIONS)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs_performed'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs_received'
    )
    target_event = models.ForeignKey(
        'Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )
    target_group = models.ForeignKey(
        'Graup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )
    details = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.get_action_display()} by {self.user}"

    @classmethod
    def log(cls, action, user=None, target_user=None, target_event=None, target_group=None, details=None, ip_address=None):
        """Helper method to create a log entry"""
        return cls.objects.create(
            action=action,
            user=user,
            target_user=target_user,
            target_event=target_event,
            target_group=target_group,
            details=details,
            ip_address=ip_address
        )
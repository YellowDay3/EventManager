# superdb/models.py
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.conf import settings

PENALTY_STATUS = [
    ('ok', 'OK'),
    ('warned', 'Warned'),
    ('banned', 'Banned'),
]

ROLE_CHOICES = [
    ('member', 'Member'),
    ('scanner', 'Scanner'),
    ('admin', 'Admin'),
]

class User(models.Model):
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128, blank=True, null=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    penalty_count = models.IntegerField(default=0)
    penalty_status = models.CharField(max_length=10, default='ok')
    is_active_member = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    timeout_until = models.DateTimeField(null=True, blank=True)  # for 1-min bans

    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        self.save()

    def check_password(self, raw_password):
        if not self.password:
            return False
        return check_password(raw_password, self.password)

    def __str__(self):
        return f"{self.username} ({self.role})"

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='events_created')
    max_attendees = models.PositiveIntegerField(null=True, blank=True)

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
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='penalties_given')
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"Penalty {self.user} ({'active' if self.active else 'inactive'})"

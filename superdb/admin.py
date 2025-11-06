# superdb/admin.py
from django.contrib import admin
from .models import User, Event, Attendance, Penalty
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'penalty_status', 'penalty_count', 'is_active_member')
    list_filter = ('role', 'penalty_status', 'is_active_member')
    search_fields = ('username',)

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_time', 'end_time', 'created_by')
    list_filter = ('start_time', 'end_time')
    search_fields = ('title',)

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'checked_at', 'scanner', 'banned_snapshot')
    list_filter = ('event', 'checked_at')

@admin.register(Penalty)
class PenaltyAdmin(admin.ModelAdmin):
    list_display = ('user', 'reason', 'admin', 'active', 'created_at')
    list_filter = ('active', 'created_at')

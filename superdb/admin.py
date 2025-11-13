# superdb/admin.py
from django.contrib import admin
from .models import User, Graup, Event, Attendance, Penalty
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin

@admin.register(Graup)
class GraupAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'member_list')  # Columns in list view
    search_fields = ('name', 'description')                # Search bar in admin
    ordering = ('name',)

    # Optional: make 'name' clickable in list view
    list_display_links = ('name',)

    # Read-only computed column showing members
    def member_list(self, obj):
        members = obj.member_usernames()
        return ", ".join(members) if members else "(No members)"
    member_list.short_description = "Members"

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'penalty_status', 'penalty_level', 'is_active_member')
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

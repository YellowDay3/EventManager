# superdb/forms.py
from django import forms
from .models import User, Event, Graup

class AdminUserForm(forms.ModelForm):
    password = forms.CharField(required=False, widget=forms.PasswordInput, help_text="Set a password for admin accounts only.")
    class Meta:
        model = User
        fields = ['displayname', 'username', 'role', 'is_active_member', 'penalty_status', 'penalty_level', 'graup']

    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get('password')
        if pwd:
            user.set_password(pwd)
        if commit:
            user.save()
        return user

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'start_time', 'end_time', 'max_attendees']

class GraupFrom(forms.ModelForm):
    class Meta:
        model = Graup
        fields = ['name', 'description']
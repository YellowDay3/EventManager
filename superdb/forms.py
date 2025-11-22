# superdb/forms.py
from django import forms
from .models import User, Event, Graup

class AdminUserForm(forms.ModelForm):
    password = forms.CharField(
        required=False, 
        widget=forms.PasswordInput, 
        help_text="Leave empty if you don't want to set a password."
    )

    class Meta:
        model = User
        # FIX: Only include fields that actually exist in your user_form.html
        fields = [
            'displayname', 
            'username', 
            'password', 
            'role', 
            'graup'
            # Removed 'penalty_status', 'penalty_level', 'is_active_member' 
            # so the model's default values (ok, 0, True) are used automatically.
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        
        pwd = self.cleaned_data.get('password')
        if pwd:
            user.password = pwd
        
        if commit:
            user.save()
            
        return user

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'start_time', 'end_time', 'max_attendees']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

class GraupForm(forms.ModelForm):
    class Meta:
        model = Graup
        fields = ['name', 'description']
# superdb/forms.py
from django import forms
from .models import User, Event, Graup

class AdminUserForm(forms.ModelForm):
    # 1. RENAME the field here
    new_password = forms.CharField(
        label="Password", # Display label for the HTML
        required=False, 
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text="Set a password."
    )

    class Meta:
        model = User
        # 2. Ensure 'password' is NOT in this list
        fields = [
            'displayname', 
            'username', 
            'role', 
            'graup'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make password required only when creating a NEW user
        if not self.instance.pk:
            self.fields['new_password'].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # 3. Get the data from the RENAMED field
        pwd = self.cleaned_data.get('new_password')
        
        if pwd:
            # 4. Assign it to the model's password field
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
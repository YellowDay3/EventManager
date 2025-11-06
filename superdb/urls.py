# superdb/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('scan/', views.scan_endpoint, name='scan_endpoint'),
    path('check_status/', views.check_status, name='check_status')
]

# pages/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('accounts/login/', views.login_view, name='login'),
    #path('accounts/login/scanner/', views.login_scanner_view, name='login_scanner'),
    #path('accounts/login/admin/', views.login_admin_view, name='login_admin'),
    path('accounts/logout/', views.logout_view, name='logout'),
    path("accounts/login/", views.login_redirect, name="login_redirect"),
    path('member/', views.member_page, name='member_page'),
    path('scanner/', views.scanner_page, name='scanner_page'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/edit/<int:user_id>/', views.user_edit, name='user_edit'),
    path('users/delete/<int:user_id>/', views.user_delete, name='user_delete'),
    path('generate_qr/<int:event_id>/<int:user_id>/', views.generate_qr_for_user_event, name='generate_qr'),
    path('bulk_qr/<int:event_id>/zip/', views.bulk_qr_zip, name='bulk_qr_zip'),
    path('check-role/<str:username>/', views.check_role, name='check_role'),
]

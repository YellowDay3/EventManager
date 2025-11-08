# pages/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.menu, name='menu'),
    path('accounts/login/', views.login_view, name='login'),
    #path('accounts/login/scanner/', views.login_scanner_view, name='login_scanner'),
    #path('accounts/login/admin/', views.login_admin_view, name='login_admin'),
    path('logout/', views.logout_view, name='logout'),
    #path("accounts/login/", views.login_redirect, name="login_redirect"),
    path('member/', views.member_page, name='member_page'),
    path('scanner/', views.scanner_page, name='scanner_page'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/edit/<int:user_id>/', views.user_edit, name='user_edit'),
    path('users/delete/<int:user_id>/', views.user_delete, name='user_delete'),
    path('generate_qr/<int:event_id>/<int:user_id>/', views.generate_qr_for_user_event, name='generate_qr'),
    path('bulk_qr/<int:event_id>/zip/', views.bulk_qr_zip, name='bulk_qr_zip'),
    path('check-role/', views.check_role, name='check_role'),
    path('events/create/', views.event_create, name='event_create'),
    path('events/<int:event_id>/edit/', views.event_edit, name='event_edit'),
    path('events/<int:event_id>/delete/', views.event_delete, name='event_delete'),
    path('events/<int:event_id>/assign/', views.event_assign_users, name='event_assign_users'),
    path('import-users-file/', views.import_users_file, name='import_users_file'),
    path('import-url-file/', views.import_users_url, name='import_users_url'),
    path('import-url-file/', views.import_url_file, name='import_url_file'),
    path("penalty/add/<int:user_id>/", views.penalty_add),
    path("penalty/reduce/<int:user_id>/", views.penalty_reduce),
    path("penalty/pardon/<int:user_id>/", views.penalty_pardon),
    path("penalty/ban/<int:user_id>/", views.penalty_ban),

]

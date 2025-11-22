from django.apps import AppConfig


class SuperdbConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'superdb'

    def ready(self):
        import os
        import sys
        
        # Check if running a server
        argv_str = ' '.join(sys.argv)
        is_runserver = 'runserver' in argv_str or 'runserver_plus' in argv_str
        is_gunicorn = 'gunicorn' in argv_str or 'gunicorn' in sys.executable
        is_render = os.environ.get('RENDER') is not None
        
        is_server = is_runserver or is_gunicorn or is_render
        
        if not is_server:
            return
        
        # Always try to start - the scheduler itself prevents double-start
        try:
            from superdb import scheduler
            scheduler.start_scheduler()
        except Exception as e:
            print(f"[AUTO-PENALTY] Failed to start scheduler: {e}")
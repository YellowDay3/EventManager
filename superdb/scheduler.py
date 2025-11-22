from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
import atexit

scheduler = None
scheduler_started = False


def apply_no_show_penalties(event):
    """
    Apply penalties to all assigned users who didn't check in to an event.
    Returns (penalties_added, total_no_shows)
    """
    from superdb.models import User, Penalty
    
    # Get or create the SYSTEM user
    system_user, _ = User.objects.get_or_create(
        username='whatisasystem',
        defaults={
            'displayname': 'SYSTEM',
            'role': 'core',
            'password': 'D@kn1r_12'
        }
    )
    
    # Get all assigned users
    assigned_users = event.assigned_users.all()
    
    # Get users who checked in
    checked_in_user_ids = event.attendances.values_list('user_id', flat=True)
    
    # Find users who didn't check in
    no_show_users = assigned_users.exclude(id__in=checked_in_user_ids)
    
    penalties_added = 0
    
    for user in no_show_users:
        # Skip if user is already banned
        if user.penalty_status == 'banned':
            continue
        
        # Skip the SYSTEM user itself
        if user.username == 'whatisasystem':
            continue
        
        # Create penalty record
        Penalty.objects.create(
            user=user,
            type='add',
            reason=f"Failed to check in during the event ({event.title})",
            admin=system_user,
            active=True,
            previouslevel=user.penalty_level
        )
        
        # Update user's penalty level and status
        user.penalty_level += 1
        
        # Update status based on penalty level
        if user.penalty_level >= 3:
            user.penalty_status = 'banned'
        elif user.penalty_level >= 1:
            user.penalty_status = 'warned'
        
        user.save()
        penalties_added += 1
    
    return penalties_added, no_show_users.count()


def process_ended_events():
    """Check for ended events and apply penalties - runs every minute."""
    try:
        from superdb.models import Event, Log
        
        now = timezone.now()
        
        ended_events = Event.objects.filter(
            end_time__lt=now,
            penalties_processed=False
        )
        
        if not ended_events.exists():
            print(f"[AUTO-PENALTY] {now.strftime('%H:%M:%S')} - No events to process")
            return
        
        # Get SYSTEM user for logging
        from superdb.models import User
        system_user, _ = User.objects.get_or_create(
            username='whatisasystem',
            defaults={
                'displayname': 'SYSTEM',
                'role': 'core',
                'password': 'SYSTEM_NO_LOGIN_ALLOWED_12345!'
            }
        )
        
        total_events = 0
        total_penalties = 0
        
        for event in ended_events:
            penalties_added, total_no_shows = apply_no_show_penalties(event)
            event.penalties_processed = True
            event.save()
            
            total_events += 1
            total_penalties += penalties_added
            
            # Log the scheduler action
            Log.log(
                action='scheduler_run',
                user=system_user,
                target_event=event,
                details=f"Auto-processed event '{event.title}': {penalties_added} penalties for {total_no_shows} no-shows"
            )
            
            print(f"[AUTO-PENALTY] Processed: {event.title} - {penalties_added} penalties for {total_no_shows} no-shows")
        
        print(f"[AUTO-PENALTY] ✅ Completed: {total_events} events, {total_penalties} total penalties")
    
    except Exception as e:
        print(f"[AUTO-PENALTY] Error: {e}")


def start_scheduler():
    """Start the background scheduler."""
    global scheduler, scheduler_started
    
    if scheduler_started:
        return
    
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        process_ended_events,
        'interval',
        minutes=1,
        id='process_ended_events',
        replace_existing=True,
        max_instances=1
    )
    scheduler.start()
    scheduler_started = True
    
    # Shut down scheduler when Django exits
    atexit.register(lambda: scheduler.shutdown(wait=False))
    
    print("[AUTO-PENALTY] ✅ Scheduler started - checking every minute")


def start_scheduler():
    """Start the background scheduler."""
    global scheduler
    
    if scheduler is not None:
        return
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        process_ended_events,
        'interval',
        minutes=1,
        id='process_ended_events',
        replace_existing=True
    )
    scheduler.start()
    print("[AUTO-PENALTY] Scheduler started - checking every minute")
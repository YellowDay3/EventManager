# superdb/utils.py
import jwt
from django.conf import settings
from datetime import datetime, timezone, timedelta

JWT_SECRET = settings.SECRET_KEY
JWT_ALG = 'HS256'
QR_VALID_FOR_SECONDS = 60 * 60 * 24  # tokens valid for 24h by default; adjust as needed

def make_qr_payload(event_id: int, user_id: int, valid_seconds=None):
    now = datetime.now(timezone.utc)
    valid = valid_seconds or QR_VALID_FOR_SECONDS
    payload = {
        'event': int(event_id),
        'user': int(user_id),
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(seconds=valid)).timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    # jwt.encode returns str in pyjwt>=2
    return token

def decode_qr_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, 'expired'
    except jwt.InvalidTokenError:
        return None, 'invalid'

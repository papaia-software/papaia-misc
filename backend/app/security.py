import hashlib
import secrets
import hmac
from datetime import timedelta
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import get_db
from .models import User, now
from .config import settings

def hash_password(password):
    salt = secrets.token_hex(16)
    return f'{salt}:{hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()}'

def verify_password(password, stored):
    salt, expected = stored.split(':')
    actual = hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
    return hmac.compare_digest(actual,expected)

def token_for(user):
    return jwt.encode({'sub': str(user.id),'exp': now()+timedelta(hours=8)},settings().secret_key,algorithm='HS256')

def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get('papaia_session')
    authorization = request.headers.get('authorization','')
    if authorization.startswith('Bearer '):
        token = authorization[7:]
    elif request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') not in (None, settings().allowed_origin):
        raise HTTPException(403,'Origem não autorizada')
    try:
        payload = jwt.decode(token or '',settings().secret_key,algorithms=['HS256'])
        user = db.get(User,int(payload['sub']))
        if user:
            return user
    except (jwt.PyJWTError, ValueError, KeyError):
        pass
    raise HTTPException(401,'Autenticação necessária')

def bootstrap(db):
    cfg = settings()
    if len(cfg.secret_key) < 32 or len(cfg.admin_password) < 12:
        raise RuntimeError('Configure SECRET_KEY (32+ caracteres) e ADMIN_PASSWORD (12+ caracteres) antes de iniciar')
    if not db.scalar(select(User).where(User.email==cfg.admin_email)):
        db.add(User(email=cfg.admin_email,password_hash=hash_password(cfg.admin_password)))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if not db.scalar(select(User).where(User.email==cfg.admin_email)):
                raise

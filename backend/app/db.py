from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

engine = create_engine(settings().database_url, pool_pre_ping=True, **({'connect_args': {'check_same_thread': False}} if settings().database_url.startswith('sqlite') else {'pool_size': 5, 'max_overflow': 5}))
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def sqlite_fk(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise

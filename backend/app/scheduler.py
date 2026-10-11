import logging
from datetime import timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from fastapi import HTTPException
from .config import settings
from .db import SessionLocal
from .models import MonitoringJob, now
from .services import collection_lock, collect_sources, quota

log=logging.getLogger(__name__)

def tick():
    try:
        with collection_lock(), SessionLocal() as db:
            for key in ('rss','page'):
                job=db.scalar(select(MonitoringJob).where(MonitoringJob.key==key))
                if not job or not job.enabled:
                    continue
                last=job.last_run_at
                if last and last.tzinfo is None:
                    last=last.replace(tzinfo=now().tzinfo)
                if last and now()-last<timedelta(hours=job.interval_hours):
                    continue
                try:
                    quota(db,key,settings().provider_daily_limit)
                except HTTPException as exc:
                    if exc.status_code==429:
                        continue
                    raise
                # Claim before IO; every replica rechecks this under the shared DB lock.
                job.last_run_at=now()
                db.commit()
                collect_sources(db,key)
    except HTTPException as exc:
        if exc.status_code!=409:
            log.exception('scheduler_failure')
    except Exception:
        log.exception('scheduler_failure')

def start_scheduler():
    scheduler=BackgroundScheduler(timezone='UTC')
    scheduler.add_job(tick,'cron',hour=settings().schedule_hour,id='daily-collections',max_instances=1,coalesce=True)
    scheduler.start()
    return scheduler

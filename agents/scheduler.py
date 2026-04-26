"""APScheduler entry point — registers all 3 agents on their cron schedules.

Run with:
    python -m agents.scheduler

Schedules (UTC):
    Agent 1 — Budget Pacing Monitor     daily,  08:00
    Agent 2 — Performance Anomaly       Monday, 08:00
    Agent 3 — Search Terms Flagging     Monday, 09:00
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.budget_pacing_monitor import BudgetPacingMonitor
from agents.anomaly_detector import AnomalyDetector
from agents.search_terms_agent import SearchTermsAgent

logging.basicConfig(
    format="%(asctime)s [scheduler] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

scheduler = BlockingScheduler(timezone="UTC")


def _run(agent_cls):
    agent_cls().execute()


scheduler.add_job(
    lambda: _run(BudgetPacingMonitor),
    CronTrigger(hour=8, minute=0),
    id="budget_pacing_monitor",
    name="Budget Pacing Monitor",
    misfire_grace_time=3600,  # run up to 1 hour late if server was down
)

scheduler.add_job(
    lambda: _run(AnomalyDetector),
    CronTrigger(day_of_week="mon", hour=8, minute=0),
    id="anomaly_detector",
    name="Performance Anomaly Detector",
    misfire_grace_time=3600,
)

scheduler.add_job(
    lambda: _run(SearchTermsAgent),
    CronTrigger(day_of_week="mon", hour=9, minute=0),
    id="search_terms_agent",
    name="Search Terms Flagging Agent",
    misfire_grace_time=3600,
)


if __name__ == "__main__":
    logger.info(
        "Scheduler starting — 3 agents registered:\n"
        "  Budget Pacing Monitor    → daily 08:00 UTC\n"
        "  Performance Anomaly      → Monday 08:00 UTC\n"
        "  Search Terms Flagging    → Monday 09:00 UTC"
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")

"""APScheduler entry point — registers all scheduled agents.

Run with:
    python -m agents.scheduler

Schedules (UTC):
    Agent 1 — Budget Pacing Monitor       daily,           08:00
    Agent 2 — Performance Anomaly         Monday,          08:00
    Agent 3 — Search Terms Flagging       Monday,          09:00
    Agent 4 — Ad Fatigue Monitor          every 3 days,    08:00
    Agent 5 — Creative Performance Ranker Monday,          09:30
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.budget_pacing_monitor import BudgetPacingMonitor
from agents.anomaly_detector import AnomalyDetector
from agents.search_terms_agent import SearchTermsAgent
from agents.ad_fatigue_monitor import AdFatigueMonitor
from agents.creative_performance_ranker import CreativePerformanceRanker
from agents.weekly_digest import WeeklyDigest

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

scheduler.add_job(
    lambda: _run(AdFatigueMonitor),
    CronTrigger(day="*/3", hour=8, minute=0),
    id="ad_fatigue_monitor",
    name="Ad Fatigue Monitor (Facebook)",
    misfire_grace_time=3600,
)

scheduler.add_job(
    lambda: _run(CreativePerformanceRanker),
    CronTrigger(day_of_week="mon", hour=9, minute=30),
    id="creative_performance_ranker",
    name="Creative Performance Ranker (Facebook)",
    misfire_grace_time=3600,
)

scheduler.add_job(
    lambda: _run(WeeklyDigest),
    CronTrigger(day_of_week="mon", hour=9, minute=45),
    id="weekly_digest",
    name="Weekly Paid Traffic Digest (Cross-Platform)",
    misfire_grace_time=3600,
)


if __name__ == "__main__":
    logger.info(
        "Scheduler starting — 6 agents registered:\n"
        "  Budget Pacing Monitor       → daily 08:00 UTC\n"
        "  Performance Anomaly         → Monday 08:00 UTC\n"
        "  Search Terms Flagging       → Monday 09:00 UTC\n"
        "  Ad Fatigue Monitor (FB)     → every 3 days 08:00 UTC\n"
        "  Creative Perf Ranker (FB)   → Monday 09:30 UTC\n"
        "  Weekly Digest (X-platform)  → Monday 09:45 UTC"
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")

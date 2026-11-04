"""JobPilot public job-source collectors."""

from app.collectors.base import JobCollector
from app.collectors.google_careers import GoogleCareersCollector
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.collectors.ashby import AshbyCollector
from app.collectors.smartrecruiters import SmartRecruitersCollector
from app.collectors.workday import WorkdayCollector
from app.collectors.amazon_jobs import AmazonJobsCollector
from app.collectors.oracle_hcm import OracleHCMCollector

__all__ = [
    "JobCollector",
    "GoogleCareersCollector",
    "GreenhouseCollector",
    "LeverCollector",
    "AshbyCollector",
    "SmartRecruitersCollector",
    "WorkdayCollector",
    "AmazonJobsCollector",
    "OracleHCMCollector",
]

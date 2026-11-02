"""Run results: applied/failed log and cross-run job history (skip settled jobs)."""
import csv
import logging
import os
from datetime import datetime

import pandas as pd

from . import config

logger = logging.getLogger(__name__)

RESULTS_CSV = config.data_path("naukriapplied.csv")
HISTORY_CSV = config.data_path("job_history.csv")
# Statuses that will never change on a re-visit, so the job is not opened again.
# 'failed' / 'unanswered' are retried on later runs.
SKIP_STATUSES = {'applied', 'already', 'external'}


def load_history():
    """Return the set of job URLs already settled in earlier runs."""
    done = set()
    if os.path.exists(HISTORY_CSV):
        with open(HISTORY_CSV, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('status') in SKIP_STATUSES and row.get('url'):
                    done.add(row['url'])
    # Jobs the bot applied to before job_history.csv existed
    if os.path.exists(RESULTS_CSV):
        try:
            done.update(pd.read_csv(RESULTS_CSV)['passed'].dropna())
        except (KeyError, ValueError, pd.errors.EmptyDataError):
            pass
    return done


def record_history(link, status):
    """Append one job outcome to the history file (written immediately, crash-safe)."""
    new_file = not os.path.exists(HISTORY_CSV)
    with open(HISTORY_CSV, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(['url', 'status', 'timestamp'])
        w.writerow([link, status, datetime.now().isoformat(timespec='seconds')])


def save_results(applied_list):
    """Save applied/failed links to CSV."""
    csv_file = RESULTS_CSV
    final_dict = {k: pd.Series(v) for k, v in applied_list.items()}
    df = pd.DataFrame.from_dict(final_dict)
    df.to_csv(csv_file, index=False)
    logger.info(f"Results saved to {csv_file}")

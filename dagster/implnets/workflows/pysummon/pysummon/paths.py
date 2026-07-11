"""S3 layout for the pysummon project.

Everything lives under PYSUMMON_DATA_PREFIX (default 'pysummon/') so the
project can run in parallel with the gleaner pipeline without touching its
prefixes. Promotion to primary = set PYSUMMON_DATA_PREFIX="" (and stop the
old pipeline's schedule); every path below then matches the legacy layout.
"""
import os

DATA_PREFIX = os.environ.get("PYSUMMON_DATA_PREFIX", "pysummon/")
if DATA_PREFIX and not DATA_PREFIX.endswith("/"):
    DATA_PREFIX += "/"

SUMMONED_PATH = f"{DATA_PREFIX}summoned"
METADATA_PATH = f"{DATA_PREFIX}metadata"
ENHANCED_PATH = f"{DATA_PREFIX}enhanced"
REPORTS_PATH = f"{DATA_PREFIX}reports"
RELEASE_PATH = f"{DATA_PREFIX}graphs/latest"
TENANTS_PATH = f"{DATA_PREFIX}tenants"

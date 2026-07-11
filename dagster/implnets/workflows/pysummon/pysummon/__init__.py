# pysummon — Python-native summoner as a standalone Dagster project.
#
# Runs in parallel with the gleaner-based pipeline project (own code
# location, own asset prefix/partitions, own S3 root PYSUMMON_DATA_PREFIX).
# Pure harvest logic lives in pysummon.summon; enhancement/report/release
# logic is shared with the pipeline package (pipeline.jsonld_utils,
# pipeline.steps, pipeline.reporting, pipeline.rdf_utils).
#
# Dagster Definitions: pysummon.definitions

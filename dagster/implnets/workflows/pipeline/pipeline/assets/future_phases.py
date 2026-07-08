# Designed-but-not-yet-implemented phases. These assets exist in the graph
# (visible in the Dagster UI with their design docstrings) but are excluded
# from the weekly job and fail fast if materialized.
#
# Phase 2.2 — keyword/vocabulary linking
# Phase 5   — spatial + vocabulary enrichment
# Phase 6   — community load files and corpus-wide reports
import os
from typing import Any

from dagster import asset, Failure, AssetKey, AssetDep, AllPartitionMapping

from .sources import sources_partitions_def, PREFIX

PROJECT = os.environ.get('PROJECT')


@asset(group_name="phase2_vocab", key_prefix=PREFIX,
       deps=[AssetKey([PREFIX, "source_report"])],
       partitions_def=sources_partitions_def)
def keyword_vocab_map(context) -> Any:
    """Phase 2.2 (planned): link keyword terms to wikidata / community
    vocabularies.

    Design: read reports/{source}/keyword_counts.csv (terms are already split
    into lists by phase 2.1), reconcile each unique term against wikidata
    (SPARQL label search or the OpenRefine reconciliation API) and community
    vocabularies, write vocab/{source}/keywords.csv mapping
    term -> vocabulary IRI -> match confidence. A later enhancement step can
    then rewrite keywords as DefinedTerm nodes with the matched IRIs.

    Per-source source columns (wikidata, scholia, ROR, re3data) already exist
    in geocodes docs/data_loading/configuration/template/sources_custom.csv
    as seed identifiers.
    """
    raise Failure("phase 2.2 keyword_vocab_map is not implemented yet")


@asset(group_name="phase5_enrich", key_prefix=PREFIX,
       deps=[AssetKey([PREFIX, "release_nquads"])],
       partitions_def=sources_partitions_def)
def spatial_enhance(context) -> Any:
    """Phase 5 (planned): enhance released RDF with spatial attributes and
    additional vocabulary links.

    Design: derive GeoSPARQL geometries from schema:spatialCoverage (see
    qleverflow/queries/facetsearch/spatial_construct.rq and
    spatial_insert_point_w_graph.rq for the target shapes), write a
    graphs/latest/{source}_spatial.nq companion file that the Qleverfile
    picks up alongside the release.
    """
    raise Failure("phase 5 spatial_enhance is not implemented yet")


@asset(group_name="phase6_publish", key_prefix=PREFIX,
       deps=[AssetDep(AssetKey([PREFIX, "release_nquads"]),
                      partition_mapping=AllPartitionMapping())])
def community_load_files(context) -> Any:
    """Phase 6 (planned): generate load files / queries for communities.

    Design: for each tenant in tenant.yaml, emit the subset of release files
    its sources list selects — a per-community Qleverfile (SOURCES list +
    GET_DATA_CMD) or a SPARQL LOAD script for other triplestores — plus
    corpus-wide reports run against Qlever using the named queries in
    qleverflow/queries/facetsearch (all_count_keywords.rq,
    all_count_datasets.rq, all_summary_query.rq).
    """
    raise Failure("phase 6 community_load_files is not implemented yet")

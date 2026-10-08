"""The two asset checks on loadstatsHistory."""

import pandas as pd

from workflows.tasks.tasks.assets.source_stats import (
    STAT_HISTORY_OBJECT,
    _csv_data_row_count,
    _non_zero_length_check_result,
)


class _FakeS3:
    GLEANERIO_MINIO_BUCKET = "test"

    def __init__(self, size=None, raises=False):
        self.size = size
        self.raises = raises
        self.s3 = self

    def get_client(self):
        return self

    def head_object(self, Bucket, Key):
        if self.raises:
            raise RuntimeError("NoSuchKey")
        return {"ContentLength": self.size}


def test_the_object_key_is_where_putReportFile_writes():
    assert STAT_HISTORY_OBJECT == "reports/all/latest/all_stats.csv"


def test_an_empty_frame_has_no_data_rows():
    """pandas writes an empty frame as "\\n", which line counting scores as 1."""
    assert _csv_data_row_count(pd.DataFrame([]).to_csv()) == 0


def test_blank_input_has_no_data_rows():
    assert _csv_data_row_count("") == 0
    assert _csv_data_row_count("\n") == 0
    assert _csv_data_row_count(None) == 0


def test_a_header_only_csv_has_no_data_rows():
    assert _csv_data_row_count("source,sitemap,date\n") == 0


def test_data_rows_are_counted():
    csv_text = pd.DataFrame([
        {"source": "iris", "summoned_count": 3},
        {"source": "bcodmo", "summoned_count": 4},
    ]).to_csv()

    assert _csv_data_row_count(csv_text) == 2


def test_a_zero_length_object_fails_the_check():
    result = _non_zero_length_check_result(_FakeS3(size=0), STAT_HISTORY_OBJECT)

    assert result.passed is False
    assert result.metadata["size_bytes"].value == 0


def test_a_populated_object_passes_the_check():
    result = _non_zero_length_check_result(_FakeS3(size=1024), STAT_HISTORY_OBJECT)

    assert result.passed is True
    assert result.metadata["size_bytes"].value == 1024
    assert result.metadata["object_name"].value == STAT_HISTORY_OBJECT


def test_a_missing_object_fails_the_check():
    result = _non_zero_length_check_result(_FakeS3(raises=True), STAT_HISTORY_OBJECT)

    assert result.passed is False
    assert "size_bytes" not in result.metadata

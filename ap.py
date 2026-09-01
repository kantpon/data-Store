"""Offline tests for the current Google Sheet batch writer in app.py.

No Google Sheet or Cloudinary data is touched. The production implementations
of ``_http_status_code``, ``_is_retryable_error`` and ``log_batch_to_sheet`` are
extracted from app.py's AST and run against a thread-safe in-memory worksheet.
"""

from __future__ import annotations

import ast
import re
import threading
import time as real_time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace


APP_PATH = Path(__file__).with_name("app.py")


class FastTime:
    """Keep retries fast while preserving production cooldown calculations."""

    @staticmethod
    def sleep(_seconds):
        return None

    @staticmethod
    def monotonic():
        return real_time.monotonic()


class FakeAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.response = SimpleNamespace(status_code=status_code)


def _column_index(column_letters: str) -> int:
    result = 0
    for character in column_letters:
        result = (result * 26) + ord(character) - ord("A") + 1
    return result - 1


class MemoryWorksheet:
    """Thread-safe gspread Worksheet stand-in with request fault injection."""

    def __init__(
        self,
        row_count=120,
        fail_read_at=None,
        fail_write_at=None,
        fail_read_from=None,
        fail_write_from=None,
    ):
        self.row_count = row_count
        self.rows = [[
            "วันที่เวลา", "ผู้กรอก", "สาขา", "Zone", "สถานะ", "เหตุผล",
            "ชื่อไฟล์", "ลิงก์รูป", "", "", "", "", "", "", "SyncQueue",
        ]]
        self.reads = 0
        self.writes = 0
        self.add_rows_calls = 0
        self.batch_get_calls = 0
        self.batch_update_calls = 0
        self.fail_read_at = set(fail_read_at or [])
        self.fail_write_at = set(fail_write_at or [])
        self.fail_read_from = fail_read_from
        self.fail_write_from = fail_write_from
        self._lock = threading.RLock()

    def _read_request(self):
        self.reads += 1
        if self.reads in self.fail_read_at or (
            self.fail_read_from is not None and self.reads >= self.fail_read_from
        ):
            raise FakeAPIError(429, "Quota exceeded: mock read quota")

    def _write_request(self):
        self.writes += 1
        if self.writes in self.fail_write_at or (
            self.fail_write_from is not None and self.writes >= self.fail_write_from
        ):
            raise FakeAPIError(429, "Quota exceeded: mock write quota")

    def _ensure_rows(self, count):
        while len(self.rows) < count:
            self.rows.append([""] * 15)

    @staticmethod
    def _trim_row(row):
        trimmed = list(row)
        while trimmed and trimmed[-1] == "":
            trimmed.pop()
        return trimmed

    @staticmethod
    def _parse_write_range(range_name):
        match = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", range_name)
        if not match:
            raise AssertionError(f"Unsupported mock write range: {range_name}")
        start_col, start_row, end_col, end_row = match.groups()
        return (
            _column_index(start_col), int(start_row),
            _column_index(end_col or start_col), int(end_row or start_row),
        )

    def _read_range_without_request(self, range_name):
        match = re.fullmatch(r"([A-Z]+):([A-Z]+)", range_name)
        if not match:
            raise AssertionError(f"Unsupported mock read range: {range_name}")
        left, right = (_column_index(value) for value in match.groups())
        last_nonempty = 0
        for row_number, row in enumerate(self.rows, start=1):
            if any(row[left:right + 1]):
                last_nonempty = row_number
        return [
            self._trim_row(row[left:right + 1])
            for row in self.rows[:last_nonempty]
        ]

    def batch_get(self, ranges):
        with self._lock:
            self._read_request()
            self.batch_get_calls += 1
            return [self._read_range_without_request(item) for item in ranges]

    def add_rows(self, count):
        with self._lock:
            self._write_request()
            self.add_rows_calls += 1
            self.row_count += int(count)

    def batch_update(self, updates, value_input_option=None):
        del value_input_option
        with self._lock:
            # Model a single atomic values.batchUpdate request: an injected
            # 429 occurs before any cell is changed.
            self._write_request()
            self.batch_update_calls += 1
            parsed_updates = []
            for update in updates:
                left, start_row, right, end_row = self._parse_write_range(update["range"])
                values = update["values"]
                if end_row > self.row_count:
                    raise FakeAPIError(400, "Range exceeds grid limits")
                assert end_row - start_row + 1 == len(values)
                assert all(len(row) == right - left + 1 for row in values)
                parsed_updates.append((left, start_row, right, end_row, values))
            for left, start_row, right, end_row, values in parsed_updates:
                self._ensure_rows(end_row)
                for row_number, incoming in zip(range(start_row, end_row + 1), values):
                    self.rows[row_number - 1][left:right + 1] = list(incoming)
            return {"totalUpdatedRows": sum(len(item[4]) for item in parsed_updates)}

    def seed_record(self, record, url=None, sync_status=""):
        """Insert an existing row without consuming a mock API request."""
        row = list(record) + [""] * 7
        if url is not None:
            row[7] = url
        row[14] = sync_status
        with self._lock:
            self.rows.append(row[:15])

    def data_rows(self):
        with self._lock:
            return [list(row) for row in self.rows[1:] if row[6]]


def load_app_functions(sheet):
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(APP_PATH))
    wanted = {"_http_status_code", "_is_retryable_error", "log_batch_to_sheet"}
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    found = {node.name for node in selected}
    assert found == wanted, f"Missing production functions: {sorted(wanted - found)}"
    namespace = {
        "threading": threading,
        "time": FastTime,
        "SHEET_WRITE_SEMAPHORE": threading.Semaphore(1),
        "SHEET_COOLDOWN_STATE": {"until": 0.0},
        "SHEET_BATCH_TIMES": [],
        "SHEET_RATE_WINDOW_SECONDS": 60,
        "MAX_SHEET_BATCHES_PER_MINUTE": 18,
        "setup_gsheet": lambda: sheet,
    }
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(APP_PATH), "exec"),
        namespace,
    )
    return SimpleNamespace(
        http_status_code=namespace["_http_status_code"],
        is_retryable_error=namespace["_is_retryable_error"],
        write_batch=namespace["log_batch_to_sheet"],
        cooldown=namespace["SHEET_COOLDOWN_STATE"],
        batch_times=namespace["SHEET_BATCH_TIMES"],
        max_batches=namespace["MAX_SHEET_BATCHES_PER_MINUTE"],
    )


def make_records(user_number, photo_count=6):
    return [[
        "01/09/2026 10:00:00", f"user-{user_number}", f"branch-{user_number}",
        "zone-test", "ครบ", "-", f"user-{user_number}-photo-{photo_number}.jpg",
        f"https://mock.invalid/user-{user_number}-photo-{photo_number}.jpg",
    ] for photo_number in range(1, photo_count + 1)]


def flatten_records(batches):
    return [record for _user_number, records in batches for record in records]


def verify_sheet(sheet, expected_records):
    actual_rows = sheet.data_rows()
    actual_by_filename = {}
    for row in actual_rows:
        filename = row[6]
        assert filename not in actual_by_filename, f"Duplicate row for {filename}"
        actual_by_filename[filename] = row
    expected_by_filename = {record[6]: record for record in expected_records}
    assert len(expected_by_filename) == len(expected_records), "Test data has duplicate UUIDs"
    assert set(actual_by_filename) == set(expected_by_filename), (
        f"Missing={sorted(set(expected_by_filename) - set(actual_by_filename))}; "
        f"unexpected={sorted(set(actual_by_filename) - set(expected_by_filename))}"
    )
    for filename, expected in expected_by_filename.items():
        actual = actual_by_filename[filename]
        assert actual[:8] == expected, f"A:H mismatch for {filename}: {actual[:8]!r}"
        assert actual[14] == "DONE", f"O is not DONE for {filename}"


def submit_concurrently(app, batches):
    if not batches:
        return []
    with ThreadPoolExecutor(max_workers=len(batches)) as pool:
        futures = [
            (user_number, records, pool.submit(app.write_batch, records))
            for user_number, records in batches
        ]
    return [
        (user_number, records, *future.result())
        for user_number, records, future in futures
    ]


def stats(sheet, results):
    return {
        "successes": sum(1 for _user, _records, ok, _error in results if ok),
        "failures": sum(1 for _user, _records, ok, _error in results if not ok),
        "sheet_rows": len(sheet.data_rows()),
        "done_rows": sum(1 for row in sheet.data_rows() if row[14] == "DONE"),
        "reads": sheet.reads,
        "writes": sheet.writes,
        "add_rows_calls": sheet.add_rows_calls,
    }


def test_happy_concurrency(users):
    sheet = MemoryWorksheet(row_count=120)
    app = load_app_functions(sheet)
    batches = [(user, make_records(user)) for user in range(1, users + 1)]
    results = submit_concurrently(app, batches)
    expected_first_successes = min(users, app.max_batches)
    assert sum(1 for _user, _records, ok, _error in results if ok) == expected_first_successes
    failed_batches = [
        (user, records) for user, records, ok, _error in results if not ok
    ]
    retry_results = []
    if failed_batches:
        # Model the next one-minute rate window used by Pending Sync.
        app.batch_times.clear()
        retry_results = submit_concurrently(app, failed_batches)
        assert all(ok for _user, _records, ok, _error in retry_results)
    verify_sheet(sheet, flatten_records(batches))
    result = stats(sheet, results + retry_results)
    result["first_wave_successes"] = expected_first_successes
    result["queued_then_recovered"] = len(failed_batches)
    return result


def test_concurrent_429_recovery(users, *, read_at=None, write_at=None):
    sheet = MemoryWorksheet(
        row_count=120,
        fail_read_at={read_at} if read_at else None,
        fail_write_at={write_at} if write_at else None,
    )
    app = load_app_functions(sheet)
    batches = [(user, make_records(user)) for user in range(1, users + 1)]
    first_results = submit_concurrently(app, batches)
    failed_batches = [
        (user, records) for user, records, ok, _error in first_results if not ok
    ]
    assert failed_batches, "Injected 429 did not produce a reported failure"
    assert any(
        "429" in error or "Quota exceeded" in error
        for _user, _records, ok, error in first_results if not ok
    )
    # Simulate successive quota windows. A write-side 429 can put nearly the
    # whole first wave into Pending, so recovery may legitimately need more
    # than one 18-batch window.
    retry_results = []
    pending = failed_batches
    while pending:
        app.cooldown["until"] = 0.0
        app.batch_times.clear()
        window_results = submit_concurrently(app, pending)
        retry_results.extend(window_results)
        next_pending = [
            (user, records)
            for user, records, ok, _error in window_results
            if not ok
        ]
        assert len(next_pending) < len(pending), "Pending recovery made no progress"
        pending = next_pending
    verify_sheet(sheet, flatten_records(batches))
    combined = first_results + retry_results
    result = stats(sheet, combined)
    result["first_wave_failures"] = len(failed_batches)
    result["retry_successes"] = sum(
        1 for _user, _records, ok, _error in retry_results if ok
    )
    return result


def test_429_after_commit_is_idempotent():
    sheet = MemoryWorksheet(row_count=120, fail_read_at={2})
    app = load_app_functions(sheet)
    records = make_records(1)
    first_ok, first_error = app.write_batch(records)
    assert not first_ok and ("429" in first_error or "Quota exceeded" in first_error)
    assert len(sheet.data_rows()) == 6, "Write should have committed before verify read failed"
    writes_after_commit = sheet.writes
    app.cooldown["until"] = 0.0
    retry_ok, retry_error = app.write_batch(records)
    assert retry_ok, retry_error
    assert sheet.writes == writes_after_commit, "Retry rewrote an already committed batch"
    verify_sheet(sheet, records)
    return {
        "first_result": "429 after commit", "retry_result": "success",
        "sheet_rows": len(sheet.data_rows()), "writes": sheet.writes,
    }


def test_exact_duplicate_is_noop():
    sheet = MemoryWorksheet(row_count=120)
    app = load_app_functions(sheet)
    records = make_records(1)
    first_ok, first_error = app.write_batch(records)
    assert first_ok, first_error
    writes_after_first = sheet.writes
    second_ok, second_error = app.write_batch(records)
    assert second_ok, second_error
    assert sheet.writes == writes_after_first
    verify_sheet(sheet, records)
    return {"sheet_rows": len(sheet.data_rows()), "writes": sheet.writes}


def test_repair_existing_url_and_done():
    sheet = MemoryWorksheet(row_count=120)
    records = make_records(1, photo_count=1)
    sheet.seed_record(records[0], url="", sync_status="")
    app = load_app_functions(sheet)
    ok, error = app.write_batch(records)
    assert ok, error
    verify_sheet(sheet, records)
    assert len(sheet.data_rows()) == 1, "Repair created a duplicate row"
    assert sheet.batch_update_calls == 1, "H and O repair should use one batch update"
    return {
        "sheet_rows": len(sheet.data_rows()), "repaired_H": sheet.data_rows()[0][7],
        "repaired_O": sheet.data_rows()[0][14], "writes": sheet.writes,
    }


def test_conflicting_duplicate_is_rejected():
    sheet = MemoryWorksheet(row_count=120)
    original = make_records(1, photo_count=1)
    sheet.seed_record(original[0], url=original[0][7], sync_status="DONE")
    conflicting = [list(original[0])]
    conflicting[0][2] = "different-branch"
    app = load_app_functions(sheet)
    ok, error = app.write_batch(conflicting)
    assert not ok
    assert "ไม่ตรง" in error
    verify_sheet(sheet, original)
    return {"result": "rejected", "error": error}


def test_error_classification():
    sheet = MemoryWorksheet()
    app = load_app_functions(sheet)
    Timeout = type("Timeout", (Exception,), {})
    assert app.http_status_code(FakeAPIError(429, "mock")) == 429
    assert app.is_retryable_error(FakeAPIError(429, "mock"))
    assert app.is_retryable_error(FakeAPIError(503, "mock"))
    assert app.is_retryable_error(Timeout("mock"))
    assert not app.is_retryable_error(FakeAPIError(403, "mock"))
    assert not app.is_retryable_error(RuntimeError("mock"))
    return {"429": "retryable", "503": "retryable", "403": "not retryable"}


def run_all_tests():
    cases = [
        ("happy_5_users_x6", lambda: test_happy_concurrency(5)),
        ("happy_20_users_x6", lambda: test_happy_concurrency(20)),
        ("happy_30_users_x6", lambda: test_happy_concurrency(30)),
        ("read_429_20_users_x6_then_recover", lambda: test_concurrent_429_recovery(20, read_at=11)),
        ("write_429_30_users_x6_then_recover", lambda: test_concurrent_429_recovery(30, write_at=5)),
        ("verify_read_429_after_commit", test_429_after_commit_is_idempotent),
        ("exact_duplicate_noop", test_exact_duplicate_is_noop),
        ("repair_existing_H_and_O", test_repair_existing_url_and_done),
        ("conflicting_duplicate_rejected", test_conflicting_duplicate_is_rejected),
        ("error_classification", test_error_classification),
    ]
    failures = []
    for name, test in cases:
        try:
            detail = test()
            print(f"PASS {name}: {detail}")
        except Exception as error:
            failures.append((name, error))
            print(f"FAIL {name}: {type(error).__name__}: {error}")
    if failures:
        raise SystemExit(f"{len(failures)} test(s) failed")
    print(f"ALL PASS: {len(cases)} scenarios")


if __name__ == "__main__":
    run_all_tests()

"""
test_logging_setup.py
Bloque 3: verifies the raw loguru API behaves as the design assumes
before any forti4d code depends on it.

Important distinction confirmed empirically here (this is the whole point
of this smoke test running before the 18-file migration):
  - logger.enable(name)/disable(name) key off the REAL __name__ of the
    module where the log call textually happens (frame inspection) — it
    cannot be faked via logger.patch(). Verified here using this test
    module's own real name ("tests...").
  - logger.add(sink, filter=name) DOES filter on record["name"], which
    logger.patch() can set — so it's fakeable/testable in isolation. This
    is what configure_logging()'s sinks rely on ("forti4d" real module
    names will match filter="forti4d" without any faking needed).
"""

from __future__ import annotations

from loguru import logger

from forti4d.lib import logging_setup


def test_loguru_level_filtering():
    """A sink's level= filters out lower-severity records."""
    buf = []
    sink_id = logger.add(buf.append, level="INFO", format="{level}|{message}")
    try:
        logger.debug("should NOT appear (sink level=INFO)")
        logger.info("should appear")
        assert len(buf) == 1
        assert "should appear" in buf[0]
    finally:
        logger.remove(sink_id)


def test_loguru_add_filter_by_name():
    """logger.add(sink, filter=name) matches record["name"] (patchable),
    unlike enable()/disable() which need a real module context."""
    buf = []
    sink_id = logger.add(buf.append, level="DEBUG", filter="forti4d", format="{name}|{message}")
    try:
        fake = logger.patch(lambda r: r.update(name="forti4d.analyzers.inventory"))
        fake.info("from forti4d namespace")
        logger.info("from this test module, should be filtered out")
        assert len(buf) == 1
        assert "forti4d.analyzers.inventory" in buf[0]
    finally:
        logger.remove(sink_id)


def test_loguru_enable_disable_keys_off_real_module_name():
    """
    enable()/disable() cannot be faked with patch() — confirmed here using
    this test module's own real __name__ instead of a fake "forti4d" one
    (tests/ has no __init__.py, so pytest imports this file as a top-level
    module — its real __name__ is whatever that is, hence using __name__
    directly rather than hardcoding a guess). Full end-to-end verification
    with real forti4d modules happens in Fase 1 (once configure_logging()
    and forti4d/__init__.py's logger.disable("forti4d") exist).
    """
    buf = []
    sink_id = logger.add(buf.append, level="INFO", format="{message}")
    try:
        logger.disable(__name__)
        logger.info("should be suppressed")
        assert buf == []

        logger.enable(__name__)
        logger.info("should appear")
        assert len(buf) == 1
    finally:
        logger.remove(sink_id)
        logger.enable(__name__)  # restore default (enabled) state for other tests


def test_configure_logging_is_idempotent(tmp_path):
    """Calling configure_logging() more than once (e.g. across tests in
    the same process) must not accumulate duplicate sinks."""
    try:
        logging_setup.configure_logging(tmp_path)
        first_count = len(logging_setup._added_sink_ids)
        logging_setup.configure_logging(tmp_path)
        second_count = len(logging_setup._added_sink_ids)
        assert first_count == second_count == 2
    finally:
        logging_setup._clear_previous_sinks()
        logger.disable("forti4d")


def test_configure_logging_console_info_file_debug(tmp_path, capsys):
    """Console sink: INFO+ by default. File sink: always DEBUG+, regardless
    of console level."""
    try:
        log_path = logging_setup.configure_logging(tmp_path, quiet=False)
        fake = logger.patch(lambda r: r.update(name="forti4d.smoketest"))
        fake.debug("debug message")
        fake.info("info message")
        logger.complete()  # file sink uses enqueue=True (async) — wait for the write to land

        captured = capsys.readouterr()
        assert "info message" in captured.err
        assert "debug message" not in captured.err  # console level=INFO filters DEBUG out

        content = log_path.read_text(encoding="utf-8")
        assert "debug message" in content
        assert "info message" in content
    finally:
        logging_setup._clear_previous_sinks()
        logger.disable("forti4d")


def test_configure_logging_quiet_raises_console_to_warning(tmp_path, capsys):
    """--quiet's new meaning: console only shows WARNING+, but the file
    sink is unaffected — still gets everything."""
    try:
        log_path = logging_setup.configure_logging(tmp_path, quiet=True)
        fake = logger.patch(lambda r: r.update(name="forti4d.smoketest"))
        fake.info("info message")
        fake.warning("warning message")
        logger.complete()  # file sink uses enqueue=True (async) — wait for the write to land

        captured = capsys.readouterr()
        assert "info message" not in captured.err
        assert "warning message" in captured.err

        content = log_path.read_text(encoding="utf-8")
        assert "info message" in content  # file always gets DEBUG+, quiet doesn't affect it
        assert "warning message" in content
    finally:
        logging_setup._clear_previous_sinks()
        logger.disable("forti4d")


def test_configure_logging_no_log_file(tmp_path):
    """log_file=False skips the file sink entirely."""
    try:
        log_path = logging_setup.configure_logging(tmp_path, log_file=False)
        assert log_path is None
        assert not (tmp_path / logging_setup.DEFAULT_LOG_FILENAME).exists()
    finally:
        logging_setup._clear_previous_sinks()
        logger.disable("forti4d")

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from b12.desktop.workers import ApiJob


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_api_job_runs_the_operation_outside_the_gui_thread(qapp):
    main_thread = threading.get_ident()
    operation_finished = threading.Event()
    result_received = []
    job = ApiJob(
        "probe",
        lambda: (threading.get_ident(), operation_finished.set())[0],
    )
    job.signals.result.connect(lambda tag, result: result_received.append((tag, result)))
    QThreadPool.globalInstance().start(job)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not result_received:
        qapp.processEvents()
        time.sleep(0.01)
    assert operation_finished.is_set()
    assert result_received and result_received[0][0] == "probe"
    assert result_received[0][1] != main_thread

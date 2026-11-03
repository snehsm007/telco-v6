

import pytest as _pytest_mock_reset


@_pytest_mock_reset.fixture(autouse=True)
def _reset_mock_mode_marker():
    """Each tool call sets the PRD §17 mock marker from its session; tests start with it off."""
    from lib.replies import set_mock_mode_active

    set_mock_mode_active(False)
    yield
    set_mock_mode_active(False)

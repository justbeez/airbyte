#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#
from __future__ import annotations

from typing import Iterable

import pytest


pytest_plugins = ("connector_acceptance_test.plugin",)


@pytest.fixture(scope="session", autouse=True)
def connector_setup() -> Iterable[None]:
    """This fixture is a placeholder for external resources that acceptance test might require."""
    return

"""Property-based regression: slugify is idempotent and produces only
safe characters across a wide input space."""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from decisionlab.tools.reports import slugify

_SAFE = re.compile(r"^([a-z0-9]+(-[a-z0-9]+)*)?$")


@given(st.text(max_size=200))
@settings(max_examples=300)
def test_slugify_idempotent_property(raw):
    once = slugify(raw)
    assert slugify(once) == once


@given(st.text(max_size=200))
@settings(max_examples=300)
def test_slugify_output_is_safe(raw):
    s = slugify(raw)
    assert _SAFE.fullmatch(s) is not None, f"unsafe slug: {s!r} from {raw!r}"

from simlab.utils import strip_markdown_fences


def test_strip_json_fence():
    assert strip_markdown_fences('```json\n{"key": "value"}\n```') == '{"key": "value"}'


def test_strip_plain_fence():
    assert strip_markdown_fences('```\n{"key": "value"}\n```') == '{"key": "value"}'


def test_no_fence_passthrough():
    assert strip_markdown_fences('{"key": "value"}') == '{"key": "value"}'


def test_strip_with_whitespace():
    assert strip_markdown_fences('  \n```json\n{"a": 1}\n```\n  ') == '{"a": 1}'


def test_text_before_fence():
    text = 'Here is the result:\n\n```json\n{"a": 1}\n```'
    assert strip_markdown_fences(text) == '{"a": 1}'


def test_text_before_and_after_fence():
    text = 'Blah blah\n```json\n{"a": 1}\n```\nMore text'
    assert strip_markdown_fences(text) == '{"a": 1}'


def test_raw_json_with_surrounding_text():
    text = 'Here is the JSON:\n\n{"key": "value"}\n\nDone.'
    assert strip_markdown_fences(text) == '{"key": "value"}'

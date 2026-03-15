from simlab.utils import strip_markdown_fences

def test_strip_json_fence():
    assert strip_markdown_fences('```json\n{"key": "value"}\n```') == '{"key": "value"}'

def test_strip_plain_fence():
    assert strip_markdown_fences('```\n{"key": "value"}\n```') == '{"key": "value"}'

def test_no_fence_passthrough():
    assert strip_markdown_fences('{"key": "value"}') == '{"key": "value"}'

def test_strip_with_whitespace():
    assert strip_markdown_fences('  \n```json\n{"a": 1}\n```\n  ') == '{"a": 1}'

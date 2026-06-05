import agrex
import pytest

from decisionlab.runtime import agrex_context
from decisionlab.runtime import usage as usage_module


class FakeUsage:
    input_tokens = 1000
    output_tokens = 100
    cache_creation_input_tokens = 50
    cache_read_input_tokens = 200


def test_record_usage_attaches_tokens_and_cost_to_agrex_parent():
    tracer = agrex.create_tracer()
    tokens = agrex_context.bind(tracer, emit=None)
    parent_token = agrex_context.set_parent("researcher")
    try:
        tracer.agent("researcher", "Researcher")
        usage_module.record("anthropic/claude-sonnet-4.6", FakeUsage())
    finally:
        agrex_context.reset_parent(parent_token)
        agrex_context.reset(tokens)
        usage_module.reset()

    update = tracer.events()[-1]
    assert update["type"] == "node_update"
    assert update["id"] == "researcher"
    metadata = update["metadata"]
    assert metadata["tokens"] == 1350
    assert metadata["llm_calls"] == 1
    assert metadata["input_tokens"] == 1000
    assert metadata["output_tokens"] == 100
    assert metadata["cache_creation_input_tokens"] == 50
    assert metadata["cache_read_input_tokens"] == 200
    assert metadata["last_model"] == "anthropic/claude-sonnet-4.6"
    assert metadata["cost"] == pytest.approx(0.00471)
    assert metadata["models"]["anthropic/claude-sonnet-4.6"]["calls"] == 1

# tests/test_smoke.py
def test_package_imports():
    import decisionlab
    from decisionlab import cli
    from decisionlab.agents import researcher
    from decisionlab.agents import deep_researcher
    from decisionlab.domain import models, ports
    from decisionlab.adapters import mock
    from decisionlab.runtime import dispatcher, loop
    from decisionlab.tools import search, agents


def test_cli_app_exists():
    from decisionlab.cli import app
    assert app is not None


def test_model_protocol_imports():
    from decisionlab.models.protocol import DecisionModel, Action, Perception


def test_denis_example_imports():
    from denis.homeostatic import HomeostaticModel
    from denis.hedonic import HedonicModel
    from denis.integrated import IntegratedModel, IntegrationMode

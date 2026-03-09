# tests/test_smoke.py
def test_package_imports():
    import decisionlab
    from decisionlab import cli
    from decisionlab.agents import researcher, reasoner, builder
    from decisionlab.tools import web_search, semantic_scholar, file_io, code_runner


def test_cli_app_exists():
    from decisionlab.cli import app
    assert app is not None


def test_model_protocol_imports():
    from decisionlab.models.protocol import DecisionModel, Action, Perception


def test_denis_example_imports():
    from denis.homeostatic import HomeostaticModel
    from denis.hedonic import HedonicModel
    from denis.integrated import IntegratedModel, IntegrationMode

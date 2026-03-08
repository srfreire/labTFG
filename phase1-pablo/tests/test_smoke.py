def test_package_imports():
    import decisionlab
    from decisionlab import cli
    from decisionlab.agents import researcher, reasoner, builder
    from decisionlab.tools import web_search, semantic_scholar, file_io, code_runner


def test_cli_app_exists():
    from decisionlab.cli import app
    assert app is not None

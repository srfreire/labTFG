"""Runtime-loaded data files shipped with the decisionlab package.

Files in this package are accessed via ``importlib.resources.files()``.
The ``uv_build`` backend (configured in ``pyproject.toml``) ships every
non-Python file under the module root with the wheel by default, so no
explicit ``package-data`` declaration is needed.
"""

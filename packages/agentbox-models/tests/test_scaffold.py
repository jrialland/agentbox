import agentbox_models


def test_package_imports():
    assert hasattr(agentbox_models, "__version__")

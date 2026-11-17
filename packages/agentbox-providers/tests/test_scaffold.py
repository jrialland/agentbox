import agentbox_providers


def test_package_imports():
    assert hasattr(agentbox_providers, "__version__")

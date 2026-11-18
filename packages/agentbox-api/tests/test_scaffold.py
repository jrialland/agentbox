import agentbox_api


def test_package_imports():
    assert hasattr(agentbox_api, "__version__")

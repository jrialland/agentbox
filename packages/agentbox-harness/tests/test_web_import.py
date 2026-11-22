import subprocess
import sys


def test_web_module_import_has_socks_support():
    code = (
        "import warnings; "
        "from urllib3.exceptions import DependencyWarning; "
        "warnings.simplefilter('error', DependencyWarning); "
        "import agentbox_harness.tools.web"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

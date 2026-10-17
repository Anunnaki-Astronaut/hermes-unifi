"""Public release contracts; no live service or screenshot binaries required."""
import json

import pytest

from conftest import ROOT


def test_public_readme():
    text = (ROOT / 'README.md').read_text()
    assert 'hermes://plugin/install?repo=Anunnaki-Astronaut/hermes-unifi&enable=1' in text
    for view in ('overview', 'sites', 'devices', 'isp'):
        assert f'(docs/screenshots/{view}.png)' in text
        image = (ROOT / f'docs/screenshots/{view}.png').read_bytes()
        assert image[:8] == b'\x89PNG\r\n\x1a\n'
        assert int.from_bytes(image[16:20], 'big') == 1440
        assert int.from_bytes(image[20:24], 'big') == 900
    for term in ('read-only', 'Current limits', 'not a troubleshooting assistant',
                 'cannot change the network', 'no agent tool', 'made-up data',
                 'do not show a real network', 'presentation-only row numbers',
                 'not device/site/host identities', 'correlate data across refreshes',
                 'Undefined units remain unlabeled rather than guessed',
                 'https://developer.ui.com/site-manager-api/gettingstarted',
                 'https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API'):
        assert term in text
    assert 'unifi-openapi.json' not in text


@pytest.mark.parametrize('path,terms', [
    ('SECURITY.md', ('private vulnerability reporting', 'public issues', 'read-only',
                     'fixed', 'GET', 'ssl.create_default_context()', 'fail closed',
                     '5 MiB', 'Retry-After', 'Desktop JavaScript', 'PRIVACY.md',
                     'presentation-only row numbers', 'correlate data across refreshes')),
    ('PRIVACY.md', ('sites', 'devices', '5-minute ISP', 'Clients', 'MAC/IP',
                    'stable identifiers', 'trace IDs', 'history', 'arbitrary fields',
                    'free-text', 'presentation-only row numbers', 'not device/site/host identities',
                    'correlate data across refreshes', 'persistence', 'telemetry', 'analytics',
                    'exports', 'third-party services', 'screenshots, issues, and logs',
                    'Desktop JavaScript', 'UNIFI_API_KEY')),
    ('CONTRIBUTING.md', ('read-only', 'fixed-origin', 'synthetic-only', 'credentials',
                         'full pytest', 'Plugin Doctor', 'write controls or agent tools',
                         'separate design and security approval')),
    ('docs/INSTALL.md', ('Desktop', 'Command-line', 'remote backend', 'Settings → API Keys',
                        'masked', 'read-only', 'fixed', 'GET', 'First-run verification',
                        'hermes plugins update unifi', 'hermes plugins remove unifi')),
])
def test_public_boundary_docs(path, terms):
    text = (ROOT / path).read_text()
    for term in terms:
        assert term in text, (path, term)


def test_release_version_and_license():
    # Runtime health and actual request User-Agent are covered in the API/client tests.
    assert json.loads((ROOT / 'dashboard/manifest.json').read_text())['version'] == '0.1.0'
    assert 'version: 0.1.0\n' in (ROOT / 'plugin.yaml').read_text()
    assert 'Hermes UniFi contributors' in (ROOT / 'LICENSE').read_text()
    changelog = (ROOT / 'CHANGELOG.md').read_text()
    assert [line for line in changelog.splitlines() if line.startswith('## ')] == ['## 0.1.0 - 2026-10-16']


def test_secret_scan_safety_contract():
    text = (ROOT / '.github/workflows/secret-scan.yml').read_text()
    for term in ('  push:', '  pull_request:', '  schedule:', '  workflow_dispatch:',
                 'permissions:\n  contents: read', 'fetch-depth: 0',
                 'actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683',
                 'trufflesecurity/trufflehog@b84c3d14d189e16da175e2c27fa8136603783ffc',
                 'version: v3.90.12', 'extra_args: --no-verification --results=verified,unknown'):
        assert term in text
    assert 'secrets.' not in text
    assert ': write' not in text

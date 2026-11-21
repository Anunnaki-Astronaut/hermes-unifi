"""Public release contracts; no live service or screenshot binaries required."""
import json

import pytest

from conftest import ROOT


def test_public_readme():
    text = (ROOT / 'README.md').read_text()
    assert 'hermes://plugin/install?repo=Anunnaki-Astronaut/hermes-unifi&enable=1' in text
    for view in ('overview', 'diagnostics', 'sites', 'devices', 'isp', 'clients'):
        assert f'(docs/screenshots/{view}.png)' in text
        image = (ROOT / f'docs/screenshots/{view}.png').read_bytes()
        assert image[:8] == b'\x89PNG\r\n\x1a\n'
        assert int.from_bytes(image[16:20], 'big') == 1440
        assert int.from_bytes(image[20:24], 'big') == (1200 if view == 'diagnostics' else 900)
    assert 'diagnostics' in text.lower() and '1440×1200' in text
    for term in ('read-only', 'Current limits', 'troubleshooting assistant', 'plain English',
                 'cannot change the network', 'Agent tools', 'read-only tools', 'no speed test',
                 'never simply disabled', 'MAC addresses', 'made-up data',
                 'do not show a real network', 'presentation-only row numbers',
                 'not device/site/host identities', 'correlate data across refreshes',
                 'Undefined units remain unlabeled rather than guessed',
                 'https://developer.ui.com/site-manager-api/gettingstarted',
                 'https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API'):
        assert term in text
    assert 'unifi-openapi.json' not in text


@pytest.mark.parametrize('path,terms', [
    ('SECURITY.md', ('private vulnerability reporting', 'public issues', 'read-only',
                     'fixed', 'GET', 'ssl.create_default_context()', 'fail closed', 'fails closed',
                     '5 MiB', 'Retry-After', 'Desktop JavaScript', 'PRIVACY.md',
                     'presentation-only row numbers', 'correlate data across refreshes',
                     'certificate_mismatch', 'certificate_untrusted', 'SHA-256', 'replaced (not skipped)',
                     'RFC 1918', 'UNIFI_NETWORK_API_KEY', 'Agent tools are read-only',
                     'dry-run preview, explicit in-chat confirmation, and before/after snapshots')),
    ('PRIVACY.md', ('sites', 'devices', '5-minute ISP', 'Clients', 'MAC/IP', 'MAC addresses',
                    'stable identifiers', 'trace IDs', 'history', 'arbitrary fields',
                    'free-text', 'presentation-only row numbers', 'not device/site/host identities',
                    'correlate data across refreshes', 'persistence', 'telemetry', 'analytics',
                    'exports', 'third-party services', 'screenshots, issues, and logs',
                    'Desktop JavaScript', 'UNIFI_API_KEY', 'UNIFI_NETWORK_API_KEY', 'Show IP addresses',
                    'agent tool output', '30-second in-memory console snapshot')),
    ('CONTRIBUTING.md', ('read-only', 'fixed-origin', 'synthetic-only', 'credentials',
                         'full pytest', 'Plugin Doctor', 'write controls or agent tools',
                         'separate design and security approval', 'never disabled', 'never raise',
                         'plain English')),
    ('docs/INSTALL.md', ('Desktop', 'Command-line', 'remote backend', 'Settings → API Keys',
                        'masked', 'read-only', 'fixed', 'GET', 'First-run verification',
                        'hermes plugins update unifi', 'hermes plugins remove unifi',
                        'UniFi Network → Integrations', 'UNIFI_NETWORK_API_KEY', 'SHA-256',
                        'certificate_untrusted', 'unifi_status', 'MAC addresses are never shown')),
])
def test_public_boundary_docs(path, terms):
    text = (ROOT / path).read_text()
    for term in terms:
        assert term in text, (path, term)


def test_release_version_and_license():
    # Runtime health and actual request User-Agent are covered in the API/client tests.
    assert json.loads((ROOT / 'dashboard/manifest.json').read_text())['version'] == '0.3.0'
    assert 'version: 0.3.0\n' in (ROOT / 'plugin.yaml').read_text()
    assert 'Hermes UniFi contributors' in (ROOT / 'LICENSE').read_text()
    changelog = (ROOT / 'CHANGELOG.md').read_text()
    assert [line for line in changelog.splitlines() if line.startswith('## ')] == [
        '## Unreleased', '## 0.3.0 - 2026-11-20', '## 0.1.0 - 2026-10-16'
    ]

    for term in ('UNIFI_NETWORK_API_KEY', 'unifi_status', 'unifi_diagnose', 'unifi_devices', 'unifi_clients',
                 'still cannot change the network', 'SHA-256 certificate pin'):
        assert term in changelog


def test_secret_scan_safety_contract():
    text = (ROOT / '.github/workflows/secret-scan.yml').read_text()
    for term in ('  push:', '  pull_request:', '  schedule:', '  workflow_dispatch:',
                 'permissions:\n  contents: read', 'fetch-depth: 0',
                 'actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683',
                 'trufflesecurity/trufflehog@b84c3d14d189e16da175e2c27fa8136603783ffc',
                 'version: 3.90.12', 'extra_args: --no-verification --results=verified,unknown'):
        assert term in text
    assert 'secrets.' not in text
    assert ': write' not in text

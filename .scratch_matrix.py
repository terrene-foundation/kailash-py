"""Scratch probe: (preset x vendor) credential-scrub coverage matrix.

NOT COMMITTED. Vectors are synthetic and assembled at runtime.

DISCRIMINATION (instrument-discipline MUST-1): the falsifying result is the
opposite column value. A vendor whose key IS claimed prints `redacted`; one
whose key survives verbatim prints `LEAK`. The probe is shown to discriminate
by the fact that known-anchored vendors (sk-, AIza, pplx-, hf_, fw_) print
`redacted` on every preset while others do not -- i.e. it does not print one
verdict indiscriminately.
"""

import itertools
import string
import sys

from kaizen.utils.credential_scrub import (
    scrub_credentials,
    scrub_local_error,
    scrub_remote_error,
)

print("resolved from:", scrub_credentials.__module__, file=sys.stderr)
import kaizen.utils.credential_scrub as _m

print("file:", _m.__file__, file=sys.stderr)


def _run(alphabet: str, n: int) -> str:
    """Deterministic synthetic run of `n` chars over `alphabet`."""
    return "".join(itertools.islice(itertools.cycle(alphabet), n))


_MIX = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
_HEX = "a1b2c3d4e5f6"
_LOWER = string.ascii_lowercase + string.digits

# (vendor, shape-label, key). Shapes derived from published provider docs;
# every VALUE is synthetic.
VECTORS = [
    ("openai", "sk- +48", "sk-" + _run(_MIX, 48)),
    ("openai", "sk-proj- +48", "sk-proj-" + _run(_MIX, 48)),
    ("anthropic", "sk-ant-api03- +95", "sk-ant-api03-" + _run(_MIX, 95)),
    ("google", "AIza +35", "AIza" + _run(_MIX, 35)),
    ("cohere", "40 alnum", _run(_MIX, 40)),
    ("cohere", "41 w/ hyphen", _run(_MIX, 20) + "-" + _run(_MIX, 20)),
    ("mistral", "32 alnum", _run(_MIX, 32)),
    ("mistral", "32 hex", _run(_HEX, 32)),
    ("perplexity", "pplx- +48", "pplx-" + _run(_MIX, 48)),
    ("huggingface", "hf_ +34", "hf_" + _run(_MIX, 34)),
    ("groq", "gsk_ +52", "gsk_" + _run(_MIX, 52)),
    ("groq", "gsk_ +36", "gsk_" + _run(_MIX, 36)),
    ("together", "64 hex", _run(_HEX, 64)),
    ("together", "tgp_v1_ +43", "tgp_v1_" + _run(_MIX, 43)),
    ("fireworks", "fw_ +24", "fw_" + _run(_MIX, 24)),
    ("openrouter", "sk-or-v1- +64hex", "sk-or-v1-" + _run(_HEX, 64)),
    ("deepseek", "sk- +32hex", "sk-" + _run(_HEX, 32)),
]

PRESETS = [
    ("P1 conservative (scrub_local_error)", lambda s: scrub_local_error(s)),
    ("P2 remote (scrub_remote_error)", lambda s: scrub_remote_error(s)),
    (
        "P3 aggressive (scrub_credentials defaults)",
        lambda s: scrub_credentials(s),
    ),
    (
        "P4 paths-on/opaque-off (direct call)",
        lambda s: scrub_credentials(s, redact_paths=True, redact_opaque_tokens=False),
    ),
]

CARRIER = "401 unauthorized: invalid api key {k}"

hdr = f"{'vendor':<12} {'shape':<18}" + "".join(f" {n[:3]:>10}" for n, _ in PRESETS)
print(hdr)
print("-" * len(hdr))
leaks = []
for vendor, label, key in VECTORS:
    row = f"{vendor:<12} {label:<18}"
    for pname, fn in PRESETS:
        out = fn(CARRIER.format(k=key))
        ok = key not in out
        row += f" {'redacted' if ok else 'LEAK':>10}"
        if not ok:
            leaks.append((vendor, label, pname))
    print(row)

print()
print(f"TOTAL LEAK CELLS: {len(leaks)} / {len(VECTORS) * len(PRESETS)}")

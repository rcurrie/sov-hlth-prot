"""Bring the Synthea engine into the project.

We use the prebuilt **fat-jar** (`synthea-with-dependencies.jar`) rather than a
source build. The jar is Java-17 bytecode and runs on any JRE >= 17 (including
brand-new JDKs whose version Gradle doesn't yet support). Synthea's resource
loader (`Utilities.readResource(.., allowFreePath=true)`) falls back to the
filesystem when a file isn't on the classpath, so our El-Salvador geography /
providers / payers — none of which are bundled in the jar — load straight from
the run directory. No source checkout, no Gradle, no JDK-version coupling.
"""
from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import config

JAR_URL = (
    "https://github.com/synthetichealth/synthea/releases/latest/download/"
    "synthea-with-dependencies.jar"
)
JAR_PATH = config.VENDOR_DIR / "synthea-with-dependencies.jar"

JAVA_HINT = (
    "Java (JRE/JDK 17+) is required to run Synthea but was not found.\n"
    "Install one, e.g.:\n"
    "  macOS (Homebrew):  brew install openjdk\n"
    "Then re-run the generate step (it auto-discovers Homebrew's keg-only JDK)."
)

# Locations to probe for a real JDK beyond PATH (macOS keg-only Homebrew openjdk
# is not symlinked into PATH and is invisible to /usr/libexec/java_home).
_JDK_CANDIDATE_HOMES = [
    "/opt/homebrew/opt/openjdk",
    "/usr/local/opt/openjdk",
    "/Library/Java/JavaVirtualMachines",  # contains */Contents/Home
]


def _is_real_java(exe: str) -> str | None:
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    text = out.stderr or out.stdout
    # macOS ships a /usr/bin/java stub that exits non-zero with no JRE; a real
    # `java -version` always mentions "version". Require both.
    if out.returncode != 0 or "version" not in text.lower():
        return None
    return text.splitlines()[0].strip()


def find_java_home() -> str | None:
    """Locate a real JDK home, probing PATH then common keg-only locations."""
    on_path = shutil.which("java")
    if on_path and _is_real_java(on_path):
        return str(Path(on_path).resolve().parent.parent)
    for base in _JDK_CANDIDATE_HOMES:
        b = Path(base)
        if (b / "bin" / "java").exists() and _is_real_java(str(b / "bin" / "java")):
            return str(b)
        for home in sorted(b.glob("*/Contents/Home"), reverse=True):
            if (home / "bin" / "java").exists() and _is_real_java(str(home / "bin" / "java")):
                return str(home)
    return None


def java_env() -> dict | None:
    """Return an env dict with JAVA_HOME + PATH set for a discovered JDK, or None."""
    import os

    home = find_java_home()
    if not home:
        return None
    env = dict(os.environ)
    env["JAVA_HOME"] = home
    env["PATH"] = f"{home}/bin:" + env.get("PATH", "")
    return env


def check_java() -> str | None:
    """Return the java version string (probing keg-only locations), else None."""
    home = find_java_home()
    if not home:
        return None
    return _is_real_java(f"{home}/bin/java")


def download_jar(force: bool = False) -> Path:
    """Download the Synthea fat-jar into vendor/ (idempotent)."""
    config.ensure_dirs()
    if JAR_PATH.exists() and not force:
        return JAR_PATH
    tmp = JAR_PATH.with_suffix(".jar.part")
    urllib.request.urlretrieve(JAR_URL, tmp)
    tmp.replace(JAR_PATH)
    return JAR_PATH


def status() -> dict:
    jar = JAR_PATH.exists()
    return {
        "java": check_java(),
        "java_home": find_java_home(),
        "synthea_jar": str(JAR_PATH) if jar else None,
        "synthea_jar_present": jar,
    }

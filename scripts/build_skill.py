"""Write the coach's Claude Skill to skills/intervals-coach/ and zip it for upload.

The skill text is rendered from the playbook, the methodology and the routine
index, so it is rebuilt whenever those change. Run with `make skill`.

    --check   exit non-zero if the committed files are stale; write nothing
    --no-zip  write the folder only

The zip lands in build/intervals-coach.zip with the folder at its root, which
is the shape Claude's "upload skill" expects.
"""

import argparse
import sys
import zipfile
from pathlib import Path

from intervals_icu_mcp.prompts.skill import SKILL_NAME, render_skill

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / SKILL_NAME
ZIP_PATH = ROOT / "build" / f"{SKILL_NAME}.zip"


def stale_files() -> list[str]:
    """Relative paths whose committed content differs from the rendered skill."""
    stale: list[str] = []
    for rel, content in render_skill().items():
        path = SKILL_DIR / rel
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            stale.append(rel)
    return stale


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()

    if args.check:
        stale = stale_files()
        if stale:
            print(f"Stale skill files (run `make skill`): {', '.join(stale)}", file=sys.stderr)
            return 1
        print("Skill is up to date.")
        return 0

    files = render_skill()
    for rel, content in files.items():
        path = SKILL_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} files to {SKILL_DIR.relative_to(ROOT)}/")

    if not args.no_zip:
        ZIP_PATH.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
            for rel in files:
                archive.write(SKILL_DIR / rel, f"{SKILL_NAME}/{rel}")
        print(f"Zipped to {ZIP_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

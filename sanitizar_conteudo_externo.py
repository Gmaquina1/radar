from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


AWS_ACCESS_KEY_ID = re.compile(
    r"(?<![A-Z0-9])(?:AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}(?![A-Z0-9])"
)
REPLACEMENT = "[CHAVE_EXTERNA_REMOVIDA]"
TEXT_EXTENSIONS = {
    ".csv",
    ".html",
    ".json",
    ".log",
    ".md",
    ".py",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def sanitize_text(value: str) -> tuple[str, int]:
    return AWS_ACCESS_KEY_ID.subn(REPLACEMENT, value)


def repository_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return [root / path for path in paths if path]


def sanitize_repository(root: Path) -> dict[str, int]:
    changed: dict[str, int] = {}
    for path in repository_files(root):
        if path.suffix.casefold() not in TEXT_EXTENSIONS or not path.is_file():
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        sanitized, replacements = sanitize_text(original)
        if not replacements:
            continue
        path.write_text(sanitized, encoding="utf-8")
        changed[str(path.relative_to(root))] = replacements
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mascara padrões de credenciais encontrados em conteúdo externo."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    changed = sanitize_repository(args.root.resolve())
    print(f"Arquivos sanitizados: {len(changed)}")
    print(f"Padrões mascarados: {sum(changed.values())}")
    for path, count in sorted(changed.items()):
        print(f"- {path}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

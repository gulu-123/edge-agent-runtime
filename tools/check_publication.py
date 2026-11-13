"""Check the exact tracked publication set without printing any secret value."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {'.github', 'adapters_ws', 'config', 'docs', 'scripts', 'tests', 'tools'}
FILES = {'.gitignore', '.gitattributes', 'README.md', 'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md'}
FORBIDDEN_PARTS = {'build', 'install', 'log', 'logs', 'runs', 'cache', 'local', 'vm-tools', '__pycache__'}
PATTERNS = [
    re.compile(r'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'(?<![\d.])(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?![\d.])'),
    re.compile(r'[A-Z]:[\\/]Users[\\/][^\s]+'),
]


def main():
    try:
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True)
        paths = [ROOT / path for path in result.stdout.decode().split('\0') if path]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = [path for path in ROOT.rglob('*') if path.is_file() and
                 (path.relative_to(ROOT).parts[0] in DIRECTORIES or str(path.relative_to(ROOT)) in FILES) and
                 not set(path.relative_to(ROOT).parts) & FORBIDDEN_PARTS]
    if not paths:
        raise SystemExit('No publication files found')
    problems = []
    for path in paths:
        relative = path.relative_to(ROOT)
        if relative.parts[0] not in DIRECTORIES and str(relative) not in FILES:
            problems.append((relative, 'unexpected publication path'))
            continue
        if set(relative.parts) & FORBIDDEN_PARTS or '.local.' in path.name:
            problems.append((relative, 'generated/private path'))
            continue
        if path.stat().st_size > 256 * 1024:
            problems.append((relative, 'oversized file'))
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeError:
            problems.append((relative, 'non-text file'))
            continue
        if any(pattern.search(text) for pattern in PATTERNS):
            problems.append((relative, 'credential or machine-specific content'))
    if problems:
        for path, reason in problems:
            print(f'FAIL {path}: {reason}', file=sys.stderr)
        raise SystemExit(1)
    print(f'PUBLICATION_CHECK_PASS: {len(paths)} text files')


if __name__ == '__main__':
    main()

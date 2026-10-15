#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fail when text carries an AI authorship or attribution statement.

Used by the pull-request check (.github/workflows/no-ai-attribution.yml) and the local
commit-msg hook (scripts/git-hooks/commit-msg), so both apply the same patterns. The
procedure it enforces is in docs/CONTRIBUTION_PROCEDURES.md.

Usage:
    python scripts/check_ai_attribution.py [--label NAME] [FILE ...]

Each FILE (or standard input when none is given) is scanned. The label names the text in the
report (for example a commit SHA or "pull request title"). Exit status is 1 when any pattern
matches, otherwise 0.
"""
from __future__ import annotations

import argparse
import re
import sys

_AI_TOOLS = r'(?:claude|anthropic|copilot|chatgpt|openai|codex|gemini|cursor)'

PATTERNS = (
    ('generated-with line', re.compile(r'generated\s+(?:with|by)\s+\[?\s*' + _AI_TOOLS, re.I)),
    ('co-author trailer naming an AI tool', re.compile(r'^\s*co-authored-by:.*' + _AI_TOOLS, re.I | re.M)),
    ('AI tool noreply address', re.compile(r'noreply@anthropic\.com', re.I)),
    ('AI tool link', re.compile(r'claude\.com/claude-code', re.I)),
    ('robot emoji', re.compile('\U0001F916')),
)


def find_attributions(text: str) -> list[str]:
    """
    Return the name of every attribution pattern found in the text.

    :param text: Text to scan, such as a commit message or a pull-request body.
    :return: Names of the matching patterns, empty when the text is clean.
    """
    return [name for name, pattern in PATTERNS if pattern.search(text)]


def main(argv: list[str] | None = None) -> int:
    """
    Scan the named files, or standard input, and report any attribution found.

    :param argv: Command-line arguments; defaults to ``sys.argv[1:]``.
    :return: 1 when any text carries an attribution, otherwise 0.
    """
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('files', nargs='*', help='files to scan; standard input when omitted')
    parser.add_argument('--label', help='name for the text in the report (default: the file name)')
    args = parser.parse_args(argv)

    if args.files:
        sources = []
        for path in args.files:
            with open(path, encoding='utf-8', errors='replace') as handle:
                sources.append((args.label or path, handle.read()))
    else:
        sources = [(args.label or 'standard input', sys.stdin.buffer.read().decode('utf-8', errors='replace'))]

    failed = False
    for label, text in sources:
        for name in find_attributions(text):
            print(f'{label}: {name}', file=sys.stderr)
            failed = True
    if failed:
        print('AI authorship or attribution statements are not allowed in commit messages, pull-request '
              'titles, or pull-request descriptions (docs/CONTRIBUTION_PROCEDURES.md). Remove them.',
              file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

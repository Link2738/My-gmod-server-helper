"""
FastDL pre-flight checks.

Source engine's download system rejects files whose paths contain characters
that are invalid in HTTP URLs or the engine's VFS:
  - Spaces
  - Parentheses  ( )
  - Plus sign    +
  - Hash         #
  - Percent      %  (would confuse URL decoding)
  - Ampersand    &
  - Any non-ASCII byte

Valid characters: a-z A-Z 0-9  _  -  .  /  (and the OS path separator)
"""

import os
import re

# Characters allowed in a FastDL path component.
# Anything outside this set will be rejected by the engine.
_VALID_RE = re.compile(r'^[a-zA-Z0-9_\-./\\]+$')

# Extensions that should never appear in a FastDL content directory.
_JUNK_EXTENSIONS = {'.gma', '.bin', '.zip', '.rar', '.7z', '.tar', '.gz'}


def scan_invalid_paths(folder, log_callback=None):
    """
    Walk *folder* and flag files whose relative paths contain characters
    that FastDL / the Source engine will refuse to serve.

    Returns a list of (relative_path, reason) tuples.
    """
    bad = []

    for root, _dirs, files in os.walk(folder):
        for fname in files:
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, folder).replace('\\', '/')

            # Check for junk file types first
            ext = os.path.splitext(fname)[1].lower()
            if ext in _JUNK_EXTENSIONS:
                reason = f'file type {ext} should not be in FastDL content'
                bad.append((rel, reason))
                if log_callback:
                    log_callback(f'[PATH] {rel}: {reason}')
                continue

            if not _VALID_RE.match(rel):
                # Find the specific offending characters
                bad_chars = sorted({c for c in rel if not re.match(r'[a-zA-Z0-9_\-./\\]', c)})
                readable = ', '.join(repr(c) for c in bad_chars)
                reason = f'invalid character(s) {readable} — FastDL will refuse this path'
                bad.append((rel, reason))
                if log_callback:
                    log_callback(f'[PATH] {rel}: {reason}')

    return bad


def preflight(folder, log_callback=None):
    """
    Run all FastDL checks on *folder*:
      1. Invalid path characters
      2. VMT structural errors (EOF, brace mismatch, null bytes)

    Returns a dict:
        {
            'path_issues':  [(rel_path, reason), ...],
            'vmt_total':    int,
            'vmt_bad':      { rel_path: [issue, ...] },
        }
    """
    from vmt_validator import scan_vmts

    if log_callback:
        log_callback('[PRE-FLIGHT] Checking file paths...')
    path_issues = scan_invalid_paths(folder, log_callback)

    if log_callback:
        log_callback('[PRE-FLIGHT] Checking VMT files...')
    vmt_total, vmt_bad = scan_vmts(folder, log_callback)

    return {
        'path_issues': path_issues,
        'vmt_total':   vmt_total,
        'vmt_bad':     vmt_bad,
    }

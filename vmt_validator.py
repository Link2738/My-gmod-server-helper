"""
VMT sanity checker and auto-fixer.

Catches common issues that make FastDL / Source engine reject material files:
  - Empty or unreadable files
  - Null bytes (binary corruption / incomplete download)
  - Unbalanced curly braces
  - File truncated before the final closing brace

Auto-fixable: truncation (missing closing braces), null bytes.
Not fixable:  unexpected extra '}'  — structure is genuinely corrupted.
"""

import os


def _parse(path):
    """
    Read and decode a VMT file.
    Returns (text, encoding, null_stripped) or raises on failure.
    """
    raw = open(path, 'rb').read()
    null_stripped = False
    if b'\x00' in raw:
        raw = raw.replace(b'\x00', b'')
        null_stripped = True
    for enc in ('utf-8', 'latin-1'):
        try:
            return raw.decode(enc), enc, null_stripped
        except UnicodeDecodeError:
            continue
    raise ValueError('cannot decode as text')


def _brace_depth(text):
    """
    Return (final_depth, went_negative) after scanning comment-stripped lines.
    went_negative means an unexpected '}' was found — not safely auto-fixable.
    """
    depth = 0
    went_negative = False
    for line in text.splitlines():
        for ch in line.split('//')[0]:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth < 0:
                    went_negative = True
                    depth = 0
    return depth, went_negative


def check_vmt(path):
    """
    Return a list of issue strings for one .vmt file.
    Empty list means the file looks clean.
    """
    issues = []

    try:
        raw = open(path, 'rb').read()
    except OSError as e:
        return [f'cannot read: {e}']

    if not raw:
        return ['empty file']

    if b'\x00' in raw:
        issues.append('null bytes (binary corruption or incomplete download)')
        raw = raw.replace(b'\x00', b'')

    try:
        text, _, _ = _parse(path)
    except ValueError as e:
        issues.append(str(e))
        return issues

    depth, went_negative = _brace_depth(text)

    if went_negative:
        issues.append('unexpected closing brace — structure corrupted (cannot auto-fix)')
    if depth > 0:
        issues.append(f'unclosed brace(s) — {depth} never closed (truncated at EOF)')

    clean = '\n'.join(l.split('//')[0] for l in text.splitlines()).rstrip()
    if clean and clean[-1] != '}' and not went_negative and depth == 0:
        issues.append('file does not end with }} — likely truncated at EOF')

    return issues


def fix_vmt(path):
    """
    Attempt to repair a single .vmt file in-place.

    Returns (fixed: bool, description: str).
    fixed=True  → file was modified and saved.
    fixed=False → either no fix needed, or the file is too corrupted to fix safely.
    """
    try:
        raw = open(path, 'rb').read()
    except OSError as e:
        return False, f'cannot read: {e}'

    if not raw:
        return False, 'empty file — skipped'

    null_stripped = b'\x00' in raw
    if null_stripped:
        raw = raw.replace(b'\x00', b'')

    encoding = None
    text = None
    for enc in ('utf-8', 'latin-1'):
        try:
            text = raw.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        return False, 'cannot decode — skipped'

    depth, went_negative = _brace_depth(text)

    if went_negative:
        return False, 'unexpected }} — structure too corrupted to auto-fix'

    changes = []

    if null_stripped:
        changes.append('stripped null bytes')

    if depth > 0:
        text = text.rstrip('\r\n') + ('\n}' * depth) + '\n'
        changes.append(f'appended {depth} closing brace(s)')
    else:
        # Check trailing-content case (braces balanced but file doesn't end with })
        clean = '\n'.join(l.split('//')[0] for l in text.splitlines()).rstrip()
        if clean and clean[-1] != '}':
            # Braces are balanced, file just has trailing garbage — nothing safe to do
            return False, 'trailing content after last }} — manual review needed'

    if not changes:
        return False, 'no fix needed'

    try:
        with open(path, 'w', encoding=encoding, newline='\n') as f:
            f.write(text)
    except OSError as e:
        return False, f'write failed: {e}'

    return True, ', '.join(changes)


def scan_vmts(folder, log_callback=None):
    """
    Recursively scan *folder* for .vmt files and run check_vmt on each.

    Returns (total_checked, bad_files) where bad_files is a dict:
        { relative_path: [issue, ...] }
    """
    bad = {}
    total = 0

    for root, _dirs, files in os.walk(folder):
        for fname in files:
            if not fname.lower().endswith('.vmt'):
                continue
            total += 1
            path = os.path.join(root, fname)
            file_issues = check_vmt(path)
            if file_issues:
                rel = os.path.relpath(path, folder)
                bad[rel] = file_issues
                if log_callback:
                    for issue in file_issues:
                        log_callback(f'[VMT] {rel}: {issue}')

    return total, bad


def fix_vmts(folder, bad_files, log_callback=None):
    """
    Attempt to fix all files listed in *bad_files* (output of scan_vmts).

    Returns (fixed_count, skipped_count).
    """
    fixed = 0
    skipped = 0

    for rel in bad_files:
        path = os.path.join(folder, rel)
        ok, desc = fix_vmt(path)
        if ok:
            fixed += 1
            if log_callback:
                log_callback(f'[VMT FIX] {rel}: {desc}')
        else:
            skipped += 1
            if log_callback:
                log_callback(f'[VMT SKIP] {rel}: {desc}')

    return fixed, skipped

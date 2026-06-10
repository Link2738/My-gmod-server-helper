"""
QC file parsing logic for $bodygroup, $texturegroup, and $cdmaterials extraction.
"""

import os
import re
from collections import defaultdict


def deduplicate_qc_animations(qc_path, log_callback=None):
    """
    Remove duplicate $animation/$sequence blocks, keeping the one with the
    most lines (most data). Ties go to the later occurrence.
    Returns True if any duplicates were removed.
    """
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return False

    _directive_re = re.compile(
        r'^\s*(\$animation|\$sequence)\s+"([^"]+)"', re.IGNORECASE
    )

    blocks = []
    i = 0
    depth = 0

    while i < len(lines):
        line = lines[i]
        m = _directive_re.match(line)
        if m and depth == 0:
            dtype = m.group(1).lower()
            dname = m.group(2)
            start = i
            block_depth = line.count('{') - line.count('}')
            j = i + 1
            while j < len(lines) and block_depth > 0:
                block_depth += lines[j].count('{') - lines[j].count('}')
                j += 1
            blocks.append({'type': dtype, 'name': dname, 'start': start, 'end': j})
            i = j
            continue
        depth += line.count('{') - line.count('}')
        i += 1

    groups = defaultdict(list)
    for b in blocks:
        groups[(b['type'], b['name'].lower())].append(b)

    to_remove = []
    for group in groups.values():
        if len(group) <= 1:
            continue
        best = max(group, key=lambda b: (b['end'] - b['start'], b['start']))
        for dup in group:
            if dup is not best:
                if log_callback:
                    log_callback(
                        f'[QC DEDUP] Removing duplicate {dup["type"]} "{dup["name"]}" '
                        f'(lines {dup["start"]+1}–{dup["end"]}, '
                        f'keeping lines {best["start"]+1}–{best["end"]})'
                    )
                to_remove.append((dup['start'], dup['end']))

    if not to_remove:
        return False

    remove_ranges = sorted(to_remove)
    out = []
    ri = 0
    for idx, line in enumerate(lines):
        while ri < len(remove_ranges) and remove_ranges[ri][1] <= idx:
            ri += 1
        if ri < len(remove_ranges) and remove_ranges[ri][0] <= idx < remove_ranges[ri][1]:
            continue
        out.append(line)

    try:
        with open(qc_path, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(out)
        return True
    except OSError:
        return False


def balance_qc_braces(qc_path, log_callback=None):
    """
    Repair a QC whose brace blocks are unbalanced by appending the missing
    closing brace(s) at EOF.

    Crowbar sometimes truncates the closing '}' of the trailing $keyvalues
    block, which makes studiomdl fail with
    "Keyvalue block missing matching braces." Braces inside // and /* */
    comments and inside double-quoted strings are ignored.

    Only acts when there are more '{' than '}' (the truncation case); does
    nothing if balanced or if there are extra closers. Returns True if the
    file was modified.
    """
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return False

    depth = 0
    in_string = in_line_comment = in_block_comment = False
    i, n = 0, len(content)
    while i < n:
        c = content[i]
        nxt = content[i + 1] if i + 1 < n else ''
        if in_line_comment:
            if c == '\n':
                in_line_comment = False
        elif in_block_comment:
            if c == '*' and nxt == '/':
                in_block_comment = False
                i += 1
        elif in_string:
            if c == '"':
                in_string = False
        elif c == '/' and nxt == '/':
            in_line_comment = True
            i += 1
        elif c == '/' and nxt == '*':
            in_block_comment = True
            i += 1
        elif c == '"':
            in_string = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1

    if depth <= 0:
        return False  # balanced, or has extra closers — don't guess

    addition = ('' if content.endswith('\n') else '\n') + '}\n' * depth
    try:
        with open(qc_path, 'a', encoding='utf-8', newline='') as f:
            f.write(addition)
    except OSError:
        return False
    if log_callback:
        log_callback(f'[QC FIX] Added {depth} missing closing brace(s) to '
                     f'{os.path.basename(qc_path)}')
    return True


def rewrite_qc_cdmaterials(qc_path, cdmat_map):
    """Rewrite $cdmaterials paths using cdmat_map {old_path: new_path}."""
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return False
    out = []
    for line in lines:
        m = re.match(r'^(\s*\$cdmaterials\s+")([^"]+)(")', line, re.IGNORECASE)
        if m:
            raw = m.group(2).strip().rstrip('/\\').replace('\\', '/')
            if raw in cdmat_map:
                line = m.group(1) + cdmat_map[raw] + '/' + m.group(3) + '\n'
        out.append(line)
    try:
        with open(qc_path, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(out)
        return True
    except OSError:
        return False


def rewrite_qc_modelname(qc_path, new_modelname):
    """Replace the $modelname value in a QC file with new_modelname."""
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return False
    out = []
    for line in lines:
        m = re.match(r'^(\s*\$modelname\s+")([^"]+)(")', line, re.IGNORECASE)
        if not m:
            m2 = re.match(r'^(\s*\$modelname\s+)(\S+)', line, re.IGNORECASE)
            if m2:
                line = m2.group(1) + '"' + new_modelname + '"\n'
        else:
            line = m.group(1) + new_modelname + m.group(3) + '\n'
        out.append(line)
    try:
        with open(qc_path, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(out)
        return True
    except OSError:
        return False


def parse_qc_cdmaterials(qc_path):
    """
    Return a list of $cdmaterials path strings from *qc_path*.
    e.g. ['character/', 'shared/']
    """
    paths = []
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                m = re.match(r'^\s*\$cdmaterials\s+"?([^"\n]+)"?', line, re.IGNORECASE)
                if m:
                    paths.append(m.group(1).strip().replace('\\', '/'))
    except OSError:
        pass
    return paths


def rewrite_qc_texturegroup(qc_path, name_map):
    """
    Replace bad material names inside $texturegroup blocks using *name_map*.
    Writes the result back to the same file. Returns True on success.
    """
    if not name_map:
        return True
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return False

    in_tg = False
    depth = 0
    lines = content.splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith('$texturegroup'):
            in_tg = True
            depth = stripped.count('{') - stripped.count('}')
            out.append(line)
            continue
        if in_tg:
            depth += stripped.count('{') - stripped.count('}')
            # Replace any quoted bad name inside the block
            def _replace(m):
                name = m.group(1)
                return f'"{name_map.get(name, name)}"'
            line = re.sub(r'"([^"]+)"', _replace, line)
            if depth <= 0:
                in_tg = False
        out.append(line)

    try:
        with open(qc_path, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(out)
        return True
    except OSError:
        return False

def parse_qc_skins(qc_path):
    """
    Parse $texturegroup blocks from a QC file and return the skin count.

    Each row inside a $texturegroup block corresponds to one skin.
    Returns the number of skins (0 if no $texturegroup is found, meaning
    the model has only the default skin).
    """
    try:
        with open(qc_path, 'r', encoding='utf-8') as f:
            lines: list[str] = f.readlines()
        skin_count: int = 0
        inside_texturegroup: bool = False
        brace_depth: int = 0
        for line in lines:
            stripped: str = line.strip()
            if stripped.lower().startswith('$texturegroup'):
                inside_texturegroup = True
                brace_depth = 0
                # The opening brace may be on the same line
                if '{' in stripped:
                    brace_depth += stripped.count('{')
                continue
            if inside_texturegroup:
                brace_depth += stripped.count('{') - stripped.count('}')
                # Each inner { ... } row is one skin
                if '{' in stripped and '}' in stripped:
                    skin_count += 1
                if brace_depth <= 0:
                    inside_texturegroup = False
        return skin_count
    except Exception as e:
        msg: str = str(e)
        print(f"Error parsing QC skins: {msg}")
        return 0


def parse_qc_bodygroups(qc_path):
    bodygroups: list[dict[str, any]] = []
    try:
        with open(qc_path, 'r', encoding='utf-8') as f:
            lines: list[str] = f.readlines()
        bg_id: int = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('$bodygroup'):
                parts: list[str] = line.strip().split()
                if len(parts) >= 2:
                    bg_name: str = parts[1]
                    values: list[int] = []
                    j: int = i + 1
                    studio_count: int = 0
                    while j < len(lines):
                        l: str = lines[j].strip()
                        if l.startswith('studio'):
                            values.append(studio_count)
                            studio_count += 1
                        elif l == 'blank':
                            values.append(studio_count)
                            studio_count += 1
                        elif l == '}':
                            break
                        j += 1
                    bodygroups.append({'name': bg_name, 'id': bg_id, 'values': values})
                    bg_id += 1
    except Exception as e:
        msg: str = str(e)
        print(f"Error parsing QC bodygroups: {msg}")
    return bodygroups


def parse_qc_type_signals(qc_path):
    """
    Extract structural signals from a QC file for model-type inference.

    Returns a dict:
      has_valvebiped_bones  bool  — any $definebone references Bip01 / ValveBiped
      has_staticprop        bool  — $staticprop directive present
      has_bbox              bool  — $bbox directive present (players/NPCs)
      has_c_arms_include    bool  — includemodel references c_arms_animations
      sequence_names        list  — lowercase names from $sequence "name" lines
      attachment_names      list  — lowercase names from $attachment "name" lines
      bodygroup_count       int
      sequence_count        int
    """
    signals = {
        'has_valvebiped_bones': False,
        'has_staticprop': False,
        'has_bbox': False,
        'has_c_arms_include': False,
        'has_hboxset': False,
        'has_ikchain': False,
        'has_collisionjoints': False,
        'sequence_names': [],
        'attachment_names': [],
        'bodygroup_count': 0,
        'sequence_count': 0,
    }
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return signals

    lo = content.lower()
    signals['has_staticprop']      = '$staticprop' in lo
    signals['has_bbox']            = '$bbox' in lo
    signals['has_c_arms_include']  = ('c_arms_animations' in lo and '$includemodel' in lo)
    signals['has_hboxset']         = '$hboxset' in lo
    signals['has_ikchain']         = '$ikchain' in lo
    signals['has_collisionjoints'] = '$collisionjoints' in lo
    signals['bodygroup_count']    = lo.count('$bodygroup')
    signals['sequence_count']     = lo.count('$sequence')

    for m in re.finditer(r'^\s*\$definebone\s+"([^"]+)"', content, re.IGNORECASE | re.MULTILINE):
        bone = m.group(1).lower()
        if 'bip01' in bone or 'valvebiped' in bone:
            signals['has_valvebiped_bones'] = True
            break

    for m in re.finditer(r'^\s*\$sequence\s+"([^"]+)"', content, re.IGNORECASE | re.MULTILINE):
        signals['sequence_names'].append(m.group(1).lower())

    for m in re.finditer(r'^\s*\$attachment\s+"([^"]+)"', content, re.IGNORECASE | re.MULTILINE):
        signals['attachment_names'].append(m.group(1).lower())

    return signals


def infer_type_from_qc(signals):
    """
    Infer a Pointshop model type from parsed QC signals.
    Returns 'swep', 'accessory', 'playermodel', or None (inconclusive).
    """
    # Arms: definitive include signal — caller is responsible for excluding these
    if signals['has_c_arms_include']:
        return None

    # SWEP: weapon sequence or attachment names
    _WEAPON_SEQ = {'fire', 'shoot', 'reload', 'draw', 'holster', 'attack1', 'attack2'}
    _WEAPON_ATT = {'muzzle', 'shell', 'eject', '1'}
    if any(n in _WEAPON_SEQ for n in signals['sequence_names']):
        return 'swep'
    if any(n in _WEAPON_ATT for n in signals['attachment_names']):
        return 'swep'

    # Playermodel: exclusive directives ($hboxset/$ikchain/$collisionjoints)
    # combined with ValveBiped bones — accessories never have these
    has_pm_signals = (signals['has_hboxset'] or
                      signals['has_ikchain'] or
                      signals['has_collisionjoints'])
    if has_pm_signals and signals['has_valvebiped_bones']:
        return 'playermodel'

    # Accessory: no ValveBiped bones and no playermodel-exclusive directives
    # ($staticprop models fall here too; accessories may still have $bbox and
    # non-ValveBiped $definebone, so we cannot rely on those signals alone)
    if not signals['has_valvebiped_bones'] and not has_pm_signals:
        return 'accessory'

    return None


# ── Shared classification helpers ─────────────────────────────────────────────

def parse_qc_modelname(qc_path: str) -> str | None:
    """Return the $modelname value from a QC file (forward-slash normalised), or None."""
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                m = re.match(r'^\s*\$modelname\s+"([^"]+)"', line, re.IGNORECASE)
                if m:
                    return m.group(1).replace('\\', '/')
                m2 = re.match(r'^\s*\$modelname\s+(\S+)', line, re.IGNORECASE)
                if m2:
                    return m2.group(1).replace('\\', '/')
    except OSError:
        pass
    return None


def is_arms_stem(stem: str) -> bool:
    """Heuristic pre-filter: does this filename stem look like an arms model?"""
    s = stem.lower()
    return (s in ('arms', 'carms', 'c_arms') or
            s.startswith('c_arms') or
            s.endswith('_arms') or
            s.endswith('arms'))


def is_arms_qc(qc_path: str) -> bool:
    """Authoritative: does this QC file belong to a c_arms model?"""
    return parse_qc_type_signals(qc_path)['has_c_arms_include']


def filter_npc_paths(paths: list) -> list:
    """Remove paths where 'npc' is a directory segment or the filename stem contains '_npc'."""
    result = []
    for p in paths:
        parts = p.replace('\\', '/').lower().split('/')
        stem  = os.path.splitext(parts[-1])[0]
        if 'npc' in parts[:-1] or '_npc' in stem:
            continue
        result.append(p)
    return result

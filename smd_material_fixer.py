"""
SMD material name scanner and rewriter.

Reference/mesh SMDs store material names as bare strings in the triangles
section — one name line followed by 3 vertex lines per face.  This module
finds names with FastDL-invalid characters and rewrites them in-place.
"""

import os
import re

# Characters allowed in a FastDL path
_VALID_RE = re.compile(r'^[a-zA-Z0-9_\-./\\]+$')


def clean_name(name):
    """
    Replace any invalid character with '_', then collapse runs of '_' and
    strip leading/trailing '_'.

    e.g. 'cool face (instance)' → 'cool_face_instance'
         'hemline+'              → 'hemline'
    """
    cleaned = re.sub(r'[^a-zA-Z0-9_\-./\\]', '_', name)
    cleaned = re.sub(r'_+', '_', cleaned)
    return cleaned.strip('_')


def is_mesh_smd(path):
    """Return True if the SMD file contains a 'triangles' section."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.strip().lower() == 'triangles':
                    return True
    except OSError:
        pass
    return False


def parse_smd_materials(path):
    """
    Parse a mesh SMD and return the set of unique material names found in
    the triangles section.

    Material name lines: appear after 'triangles', before 'end'.
    They are the only lines in that section that don't start with a digit
    or whitespace+digit.
    """
    materials = set()
    in_triangles = False
    vertex_count = 0

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                lo = line.lower()
                if lo == 'triangles':
                    in_triangles = True
                    vertex_count = 0
                    continue
                if lo == 'end' and in_triangles:
                    in_triangles = False
                    continue
                if not in_triangles:
                    continue

                # Every 4th line starting from 0 is a material name;
                # the other 3 are vertex lines (start with an integer).
                if vertex_count % 4 == 0:
                    materials.add(line)
                vertex_count += 1
    except OSError:
        pass

    return materials


def bad_names(material_set):
    """Return the subset of material names that contain invalid characters."""
    return {n for n in material_set if not _VALID_RE.match(n)}


def rewrite_smd_materials(path, name_map):
    """
    Rewrite material name lines in the triangles section using *name_map*.
    Writes the result back to the same file.
    Returns True on success.
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return False

    in_triangles = False
    vertex_count = 0
    out = []

    for raw in lines:
        line = raw.strip()
        lo = line.lower()

        if lo == 'triangles':
            in_triangles = True
            vertex_count = 0
            out.append(raw)
            continue

        if lo == 'end' and in_triangles:
            in_triangles = False
            out.append(raw)
            continue

        if in_triangles and vertex_count % 4 == 0 and line in name_map:
            out.append(name_map[line] + '\n')
            vertex_count += 1
            continue

        if in_triangles:
            vertex_count += 1

        out.append(raw)

    try:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(out)
        return True
    except OSError:
        return False


_PHYSICS_SMD_RE = re.compile(r'_phys(ics)?\.smd$', re.IGNORECASE)


def scan_decompiled(crowbar_out_dir):
    """
    Walk all SMD files under *crowbar_out_dir*, collect every material name
    found in mesh SMDs. Physics SMDs (*_physics.smd, *_phys.smd) are skipped
    because their material names are collision placeholders, not render materials.

    Returns (all_names: set, bad_names: set, smd_paths: list, mat_to_smds: dict).
    mat_to_smds maps each material name to the list of SMD basenames that reference it.
    """
    all_names   = set()
    smd_paths   = []
    mat_to_smds = {}

    for root, _dirs, files in os.walk(crowbar_out_dir):
        for fname in files:
            if not fname.lower().endswith('.smd'):
                continue
            if _PHYSICS_SMD_RE.search(fname):
                continue
            path = os.path.join(root, fname)
            if not is_mesh_smd(path):
                continue
            smd_paths.append(path)
            mats = parse_smd_materials(path)
            all_names |= mats
            for m in mats:
                mat_to_smds.setdefault(m, []).append(fname)

    return all_names, bad_names(all_names), smd_paths, mat_to_smds

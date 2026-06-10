"""
FastDL resource.AddFile() generator.

Scans extracted addon content and writes a server-side Lua file that
forces clients to download every model, material, and sound file via
resource.AddFile().

Supported content types:
  models/    .mdl .vvd .vtx .phy .ani
  materials/ .vmt .vtf .png .jpg
  sound/     .wav .mp3 .ogg
  maps/      .bsp
  resource/  .ttf .otf (custom fonts)
"""

import os
import shutil

# File extensions that clients need to download, grouped by content root.
# Keys are the top-level folder name ("models", "materials", etc.).
# Values are sets of lowercase extensions to include.
CONTENT_EXTENSIONS = {
    'models':    {'.mdl', '.vvd', '.vtx', '.phy', '.ani'},
    'materials': {'.vmt', '.vtf', '.png', '.jpg', '.jpeg'},
    'sound':     {'.wav', '.mp3', '.ogg'},
    # maps/.bsp ARE listed via resource.AddFile() so every map in a rotation
    # (e.g. a mapvote) is pre-downloaded — sv_downloadurl alone only serves the
    # currently-running map on demand. The .bsp is copied into fastdl/ as an opaque
    # blob; its packed (pakfile) contents are never unpacked into loose files.
    'maps':      {'.bsp', '.png'},   # .bsp + thumbnails/overviews
    'resource':  {'.ttf', '.otf'},
}

# Flatten for quick lookup (used by scan_content_files → resource.AddFile lua)
_ALL_EXTENSIONS = set()
for exts in CONTENT_EXTENSIONS.values():
    _ALL_EXTENSIONS |= exts

# Extensions that should be copied to fastdl/ even if NOT listed in resource.AddFile()
# .bsp maps are served automatically by GMod via sv_downloadurl — no lua entry needed.
_COPY_ONLY_EXTENSIONS = {'.bsp'}


def scan_content_files(content_root, log_callback=None):
    """
    Walk a directory tree and collect all files that need resource.AddFile().

    Handles both flat structures (models/ directly under content_root) and
    nested structures where addon subdirectories sit between content_root and
    the content folders (e.g. content_root/addon1/models/...).

    Parameters
    ----------
    content_root : str
        Root folder to scan.
    log_callback : callable, optional
        Receives log messages.

    Returns
    -------
    list[str]
        Sorted, deduplicated list of relative paths (forward-slash, lowercase),
        e.g. 'models/player/soldier.mdl', 'maps/gm_flatgrass.bsp'.
    """
    seen = set()
    results = []

    for dirpath, _dirs, filenames in os.walk(content_root):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(full_path, content_root).replace('\\', '/').lower()
            parts = rel.split('/')

            # Find the first path component that matches a known content folder.
            # This handles both flat (models/foo.mdl) and nested
            # (addon_name/models/foo.mdl) structures.
            content_idx = next(
                (i for i, p in enumerate(parts) if p in CONTENT_EXTENSIONS), -1
            )
            if content_idx == -1:
                continue

            _, ext = os.path.splitext(fname.lower())
            if ext not in _ALL_EXTENSIONS:
                continue

            # Canonical path starting from the content folder
            content_rel = '/'.join(parts[content_idx:])
            if content_rel not in seen:
                seen.add(content_rel)
                results.append(content_rel)

    results.sort()

    if log_callback:
        log_callback(f'[RESOURCE] Found {len(results)} content file(s) to add')
        counts = {}
        for r in results:
            folder = r.split('/')[0]
            counts[folder] = counts.get(folder, 0) + 1
        for folder, count in sorted(counts.items()):
            log_callback(f'  {folder}: {count} file(s)')

    return results


def merge_content_into_fastdl(extracted_parent, fastdl_dir, log_callback=None):
    """
    Walk extracted_parent (which contains per-addon subdirectories whose
    internals have the standard content layout) and copy every recognised
    content file into fastdl_dir with a flat content-relative path:

        extracted_parent/addon1/models/player/foo.mdl
        -> fastdl_dir/models/player/foo.mdl

    Existing files are not overwritten (first addon wins for duplicates).

    Returns
    -------
    int
        Number of files copied.
    """
    copied = 0

    for dirpath, _dirs, filenames in os.walk(extracted_parent):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(full_path, extracted_parent).replace('\\', '/').lower()
            parts = rel.split('/')

            content_idx = next(
                (i for i, p in enumerate(parts) if p in CONTENT_EXTENSIONS), -1
            )
            if content_idx == -1:
                continue

            _, ext = os.path.splitext(fname.lower())
            if ext not in _ALL_EXTENSIONS and ext not in _COPY_ONLY_EXTENSIONS:
                continue

            content_rel = '/'.join(parts[content_idx:])
            dst = os.path.join(fastdl_dir, *content_rel.split('/'))
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(full_path, dst)
                copied += 1

    if log_callback:
        log_callback(f'[FASTDL] Merged {copied} file(s) into: {fastdl_dir}')
    return copied


def write_resource_lua(file_list, output_path, addon_name=None, log_callback=None):
    """
    Write a resource.AddFile() Lua file from a list of relative paths.

    Parameters
    ----------
    file_list : list[str]
        Relative paths as returned by scan_content_files().
    output_path : str
        Full path to write the .lua file to.
    addon_name : str, optional
        Name shown in the header comment.
    log_callback : callable, optional
        Receives log messages.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    header_name = addon_name or 'Custom Content'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f'-- FastDL Resource List: {header_name}\n')
        f.write('-- Auto-generated by resource_gen.py\n')
        f.write('-- Place in lua/autorun/server/ to force client downloads.\n\n')
        f.write('if not SERVER then return end\n\n')

        current_section = None
        for rel_path in file_list:
            section = rel_path.split('/')[0]
            if section != current_section:
                if current_section is not None:
                    f.write('\n')
                f.write(f'-- {section}\n')
                current_section = section
            f.write(f'resource.AddFile( "{rel_path}" )\n')

    if log_callback:
        log_callback(f'[RESOURCE] Wrote {len(file_list)} entries → {output_path}')


def generate_resource_file(content_root, output_dir, addon_name=None, log_callback=None):
    """
    High-level: scan content_root for downloadable files and write the
    resource Lua file into output_dir/lua/autorun/server/.

    Parameters
    ----------
    content_root : str
        Extracted content directory to scan.
    output_dir : str
        Root output directory (resource file goes into lua/autorun/server/).
    addon_name : str, optional
        Display name in the file header.
    log_callback : callable, optional
        Receives log messages.

    Returns
    -------
    str or None
        Path to the written file, or None if no content found.
    """
    file_list = scan_content_files(content_root, log_callback)
    if not file_list:
        if log_callback:
            log_callback('[RESOURCE] No content files found — skipping resource file generation.')
        return None

    # Sanitize addon name for filename
    safe_name = (addon_name or 'content').lower()
    safe_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe_name)
    safe_name = safe_name.strip('_') or 'content'

    lua_filename = f'resource_{safe_name}.lua'
    lua_path = os.path.join(output_dir, 'lua', 'autorun', 'server', lua_filename)

    write_resource_lua(file_list, lua_path, addon_name=addon_name, log_callback=log_callback)
    return lua_path

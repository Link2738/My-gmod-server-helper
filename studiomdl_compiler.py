"""
studiomdl.exe wrapper for compiling QC files.
"""

import os
import re
import shutil
import subprocess


_CANDIDATES = [
    # Source SDK Base 2013 Multiplayer (most common for GMod modding)
    'steamapps/common/Source SDK Base 2013 Multiplayer/bin/studiomdl.exe',
    # GMod ships its own in some installs
    'steamapps/common/GarrysMod/bin/studiomdl.exe',
    # Half-Life 2 tools
    'steamapps/common/Half-Life 2/bin/studiomdl.exe',
]

_GARRYSMOD_GAME = 'steamapps/common/GarrysMod/garrysmod'


def find_studiomdl(steam_path):
    """
    Try to locate studiomdl.exe under *steam_path*.
    Returns the full path string or None.
    """
    if not steam_path:
        return None
    for rel in _CANDIDATES:
        candidate = os.path.join(steam_path, rel)
        if os.path.isfile(candidate):
            return candidate
    return None


def default_game_dir(steam_path):
    """Return the GarrysMod garrysmod directory for use as studiomdl -game."""
    if not steam_path:
        return None
    path = os.path.join(steam_path, _GARRYSMOD_GAME)
    return path if os.path.isdir(path) else None


def _parse_modelname(qc_path):
    """Extract the $modelname value from a QC file."""
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                m = re.match(r'^\s*\$modelname\s+"([^"]+)"', line, re.IGNORECASE)
                if not m:
                    m = re.match(r'^\s*\$modelname\s+(\S+)', line, re.IGNORECASE)
                if m:
                    return m.group(1).replace('\\', '/')
    except OSError:
        pass
    return None


def compile_qc(studiomdl_path, qc_path, game_dir, log_callback=None):
    """
    Compile *qc_path* using studiomdl.exe.

    studiomdl outputs the .mdl to {game_dir}/models/{$modelname}.
    Returns the output .mdl path on success, or None on failure.
    """
    if not studiomdl_path or not os.path.isfile(studiomdl_path):
        if log_callback:
            log_callback('[STUDIOMDL] studiomdl.exe not found — cannot compile.')
        return None

    if not game_dir or not os.path.isdir(game_dir):
        if log_callback:
            log_callback(f'[STUDIOMDL] Game directory not found: {game_dir}')
        return None

    cmd = [studiomdl_path, '-game', game_dir, '-nop4', qc_path]
    if log_callback:
        log_callback(f'[STUDIOMDL] Compiling: {os.path.basename(qc_path)}')
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=os.path.dirname(qc_path)
        )
        stdout, stderr = proc.communicate(timeout=120)
        for line in stdout.splitlines():
            s = line.strip()
            if s and log_callback:
                log_callback(f'[STUDIOMDL] {s}')
        for line in stderr.splitlines():
            s = line.strip()
            if s and log_callback:
                log_callback(f'[STUDIOMDL ERR] {s}')
    except Exception as e:
        if log_callback:
            log_callback(f'[STUDIOMDL] Failed: {e}')
        return None

    modelname = _parse_modelname(qc_path)
    if not modelname:
        return None
    if not modelname.endswith('.mdl'):
        modelname += '.mdl'

    compiled = os.path.join(game_dir, 'models', modelname)
    return compiled if os.path.isfile(compiled) else None


def copy_mdl_to_addon(compiled_mdl, addon_models_dir, modelname, log_callback=None):
    """
    Copy the compiled MDL (and any companion .vvd/.dx90.vtx/.phy) from the
    studiomdl output location back into the addon's models directory.
    """
    if not compiled_mdl or not os.path.isfile(compiled_mdl):
        return False

    base = os.path.splitext(compiled_mdl)[0]
    companions = [compiled_mdl]
    for ext in ('.vvd', '.dx90.vtx', '.dx80.vtx', '.sw.vtx', '.phy'):
        p = base + ext
        if os.path.isfile(p):
            companions.append(p)

    dest_base = os.path.join(addon_models_dir, os.path.dirname(modelname))
    os.makedirs(dest_base, exist_ok=True)

    for src in companions:
        dst = os.path.join(dest_base, os.path.basename(src))
        shutil.copy2(src, dst)
        if log_callback:
            log_callback(f'[COPY] {os.path.basename(src)} → {dst}')

    return True

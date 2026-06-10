"""
VTF dimension reading and aspect-ratio-preserving resize via VTFCmd.
"""

import os
import struct
import subprocess
import tempfile


def read_vtf_dimensions(path):
    """Return (width, height) from VTF binary header, or None on failure."""
    try:
        with open(path, 'rb') as f:
            data = f.read(20)
        if len(data) < 20 or data[:4] != b'VTF\x00':
            return None
        w, h = struct.unpack_from('<HH', data, 16)
        return (w, h)
    except OSError:
        return None


def _pow2_floor(n):
    """Largest power of 2 that is ≤ n (minimum 1)."""
    if n <= 1:
        return 1
    p = 1
    while p * 2 <= n:
        p *= 2
    return p


def _pow2_nearest(n):
    """Power of 2 closest to n (ties round down). Minimum 1."""
    lo = _pow2_floor(n)
    hi = lo * 2
    return hi if (hi - n) < (n - lo) else lo


def _is_pow2(n):
    return n >= 1 and (n & (n - 1)) == 0


def clamp_dimensions(w, h, max_w, max_h):
    """
    Return (new_w, new_h) that fit within max_w × max_h, preserving the original
    aspect ratio and producing power-of-two dimensions.

    Both axes are divided by a *single* shared power-of-two factor (mip-style
    halving) chosen as the smallest 2^n that brings both within the limits. Since
    Source textures are always power-of-two, this keeps the output power-of-two
    AND preserves the ratio exactly. As a defensive fallback for a non-power-of-two
    source, each axis is snapped to the nearest power of two that still fits the
    limit (accepts minor ratio drift on already-odd textures).

    max_w or max_h of 0 means no limit on that axis.
    Returns the original (w, h) unchanged if no clamping is needed.
    """
    limit_w = max_w if max_w > 0 else w
    limit_h = max_h if max_h > 0 else h

    if w <= limit_w and h <= limit_h:
        return w, h

    # Smallest shared power-of-two divisor that fits both axes within the limits.
    k = 1
    while (w // k) > limit_w or (h // k) > limit_h:
        k *= 2

    new_w = max(1, w // k)
    new_h = max(1, h // k)

    # Guarantee power-of-two output. No-op for pow2 sources (the normal case);
    # only odd sources hit this, snapped to the nearest pow2 within the limit.
    if not _is_pow2(new_w):
        new_w = min(_pow2_nearest(new_w), _pow2_floor(limit_w))
    if not _is_pow2(new_h):
        new_h = min(_pow2_nearest(new_h), _pow2_floor(limit_h))

    return new_w, new_h


def resize_vtf(vtfcmd_path, vtf_path, new_w, new_h, log_callback=None):
    """
    Resize a VTF in-place using VTFCmd: export → TGA → reimport with explicit
    clamp dimensions (new_w × new_h). The output overwrites vtf_path.
    Returns True on success.
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)

    stem = os.path.splitext(os.path.basename(vtf_path))[0]
    out_dir = os.path.dirname(vtf_path)

    with tempfile.TemporaryDirectory() as tmp:
        # Step 1: VTF → TGA
        r1 = subprocess.run(
            [vtfcmd_path, '-file', vtf_path, '-exportformat', 'tga', '-output', tmp],
            capture_output=True, text=True
        )
        tga_path = os.path.join(tmp, stem + '.tga')
        if r1.returncode != 0 or not os.path.isfile(tga_path):
            _log(f'[VTF] WARN: VTFCmd export failed: {r1.stderr.strip() or r1.stdout.strip()}')
            return False

        # Step 2: TGA → VTF resized to exact target dimensions
        r2 = subprocess.run(
            [vtfcmd_path, '-file', tga_path,
             '-resize', '-rwidth', str(new_w), '-rheight', str(new_h),
             '-output', out_dir],
            capture_output=True, text=True
        )
        if r2.returncode != 0:
            _log(f'[VTF] WARN: VTFCmd reimport failed: {r2.stderr.strip() or r2.stdout.strip()}')
            return False

    return True


def clamp_vtfs_in_tree(root, vtfcmd_path, max_w, max_h, log_callback=None):
    """
    Walk *root* and clamp every .vtf to max_w × max_h (aspect-preserving,
    power-of-two) in place using VTFCmd.

    A max of 0 on an axis means no limit. If no clamp is set, returns immediately.
    Files already within limits are left untouched. Resizing requires a valid
    vtfcmd_path; without it, oversized files are logged and skipped.

    Returns (checked, resized): VTFs inspected and VTFs actually resized.
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)

    if (not max_w or max_w <= 0) and (not max_h or max_h <= 0):
        return 0, 0

    have_vtfcmd = bool(vtfcmd_path) and os.path.isfile(vtfcmd_path)
    checked = 0
    resized = 0

    for dirpath, _dirs, filenames in os.walk(root):
        for fname in filenames:
            if not fname.lower().endswith('.vtf'):
                continue
            path = os.path.join(dirpath, fname)
            dims = read_vtf_dimensions(path)
            if not dims:
                continue
            checked += 1
            w, h = dims
            new_w, new_h = clamp_dimensions(w, h, max_w, max_h)
            if (new_w, new_h) == (w, h):
                continue

            rel = os.path.relpath(path, root)
            if not have_vtfcmd:
                _log(f'[VTF] {rel} [{w}×{h}] WARN: over limit ({new_w}×{new_h}), VTFCmd not configured')
                continue

            ok = resize_vtf(vtfcmd_path, path, new_w, new_h, log_callback)
            final = read_vtf_dimensions(path) if ok else None
            if ok and final:
                resized += 1
                _log(f'[VTF] {rel} [{w}×{h} → {final[0]}×{final[1]}]')
            else:
                _log(f'[VTF] {rel} [{w}×{h}] (resize failed, kept original)')

    if log_callback:
        _log(f'[VTF] Clamp pass: {resized} resized of {checked} checked')
    return checked, resized

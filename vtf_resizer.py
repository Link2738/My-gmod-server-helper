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


def clamp_dimensions(w, h, max_w, max_h):
    """
    Return (new_w, new_h) that fit within max_w × max_h while preserving
    the original aspect ratio. Both output values are snapped to the nearest
    power-of-two that is ≤ the scaled value.

    max_w or max_h of 0 means no limit on that axis.
    Returns the original (w, h) unchanged if no clamping is needed.
    """
    limit_w = max_w if max_w > 0 else w
    limit_h = max_h if max_h > 0 else h

    if w <= limit_w and h <= limit_h:
        return w, h

    scale = min(limit_w / w, limit_h / h)
    new_w = _pow2_floor(int(w * scale))
    new_h = _pow2_floor(int(h * scale))
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

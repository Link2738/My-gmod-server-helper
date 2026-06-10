"""
Extraction logic for GMA, VPK, and GMod legacy .bin files.
"""

import io
import lzma
import os
import struct


def _read_cstring(f) -> str:
    chars = []
    while True:
        c = f.read(1)
        if c == b'\x00' or c == b'':
            break
        chars.append(c)
    return b''.join(chars).decode('utf-8', errors='replace')


def _makedirs_for(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _extract_gma_from_fileobj(f, output_dir, log_callback=None):
    os.makedirs(output_dir, exist_ok=True)
    magic = f.read(4)
    if magic != b'GMAD':
        if log_callback:
            log_callback("[ERROR] Not a valid GMA file (missing GMAD header)")
        return False
    version   = struct.unpack('<B', f.read(1))[0]
    steamid   = struct.unpack('<Q', f.read(8))[0]
    timestamp = struct.unpack('<Q', f.read(8))[0]
    required_content = _read_cstring(f)
    addon_name       = _read_cstring(f)
    addon_desc       = _read_cstring(f)
    addon_author     = _read_cstring(f)
    addon_version    = struct.unpack('<I', f.read(4))[0]
    if log_callback:
        log_callback(f"Addon: {addon_name}, Author: {addon_author}, Version: {addon_version}")
    files = []
    while True:
        file_num = struct.unpack('<I', f.read(4))[0]
        if file_num == 0:
            break
        file_path = _read_cstring(f)
        file_size = struct.unpack('<Q', f.read(8))[0]
        file_crc  = struct.unpack('<I', f.read(4))[0]
        files.append({'num': file_num, 'path': file_path, 'size': file_size, 'crc': file_crc})
    if log_callback:
        log_callback(f"Found {len(files)} files in archive.")
    for entry in files:
        out_path = os.path.join(output_dir, entry['path'])
        _makedirs_for(out_path)
        data = f.read(entry['size'])
        with open(out_path, 'wb') as out_f:
            out_f.write(data)
        if entry['path'].endswith('.bsp'):
            if log_callback:
                log_callback(f"EXCEPTION: .bsp file extracted: {entry['path']} ({entry['size']} bytes)")
        else:
            if log_callback:
                log_callback(f"Extracted: {entry['path']} ({entry['size']} bytes)")
    if log_callback:
        log_callback("Extraction complete.")
    return True


def extract_gma(gma_path, output_dir, log_callback=None):
    if not os.path.isfile(gma_path):
        if log_callback:
            log_callback(f"[ERROR] .gma file not found: {gma_path}")
        return False
    if log_callback:
        log_callback(f"Opening {gma_path}")
    with open(gma_path, 'rb') as f:
        return _extract_gma_from_fileobj(f, output_dir, log_callback)


def extract_legacy_bin(bin_path, output_dir, log_callback=None):
    if not os.path.isfile(bin_path):
        if log_callback:
            log_callback(f"[ERROR] .bin file not found: {bin_path}")
        return False
    if log_callback:
        log_callback(f"Opening legacy .bin: {bin_path}")
    with open(bin_path, 'rb') as f:
        raw = f.read()
    if len(raw) < 13:
        if log_callback:
            log_callback("[ERROR] File too small to be a valid legacy .bin")
        return False
    uncompressed_size = struct.unpack('<Q', raw[5:13])[0]
    if log_callback:
        log_callback(f"  LZMA props: {raw[0:5].hex()}")
        log_callback(f"  Uncompressed size: {uncompressed_size:,} bytes")
        log_callback(f"  Compressed size:   {len(raw) - 13:,} bytes")

    # Old GMod .bin files use LZMA ALONE format but omit the end-of-stream
    # marker, so lzma.decompress() always raises "stream ended before
    # end-of-stream marker".  Feed the data incrementally; if decompression
    # fails after we already have the expected number of bytes, that's fine.
    decomp = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    chunks = []
    chunk_size = 1 << 20  # 1 MB
    offset = 0
    try:
        while offset < len(raw) and not decomp.eof:
            end = min(offset + chunk_size, len(raw))
            chunk = decomp.decompress(raw[offset:end])
            if chunk:
                chunks.append(chunk)
            offset = end
    except lzma.LZMAError as e:
        got = sum(len(c) for c in chunks)
        if got < uncompressed_size * 0.99:
            if log_callback:
                log_callback(f"[ERROR] LZMA decompression failed after {got:,} bytes: {e}")
            return False
        if log_callback:
            log_callback(f"  [WARN] LZMA stream has no end-of-stream marker (harmless) — got {got:,} bytes")

    decompressed = b''.join(chunks)
    if log_callback:
        log_callback(f"  Decompressed to {len(decompressed):,} bytes - passing to GMA extractor...")
    return _extract_gma_from_fileobj(io.BytesIO(decompressed), output_dir, log_callback)


def extract_vpk(vpk_path, output_dir, log_callback=None):
    if not os.path.isfile(vpk_path):
        if log_callback:
            log_callback(f"[ERROR] .vpk file not found: {vpk_path}")
        return False
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(vpk_path)[0]
    archive_prefix = stem[:-4] if stem.endswith('_dir') else stem
    with open(vpk_path, 'rb') as f:
        if log_callback:
            log_callback(f"Opening {vpk_path}")
        sig = struct.unpack('<I', f.read(4))[0]
        if sig != 0x55AA1234:
            if log_callback:
                log_callback("[ERROR] Not a valid VPK file (bad signature)")
            return False
        version   = struct.unpack('<I', f.read(4))[0]
        tree_size = struct.unpack('<I', f.read(4))[0]
        if version == 2:
            _fds = struct.unpack('<I', f.read(4))[0]
            _amd = struct.unpack('<I', f.read(4))[0]
            _omd = struct.unpack('<I', f.read(4))[0]
            _sig = struct.unpack('<I', f.read(4))[0]
        elif version == 1:
            pass
        else:
            if log_callback:
                log_callback(f"[ERROR] Unsupported VPK version: {version}")
            return False
        tree_start          = f.tell()
        embedded_data_start = tree_start + tree_size
        if log_callback:
            log_callback(f"VPK v{version}, tree size: {tree_size} bytes")
        entries = []
        while True:
            ext = _read_cstring(f)
            if ext == '':
                break
            while True:
                path = _read_cstring(f)
                if path == '':
                    break
                while True:
                    filename = _read_cstring(f)
                    if filename == '':
                        break
                    crc           = struct.unpack('<I', f.read(4))[0]
                    preload_bytes = struct.unpack('<H', f.read(2))[0]
                    archive_index = struct.unpack('<H', f.read(2))[0]
                    entry_offset  = struct.unpack('<I', f.read(4))[0]
                    entry_length  = struct.unpack('<I', f.read(4))[0]
                    _term         = struct.unpack('<H', f.read(2))[0]
                    preload_data  = f.read(preload_bytes) if preload_bytes else b''
                    full_path     = f"{filename}.{ext}" if path == ' ' else f"{path}/{filename}.{ext}"
                    entries.append({'path': full_path, 'archive_index': archive_index,
                                    'offset': entry_offset, 'length': entry_length, 'preload': preload_data})
        if log_callback:
            log_callback(f"Found {len(entries)} files in VPK archive.")
        archive_handles = {}
        try:
            for entry in entries:
                out_path = os.path.join(output_dir, entry['path'].replace('/', os.sep))
                _makedirs_for(out_path)
                data = entry['preload']
                if entry['length'] > 0:
                    idx = entry['archive_index']
                    if idx == 0x7FFF:
                        f.seek(embedded_data_start + entry['offset'])
                        data += f.read(entry['length'])
                    else:
                        if idx not in archive_handles:
                            part_path = f"{archive_prefix}_{idx:03d}.vpk"
                            if not os.path.isfile(part_path):
                                if log_callback:
                                    log_callback(f"[WARN] Part not found: {part_path}, skipping {entry['path']}")
                                continue
                            archive_handles[idx] = open(part_path, 'rb')
                        ah = archive_handles[idx]
                        ah.seek(entry['offset'])
                        data += ah.read(entry['length'])
                with open(out_path, 'wb') as out_f:
                    out_f.write(data)
                if log_callback:
                    log_callback(f"Extracted: {entry['path']} ({len(data)} bytes)")
        finally:
            for ah in archive_handles.values():
                ah.close()
    if log_callback:
        log_callback("VPK extraction complete.")
    return True


def extract_archive(file_path, output_dir, log_callback=None):
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(4)
    except Exception:
        magic = b''

    if magic == b'GMAD':
        return extract_gma(file_path, output_dir, log_callback)

    if len(magic) == 4 and struct.unpack('<I', magic)[0] == 0x55AA1234:
        return extract_vpk(file_path, output_dir, log_callback)

    if file_path.lower().endswith('.vpk'):
        return extract_vpk(file_path, output_dir, log_callback)

    if (magic and magic[0] == 0x5D) or file_path.lower().endswith('.bin'):
        return extract_legacy_bin(file_path, output_dir, log_callback)

    return extract_gma(file_path, output_dir, log_callback)
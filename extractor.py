"""
Extraction logic for GMA files
"""

def extract_gma(gma_path, output_dir, log_callback=None):
    import struct
    import os
    def read_cstring(f: any) -> str:
        chars: list[bytes] = []
        while True:
            c: bytes = f.read(1)
            if c == b'\x00' or c == b'':
                break
            chars.append(c)
        return b''.join(chars).decode('utf-8', errors='replace')
    if not os.path.isfile(gma_path):
        if log_callback:
            log_callback(f"[ERROR] .gma file not found: {gma_path}")
        return False
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    with open(gma_path, 'rb') as f:
        if log_callback:
            log_callback(f"Opening {gma_path}")
        magic: bytes = f.read(4)
        if magic != b'GMAD':
            if log_callback:
                log_callback("Not a valid GMA file (missing GMAD header)")
            return False
        version: int = struct.unpack('<B', f.read(1))[0]
        steamid: int = struct.unpack('<Q', f.read(8))[0]
        timestamp: int = struct.unpack('<Q', f.read(8))[0]
        required_content: str = read_cstring(f)
        addon_name: str = read_cstring(f)
        addon_desc: str = read_cstring(f)
        addon_author: str = read_cstring(f)
        addon_version: int = struct.unpack('<I', f.read(4))[0]
        if log_callback:
            log_callback(f"Addon: {addon_name}, Author: {addon_author}, Version: {addon_version}")
        files: list[dict[str, any]] = []
        while True:
            file_num = struct.unpack('<I', f.read(4))[0]
            if file_num == 0:
                break
            file_path = read_cstring(f)
            file_size = struct.unpack('<Q', f.read(8))[0]
            file_crc = struct.unpack('<I', f.read(4))[0]
            files.append({'num': file_num, 'path': file_path, 'size': file_size, 'crc': file_crc})
        if log_callback:
            log_callback(f"Found {len(files)} files in archive.")
        for file in files:
            out_path = os.path.join(output_dir, file['path'])
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            data = f.read(file['size'])
            with open(out_path, 'wb') as out_f:
                out_f.write(data)
            if file['path'].endswith('.bsp'):
                if log_callback:
                    log_callback(f"EXCEPTION: .bsp file extracted: {file['path']} ({file['size']} bytes)")
            else:
                if log_callback:
                    log_callback(f"Extracted: {file['path']} ({file['size']} bytes)")
    if log_callback:
        log_callback("Extraction complete.")
    return True

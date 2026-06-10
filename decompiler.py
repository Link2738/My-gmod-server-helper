
"""
Decompiling logic for .mdl files using CrowbarCommandLineDecomp.exe
"""

def decompile_mdl(mdl_path, crowbar_path, out_dir, log_callback=None, quiet=False):
    import subprocess
    import shutil
    import os
    crowbar_exe: str = crowbar_path
    if not crowbar_exe:
        possible: list[str] = [
            os.path.join(os.path.dirname(__file__), 'CrowbarCommandLineDecomp.exe'),
            os.path.join(os.getcwd(), 'CrowbarCommandLineDecomp.exe'),
            shutil.which('CrowbarCommandLineDecomp'),
            shutil.which('CrowbarCommandLineDecomp.exe'),
        ]
        crowbar_exe = next((p for p in possible if p and os.path.isfile(p)), None)
    if not crowbar_exe:
        if log_callback:
            log_callback("[ERROR] CrowbarCommandLineDecomp.exe not found. Please place it in the script directory or set the correct path in config.")
        return None
    os.makedirs(out_dir, exist_ok=True)
    cmd: list[str] = [crowbar_exe, '-p', mdl_path, '-o', out_dir]
    if not quiet and log_callback:
        log_callback(f"Decompiling {mdl_path}: {' '.join(cmd)}")
    try:
        proc: subprocess.Popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate(timeout=120)
        if log_callback:
            if quiet:
                for line in stdout.splitlines():
                    ls = line.strip().lower()
                    if ls.startswith('error') or ls.startswith('warning') or '[error]' in ls:
                        log_callback(f"[Crowbar] {line}")
            else:
                log_callback(f"[Crowbar Output]:\n{stdout}")
            if stderr:
                for line in stderr.splitlines():
                    if line.strip():
                        log_callback(f"[Crowbar Error] {line}")
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Crowbar decompiling failed: {e}")
        return None
    return True

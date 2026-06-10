import os
import re
import shutil
import subprocess

import requests
from bs4 import BeautifulSoup


def detect_steam_path():
    """Auto-detect Steam install path from Windows registry.
    Returns the path string, or '' if not found."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        steam_path, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        if steam_path and os.path.isdir(steam_path):
            return os.path.normpath(steam_path)
    except Exception:
        pass
    # Fallback: common default locations
    for candidate in [
        os.path.expandvars(r'%ProgramFiles(x86)%\Steam'),
        os.path.expandvars(r'%ProgramFiles%\Steam'),
        r'C:\Program Files (x86)\Steam',
    ]:
        if os.path.isdir(candidate):
            return os.path.normpath(candidate)
    return ''


# Game-specific workshop addon folder paths (relative to <library>/steamapps/common/)
# L4D2 stores subscribed workshop items as individual .vpk files here rather than
# in the central steamapps/workshop/content/ tree.
_GAME_ADDON_PATHS = {
    '550': os.path.join('Left 4 Dead 2', 'left4dead2', 'addons', 'workshop'),
}


def find_workshop_in_steam(steam_path, app_id, workshop_id, output_dir, log_callback=None):
    """Find a workshop item already downloaded via the Steam client.

    Search order (per library folder):
      1. <library>/steamapps/workshop/content/<app_id>/<workshop_id>/  (generic)
      2. Game-specific addon folder (e.g. L4D2's addons/workshop/<id>.vpk)

    Copies found files to output_dir/workshop_download/<workshop_id>/
    Returns the path to the first copied file, or None if not found.
    """
    if not steam_path or not os.path.isdir(steam_path):
        if log_callback:
            log_callback("[ERROR] Steam path is not set or invalid. Set it in Config.")
        return None

    # Build list of Steam library folders
    library_folders = [os.path.normpath(steam_path)]
    vdf_path = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
    if os.path.isfile(vdf_path):
        try:
            with open(vdf_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                lib_path = os.path.normpath(match.group(1))
                if lib_path not in library_folders and os.path.isdir(lib_path):
                    library_folders.append(lib_path)
        except Exception:
            pass

    if log_callback:
        log_callback(f"[INFO] Searching {len(library_folders)} Steam library folder(s)...")

    workshop_folder = os.path.join(output_dir, 'workshop_download', workshop_id)

    for lib in library_folders:
        # ── Strategy 1: central workshop/content tree ────────────────
        item_dir = os.path.join(lib, 'steamapps', 'workshop', 'content', app_id, workshop_id)
        if os.path.isdir(item_dir):
            if log_callback:
                log_callback(f"[INFO] Found workshop item at: {item_dir}")
            result = _copy_item_dir(item_dir, workshop_folder, workshop_id, log_callback)
            if result:
                return result

        # ── Strategy 2: game-specific addon folder (e.g. L4D2) ──────
        addon_rel = _GAME_ADDON_PATHS.get(app_id)
        if addon_rel:
            addon_dir = os.path.join(lib, 'steamapps', 'common', addon_rel)
            if os.path.isdir(addon_dir):
                # Look for <workshop_id>.vpk (or other archive files), skip images
                for fname in os.listdir(addon_dir):
                    name_no_ext, ext = os.path.splitext(fname)
                    if name_no_ext == workshop_id and ext.lower() in ('.vpk', '.gma', '.bin'):
                        src = os.path.join(addon_dir, fname)
                        os.makedirs(workshop_folder, exist_ok=True)
                        dst = os.path.join(workshop_folder, fname)
                        shutil.copy2(src, dst)
                        if log_callback:
                            log_callback(f"[INFO] Found in game addons: {src}")
                            log_callback(f"[INFO] Copied: {fname} ({os.path.getsize(src)} bytes)")
                        return dst

        # ── Strategy 3: GMod client cache (cache/workshop/<id>.gma) ─────
        if app_id == '4000':
            gmod_cache = os.path.join(lib, 'steamapps', 'common', 'GarrysMod', 'garrysmod', 'cache', 'workshop')
            if os.path.isdir(gmod_cache):
                for ext in ('.gma', '.bin', '.vpk'):
                    candidate = os.path.join(gmod_cache, f'{workshop_id}{ext}')
                    if os.path.isfile(candidate):
                        os.makedirs(workshop_folder, exist_ok=True)
                        dst = os.path.join(workshop_folder, os.path.basename(candidate))
                        shutil.copy2(candidate, dst)
                        if log_callback:
                            log_callback(f"[INFO] Found in GMod cache: {candidate}")
                            log_callback(f"[INFO] Copied: {os.path.basename(candidate)} ({os.path.getsize(candidate)} bytes)")
                        return dst

    if log_callback:
        log_callback(f"[ERROR] Workshop item {workshop_id} not found in Steam library.")
        log_callback("[INFO] Make sure you've subscribed to the item in Steam and the game has downloaded it.")
    return None


def _copy_item_dir(item_dir, workshop_folder, workshop_id, log_callback):
    """Copy all files from a workshop item directory to the output folder.
    Returns the path to the first copied file (renamed with workshop ID), or None."""
    os.makedirs(workshop_folder, exist_ok=True)
    found_files = []
    for root, dirs, files in os.walk(item_dir):
        for fname in files:
            src = os.path.join(root, fname)
            rel = os.path.relpath(src, item_dir)
            dst = os.path.join(workshop_folder, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            found_files.append(dst)
            if log_callback:
                log_callback(f"[INFO] Copied: {rel} ({os.path.getsize(src)} bytes)")
    if found_files:
        first = found_files[0]
        ext = os.path.splitext(first)[1] or '.bin'
        renamed = os.path.join(workshop_folder, f'{workshop_id}_1{ext}')
        try:
            if first != renamed:
                if os.path.exists(renamed):
                    os.remove(renamed)
                os.replace(first, renamed)
                found_files[0] = renamed
        except Exception:
            pass
        return found_files[0]
    return None

def parse_collection_items(collection_id_or_url, log_callback=None):
    """
    Fetches all workshop item IDs from a Steam Workshop collection page.
    Accepts a collection ID or full URL.
    Returns a list of item IDs as strings.
    """
    if collection_id_or_url.isdigit():
        collection_id: str = collection_id_or_url
        url: str = f"https://steamcommunity.com/sharedfiles/filedetails/?id={collection_id}"
    else:
        url: str = collection_id_or_url
        match: re.Match | None = re.search(r'id=(\d+)', url)
        if match:
            collection_id: str = match.group(1)
        else:
            if log_callback:
                log_callback(f"[ERROR] Invalid collection URL: {collection_id_or_url}")
            return []
    try:
        if log_callback:
            log_callback(f"[Collection] Fetching collection page: {url}")
        response: requests.Response = requests.get(url)
        response.raise_for_status()
        soup: BeautifulSoup = BeautifulSoup(response.text, 'html.parser')
        item_ids: list[str] = []
        # Look for <div class="workshopItem"> with direct <a href=...> children
        for item_div in soup.find_all('div', class_='workshopItem'):
            link = item_div.find('a', href=True, recursive=False)
            if link:
                href: str = link['href']
                match: re.Match | None = re.match(r'^https?://steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)$', href)
                if match:
                    item_id: str = match.group(1)
                    if item_id != collection_id and item_id not in item_ids:
                        item_ids.append(item_id)
        if log_callback:
            log_callback(f"[Collection] Found {len(item_ids)} items in collection.")
        return item_ids
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to fetch collection items: {e}")
        return []

def download_workshop_item(steamcmd_path, workshop_id, output_dir, log_callback=None, app_id='4000'):
    """
    Downloads a single workshop item using SteamCMD and returns the path to the downloaded file, or None on failure.
    app_id: Steam App ID (default '4000' for GMod). Use '550' for L4D2, etc.
    """
    if not steamcmd_path or not os.path.isfile(steamcmd_path):
        if log_callback:
            log_callback("[ERROR] SteamCMD path is invalid.")
        return None
    if not workshop_id.isdigit():
        if log_callback:
            log_callback("[ERROR] Workshop ID must be numeric.")
        return None
    os.makedirs(output_dir, exist_ok=True)
    steamcmd_dir = os.path.dirname(os.path.normpath(steamcmd_path))
    workshop_folder = os.path.join(output_dir, 'workshop_download', workshop_id)
    if os.path.isdir(workshop_folder):
        for f in os.listdir(workshop_folder):
            file_path = os.path.join(workshop_folder, f)
            if os.path.isfile(file_path) and f.lower().endswith(('.gma', '.bin', '.vpk')):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
    else:
        os.makedirs(workshop_folder, exist_ok=True)
    try:
        if log_callback:
            log_callback(f"[SteamCMD] Running steamcmd.exe in background...")
        cmd = [steamcmd_path, '+login', 'anonymous', '+workshop_download_item', app_id, workshop_id, '+quit']

        # Merge stderr into stdout so we only need one pipe to stream line-by-line.
        # This is intentional: SteamCMD's self-update deletes the workshop content
        # folder after downloading. By reading output as it arrives, we copy the file
        # the moment SteamCMD reports it — before the self-update wipes it.
        proc = subprocess.Popen(
            cmd, cwd=steamcmd_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        output_lines = []
        found_files = []
        already_copied = set()
        os.makedirs(workshop_folder, exist_ok=True)

        for raw_line in (proc.stdout or []):
            line = raw_line.rstrip('\n')
            output_lines.append(line)

            # As soon as SteamCMD reports a successful download, copy immediately
            m = re.search(r'Downloaded item \d+ to "([^"]+)"', line)
            if m:
                src = os.path.normpath(m.group(1))
                if os.path.isfile(src):
                    fname = os.path.basename(src)
                    base, ext = os.path.splitext(fname)
                    # Always rename to <workshop_id><ext> for consistency
                    dst_name = f'{workshop_id}{ext}' if workshop_id not in base else fname
                    dst = os.path.normpath(os.path.join(workshop_folder, dst_name))
                    shutil.copy2(src, dst)
                    if log_callback:
                        log_callback(f"[SteamCMD] Copied on-the-fly: {dst}")
                    already_copied.add(dst_name)
                    found_files.append(dst)
                else:
                    if log_callback:
                        log_callback(f"[DEBUG] Reported path not yet on disk (will retry after exit): {src}")

        proc.wait()

        if log_callback:
            log_callback(f"[SteamCMD Output]:\n" + '\n'.join(output_lines))

        # If the on-the-fly copy missed (file appeared after the line printed),
        # re-parse the output and try once more now that the process has exited.
        if not found_files:
            for m in re.finditer(r'Downloaded item \d+ to "([^"]+)"', '\n'.join(output_lines)):
                src = os.path.normpath(m.group(1))
                if os.path.isfile(src):
                    fname = os.path.basename(src)
                    base, ext = os.path.splitext(fname)
                    dst_name = f'{workshop_id}{ext}' if workshop_id not in base else fname
                    if dst_name in already_copied:
                        continue
                    dst = os.path.normpath(os.path.join(workshop_folder, dst_name))
                    shutil.copy2(src, dst)
                    already_copied.add(dst_name)
                    found_files.append(dst)

        if log_callback:
            log_callback(f"[DEBUG] found_files ({len(found_files)}): {found_files}")

        gma_file = None
        if found_files:
            gma_file = found_files[0] if os.path.isfile(found_files[0]) else None

        # Fallback for legacy items: SteamCMD may download then delete the file
        # during a self-update. Check the Steam client's own copy instead.
        if gma_file is None:
            if log_callback:
                log_callback(f"[INFO] SteamCMD file unavailable (legacy item?); checking Steam client library...")
            steam_path = detect_steam_path()
            gma_file = find_workshop_in_steam(steam_path, app_id, workshop_id, output_dir, log_callback)

        return gma_file
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] SteamCMD failed: {e}")
        return None

def download_collection(steamcmd_path, collection_ids, output_dir, log_callback=None, app_id='4000'):
    """
    Downloads all items in a collection using a single SteamCMD session. Accepts a list of workshop IDs.
    app_id: Steam App ID (default '4000' for GMod). Use '550' for L4D2, etc.
    Returns a list of downloaded file paths.
    """
    # Accepts a collection ID, URL, or list of IDs
    if isinstance(collection_ids, str):
        # Could be a collection ID or URL
        item_ids = parse_collection_items(collection_ids, log_callback=log_callback)
    elif isinstance(collection_ids, list):
        # If list of all digits, treat as IDs
        if all(isinstance(i, str) and i.isdigit() for i in collection_ids):
            item_ids = collection_ids
        else:
            # Assume list of URLs or mixed
            item_ids = []
            for entry in collection_ids:
                item_ids.extend(parse_collection_items(entry, log_callback=log_callback))
    else:
        if log_callback:
            log_callback(f"[ERROR] Invalid collection_ids argument: {collection_ids}")
        return []
    if not item_ids:
        if log_callback:
            log_callback(f"[ERROR] No valid workshop items found in collection.")
        return []
    # Build a single SteamCMD command with all download requests
    steamcmd_dir = os.path.dirname(os.path.normpath(steamcmd_path))
    os.makedirs(output_dir, exist_ok=True)
    workshop_folder = os.path.join(output_dir, 'workshop_download')
    os.makedirs(workshop_folder, exist_ok=True)
    cmd = [steamcmd_path, '+login', 'anonymous']
    for workshop_id in item_ids:
        cmd += ['+workshop_download_item', app_id, workshop_id]
    cmd += ['+quit']
    try:
        if log_callback:
            log_callback(f"[SteamCMD] Running single session for {len(item_ids)} items...")

        # Stream output line-by-line and copy each file the instant SteamCMD
        # reports it — before any self-update can wipe the content folder.
        proc = subprocess.Popen(
            cmd, cwd=steamcmd_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )

        output_lines = []
        # Map workshop_id -> first dst path captured on-the-fly
        captured: dict[str, str] = {}

        for raw_line in (proc.stdout or []):
            line = raw_line.rstrip('\n')
            output_lines.append(line)

            m = re.search(r'Downloaded item (\d+) to "([^"]+)"', line)
            if m:
                wid, src = m.group(1), os.path.normpath(m.group(2))
                if wid in item_ids and os.path.isfile(src):
                    fname = os.path.basename(src)
                    base, ext = os.path.splitext(fname)
                    dst_name = f'{wid}{ext}' if wid not in base else fname
                    dst_folder = os.path.join(workshop_folder, wid)
                    os.makedirs(dst_folder, exist_ok=True)
                    dst = os.path.join(dst_folder, dst_name)
                    shutil.copy2(src, dst)
                    if log_callback:
                        log_callback(f"[SteamCMD] Copied on-the-fly: {dst}")
                    if wid not in captured:
                        captured[wid] = dst

        proc.wait()

        if log_callback:
            log_callback(f"[SteamCMD Output]:\n" + '\n'.join(output_lines))

        # Second pass: re-parse output for any item the on-the-fly copy missed
        for m in re.finditer(r'Downloaded item (\d+) to "([^"]+)"', '\n'.join(output_lines)):
            wid, src = m.group(1), os.path.normpath(m.group(2))
            if wid in item_ids and wid not in captured and os.path.isfile(src):
                fname = os.path.basename(src)
                base, ext = os.path.splitext(fname)
                dst_name = f'{wid}{ext}' if wid not in base else fname
                dst_folder = os.path.join(workshop_folder, wid)
                os.makedirs(dst_folder, exist_ok=True)
                dst = os.path.join(dst_folder, dst_name)
                shutil.copy2(src, dst)
                captured[wid] = dst

        # Build result list; fall back to Steam client library for anything missed
        steam_path = detect_steam_path()
        gma_files = []
        for workshop_id in item_ids:
            if workshop_id in captured:
                gma_files.append(captured[workshop_id])
            else:
                if log_callback:
                    log_callback(f"[INFO] SteamCMD missed {workshop_id} (legacy item?); checking Steam client library...")
                fallback = find_workshop_in_steam(steam_path, app_id, workshop_id, output_dir, log_callback)
                if fallback:
                    gma_files.append(fallback)
                else:
                    if log_callback:
                        log_callback(f"[ERROR] No downloadable file found for workshop item {workshop_id}")

        return gma_files
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] SteamCMD failed: {e}")
        return []

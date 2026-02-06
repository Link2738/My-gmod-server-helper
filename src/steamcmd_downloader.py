import requests
from bs4 import BeautifulSoup

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
        import re
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
        import re
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
import os
import shutil
import subprocess

def download_workshop_item(steamcmd_path, workshop_id, output_dir, log_callback=None):
    """
    Downloads a GMod workshop item using SteamCMD.
    Returns the path to the downloaded .gma file, or None on failure.
    """
    if not os.path.isfile(steamcmd_path):
        if log_callback:
            log_callback(f"[ERROR] SteamCMD not found at: {steamcmd_path}")
        return None
    if not workshop_id.isdigit():
        if log_callback:
            log_callback(f"[ERROR] Invalid workshop ID: {workshop_id}")
        return None
    steamcmd_dir = os.path.dirname(steamcmd_path)
    steamapps_dir = os.path.join(steamcmd_dir, 'steamapps', 'workshop', 'content', '4000')
    os.makedirs(output_dir, exist_ok=True)
    workshop_folder = os.path.join(output_dir, 'workshop_download', workshop_id)
    if os.path.isdir(workshop_folder):
        for f in os.listdir(workshop_folder):
            file_path = os.path.join(workshop_folder, f)
            if os.path.isfile(file_path) and f.lower().endswith('.gma'):
                try:
                    os.remove(file_path)
                    if log_callback:
                        log_callback(f"[DEBUG] Deleted old .gma file before download: {f}")
                except Exception as e:
                    if log_callback:
                        log_callback(f"[ERROR] Failed to delete old .gma file {f}: {e}")
    else:
        os.makedirs(workshop_folder, exist_ok=True)
    try:
        if log_callback:
            log_callback(f"[SteamCMD] Running steamcmd.exe in background...")
        cmd = [steamcmd_path, '+login', 'anonymous', '+workshop_download_item', '4000', workshop_id, '+quit']
        proc = subprocess.Popen(cmd, cwd=steamcmd_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()
        if log_callback:
            log_callback(f"[SteamCMD Output]:\n{stdout}")
            if stderr:
                log_callback(f"[SteamCMD Error]:\n{stderr}")
        found_gma_files = []
        already_copied = set()
        if os.path.isdir(steamapps_dir):
            for root, dirs, files in os.walk(steamapps_dir):
                for fname in files:
                    if fname.endswith('.gma'):
                        src = os.path.normpath(os.path.join(root, fname))
                        if fname == 'temp.gma' or workshop_id in fname:
                            if fname in already_copied:
                                continue
                            already_copied.add(fname)
                            dst = os.path.normpath(os.path.join(workshop_folder, fname))
                            if not os.path.exists(dst):
                                shutil.copy2(src, dst)
                            if fname == 'temp.gma':
                                renamed_dst = os.path.normpath(os.path.join(workshop_folder, f'{workshop_id}.gma'))
                                try:
                                    if os.path.exists(renamed_dst):
                                        os.remove(renamed_dst)
                                    os.replace(dst, renamed_dst)
                                    dst = renamed_dst
                                    if log_callback:
                                        log_callback(f"[SteamCMD] Renamed temp.gma to {workshop_id}.gma")
                                except Exception as e:
                                    if log_callback:
                                        log_callback(f"[ERROR] Failed to rename temp.gma: {e}")
                            found_gma_files.append(dst)
                            if log_callback:
                                log_callback(f"[SteamCMD] Downloaded and copied to {workshop_folder}: {os.path.basename(dst)}")
        gma_file = None
        renamed_gma_files = []
        if found_gma_files:
            for idx, original_gma in enumerate(found_gma_files, start=1):
                renamed_gma = os.path.join(workshop_folder, f'{workshop_id}_{idx}.gma')
                try:
                    os.replace(original_gma, renamed_gma)
                    renamed_gma_files.append(renamed_gma)
                    if log_callback:
                        log_callback(f"[SteamCMD] Renamed {os.path.basename(original_gma)} to {workshop_id}_{idx}.gma")
                except Exception as e:
                    renamed_gma_files.append(original_gma)
                    if log_callback:
                        log_callback(f"[ERROR] Failed to rename {os.path.basename(original_gma)}: {e}")
            if log_callback:
                log_callback(f"[DEBUG] Renamed .gma files: {renamed_gma_files}\nUsing: {renamed_gma_files[0] if renamed_gma_files else None}")
            gma_file = renamed_gma_files[0] if renamed_gma_files and os.path.isfile(renamed_gma_files[0]) else None
        else:
            if log_callback:
                log_callback(f"[ERROR] No .gma file found after SteamCMD run.\nChecked path: {steamapps_dir}")
        return gma_file
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] SteamCMD failed: {e}")
        return None
"""
SteamCMD Workshop/Collection downloader module
"""
import subprocess
import os

def download_workshop_item(steamcmd_path, workshop_id, output_dir, log_callback=None):
    """
    Downloads a single workshop item using SteamCMD and returns the path to the downloaded .gma file, or None on failure.
    """
    import shutil
    if not steamcmd_path or not os.path.isfile(steamcmd_path):
        if log_callback:
            log_callback("[ERROR] SteamCMD path is invalid.")
        return None
    if not workshop_id.isdigit():
        if log_callback:
            log_callback("[ERROR] Workshop ID must be numeric.")
        return None
    os.makedirs(output_dir, exist_ok=True)
    steamcmd_dir = os.path.dirname(steamcmd_path)
    steamapps_dir = os.path.join(steamcmd_dir, 'steamapps', 'workshop', 'content', '4000')
    workshop_folder = os.path.join(output_dir, 'workshop_download', workshop_id)
    if os.path.isdir(workshop_folder):
        for f in os.listdir(workshop_folder):
            file_path = os.path.join(workshop_folder, f)
            if os.path.isfile(file_path) and f.lower().endswith('.gma'):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
    else:
        os.makedirs(workshop_folder, exist_ok=True)
    import subprocess
    try:
        if log_callback:
            log_callback(f"[SteamCMD] Running steamcmd.exe in background...")
        cmd = [steamcmd_path, '+login', 'anonymous', '+workshop_download_item', '4000', workshop_id, '+quit']
        proc = subprocess.Popen(cmd, cwd=steamcmd_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()
        if log_callback:
            log_callback(f"[SteamCMD Output]:\n{stdout}")
            if stderr:
                log_callback(f"[SteamCMD Error]:\n{stderr}")
        # Find the downloaded .gma file
        found_gma_files = []
        already_copied = set()
        if os.path.isdir(steamapps_dir):
            for root, dirs, files in os.walk(steamapps_dir):
                for fname in files:
                    if fname.endswith('.gma'):
                        src = os.path.normpath(os.path.join(root, fname))
                        if fname == 'temp.gma' or workshop_id in fname:
                            if fname in already_copied:
                                continue
                            already_copied.add(fname)
                            dst = os.path.normpath(os.path.join(workshop_folder, fname))
                            if not os.path.exists(dst):
                                shutil.copy2(src, dst)
                            if fname == 'temp.gma':
                                renamed_dst = os.path.normpath(os.path.join(workshop_folder, f'{workshop_id}.gma'))
                                try:
                                    if os.path.exists(renamed_dst):
                                        os.remove(renamed_dst)
                                    os.replace(dst, renamed_dst)
                                    dst = renamed_dst
                                except Exception:
                                    pass
                            found_gma_files.append(dst)
        gma_file = None
        renamed_gma_files = []
        if found_gma_files:
            for idx, original_gma in enumerate(found_gma_files, start=1):
                renamed_gma = os.path.join(workshop_folder, f'{workshop_id}_{idx}.gma')
                try:
                    os.replace(original_gma, renamed_gma)
                    renamed_gma_files.append(renamed_gma)
                except Exception:
                    renamed_gma_files.append(original_gma)
            gma_file = renamed_gma_files[0] if renamed_gma_files and os.path.isfile(renamed_gma_files[0]) else None
        return gma_file
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] SteamCMD failed: {e}")
        return None

def download_collection(steamcmd_path, collection_ids, output_dir, log_callback=None):
    """
    Downloads all items in a collection using a single SteamCMD session. Accepts a list of workshop IDs.
    Returns a list of downloaded .gma file paths.
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
    steamcmd_dir = os.path.dirname(steamcmd_path)
    steamapps_dir = os.path.join(steamcmd_dir, 'steamapps', 'workshop', 'content', '4000')
    os.makedirs(output_dir, exist_ok=True)
    workshop_folder = os.path.join(output_dir, 'workshop_download')
    os.makedirs(workshop_folder, exist_ok=True)
    cmd = [steamcmd_path, '+login', 'anonymous']
    for workshop_id in item_ids:
        cmd += ['+workshop_download_item', '4000', workshop_id]
    cmd += ['+quit']
    try:
        if log_callback:
            log_callback(f"[SteamCMD] Running single session for {len(item_ids)} items...")
        import subprocess
        proc = subprocess.Popen(cmd, cwd=steamcmd_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()
        if log_callback:
            log_callback(f"[SteamCMD Output]:\n{stdout}")
            if stderr:
                log_callback(f"[SteamCMD Error]:\n{stderr}")
        # After download, copy/rename all .gma files for each item
        gma_files = []
        for workshop_id in item_ids:
            item_gma_files = []
            item_dir = os.path.join(steamapps_dir, workshop_id)
            if os.path.isdir(item_dir):
                for fname in os.listdir(item_dir):
                    if fname.endswith('.gma'):
                        src = os.path.join(item_dir, fname)
                        dst_folder = os.path.join(workshop_folder, workshop_id)
                        os.makedirs(dst_folder, exist_ok=True)
                        dst = os.path.join(dst_folder, fname)
                        import shutil
                        shutil.copy2(src, dst)
                        # Optionally rename temp.gma
                        if fname == 'temp.gma':
                            renamed_dst = os.path.join(dst_folder, f'{workshop_id}.gma')
                            try:
                                if os.path.exists(renamed_dst):
                                    os.remove(renamed_dst)
                                os.replace(dst, renamed_dst)
                                dst = renamed_dst
                                if log_callback:
                                    log_callback(f"[SteamCMD] Renamed temp.gma to {workshop_id}.gma")
                            except Exception as e:
                                if log_callback:
                                    log_callback(f"[ERROR] Failed to rename temp.gma: {e}")
                        item_gma_files.append(dst)
                        if log_callback:
                            log_callback(f"[SteamCMD] Downloaded and copied to {dst_folder}: {os.path.basename(dst)}")
            if item_gma_files:
                gma_files.append(item_gma_files[0])
            else:
                if log_callback:
                    log_callback(f"[ERROR] No .gma file found for workshop item {workshop_id}")
        return gma_files
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] SteamCMD failed: {e}")
        return []

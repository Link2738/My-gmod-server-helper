"""
Configuration management for saving/loading paths and settings
"""

import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'last_paths.json')

def load_last_paths():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data: dict[str, any] = json.load(f)

        # Per-type input paths (migrate legacy single 'input_path' key)
        default_paths = {'File': '', 'Folder': '', 'Workshop': '', 'Collection': ''}
        saved_paths = data.get('input_paths', {})
        # Back-compat: if old single key exists and new dict is empty, seed it
        if not saved_paths and data.get('input_path'):
            saved_paths[data.get('input_type', 'File')] = data['input_path']
        input_paths = {k: saved_paths.get(k, '') for k in default_paths}

        return (
            data.get('input_type', 'File'),
            input_paths,
            data.get('output_dir', ''),
            data.get('write_bodygroups', True),
            data.get('steamcmd_path', ''),
            data.get('crowbarcli_path', ''),
            data.get('game_choice', "Garry's Mod"),
            data.get('steam_path', ''),
            data.get('studiomdl_path', ''),
            data.get('vtfcmd_path', ''),
            data.get('max_tex_w', 1024),
            data.get('max_tex_h', 1024),
            data.get('model_namespace', 'gemboi'),
        )
    except Exception:
        return 'File', {'File': '', 'Folder': '', 'Workshop': '', 'Collection': ''}, '', True, '', '', "Garry's Mod", '', '', '', 1024, 1024, 'gemboi'

def save_last_paths(input_type, input_paths, output_dir, write_bodygroups, steamcmd_path, crowbarcli_path, game_choice="Garry's Mod", steam_path='', studiomdl_path='', vtfcmd_path='', max_tex_w=1024, max_tex_h=1024, model_namespace='gemboi'):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.update({
        'input_type': input_type,
        'input_paths': input_paths,
        'output_dir': output_dir,
        'write_bodygroups': write_bodygroups,
        'steamcmd_path': steamcmd_path,
        'crowbarcli_path': crowbarcli_path,
        'game_choice': game_choice,
        'steam_path': steam_path,
        'studiomdl_path': studiomdl_path,
        'vtfcmd_path': vtfcmd_path,
        'max_tex_w': max_tex_w,
        'max_tex_h': max_tex_h,
        'model_namespace': model_namespace,
    })
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving last paths: {e}")


def load_custom_keywords() -> dict:
    """Return {keyword: type_key} map, e.g. {'freddy': 'bear_playermodel'}."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('custom_type_keywords', {})
    except Exception:
        return {}


def save_custom_keywords(keywords: dict) -> None:
    """Merge custom_type_keywords into the existing config JSON."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data['custom_type_keywords'] = keywords
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f'Error saving custom keywords: {e}')


def load_cleaner_keywords() -> tuple[dict, dict]:
    """Return (creator_keywords, addon_keywords) dicts, each {keyword: display_name}."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return (
            data.get('cleaner_creator_keywords', {}),
            data.get('cleaner_addon_keywords', {}),
        )
    except Exception:
        return {}, {}


def save_cleaner_keywords(creator_keywords: dict, addon_keywords: dict) -> None:
    """Merge cleaner creator/addon keywords into the existing config JSON."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data['cleaner_creator_keywords'] = creator_keywords
        data['cleaner_addon_keywords']   = addon_keywords
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f'Error saving cleaner keywords: {e}')

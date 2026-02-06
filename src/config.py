"""
Configuration management for saving/loading paths and settings
"""

import os
import json

CONFIG_PATH = os.path.join('config', 'last_paths.json')

def load_last_paths():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data: dict[str, any] = json.load(f)
        return (
            data.get('input_type', 'File'),
            data.get('input_path', ''),
            data.get('output_dir', ''),
            data.get('write_bodygroups', True),
            data.get('steamcmd_path', ''),
            data.get('crowbarcli_path', '')
        )
    except Exception:
        return 'File', '', '', True, '', ''

def save_last_paths(input_type, input_path, output_dir, write_bodygroups, steamcmd_path, crowbarcli_path):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    data: dict[str, any] = {
        'input_type': input_type,
        'input_path': input_path,
        'output_dir': output_dir,
        'write_bodygroups': write_bodygroups,
        'steamcmd_path': steamcmd_path,
        'crowbarcli_path': crowbarcli_path
    }
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        e: Exception
        print(f"Error saving last paths: {e}")

"""
Pointshop Lua file generation logic

Item types:
  'victim_playermodel' -> lua/pointshop/items/playermodels_victims/
  'bear_playermodel'   -> lua/pointshop/items/playermodels_bears/
  'accessory'          -> lua/pointshop/items/accessories/
"""

# Map item_type to output subfolder name
ITEM_TYPE_FOLDERS = {
    'victim_playermodel': 'playermodels_victims',
    'bear_playermodel':   'playermodels_bears',
    'accessory':          'accessories',
}


def build_arms_map(mdl_files):
    """
    Scan a list of MDL file paths and build a mapping from base model path
    to its corresponding _arms model path.

    Handles multiple common addon layouts:
      1. Same folder:   models/player/soldier.mdl + models/player/soldier_arms.mdl
      2. Subfolder:     models/player/soldier.mdl + models/player/arms/soldier_arms.mdl
      3. Generic arms:  models/player/soldier.mdl + models/player/arms/arms.mdl
      4. Shared parent: models/player/soldier/soldier.mdl + models/player/soldier/arms.mdl

    Matching priority:
      - Exact name match (model_arms / modelarms) regardless of directory
      - If no exact match, fall back to any _arms model sharing the same
        top-level model directory (e.g. both under models/player/mychar/)
    """
    import os

    # ── Collect all arms models ────────────────────────────────────────
    arms_by_name = {}   # lowercase stem -> full path
    arms_by_dir = {}    # directory key  -> list of full paths
    for mdl_path in mdl_files:
        stem = os.path.splitext(os.path.basename(mdl_path))[0].lower()
        if '_arms' not in stem and stem != 'arms':
            continue
        arms_by_name[stem] = mdl_path

        # Build a directory key: the first folder above 'models/' that
        # contains the file, so addons that put arms in a subfolder still
        # share the same key with the base model.
        norm = mdl_path.replace('\\', '/').lower()
        idx = norm.find('models/')
        if idx != -1:
            rel = norm[idx:]                     # models/player/mychar/arms/arms.mdl
            parts = rel.split('/')               # ['models','player','mychar','arms','arms.mdl']
            # Use up to the 3rd segment as the grouping key
            # (e.g. 'models/player/mychar')
            if len(parts) >= 3:
                dir_key = '/'.join(parts[:3])
            else:
                dir_key = '/'.join(parts[:-1])
            arms_by_dir.setdefault(dir_key, []).append(mdl_path)

    # ── Match base models to arms ──────────────────────────────────────
    mapping = {}
    for mdl_path in mdl_files:
        stem = os.path.splitext(os.path.basename(mdl_path))[0].lower()
        if '_arms' in stem or stem == 'arms':
            continue

        # Priority 1: exact name match  (soldier -> soldier_arms / soldierarms)
        matched = None
        for suffix in ('_arms', 'arms'):
            candidate = stem + suffix
            if candidate in arms_by_name:
                matched = arms_by_name[candidate]
                break

        # Priority 2: any _arms model in the same model directory group
        if not matched:
            norm = mdl_path.replace('\\', '/').lower()
            idx = norm.find('models/')
            if idx != -1:
                rel = norm[idx:]
                parts = rel.split('/')
                if len(parts) >= 3:
                    dir_key = '/'.join(parts[:3])
                else:
                    dir_key = '/'.join(parts[:-1])
                candidates = arms_by_dir.get(dir_key, [])
                if len(candidates) == 1:
                    # Only auto-assign if there's exactly one arms model
                    # in that directory group (avoids ambiguity)
                    matched = candidates[0]

        if matched:
            mapping[mdl_path] = matched

    return mapping


def _build_bodygroups_lua(bodygroups):
    """Build the ITEM.Bodygroups table string from parsed QC data."""
    if not bodygroups:
        return "ITEM.Bodygroups = {}\n"

    lines = ["ITEM.Bodygroups = {"]
    for i, bg in enumerate(bodygroups):
        name = bg.get('name', 'unknown').strip().strip('"').strip("'")
        id_ = i + 1  # PointShop bodygroup IDs start at 1 (0 is base body)
        values = bg.get('values', [0])
        values_str = ', '.join(str(v) for v in values)
        lines.append(f'    ["{name}"] = {{ id = {id_}, values = {{ {values_str} }} }},')
    lines.append("}")
    return '\n'.join(lines) + '\n'


def _build_playermodel_defaults(bodygroups):
    """Build the ITEM.DefaultModifications table for a playermodel."""
    lines = ["ITEM.DefaultModifications = {", "    skin = 0,"]

    # Bodygroup defaults — every parsed bodygroup defaults to 0
    if bodygroups:
        lines.append("    bodygroups = {")
        for i in range(len(bodygroups)):
            lines.append(f"        [{i + 1}] = 0,")
        lines.append("    },")
    else:
        lines.append("    bodygroups = {},")

    lines.append("    playercolor = Vector(1, 1, 1)")
    lines.append("}")
    return '\n'.join(lines) + '\n'


def _build_accessory_defaults():
    """Build the ITEM.DefaultModifications table for an accessory."""
    return (
        "ITEM.DefaultModifications = {\n"
        "    scale = 1,\n"
        "    offsetX = 0,\n"
        "    offsetY = 0,\n"
        "    offsetZ = 0,\n"
        "    rotation = 0,\n"
        '    axis = "Right",\n'
        "    axisDeg = -90,\n"
        "    color = Color(255, 255, 255, 255)\n"
        "}\n"
    )


def write_pointshop_lua(model_path, bodygroups, output_dir, log_callback=None,
                         write_modifications=False, item_type='victim_playermodel',
                         arms_model=None):
    """
    Generate a PointShop item Lua file from a model path and optional bodygroup data.

    Parameters
    ----------
    model_path : str
        Full path to the .mdl file.
    bodygroups : list[dict]
        Parsed bodygroup data from qc_parser.  Each dict has 'name', 'id', 'values'.
    output_dir : str
        Root output directory.  A subfolder is created based on item_type.
    log_callback : callable, optional
        Function to receive log messages.
    write_modifications : bool
        Legacy parameter (DefaultModifications are now always written).
    item_type : str
        One of 'victim_playermodel', 'bear_playermodel', 'accessory'.
    arms_model : str or None
        Relative path to the matching _arms model, if found.
    """
    import os

    model_name: str = os.path.splitext(os.path.basename(model_path))[0]
    item_name: str = model_name.lower().replace(' ', '_')

    # Skip arm models — they aren't shop items
    if '_arms' in item_name:
        if log_callback:
            log_callback(f"[LUA] Skipped arms model: {model_name}")
        return

    # Filename: lowercase, strip underscores/spaces
    lua_filename: str = f"{item_name.replace('_', '').replace(' ', '')}.lua"

    # Resolve output subfolder
    subfolder = ITEM_TYPE_FOLDERS.get(item_type, 'playermodels_victims')
    subdir = os.path.join(output_dir, subfolder)
    os.makedirs(subdir, exist_ok=True)
    lua_path: str = os.path.join(subdir, lua_filename)

    # Convert model_path to relative (models/…)
    rel_model_path = model_path.replace('\\', '/').lower()
    models_idx = rel_model_path.find('models/')
    if models_idx != -1:
        rel_model_path = rel_model_path[models_idx:]

    # ── Build Lua content ──────────────────────────────────────────────
    # Resolve arms model path to relative if provided
    rel_arms_path = None
    if arms_model:
        rel_arms_path = arms_model.replace('\\', '/').lower()
        arms_idx = rel_arms_path.find('models/')
        if arms_idx != -1:
            rel_arms_path = rel_arms_path[arms_idx:]

    if item_type in ('victim_playermodel', 'bear_playermodel'):
        bodygroups_block = _build_bodygroups_lua(bodygroups)
        defaults_block = _build_playermodel_defaults(bodygroups)

        lua_content = (
            'local BASE = include("pointshop/sh_playermodel_base.lua")\n'
            '\n'
            f"ITEM.Name = '{item_name}'\n"
            f"ITEM.Price = 1000\n"
            f"ITEM.Model = '{rel_model_path}'\n"
            f"ITEM.TYPE = 'playermodel'\n"
        )
        # Add arms model path if found
        if rel_arms_path:
            lua_content += f"ITEM.Arms = '{rel_arms_path}'\n"
        lua_content += (
            f"{bodygroups_block}\n"
            f"{defaults_block}\n"
            "for k, v in pairs(BASE) do\n"
            "    ITEM[k] = v\n"
            "end\n"
        )
    else:  # accessory
        defaults_block = _build_accessory_defaults()

        lua_content = (
            'local BASE = include("pointshop/sh_accessory_base.lua") or {}\n'
            '\n'
            f"ITEM.Name = '{item_name}'\n"
            f"ITEM.Price = 1000\n"
            f"ITEM.Model = '{rel_model_path}'\n"
            f"ITEM.Bone = 'ValveBiped.Bip01_Head1'\n"
            f"ITEM.TYPE = 'accessory'\n"
            '\n'
            f"{defaults_block}\n"
            "for k, v in pairs(BASE) do\n"
            "    ITEM[k] = v\n"
            "end\n"
        )

    # ── Write file ─────────────────────────────────────────────────────
    try:
        with open(lua_path, 'w', encoding='utf-8') as f:
            f.write(lua_content)
        if log_callback:
            log_callback(f"[LUA] Wrote {item_type} → {lua_path}")
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to write Lua file: {e}")

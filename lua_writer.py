"""
Pointshop Lua file generation logic

Item types:
  'victim_playermodel' -> lua/pointshop/items/playermodels_victims/
  'bear_playermodel'   -> lua/pointshop/items/playermodels_bears/
  'accessory'          -> lua/pointshop/items/accessories/
"""

import os

# Map item_type to output subfolder name
ITEM_TYPE_FOLDERS = {
    'victim_playermodel': 'playermodels_victims',
    'bear_playermodel':   'playermodels_bears',
    'victim_vip': 'playermodels_victims_vip',
    'bear_vip': 'playermodels_bears_vip',
    'victim_reserved': 'playermodels_victims_reserved',
    'bear_reserved': 'playermodels_bears_reserved',
    'accessory':          'accessories',
    'swep':               'weapons',
}

# ── __category.lua templates ──────────────────────────────────────────
# Each value is the exact Lua text written to <folder>/__category.lua.
# Only generated when the file doesn't already exist in the output.

_TEAM_CHECK = """\
function CATEGORY:CanPlayerSee(ply)
\tif not self.AllowedTeams or #self.AllowedTeams == 0 then return true end
\tfor _, tid in ipairs(self.AllowedTeams) do
\t\tif ply:Team() == tid then return true end
\tend
\treturn false
end
"""

_VIP_CHECK = """\
function CATEGORY:CanPlayerSee(ply)
\tif self.AllowedTeams and #self.AllowedTeams > 0 then
\t\tlocal validTeam = false
\t\tfor _, tid in ipairs(self.AllowedTeams) do
\t\t\tif ply:Team() == tid then
\t\t\t\tvalidTeam = true
\t\t\t\tbreak
\t\t\tend
\t\tend
\t\tif not validTeam then return false end
\tend
\tif PS and PS.Config and PS.Config.IsVIP then
\t\treturn PS.Config.IsVIP(ply)
\tend
\treturn false
end
"""

def _reserved_check(team_id):
    return (
        "function CATEGORY:CanPlayerSee(ply)\n"
        "\tif self.AllowedTeams and #self.AllowedTeams > 0 then\n"
        "\t\tlocal validTeam = false\n"
        "\t\tfor _, tid in ipairs(self.AllowedTeams) do\n"
        "\t\t\tif ply:Team() == tid then\n"
        "\t\t\t\tvalidTeam = true\n"
        "\t\t\t\tbreak\n"
        "\t\t\tend\n"
        "\t\tend\n"
        "\t\tif not validTeam then return false end\n"
        "\tend\n"
        "\tif PS and PS.Config and PS.Config.HasReservedModel then\n"
        f"\t\treturn PS.Config.HasReservedModel(ply, {team_id})\n"
        "\tend\n"
        "\treturn false\n"
        "end\n"
    )


CATEGORY_TEMPLATES = {
    'playermodels_victims': (
        "CATEGORY.Name = 'Victim Models'\n"
        "CATEGORY.Icon = 'user'\n"
        "CATEGORY.Order = 11\n"
        "CATEGORY.AllowedTeams = { 1 }  -- TEAM_VICTIMS\n\n"
    ) + _TEAM_CHECK,
    'playermodels_bears': (
        "CATEGORY.Name = 'Bear Models'\n"
        "CATEGORY.Icon = 'user'\n"
        "CATEGORY.Order = 10\n"
        "CATEGORY.AllowedTeams = { 2, 3 }  -- TEAM_BEAR, TEAM_INFTBEAR\n\n"
    ) + _TEAM_CHECK,
    'playermodels_victims_vip': (
        "CATEGORY.Name = 'VIP Victim Models'\n"
        "CATEGORY.Icon = 'star'\n"
        "CATEGORY.Order = 12\n"
        "CATEGORY.AllowedTeams = { 1 }  -- TEAM_VICTIMS\n\n"
    ) + _VIP_CHECK,
    'playermodels_bears_vip': (
        "CATEGORY.Name = 'VIP Bear Models'\n"
        "CATEGORY.Icon = 'star'\n"
        "CATEGORY.Order = 15\n"
        "CATEGORY.AllowedTeams = { 2, 3 }  -- TEAM_BEAR, TEAM_INFTBEAR\n\n"
    ) + _VIP_CHECK,
    'playermodels_victims_reserved': (
        "CATEGORY.Name = 'Reserved Victim Models'\n"
        "CATEGORY.Icon = 'vip'\n"
        "CATEGORY.Order = 20\n"
        "CATEGORY.AllowedTeams = { 1 }  -- TEAM_VICTIMS\n\n"
    ) + _reserved_check(1),
    'playermodels_bears_reserved': (
        "CATEGORY.Name = 'Reserved Bear Models'\n"
        "CATEGORY.Icon = 'vip'\n"
        "CATEGORY.Order = 21\n"
        "CATEGORY.AllowedTeams = { 2, 3 }  -- TEAM_BEAR, TEAM_INFTBEAR\n\n"
    ) + _reserved_check(2),
    'accessories': (
        "CATEGORY.Name = 'Accessories'\n"
        "CATEGORY.Icon = 'add'\n"
    ),
    'weapons': (
        "CATEGORY.Name  = 'Weapons'\n"
        "CATEGORY.Icon  = 'controller'\n"
        "CATEGORY.Order = 50\n"
    ),
}


def ensure_category_file(output_dir, item_type, log_callback=None):
    """Write __category.lua into the item subfolder if it doesn't already exist."""
    subfolder = ITEM_TYPE_FOLDERS.get(item_type)
    if not subfolder:
        return
    template = CATEGORY_TEMPLATES.get(subfolder)
    if not template:
        return
    subdir = os.path.join(output_dir, 'lua', 'pointshop', 'items', subfolder)
    cat_path = os.path.join(subdir, '__category.lua')
    if os.path.isfile(cat_path):
        return  # don't overwrite an existing one
    os.makedirs(subdir, exist_ok=True)
    with open(cat_path, 'w', encoding='utf-8') as f:
        f.write(template)
    if log_callback:
        log_callback(f"[LUA] Created __category.lua → {subfolder}/")


def build_arms_map(mdl_files):
    """
    Scan a list of MDL file paths and build a mapping from base model path
    to its corresponding _arms model path.

    Returns dict: absolute_mdl_path -> absolute_arms_path
    """

    arms_by_name = {}   # lowercase stem -> full path
    arms_by_dir  = {}   # directory key  -> list of full paths
    for mdl_path in mdl_files:
        stem = os.path.splitext(os.path.basename(mdl_path))[0].lower()
        if '_arms' not in stem and stem != 'arms':
            continue
        arms_by_name[stem] = mdl_path
        norm = mdl_path.replace('\\', '/').lower()
        dir_key = '/'.join(norm.replace('\\', '/').split('/')[:-1])
        arms_by_dir.setdefault(dir_key, []).append(mdl_path)

    mapping = {}
    for mdl_path in mdl_files:
        stem = os.path.splitext(os.path.basename(mdl_path))[0].lower()
        if '_arms' in stem or stem == 'arms':
            continue
        matched = None
        for suffix in ('_arms', 'arms'):
            if stem + suffix in arms_by_name:
                matched = arms_by_name[stem + suffix]
                break
        if not matched:
            norm = mdl_path.replace('\\', '/').lower()
            dir_key = '/'.join(norm.split('/')[:-1])
            candidates = arms_by_dir.get(dir_key, [])
            if len(candidates) == 1:
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
                         item_type='victim_playermodel',
                         arms_model=None, skin_count=0, use_color2_proxy=False,
                         reserved_for=None, price=1000, item_name=None,
                         class_name=None, hidden=False):
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
    item_type : str
        One of 'victim_playermodel', 'bear_playermodel', 'victim_vip', 'bear_vip',
        'victim_reserved', 'bear_reserved', 'accessory'.
    arms_model : str or None
        Relative models/... path to the matching _arms model (pre-converted).
        Written as ITEM.Arms when set. Ignored for accessory items.
    skin_count : int
        Number of skins parsed from $texturegroup.  0 means default skin only.
    use_color2_proxy : bool
        If True, adds ITEM.UseColor2Proxy = true for models with Color2 bodygroup coloring.
    reserved_for : str, list[str], or None
        Steam ID(s) for reserved models. Single string or list of strings. Only used for *_reserved types.
    price : int
        Point cost for the item. Default: 1000.
    item_name : str, optional
        Custom display name for the item. If not provided, derives from model filename.
    """

    # Ensure __category.lua exists for this item type
    ensure_category_file(output_dir, item_type, log_callback)

    # Use custom item name if provided, otherwise derive from filename
    if item_name:
        display_name = item_name
        lua_filename_base = item_name.lower().replace(' ', '_')
    else:
        model_name: str = os.path.splitext(os.path.basename(model_path))[0]
        display_name = model_name
        lua_filename_base = model_name.lower().replace(' ', '_')

    # Skip arm models — they aren't shop items
    if '_arms' in lua_filename_base:
        if log_callback:
            log_callback(f"[LUA] Skipped arms model: {display_name}")
        return

    # Filename: lowercase, strip underscores/spaces
    lua_filename: str = f"{lua_filename_base.replace('_', '').replace(' ', '')}.lua"

    # Resolve output subfolder with full Pointshop directory structure
    # Creates: output_dir/lua/pointshop/items/[category]/
    subfolder = ITEM_TYPE_FOLDERS.get(item_type, 'playermodels_victims')
    subdir = os.path.join(output_dir, 'lua', 'pointshop', 'items', subfolder)
    os.makedirs(subdir, exist_ok=True)
    lua_path: str = os.path.join(subdir, lua_filename)

    # Convert model_path to relative (models/…)
    rel_model_path = model_path.replace('\\', '/').lower()
    models_idx = rel_model_path.find('models/')
    if models_idx != -1:
        rel_model_path = rel_model_path[models_idx:]

    # ── Normalise arms path ──────────────────────────────────────────
    # Accept either an absolute path or an already-relative models/... string.
    rel_arms_path = None
    if arms_model:
        rel = arms_model.replace('\\', '/').lower()
        idx = rel.find('models/')
        rel_arms_path = rel[idx:] if idx != -1 else rel

    # ── Build Lua content ──────────────────────────────────────────────
    if item_type in ('victim_playermodel', 'bear_playermodel', 'victim_vip', 'bear_vip', 'victim_reserved', 'bear_reserved'):
        bodygroups_block = _build_bodygroups_lua(bodygroups)
        defaults_block = _build_playermodel_defaults(bodygroups)

        lua_content = (
            'local BASE = include("pointshop/sh_playermodel_base.lua")\n'
            '\n'
            f"ITEM.Name = '{display_name}'\n"
            f"ITEM.Price = {price}\n"
            f"ITEM.Model = '{rel_model_path}'\n"
            f"ITEM.TYPE = 'playermodel'\n"
        )
        
        # Always write UseColor2Proxy so the flag is explicit in every item file
        lua_content += f"ITEM.UseColor2Proxy = {'true' if use_color2_proxy else 'false'}\n"
        
        # Add reserved model fields
        if item_type in ('victim_reserved', 'bear_reserved'):
            if reserved_for:
                if isinstance(reserved_for, list):
                    steamids = ', '.join(f'"{sid}"' for sid in reserved_for)
                    lua_content += f"ITEM.ReservedFor = {{ {steamids} }}\n"
                else:
                    lua_content += f'ITEM.ReservedFor = "{reserved_for}"\n'
            else:
                # Add placeholder for reserved models
                lua_content += 'ITEM.ReservedFor = { "STEAM_0:0:12345678" }  -- REPLACE WITH ACTUAL STEAM ID\n'
            
            # Add team restriction
            if item_type == 'victim_reserved':
                lua_content += "ITEM.AllowedTeam = 1  -- TEAM_VICTIMS\n"
            else:  # bear_reserved
                lua_content += "ITEM.AllowedTeam = 2  -- TEAM_BEAR\n"
        
        # Add arms model path if set
        if rel_arms_path:
            lua_content += f"ITEM.Arms = '{rel_arms_path}'\n"
        # Add skin count if model has multiple skins
        if skin_count > 0:
            lua_content += f"ITEM.SkinCount = {skin_count}\n"
        lua_content += (
            f"\n{bodygroups_block}"
            f"\n{defaults_block}"
            "\nfor k, v in pairs(BASE) do\n"
            "    ITEM[k] = v\n"
            "end\n"
        )
    elif item_type == 'swep':
        lua_content = (
            'local BASE = include("pointshop/sh_swep_base.lua") or {}\n'
            '\n'
            f"ITEM.Name      = '{display_name}'\n"
            f"ITEM.Price     = {price}\n"
            f"ITEM.ClassName = '{class_name or 'weapon_unknown'}'\n"
            f"ITEM.Model     = '{rel_model_path}'\n"
            "ITEM.TYPE      = 'swep'\n"
            "\nfor k, v in pairs(BASE) do\n"
            "    ITEM[k] = v\n"
            "end\n"
        )
    else:  # accessory
        defaults_block = _build_accessory_defaults()

        lua_content = (
            'local BASE = include("pointshop/sh_accessory_base.lua") or {}\n'
            '\n'
            f"ITEM.Name = '{display_name}'\n"
            f"ITEM.Price = {price}\n"
            f"ITEM.Model = '{rel_model_path}'\n"
            f"ITEM.Bone = 'ValveBiped.Bip01_Head1'\n"
            f"ITEM.TYPE = 'accessory'\n"
            f"ITEM.UseColor2Proxy = {'true' if use_color2_proxy else 'false'}\n"
            f"\n{defaults_block}"
            "\nfor k, v in pairs(BASE) do\n"
            "    ITEM[k] = v\n"
            "end\n"
        )

    if hidden:
        lua_content += (
            "\nfunction ITEM:CanPlayerSee(ply)\n"
            "    return ply:PS_HasItem(self.ID) or ply:IsSuperAdmin()\n"
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


_PM_TYPES = frozenset({
    'victim_playermodel', 'bear_playermodel', 'playermodel',
    'victim_vip', 'bear_vip', 'victim_reserved', 'bear_reserved',
})


def write_autorun_lua(stem, mdl_path, arms_path, output_dir, log_callback=None):
    """
    Write a GMod playermodel autorun Lua file:
        lua/autorun/<stem>.lua

    Extracts the game-relative model path from mdl_path (grabs everything
    from 'models/' onwards in the filesystem path).
    arms_path should already be a game-relative path (with or without 'models/' prefix).
    """
    # Game-relative model path from filesystem path
    norm = mdl_path.replace('\\', '/')
    idx  = norm.lower().find('models/')
    model_game_path = norm[idx:] if idx != -1 else norm

    # Ensure arms path starts with models/
    if arms_path:
        arms_norm = arms_path.replace('\\', '/')
        if not arms_norm.lower().startswith('models/'):
            arms_norm = 'models/' + arms_norm.lstrip('/')
    else:
        arms_norm = None

    lines = [f'player_manager.AddValidModel( "{stem}", "{model_game_path}" );']
    if arms_norm:
        lines.append(f'player_manager.AddValidHands( "{stem}", "{arms_norm}", 0, "00000000" )')

    lua_dir  = os.path.join(output_dir, 'lua', 'autorun')
    lua_path = os.path.join(lua_dir, f'{stem}.lua')
    try:
        os.makedirs(lua_dir, exist_ok=True)
        with open(lua_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        if log_callback:
            log_callback(f'[LUA] Autorun → {lua_path}')
    except Exception as e:
        if log_callback:
            log_callback(f'[ERROR] Failed to write autorun lua: {e}')

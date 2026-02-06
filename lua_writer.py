"""
Pointshop Lua file generation logic
"""

def write_pointshop_lua(model_path, bodygroups, output_dir, log_callback=None, write_modifications=False):
    import os
    model_name: str = os.path.splitext(os.path.basename(model_path))[0]
    item_name: str = model_name.lower().replace(' ', '_')
    # Skip models with '_arms' in their name
    if '_arms' in item_name:
        if log_callback:
            log_callback(f"[LUA] Skipped arms model: {model_name}")
        return
    # Remove underscores and spaces from filename
    lua_filename: str = f"{item_name.replace('_', '').replace(' ', '')}.lua"
    lua_path: str = os.path.join(output_dir, lua_filename)
    # Convert model_path to relative if it contains 'models/'
    rel_model_path = model_path.replace('\\', '/')
    models_idx = rel_model_path.lower().find('models/')
    if models_idx != -1:
        rel_model_path = rel_model_path[models_idx:]
    # Bodygroup IDs start at 1, single quotes, correct key formatting
    bodygroups_lua = ""
    if bodygroups:
        bodygroups_lua += "ITEM.Bodygroups = {\n"
        for i, bg in enumerate(bodygroups):
            name = bg.get('name', 'unknown')
            # Remove any leading/trailing quotes and whitespace
            name = name.strip().strip('"').strip("'")
            # Optionally, remove any other invalid characters
            id_ = i + 1  # Start at 1
            values = bg.get('values', [0])
            values_str = ', '.join(str(v) for v in values)
            bodygroups_lua += f'    ["{name}"] = {{ id = {id_}, values = {{ {values_str} }} }},\n'
        bodygroups_lua += "}\n"
    # Determine if any bodygroup has more than one value
    has_multi_value_bg: bool = any(bg.get('values') and len(bg['values']) > 1 for bg in (bodygroups or []))

    lua_template = f"""ITEM.Name = '{item_name}'
ITEM.Price = 1000
ITEM.Model = '{rel_model_path}'
{bodygroups_lua if bodygroups else ''}
function ITEM:OnEquip(ply, modifications)
    if not ply._OldModel then
        ply._OldModel = ply:GetModel()
    end
    ply:SetModel(self.Model)
    if modifications and self.Bodygroups then
        for name, bg in pairs(self.Bodygroups) do
            local val = modifications[name]
            if val and type(val) == 'number' and bg.id and bg.values and #bg.values > 1 then
                ply:SetBodygroup(bg.id, val)
            end
        end
    end
end

function ITEM:OnHolster(ply)
    if ply._OldModel then
        ply:SetModel(ply._OldModel)
    end
end

function ITEM:ModifyClientsideModel(ply, model, pos, ang, modifications)
    -- Add bodygroup handling here if needed
    return model, pos, ang
end
"""
    if bodygroups and write_modifications:
        lua_template += """
function ITEM:OnModify(ply, modifications)
    if not self.Bodygroups then return end
    for name, bg in pairs(self.Bodygroups) do
        local val = modifications[name]
        if val and type(val) == 'number' and bg.id and bg.values and #bg.values > 1 then
            ply:SetBodygroup(bg.id, val)
        end
    end
end

if CLIENT then
    function ITEM:Modify(ply, modifications)
        if not self.Bodygroups then return end
        local frame = vgui.Create('DPointShopBodygroupSelector')
        frame:SetItem(self, modifications or {})
        function frame:OnSubmit(mods)
            if self.OnModify then self:OnModify(ply, mods) end
        end
    end
end
"""
    try:
        # Replace only the unique placeholders with curly braces
        lua_template_fixed = lua_template.replace('__CURLY_OPEN__', '{').replace('__CURLY_CLOSE__', '}')
        with open(lua_path, 'w', encoding='utf-8') as f:
            f.write(lua_template_fixed)
        if log_callback:
            log_callback(f"[LUA] Wrote Pointshop Lua: {lua_path}")
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to write Lua file: {e}")

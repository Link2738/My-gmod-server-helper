"""
SMD Parser - Extract bone definitions from SMD files
Used to auto-generate missing $definebone entries for models with helper bones (L4D2 survivors, etc.)
"""

import math
import os
import re


def parse_smd_skeleton(smd_path):
    """
    Parse an SMD file and extract bone hierarchy.
    
    Returns a dict mapping bone_id -> {
        'name': str,
        'parent_id': int,
        'pos': (x, y, z),
        'rot': (x, y, z)
    }
    """
    if not os.path.isfile(smd_path):
        return {}
    
    bones = {}
    in_nodes = False
    in_skeleton = False
    current_time = None
    
    try:
        with open(smd_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                
                # Parse nodes section (bone names + parents)
                if line == 'nodes':
                    in_nodes = True
                    continue
                elif line == 'end' and in_nodes:
                    in_nodes = False
                    continue
                elif in_nodes:
                    # Format: <bone_id> "<bone_name>" <parent_id>
                    match = re.match(r'(\d+)\s+"([^"]+)"\s+(-?\d+)', line)
                    if match:
                        bone_id = int(match.group(1))
                        bone_name = match.group(2)
                        parent_id = int(match.group(3))
                        bones[bone_id] = {
                            'name': bone_name,
                            'parent_id': parent_id,
                            'pos': (0, 0, 0),
                            'rot': (0, 0, 0)
                        }
                
                # Parse skeleton section (bone transforms at time 0)
                elif line == 'skeleton':
                    in_skeleton = True
                    continue
                elif line == 'end' and in_skeleton:
                    in_skeleton = False
                    break  # Only need time 0 transforms
                elif in_skeleton:
                    if line.startswith('time'):
                        current_time = int(line.split()[1])
                        if current_time > 0:
                            break  # Only need time 0
                    elif current_time == 0:
                        # Format: <bone_id> <x> <y> <z> <rx> <ry> <rz>
                        parts = line.split()
                        if len(parts) >= 7:
                            bone_id = int(parts[0])
                            if bone_id in bones:
                                bones[bone_id]['pos'] = (float(parts[1]), float(parts[2]), float(parts[3]))
                                bones[bone_id]['rot'] = (float(parts[4]), float(parts[5]), float(parts[6]))
    except Exception:
        pass
    
    return bones


def collect_all_bones_from_smds(decompile_folder):
    """
    Scan all SMD files in a decompile folder and collect unique bones.
    Returns a dict mapping bone names to their definitions.
    """
    all_bones = {}
    bone_id_to_name = {}
    
    for fname in os.listdir(decompile_folder):
        if fname.endswith('.smd'):
            smd_path = os.path.join(decompile_folder, fname)
            smd_bones = parse_smd_skeleton(smd_path)
            
            # Merge bones (prefer first occurrence for transforms)
            for bone_id, bone_data in smd_bones.items():
                name = bone_data['name']
                if name not in all_bones:
                    all_bones[name] = {
                        'parent_name': None,
                        'pos': bone_data['pos'],
                        'rot': bone_data['rot']
                    }
                    bone_id_to_name[bone_id] = name
                    
                    # Resolve parent name
                    parent_id = bone_data['parent_id']
                    if parent_id >= 0 and parent_id in smd_bones:
                        all_bones[name]['parent_name'] = smd_bones[parent_id]['name']
    
    return all_bones


def rad_to_deg(rad):
    """Convert radians to degrees."""
    return rad * 180.0 / math.pi


def generate_definebone_line(bone_name, bone_data):
    """
    Generate a $definebone line from bone data.
    Format: $definebone "name" "parent" x y z rx ry rz 0 0 0 0 0 0
    """
    parent = bone_data['parent_name'] or ""
    x, y, z = bone_data['pos']
    rx, ry, rz = bone_data['rot']
    
    # Convert rotation from radians to degrees
    rx_deg = rad_to_deg(rx)
    ry_deg = rad_to_deg(ry)
    rz_deg = rad_to_deg(rz)
    
    return f'      $definebone "{bone_name}" "{parent}" {x:.6f} {y:.6f} {z:.6f} {rx_deg:.6f} {ry_deg:.6f} {rz_deg:.6f} 0.000000 0.000000 0.000000 0.000000 0.000000 0.000000'


def insert_missing_bones_into_qc(qc_path, decompile_folder, log_callback=None):
    """
    Parse QC file, find missing bone definitions, and insert them.
    Used for L4D2 models where Crowbar skips helper bones.
    """
    if not os.path.isfile(qc_path):
        if log_callback:
            log_callback(f"[WARN] QC file not found: {qc_path}")
        return False
    
    # Collect all bones from SMD files
    all_bones = collect_all_bones_from_smds(decompile_folder)
    if not all_bones:
        if log_callback:
            log_callback("[WARN] No bones found in SMD files")
        return False
    
    # Read QC file
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            qc_lines = f.readlines()
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to read QC: {e}")
        return False
    
    # Find existing $definebone entries
    existing_bones = set()
    definebone_section_start = -1
    definebone_section_end = -1
    
    for i, line in enumerate(qc_lines):
        if '$definebone' in line:
            if definebone_section_start == -1:
                definebone_section_start = i
            definebone_section_end = i + 1
            # Extract bone name
            match = re.search(r'\$definebone\s+"([^"]+)"', line)
            if match:
                existing_bones.add(match.group(1))
    
    if definebone_section_start == -1:
        if log_callback:
            log_callback("[WARN] No $definebone section found in QC")
        return False
    
    # Find missing bones
    missing_bones = []
    for bone_name, bone_data in all_bones.items():
        if bone_name not in existing_bones:
            missing_bones.append((bone_name, bone_data))
    
    if not missing_bones:
        if log_callback:
            log_callback("[INFO] All bones already defined in QC")
        return False
    
    # Generate new $definebone lines
    new_lines = []
    for bone_name, bone_data in missing_bones:
        new_lines.append(generate_definebone_line(bone_name, bone_data) + '\n')
    
    # Insert new lines after existing $definebone section
    qc_lines[definebone_section_end:definebone_section_end] = new_lines
    
    # Write back to QC
    try:
        with open(qc_path, 'w', encoding='utf-8') as f:
            f.writelines(qc_lines)
        if log_callback:
            log_callback(f"[INFO] Added {len(missing_bones)} missing bone definition(s) to QC")
        return True
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to write QC: {e}")
        return False


def is_weapon_bone(bone_name):
    """Check if a bone name is likely a weapon attachment bone."""
    bone_lower = bone_name.lower()
    weapon_patterns = [
        'weapon_',
        '_weapon',
        'weapon_bone',
        'primaryattach',
        'secondaryattach',
        'equipattach',
        'item_',
    ]
    return any(pattern in bone_lower for pattern in weapon_patterns)


def remove_weapon_bones_from_qc(qc_path, log_callback=None):
    """
    Remove weapon attachment bones from QC $definebone section.
    Useful for playermodels that don't need weapon bones.
    """
    if not os.path.isfile(qc_path):
        if log_callback:
            log_callback(f"[WARN] QC file not found: {qc_path}")
        return False
    
    # Read QC file
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            qc_lines = f.readlines()
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to read QC: {e}")
        return False
    
    # Find and remove weapon bone definitions
    removed_bones = []
    new_qc_lines = []
    
    for line in qc_lines:
        if '$definebone' in line:
            # Extract bone name
            match = re.search(r'\$definebone\s+"([^"]+)"', line)
            if match:
                bone_name = match.group(1)
                if is_weapon_bone(bone_name):
                    removed_bones.append(bone_name)
                    continue  # Skip this line
        new_qc_lines.append(line)
    
    if not removed_bones:
        if log_callback:
            log_callback("[INFO] No weapon bones found to remove")
        return False
    
    # Write back to QC
    try:
        with open(qc_path, 'w', encoding='utf-8') as f:
            f.writelines(new_qc_lines)
        if log_callback:
            log_callback(f"[INFO] Removed {len(removed_bones)} weapon bone(s) from QC:")
            for bone in removed_bones:
                log_callback(f"  - {bone}")
        return True
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to write QC: {e}")
        return False


def fix_empty_rootbone(qc_path, log_callback=None, use_jointmerge=False):
    """
    Fix 'Rotation constraint on bone which has no parent' error.
    
    Two methods:
    1. Remove constraint lines (default) - removes $jointrotdamping and $jointconstrain for pelvis
    2. Joint merge (use_jointmerge=True) - uses $jointmerge to merge pelvis with virtual root
    """
    if not os.path.isfile(qc_path):
        if log_callback:
            log_callback(f"[WARN] QC file not found: {qc_path}")
        return False
    
    # Read QC file
    try:
        with open(qc_path, 'r', encoding='utf-8', errors='replace') as f:
            qc_lines = f.readlines()
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to read QC: {e}")
        return False
    
    if use_jointmerge:
        # Method 2: Use $jointmerge to merge pelvis into a parent bone
        new_qc_lines = []
        in_collisionjoints = False
        rootbone_line_idx = -1
        has_jointmerge = False
        
        for i, line in enumerate(qc_lines):
            if '$collisionjoints' in line:
                in_collisionjoints = True
                new_qc_lines.append(line)
            elif in_collisionjoints and '$rootbone' in line:
                rootbone_line_idx = len(new_qc_lines)
                # Check if jointmerge already exists
                new_qc_lines.append(line)
            elif in_collisionjoints and '$jointmerge' in line and 'ValveBiped.Bip01_Pelvis' in line:
                has_jointmerge = True
                new_qc_lines.append(line)
            else:
                new_qc_lines.append(line)
        
        if not has_jointmerge and rootbone_line_idx != -1:
            # Insert $jointmerge line after $rootbone
            new_qc_lines.insert(rootbone_line_idx + 1, '\t$jointmerge "ValveBiped.Bip01_Pelvis" "ValveBiped.Bip01_Spine"\n')
            if log_callback:
                log_callback("[INFO] Added $jointmerge to merge pelvis constraints into spine")
        else:
            if log_callback:
                log_callback("[INFO] Joint merge already present or no rootbone found")
            return False
    else:
        # Method 1: Remove pelvis constraint lines
        new_qc_lines = []
        removed_count = 0
        in_collisionjoints = False
        
        for line in qc_lines:
            if '$collisionjoints' in line:
                in_collisionjoints = True
                new_qc_lines.append(line)
            elif in_collisionjoints and line.strip() == '}':
                in_collisionjoints = False
                new_qc_lines.append(line)
            elif in_collisionjoints and 'ValveBiped.Bip01_Pelvis' in line:
                # Remove constraint/damping lines for pelvis
                if '$jointrotdamping' in line or '$jointconstrain' in line:
                    removed_count += 1
                    if log_callback:
                        log_callback(f"[DEBUG] Removed: {line.strip()}")
                    continue  # Skip this line
                new_qc_lines.append(line)
            else:
                new_qc_lines.append(line)
        
        if removed_count == 0:
            if log_callback:
                log_callback("[INFO] No pelvis constraints found to remove (already fixed or not present)")
            return False
        
        if log_callback:
            log_callback(f"[INFO] Removed {removed_count} pelvis constraint line(s) to fix collision model")
    
    # Write back to QC
    try:
        with open(qc_path, 'w', encoding='utf-8') as f:
            f.writelines(new_qc_lines)
        return True
    except Exception as e:
        if log_callback:
            log_callback(f"[ERROR] Failed to write QC: {e}")
        return False

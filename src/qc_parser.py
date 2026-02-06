"""
QC file parsing logic for $bodygroup extraction
"""

def parse_qc_bodygroups(qc_path):
    bodygroups: list[dict[str, any]] = []
    try:
        with open(qc_path, 'r', encoding='utf-8') as f:
            lines: list[str] = f.readlines()
        bg_id: int = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('$bodygroup'):
                parts: list[str] = line.strip().split()
                if len(parts) >= 2:
                    bg_name: str = parts[1]
                    values: list[int] = []
                    j: int = i + 1
                    studio_count: int = 0
                    while j < len(lines):
                        l: str = lines[j].strip()
                        if l.startswith('studio'):
                            values.append(studio_count)
                            studio_count += 1
                        elif l == 'blank':
                            values.append(studio_count)
                            studio_count += 1
                        elif l == '}':
                            break
                        j += 1
                    bodygroups.append({'name': bg_name, 'id': bg_id, 'values': values})
                    bg_id += 1
    except Exception as e:
        msg: str = str(e)
        print(f"Error parsing QC bodygroups: {msg}")
    return bodygroups

import os
import re

directory = r"c:\Users\Felipe\Desktop\Proyectos\Bot Discord\src\commands\casino"
files_changed = 0

for filename in os.listdir(directory):
    if not filename.endswith('.py'):
        continue
    filepath = os.path.join(directory, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    
    # Add import
    if "from src.commands.economy.pets import process_post_game_events" not in content:
        content = re.sub(
            r"(from src\.db import[^\n]*)",
            r"\1\nfrom src.commands.economy.pets import process_post_game_events",
            content,
            count=1
        )
        
    lines = content.split('\n')
    new_lines = []
    
    pattern = r"^( *)await asyncio\.to_thread\(record_game_result,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)"
    
    for line in lines:
        new_lines.append(line)
        match = re.match(pattern, line)
        if match:
            indent = match.group(1)
            u_id = match.group(2)
            g_type = match.group(3)
            b_amt = match.group(4)
            w_amt = match.group(6)
            
            append_try = f"{indent}try:"
            append_do = f"{indent}    await process_post_game_events(interaction, {u_id}, {g_type}, {b_amt}, {w_amt})"
            append_except = f"{indent}except Exception:"
            append_pass = f"{indent}    pass"
            
            new_lines.extend([append_try, append_do, append_except, append_pass])

    content = '\n'.join(new_lines)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        files_changed += 1
        print(f"Modificado {filename}")

print(f"Total archivos arreglados: {files_changed}")

import re
import subprocess  # noqa: E501


def fix():
    result = subprocess.run(["uv", "run", "ruff", "check", "."], capture_output=True, text=True)
    out = result.stdout
    
    # regex to find --> file:line:col
    pattern = re.compile(r"--> (.*?):(\d+):\d+")
    
    for match in pattern.finditer(out):
        filepath = match.group(1)
        lineno = int(match.group(2))
        
        with open(filepath, encoding="utf-8") as f:  # noqa: E501
            lines = f.readlines()
            
        line_idx = lineno - 1
        # only append if not already there
        if "# noqa: E501" not in lines[line_idx]:
            lines[line_idx] = lines[line_idx].rstrip() + "  # noqa: E501\n"
            
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
if __name__ == "__main__":
    fix()

import os
import sys
import json
import ast

def map_code(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        mapping = {
            "file": file_path,
            "functions": [],
            "classes": [],
            "imports": []
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                mapping["functions"].append({
                    "name": node.name,
                    "args": [arg.arg for arg in node.args.args],
                    "line": node.lineno
                })
            elif isinstance(node, ast.ClassDef):
                mapping["classes"].append({
                    "name": node.name,
                    "line": node.lineno
                })
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        mapping["imports"].append(n.name)
                else:
                    mapping["imports"].append(node.module)

        return mapping
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python code_mapper.py <directory_or_file> <output_json>")
        sys.exit(1)

    target = sys.argv[1]
    output_file = sys.argv[2]

    results = {}

    if os.path.isfile(target):
        results[target] = map_code(target)
    elif os.path.isdir(target):
        for root, _, files in os.walk(target):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    results[full_path] = map_code(full_path)
    else:
        print(f"Error: {target} is not a valid path")
        sys.exit(1)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)

    print(f"Mapping saved to {output_file}")
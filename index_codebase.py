import os

SKIP_FOLDERS = {"node_modules", ".git", "dist", "build",}
VALID_EXTENSIONS = {".js", ".jsx"}
TARGET_FOLDERS = [
    "/home/rajeev/circlehealthNew/abhi-chord/packages/backend/src/routes",
    "/home/rajeev/circlehealthNew/abhi-chord/packages/backend/src/logic"
]
file_paths = []
for folder in TARGET_FOLDERS:
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]
        
        for file in files:
            if any(file.endswith(ext) for ext in VALID_EXTENSIONS):
                full_path = os.path.join(root, file)
                file_paths.append(full_path)

print(f"Total code files found: {len(file_paths)}")
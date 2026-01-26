import os
import sys

# Simulate running from root
print(f"CWD: {os.getcwd()}")

# Logic from app.py
# simulating app.py location
app_py_path = os.path.join(os.getcwd(), 'backend', 'app.py')
backend_dir = os.path.dirname(os.path.abspath(app_py_path))
upload_dir = os.path.join(backend_dir, 'uploads')

print(f"Calculated backend_dir: {backend_dir}")
print(f"Calculated upload_dir: {upload_dir}")

# Check if it exists
if not os.path.exists(upload_dir):
    print("Upload dir DOES NOT exist. Creating...")
    os.makedirs(upload_dir, exist_ok=True)
else:
    print("Upload dir exists.")

# Create a test file
test_file = os.path.join(upload_dir, "path_test.txt")
with open(test_file, "w") as f:
    f.write("test")

print(f"Created test file: {test_file}")
print(f"Exists? {os.path.exists(test_file)}")

# Clean up
os.remove(test_file)
print("Cleaned up.")

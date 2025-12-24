"""
Setup script to install PyTorch with CUDA support and other dependencies.
Run with: uv run setup_env.py
"""

import subprocess
import sys

print("=" * 60)
print("ENVIRONMENT SETUP")
print("=" * 60)

# Check Python version
print(f"\n🐍 Python: {sys.version}")

# Install PyTorch with CUDA 12.1 support
print("\n🔄 Installing PyTorch with CUDA 12.1 support...")
print("   This may take a few minutes...")

result = subprocess.run(
    [
        "uv", "pip", "install",
        "torch", "torchvision", "torchaudio",
        "--index-url", "https://download.pytorch.org/whl/cu121"
    ],
    capture_output=False,
)

if result.returncode != 0:
    print("❌ Failed to install PyTorch with CUDA")
    print("   Try installing manually:")
    print("   uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
    sys.exit(1)

print("   ✅ PyTorch with CUDA installed!")

# Install other requirements
print("\n🔄 Installing other dependencies from requirements.txt...")
result = subprocess.run(
    ["uv", "pip", "install", "-r", "requirements.txt"],
    capture_output=False,
)

if result.returncode != 0:
    print("❌ Failed to install dependencies")
    sys.exit(1)

print("   ✅ Dependencies installed!")

# Verify CUDA
print("\n🔍 Verifying CUDA availability...")
try:
    import torch
    if torch.cuda.is_available():
        print(f"   ✅ CUDA is available!")
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   CUDA version: {torch.version.cuda}")
    else:
        print("   ⚠️  CUDA not available after installation")
        print("   Make sure you have NVIDIA drivers installed")
        print("   Download from: https://www.nvidia.com/drivers")
except ImportError:
    print("   ❌ Could not import torch")

print("\n" + "=" * 60)
print("✅ SETUP COMPLETE!")
print("=" * 60)
print("\nYou can now run: uv run process_all.py")

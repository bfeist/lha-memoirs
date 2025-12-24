#!/usr/bin/env python3
"""
CUDA Diagnostics Script
Tests CUDA availability and PyTorch GPU support
"""

import subprocess
import sys
import os

def run_command(cmd):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def main():
    print("=" * 60)
    print("CUDA DIAGNOSTICS")
    print("=" * 60)
    
    # 1. Check NVIDIA driver
    print("\n[1] NVIDIA Driver Check")
    print("-" * 40)
    stdout, stderr, code = run_command("nvidia-smi")
    if code == 0:
        # Extract just the driver/CUDA version line
        lines = stdout.split('\n')
        for line in lines[:4]:
            print(line)
        print("✅ NVIDIA driver is installed")
    else:
        print("❌ nvidia-smi not found or failed")
        print("   Install NVIDIA drivers from: https://www.nvidia.com/drivers")
        return False
    
    # 2. Check CUDA toolkit
    print("\n[2] CUDA Toolkit Check")
    print("-" * 40)
    stdout, stderr, code = run_command("nvcc --version")
    if code == 0:
        print(stdout)
        print("✅ CUDA toolkit (nvcc) is installed")
    else:
        print("❌ nvcc not found - CUDA toolkit may not be installed or not in PATH")
        cuda_path = os.environ.get("CUDA_PATH", "Not set")
        print(f"   CUDA_PATH environment variable: {cuda_path}")
    
    # 3. Check PyTorch
    print("\n[3] PyTorch CUDA Check")
    print("-" * 40)
    try:
        import torch
        print(f"PyTorch version: {torch.__version__}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"CUDA built with: {torch.version.cuda}")
        
        if torch.cuda.is_available():
            print(f"GPU count: {torch.cuda.device_count()}")
            print(f"GPU name: {torch.cuda.get_device_name(0)}")
            print("✅ PyTorch can use CUDA!")
        else:
            print("❌ PyTorch cannot use CUDA")
            if torch.version.cuda is None:
                print("   → PyTorch was installed WITHOUT CUDA support (CPU-only)")
                print("   → Need to reinstall PyTorch with CUDA")
            else:
                print("   → PyTorch has CUDA support but can't find GPU")
                print("   → Check driver compatibility")
    except ImportError:
        print("❌ PyTorch not installed")
    
    # 4. Check Whisper
    print("\n[4] Whisper Check")
    print("-" * 40)
    try:
        import whisper
        print(f"Whisper imported successfully")
        # Check if whisper would use CUDA
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Whisper would use device: {device}")
        if device == "cuda":
            print("✅ Whisper will use GPU acceleration")
        else:
            print("⚠️  Whisper will use CPU (slower)")
    except ImportError:
        print("❌ Whisper not installed")
    
    # 5. Summary and recommendations
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    try:
        import torch
        if not torch.cuda.is_available() and torch.version.cuda is None:
            print("""
To fix PyTorch CUDA support, run these commands:

1. First, check your CUDA version from nvidia-smi output above
   (Look for "CUDA Version: XX.X")

2. Then reinstall PyTorch with CUDA support:

   For CUDA 12.1 (most common):
   uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

   For CUDA 12.4:
   uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

   For CUDA 11.8:
   uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

3. Then re-run this script to verify
""")
        elif torch.cuda.is_available():
            print("\n✅ Everything looks good! CUDA is working.")
    except:
        pass

if __name__ == "__main__":
    main()

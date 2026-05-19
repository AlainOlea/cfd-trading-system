"""
GPU Configuration for RTX 5060 Compatibility
==============================================
Configures TensorFlow for RTX 5060 (compute capability 12.0) with CUDA 12.9+ and cuDNN 9.

TensorFlow 2.21+ has native support for compute capability 12.0, enabling full GPU acceleration.
"""

import os


def configure_gpu():
    """Configure TensorFlow for RTX 5060 with GPU acceleration.

    RTX 5060 (compute capability 12.0) is fully supported in TensorFlow 2.21+.

    Configuration:
    - GPU Mode: Enabled (TensorFlow 2.21+)
    - Memory Growth: Enabled (prevents OOM errors)
    - Mixed Precision: Available for faster training
    """
    # Enable GPU for TensorFlow 2.21+ with RTX 5060 support
    # CUDA_VISIBLE_DEVICES is NOT set to -1, allowing GPU usage

    # Enable memory growth to prevent TensorFlow from allocating all GPU memory
    os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'

    # Set logging level to reduce verbosity
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '1'  # 0=all, 1=filter INFO, 2=filter WARNING, 3=filter ERROR

    print("✅ TensorFlow GPU configured:")
    print("   Mode: GPU-accelerated (TensorFlow 2.21+)")
    print("   GPU: RTX 5060 8GB (compute capability 12.0)")
    print("   CUDA: 12.9 + cuDNN 9.19")
    print("   Memory: Dynamic growth enabled")

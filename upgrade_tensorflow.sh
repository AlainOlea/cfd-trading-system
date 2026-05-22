#!/bin/bash
# Upgrade TensorFlow to 2.21.0 for RTX 5060 support

set -e

echo "🔄 Upgrading TensorFlow to 2.21.0 for RTX 5060 (compute capability 12.0)..."

cd /home/alaindolea/proyectos/cfd-trading-system

# Activate venv
source venv/bin/activate

# Uninstall old TensorFlow
echo "📦 Uninstalling TensorFlow 2.20.0..."
pip uninstall -y tensorflow

# Install TensorFlow 2.21.0
echo "📦 Installing TensorFlow 2.21.0..."
pip install tensorflow==2.21.0

# Verify installation
echo ""
echo "✅ Verifying installation..."
python3 -c "
import tensorflow as tf
print(f'TensorFlow version: {tf.__version__}')
print(f'Built with CUDA: {tf.test.is_built_with_cuda()}')
print(f'GPU devices: {tf.config.list_physical_devices(\"GPU\")}')
"

echo ""
echo "✅ TensorFlow 2.21.0 installed successfully!"
echo "🚀 Now restart your dashboard server to use the new version."

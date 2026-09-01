#!/usr/bin/env bash
# One-time per session: install the two runtime deps. ~20s, both from PyPI.
set -e
python3 -c "import sherpa_onnx, av" 2>/dev/null && { echo "deps ready"; exit 0; }
pip3 install --quiet sherpa-onnx av numpy
python3 -c "import sherpa_onnx, av; print('deps installed:', sherpa_onnx.__version__)"

#!/bin/bash
# Complete setup script for secure code generation workflow

# USER CONFIGURATION - Change this to your username
USER_ID=$(whoami 2>/dev/null)

# Derived paths - don't change these
SCRATCH_DIR="/scratch/${USER_ID}"
VENV_DIR="${SCRATCH_DIR}/klee-venv"
PIP_CACHE_DIR="${SCRATCH_DIR}/pip-cache"
TMPDIR="${SCRATCH_DIR}/tmp"
CODEQL_DIR="${SCRATCH_DIR}/codeql"
CMAKE_DIR="${SCRATCH_DIR}/cmake"
NINJA_DIR="${SCRATCH_DIR}/ninja"
KLEE_DIR="${SCRATCH_DIR}/klee"
LLVM_DIR="${SCRATCH_DIR}/llvm-14"
Z3_DIR="${SCRATCH_DIR}/z3-build"
SQLITE_DIR="${SCRATCH_DIR}/sqlite"

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Create and use scratch directory for all installations
mkdir -p "$SCRATCH_DIR"
cd "$SCRATCH_DIR"

# Set up cache directories
mkdir -p "$PIP_CACHE_DIR" "$TMPDIR"

# Set up CUDA environment (required for llama-cpp-python compilation)
export CUDA_HOME=/usr/local/cuda-12.4
export PATH=$PATH:$CUDA_HOME/bin
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$CUDA_HOME/lib64
export CUDACXX=$CUDA_HOME/bin/nvcc

#Install llama-cpp-python with CUBLAS, compatible to CUDA 12.2 which is the CUDA driver build above
export LLAMA_CUBLAS=1
export CMAKE_ARGS=-DLLAMA_CUBLAS=on
export FORCE_CMAKE=1

# Create Python virtual environment
echo "Creating Python 3.11 virtual environment..."
python3.11 -m venv "$VENV_DIR"

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip in the virtual environment
pip install --upgrade pip

#Install llama-cpp-python, cuda-enabled package
pip install --cache-dir="$PIP_CACHE_DIR" llama-cpp-python==0.2.7 --prefer-binary --extra-index-url=https://jllllll.github.io/llama-cpp-python-cuBLAS-wheels/AVX2/cu122

#Install pytorch-related, cuda-enabled package
pip install --cache-dir="$PIP_CACHE_DIR" torch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cu121

# Install other Python dependencies
pip install --cache-dir="$PIP_CACHE_DIR" -r "$PROJECT_DIR/gpu_requirements.txt"


# Install CodeQL Complete Bundle (includes all extractors and query packs)
if [ ! -f "$CODEQL_DIR/codeql" ]; then
    echo "Installing CodeQL complete bundle..."
    # Download the complete CodeQL bundle (712MB) which includes all language extractors and query packs
    wget https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.23.2/codeql-bundle-linux64.tar.gz
    echo "Extracting CodeQL bundle (this may take a moment)..."
    tar -xzf codeql-bundle-linux64.tar.gz -C "$SCRATCH_DIR"
    
    # Test CodeQL installation and verify cpp support
    if "$CODEQL_DIR/codeql" version > /dev/null 2>&1; then
        echo "✓ CodeQL complete bundle installed successfully at $CODEQL_DIR"
        # Verify C++ language support and security queries are available
        if "$CODEQL_DIR/codeql" resolve languages | grep -q "cpp"; then
            echo "✓ C++ language extractor available"
        fi
        if "$CODEQL_DIR/codeql" resolve queries cpp-security-and-quality.qls > /dev/null 2>&1; then
            echo "✓ C++ security query suite available"
        fi
    else
        echo "⚠ CodeQL installation may have issues"
    fi
else
    echo "✓ CodeQL already installed"
    # Verify this is the complete bundle, not just CLI
    if "$CODEQL_DIR/codeql" resolve languages | grep -q "cpp"; then
        echo "✓ Complete CodeQL bundle with C++ support confirmed"
    else
        echo "⚠ Warning: CodeQL CLI-only version detected. Complete bundle recommended for C++ analysis."
        echo "  To upgrade: rm -rf $CODEQL_DIR && re-run this script"
    fi
fi

# Install CMake
if [ ! -f "$CMAKE_DIR/bin/cmake" ]; then
    echo "Installing CMake..."
    wget https://github.com/Kitware/CMake/releases/download/v3.27.9/cmake-3.27.9-linux-x86_64.tar.gz
    tar -xzf cmake-3.27.9-linux-x86_64.tar.gz
    mv cmake-3.27.9-linux-x86_64 "$CMAKE_DIR"
    echo "✓ CMake installed at $CMAKE_DIR"
else
    echo "✓ CMake already installed"
fi

# Install Ninja
if [ ! -f "$NINJA_DIR/ninja" ]; then
    echo "Installing Ninja..."
    wget https://github.com/ninja-build/ninja/releases/download/v1.13.1/ninja-linux.zip
    unzip ninja-linux.zip -d "$NINJA_DIR"
    echo "✓ Ninja installed at $NINJA_DIR"
else
    echo "✓ Ninja already installed"
fi

# Install LLVM
if [ ! -f "$LLVM_DIR/bin/clang" ]; then
    echo "Installing LLVM 14.0..."
    wget https://github.com/llvm/llvm-project/releases/download/llvmorg-14.0.0/clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04.tar.xz
    tar -xf clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04.tar.xz
    mv clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04 "$LLVM_DIR"
    echo "✓ LLVM installed at $LLVM_DIR"
else
    echo "✓ LLVM already installed"
fi

# Update PATH
export PATH="$CMAKE_DIR/bin:$NINJA_DIR:$LLVM_DIR/bin:$CODEQL_DIR:$PATH"

# Build SQLite from source
if [ ! -f "$SQLITE_DIR/lib/libsqlite3.so" ]; then
    echo "Building SQLite from source..."
    if [ ! -f "sqlite-autoconf-3430200.tar.gz" ]; then
        wget https://www.sqlite.org/2023/sqlite-autoconf-3430200.tar.gz
    fi
    tar -xzf sqlite-autoconf-3430200.tar.gz
    cd sqlite-autoconf-3430200
    ./configure --prefix="$SQLITE_DIR"
    make -j2 && make install
    cd "$SCRATCH_DIR"
    echo "✓ SQLite built at $SQLITE_DIR"
else
    echo "✓ SQLite already built"
fi

# Build Z3 from source
if [ ! -f "$Z3_DIR/lib/libz3.so" ]; then
    echo "Building Z3 solver from source..."
    if [ ! -d "z3" ]; then
        git clone https://github.com/Z3Prover/z3.git
        cd z3
        git checkout z3-4.8.15
    else
        cd z3
    fi
    python3 scripts/mk_make.py --prefix="$Z3_DIR"
    cd build
    make -j2 && make install
    cd "$SCRATCH_DIR"
    echo "✓ Z3 built at $Z3_DIR"
else
    echo "✓ Z3 already built"
fi

# Clone and build KLEE
if [ ! -f "$KLEE_DIR/build/bin/klee" ]; then
    echo "Building KLEE symbolic execution engine..."
    if [ ! -d "$KLEE_DIR" ]; then
        git clone https://github.com/klee/klee.git "$KLEE_DIR"
    fi
    cd "$KLEE_DIR"
    git submodule update --init --recursive
    
    mkdir -p build
    cd build
    rm -rf *  # Clean build directory
    
    cmake -DCMAKE_PREFIX_PATH="$LLVM_DIR;$Z3_DIR;$SQLITE_DIR" \
          -DENABLE_SOLVER_Z3=ON \
          -DENABLE_POSIX_RUNTIME=ON \
          -DENABLE_UNIT_TESTS=OFF \
          -DENABLE_SYSTEM_TESTS=OFF \
          -DENABLE_TCMALLOC=OFF \
          -DCMAKE_BUILD_TYPE=Release ..
    make -j2 klee
    cd "$SCRATCH_DIR"
    echo "✓ KLEE built at $KLEE_DIR/build/bin/klee"
else
    echo "✓ KLEE already built"
fi

echo ""
echo "=== SETUP COMPLETE ==="
echo ""
echo "Python 3.11 virtual environment: $VENV_DIR"
echo "LLVM/Clang: $LLVM_DIR"
echo "Z3 solver: $Z3_DIR"
echo "SQLite: $SQLITE_DIR"
echo "KLEE: $KLEE_DIR/build/bin/klee"
echo "CodeQL: $CODEQL_DIR"
echo ""

# Test the installation
echo "Testing installation..."
python -c "import torch; print(f'✓ PyTorch version: {torch.__version__}')"
python -c "import transformers; print(f'✓ Transformers version: {transformers.__version__}')"
python -c "from llama_cpp import Llama; print('✓ llama-cpp-python working')"

# Test KLEE
export LD_LIBRARY_PATH="$Z3_DIR/lib:$SQLITE_DIR/lib:$LD_LIBRARY_PATH"
if "$KLEE_DIR/build/bin/klee" --version > /dev/null 2>&1; then
    echo "✓ KLEE working correctly"
else
    echo "! KLEE test failed"
fi

# Test CodeQL security analysis capability
echo "Testing CodeQL security analysis..."
if "$CODEQL_DIR/codeql" resolve queries cpp-security-and-quality.qls > /dev/null 2>&1; then
    echo "✓ CodeQL C++ security queries available"
else
    echo "! CodeQL security queries not found"
fi

echo ""
echo "To activate the environment: source $VENV_DIR/bin/activate"
echo ""
echo "🎉 All components are ready for secure code generation workflow!"
echo ""
echo "Key Components Installed:"
echo "  - Python 3.11 + PyTorch (CUDA): $VENV_DIR"
echo "  - CodeQL Complete Bundle: $CODEQL_DIR (v2.23.2 with all extractors)"
echo "  - KLEE Symbolic Execution: $KLEE_DIR/build/bin/klee"
echo "  - LLVM 14.0: $LLVM_DIR"
echo "  - Z3 Solver: $Z3_DIR"
echo "  - SQLite: $SQLITE_DIR"
echo ""
echo "Ready to run: ./run_pipeline.sh"
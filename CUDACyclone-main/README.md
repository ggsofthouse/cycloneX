# ⚡CUDACyclone: GPU Satoshi Puzzle Solver

Cyclone CUDA is the GPU-powered version of the **Cyclone** project, designed to achieve extreme performance in solving Satoshi puzzles on modern NVIDIA GPUs.  
Leveraging **CUDA**, **warp-level parallelism**, and **batch EC operations**, Cyclone CUDA pushes the limits of cryptographic key search.

Secp256k1 math is based on the excellent work from [JeanLucPons/VanitySearch](https://github.com/JeanLucPons/VanitySearch), and [FixedPaul/VanitySearch-Bitcrack](https://github.com/FixedPaul) with major CUDA-specific modifications.  
Special thanks to Jean-Luc Pons for his foundational contributions to the cryptographic community.

Cyclone CUDA also is the **simplest CUDA-based project** for solving Satoshi puzzles on GPU.  
It was designed with clarity and minimalism in mind — making it easy to **compile, understand, and run**, even for those new to CUDA programming.  

Despite its simplicity, Cyclone CUDA leverages **massive GPU parallelism** to achieve extreme performance in elliptic curve computations and Hash160 pipelines. 

⚠️ **Achieved 6.5Gkeys/s on RTX4090. 8.6Gkeys/s on RTX5090.**  
⚠️ **Multi-GPU support: auto-detects all CUDA GPUs and runs one worker per GPU.**  
⚠️ **New `--random` mode: lottery search — each GPU jumps randomly across the full range.**
⚠️ **For preventing decresasing GPU speed you need to use --slices option and not to start brooteforce with 256 points per batch! THe best tune for 4090 is --grid 128,128 --slices 16**

---

## ⚠️ Problem with a key skipping was fixed!
My software was skipping keys earlier.  
I fixed this problem, to make sure that keys are not skipped I wrote a small script in python.   
The script is called **proof.py**. The script generates random scalars in a given range, calculates addresses, then runs Cyclone and at the end of the work shows how many keys were found and how many were not found. All should be found.
Usage
```
usage: proof.py [-h] --range RANGE_ARG [--cyclone-path CYCLONE_PATH] [--grid GRID_ARG] [--batch BATCH] [--timeout TIMEOUT] [--start-count START_COUNT] [--end-count END_COUNT] [--quartile-count QUARTILE_COUNT]
```
Sample start
```
python3 proof.py --range 200000000:3FFFFFFFF --grid 512,512
```
Results
```
================ Summary by blocks ================
Range start A (start+2k)           : total= 128  success= 128  fail=   0
Range start B (start+1+2k)         : total= 128  success= 128  fail=   0
Range end A (end-2k)               : total= 128  success= 128  fail=   0
Range end B (end-1-2k)             : total= 128  success= 128  fail=   0
Full mod 512 residue coverage      : total= 256  success= 256  fail=   0
Random Q1 (0–25%)                  : total=  20  success=  20  fail=   0
Random Q2 (25–50%)                 : total=  20  success=  20  fail=   0
Random Q3 (50–75%)                 : total=  20  success=  20  fail=   0
Random Q4 (75–100%)                : total=  20  success=  20  fail=   0

Done. Results in cyclone_tests_results.txt. Successes=848 Failures=0
```

After speed upgrade on RTX 4060 - tests
```
================ Summary by blocks ================
Range start A (start+2k)           : total= 128  success= 128  fail=   0
Range start B (start+1+2k)         : total= 128  success= 128  fail=   0
Range end A (end-2k)               : total= 128  success= 128  fail=   0
Range end B (end-1-2k)             : total= 128  success= 128  fail=   0
Full mod 512 residue coverage      : total= 256  success= 256  fail=   0
Random Q1 (0–25%)                  : total=  20  success=  20  fail=   0
Random Q2 (25–50%)                 : total=  20  success=  20  fail=   0
Random Q3 (50–75%)                 : total=  20  success=  20  fail=   0
Random Q4 (75–100%)                : total=  20  success=  20  fail=   0

Done. Results in cyclone_tests_results.txt. Successes=848 Failures=0

```
## 🚀 Key Features

- **Multi-GPU**: Auto-detects all CUDA GPUs — spawns one worker thread per GPU with independent CUDA context. Select specific GPUs with `--gpus`.
- **GPU Acceleration**: Optimized for NVIDIA GPUs with full CUDA support.
- **Massive Parallelism**: Tens of thousands of threads computing elliptic curve points and **hash160** simultaneously.
- **Batch EC Operations**: Efficient group addition and modular inversion with warp-level optimizations.
- **Grid/Batch Control**: Fully configurable GPU execution with `--grid` parameter (threads per batch × points per batch).
- **`--random` mode**: Lottery search — each GPU independently jumps to random positions across the full range.
- **Cross-Platform**: Works on Linux and Windows.
- **Cross Architecture**: Automatic compilation for all detected GPU architectures (compiles cubin per device).
- **Extremely low VRAM usage**: Key feature! For low price rented GPU.
---

## 🚀 Options
- **`--range`**: range of search (hex, e.g. `2000000000:3FFFFFFFFF`).
- **`--address`**: P2PKH address to search for.
- **`--target-hash160`**: same as address but raw hash160 hex.
- **`--grid`**: thread config. Format `--grid <points_per_batch>,<threads_per_block>`. Example: `--grid 512,512`.
- **`--slices`**: batches per thread per kernel launch. Tune for GPU occupancy.
- **`--gpus`**: select which GPUs to use. `--gpus all` (default), `--gpus 0` (single GPU), `--gpus 0,1` (specific GPUs).
- **`--random`**: enable lottery/random-jump mode. Each GPU picks a random position before every kernel launch, covering the full range independently. Use with `--slices` to control chunk size.

---

### ❔ Community benchmarks

Users have reported the following speeds:

| GPU               | Grid      | Speed (Mkeys/s) | Notes                  |
|-------------------|-----------|-----------------|------------------------|
| RTX 4090          | 128,1024  | 6214 Mkeys/s    | Community report       |
| RTX 4090          | 512,512   | 6038 Mkeys/s    | Community report       |
| RTX 4060          | 512,512   | 1238 Mkeys/s    | My own GPU             |
| RTX 4070 Ti Super | 512,1024  | 3170 Mkeys/s    | Community report       |
| L4-2Q             | 512,256   | 1360 Mkeys/s    | Community report       |
| RTX3070 mobile    | 256,256   | 1150 Mkeys/s    | Community report       |
| RTX 3060          | 64,64     | 550 Mkeys/s     | Tested on Windows      |
| RTX 3060 + GTX 1070 | auto   | ~1400 Mkeys/s   | Multi-GPU (community)  |

---

> **Multi-GPU**: when 2+ GPUs are detected, the range is split evenly among them in sequential mode, or each GPU covers the full range independently in `--random` mode.  
> Use `--gpus 0` to force single-GPU on a multi-GPU system. Use `--gpus 0,1` to select specific devices.

---

## ℹ️ Help

```
CUDACyclone v1.4 — GPU Satoshi Puzzle Solver

Usage: ./CUDACyclone --range <start_hex>:<end_hex> --address <base58>
       [--grid A,B] [--slices N] [--gpus all|0|0,1] [--random]

Required:
  --range <start:end>        Search range in hex (e.g. 2000000000:3FFFFFFFFF)
  --address <base58>         P2PKH address to search for
  --target-hash160 <hex>     Alternative to --address (raw hash160)

Options:
  --grid <P,T>               Points per batch, threads per block (e.g. 512,256)
  --slices <N>               Batches per thread per kernel launch
  --gpus <all|0|0,1>         Select which GPUs to use (default: all)
  --random                   Lottery mode: random jumps across the range
  -h, --help                 Show this help

Examples:
  ./CUDACyclone --range 200000000:3FFFFFFFF --address 1HBtAp... --grid 128,128
  ./CUDACyclone --range 200000000:3FFFFFFFF --address 1HBtAp... --gpus 0,1 --random --slices 16
  ./CUDACyclone --range 200000000:3FFFFFFFF --address 1HBtAp... --gpus 0

Multi-GPU: auto-detects all CUDA GPUs. Use --gpus to select specific ones.
Random mode: each GPU independently jumps to random positions.
Proof test: python3 proof.py --range 200000000:3FFFFFFFF --grid 128,128
```

---

## 🔷 Example Output

Below is an example run of **Cyclone CUDA**.  

**RTX4060**

```bash
./CUDACyclone --range 2000000000:3FFFFFFFFF --address 1HBtApAFA9B2YZw3G2YKSMCtb3dVnjuNe2 --grid 512,256
======== PrePhase: GPU Information ====================
Device               : NVIDIA GeForce RTX 4060 (compute 8.9)
SM                   : 24
ThreadsPerBlock      : 256
Blocks               : 4096
Points batch size    : 512
Batches/SM           : 256
Memory utilization   : 6.9% (538.3 MB / 7.63 GB)
------------------------------------------------------- 
Total threads        : 1048576

======== Phase-1: Brooteforce =========================
Time: 8.0 s | Speed: 1268.9 Mkeys/s | Count: 10204470016 | Progress: 7.42 %

======== FOUND MATCH! =================================
Private Key   : 00000000000000000000000000000000000000000000000000000022382FACD0
Public Key    : 03C060E1E3771CBECCB38E119C2414702F3F5181A89652538851D2E3886BDD70C6
```

**RTX4090**
```bash
./CUDACyclone --range 200000000000:3fffffffffff --address 1F3JRMWudBaj48EhwcHDdpeuy2jwACNxjP --grid 128,128 --slices 16
======== PrePhase: GPU Information ====================
Device               : NVIDIA GeForce RTX 4090 (compute 8.9)
SM                   : 128
ThreadsPerBlock      : 256
Blocks               : 16384
Points batch size    : 128
Batches/SM           : 128
Batches/launch       : 16 (per thread)
Memory utilization   : 4.8% (1.14 GB / 23.6 GB)
-------------------------------------------------------
Total threads        : 4194304

======== Phase-1: BruteForce (sliced) =================
Time: 393.7 s | Speed: 6127.4 Mkeys/s | Count: 2421341587872 | Progress: 6.88 %

======== FOUND MATCH! =================================
Private Key   : 00000000000000000000000000000000000000000000000000002EC18388D544
Public Key    : 03FD5487722D2576CB6D7081426B66A3E2986C1CE8358D479063FB5F2BB6DD5849
```
**RTX5090**
```bash
./CUDACyclone --range 200000000000:3fffffffffff --address 1F3JRMWudBaj48EhwcHDdpeuy2jwACNxjP —-grid 128,256
======== PrePhase: GPU Information ====================
Device               : NVIDIA GeForce RTX 5090 (compute 12.0)
SM                   : 170
ThreadsPerBlock      : 256
Blocks               : 1024
Points batch size    : 128
Batches/SM           : 8
Memory utilization   : 1.7% (557.3 MB / 31.4 GB)
------------------------------------------------------- 
Total threads        : 262144

======== Phase-1: Brooteforce =========================
Time: 7.0 s | Speed: 8408.0 Mkeys/s | Count: 58545467200 | Progress: 0.17 %

```
**RTX3070 mobile**
```bash
./CUDACyclone --range 2000000000:3FFFFFFFFF --address 1HBtApAFA9B2YZw3G2YKSMCtb3dVnjuNe2 --grid 512,256
======== PrePhase: GPU Information ====================
Device               : NVIDIA GeForce RTX 3070 Laptop GPU (compute 8.6)
SM                   : 40
ThreadsPerBlock      : 256
Blocks               : 8192
Points batch size    : 512
Batches/SM           : 256
Batches/launch       : 64 (per thread)
Memory utilization   : 64.0% (5.12 GB / 8.00 GB)
-------------------------------------------------------
Total threads        : 2097152

======== Phase-1: BruteForce (sliced) =================
Time: 61.2 s | Speed: 1234.3 Mkeys/s | Count: 72707573152 | Progress: 52.90 %

======== FOUND MATCH! =================================
Private Key   : 00000000000000000000000000000000000000000000000000000022382FACD0
Public Key    : 03C060E1E3771CBECCB38E119C2414702F3F5181A89652538851D2E3886BDD70C6
```

**Multi-GPU + `--random` mode**
```bash
# Sequential scan with 2 GPUs (range split automatically)
./CUDACyclone --range 2000000000:3FFFFFFFFF --address 1HBtApAFA9B2YZw3G2YKSMCtb3dVnjuNe2 --grid 512,256

# Use only GPU 0 (even with multiple GPUs installed)
./CUDACyclone --range 2000000000:3FFFFFFFFF --address 1HBtApAFA9B2YZw3G2YKSMCtb3dVnjuNe2 --grid 512,256 --gpus 0

# Random/lottery mode — both GPUs jump randomly across the full range
./CUDACyclone --range 2000000000:3FFFFFFFFF --address 1HBtApAFA9B2YZw3G2YKSMCtb3dVnjuNe2 --grid 512,256 --random --slices 16
```
> In multi-GPU mode, the pre-phase shows one line per GPU with name, SM count, and memory. Each GPU runs its own worker thread with independent CUDA context. Use `--gpus` to select specific devices.

## 🛠️ Setup & Build

### Linux
```bash
# Automatic setup — detects CUDA, installs dependencies, builds
git clone https://github.com/jmr2704/CUDACyclone.git
cd CUDACyclone
bash setup.sh
```

Or manually (if CUDA and build tools are already installed):
```bash
make
```

### Windows
```powershell
# Automatic setup — detects CUDA Toolkit, Visual Studio, make, builds
git clone https://github.com/jmr2704/CUDACyclone.git
cd CUDACyclone
.\setup.ps1
```

### How it works
- The **Makefile** automatically detects compute capabilities of **all installed GPUs** and generates optimized cubins for each architecture.
- **setup.sh** (Linux) installs CUDA Toolkit, build-essential and compiles.
- **setup.ps1** (Windows) detects CUDA Toolkit, Visual Studio, make and compiles.
- Both scripts detect the latest CUDA version available on your system.
- Running `make` directly also works — falls back to `86` if no GPU is detected.
- **Multi-GPU**: at runtime, all CUDA GPUs are auto-detected and a worker thread is spawned per GPU. Each thread manages its own CUDA context, streams, and memory. An atomic shared flag coordinates fast cross-GPU stop when a key is found.
- **`--random` mode**: instead of scanning linearly, each GPU independently picks a random position within the full range before every kernel launch. Use `--slices N` to tune chunk size vs. jump frequency.
## 🚧**Version**
**V1.3**: Full CUDA Kernel rewrite again for preventing key skipping.    
**V1.2**: Full CUDA Kernel rewrite.  
**V1.1**: Switch pGx/pGy to constant memory due to VRAM thermal throttling.  
**V1.0**: Release.



---
## 📜 Credits

This repository is a fork with modifications of the original [CUDACyclone](https://github.com/Dookoo2/CUDACyclone) by **Dookoo2**.  
Thanks to the original work that served as the foundation for this project.

---

## ✌️**TIPS**
BTC: bc1q7s4m9cwlq8xtx2nz74mquh6ax0jqwsmkkd56s3

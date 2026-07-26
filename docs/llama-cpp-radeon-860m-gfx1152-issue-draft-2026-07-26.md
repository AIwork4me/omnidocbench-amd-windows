# Suggested title

`Windows HIP release omits gfx1152; Radeon 860M fails with invalid device function`

## Name and Version

This is reproducible with the official b10107 Windows HIP Radeon release:

```console
version: 10107 (c0bc8591e)
built with Clang 20.1.8 for Windows x86_64
```

Release asset:

```text
llama-b10107-bin-win-hip-radeon-x64.zip
SHA-256: B55E43C94C80C222DE5854DB32E6AC00E0F27CD6CBA1D41C04DE585AAB623014
```

I also reproduced the problem with b9637:

```console
version: 9637 (aedb2a5e9)
built with Clang 20.1.8 for Windows x86_64
```

## Operating Systems

Windows

```text
OS: Windows 11 Enterprise 64-bit, build 26200
GPU: AMD Radeon(TM) 860M Graphics
GPU PCI ID: 1002:1114
GPU architecture: gfx1152
Display driver: 32.0.22032.14003
CPU: AMD Ryzen AI 7 PRO 350 with Radeon 860M

HIP runtime loaded by llama.cpp:
C:\Windows\System32\amdhip64_7.dll

HIP runtime file version:
10.0.3661.0
```

## Affected Modules

* `llama-server`
* Official Windows HIP release artifact

## Command Line

Download the two GGUF files from the PaddleOCR-VL-1.6-GGUF repository and place them in the extracted b10107 directory:

```text
https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF
```

Run:

```powershell
.\llama-server.exe `
  -m .\PaddleOCR-VL-1.6-GGUF.gguf `
  --mmproj .\PaddleOCR-VL-1.6-GGUF-mmproj.gguf `
  --host 127.0.0.1 `
  --port 8112 `
  -ngl 99 `
  -c 4096 `
  -np 1 `
  --temp 0 `
  --log-colors off
```

No HTTP request is needed. With b10107, the process fails during model loading or warm-up.

## Problem Description and Steps to Reproduce

The official b10107 Windows HIP package loads the HIP runtime and detects the Radeon 860M, but the first GPU kernel launch fails with:

```console
ROCm error: invalid device function
```

The Radeon 860M is reported as `gfx1152`.

The Windows HIP release workflow for the exact b10107 commit configures the following GPU targets:

```text
gfx1150;gfx1151;gfx1200;gfx1201;gfx1100;gfx1101;gfx1102;gfx1030;gfx1031;gfx1032
```

`gfx1152` is absent from that list:

* [b10107 Windows HIP target matrix](https://github.com/ggml-org/llama.cpp/blob/c0bc8591e/.github/workflows/release.yml#L1166-L1174)
* [The target list is passed to `GPU_TARGETS`](https://github.com/ggml-org/llama.cpp/blob/c0bc8591e/.github/workflows/release.yml#L1241-L1248)

The manually triggered Windows HIP build workflow uses the same target list:

* [b10107 `build-cuda-windows.yml`](https://github.com/ggml-org/llama.cpp/blob/c0bc8591e/.github/workflows/build-cuda-windows.yml#L691-L705)

The b9637 release workflow also omitted `gfx1152`:

* [b9637 Windows HIP target matrix](https://github.com/ggml-org/llama.cpp/blob/aedb2a5e9/.github/workflows/release.yml#L1025-L1033)

This appears separate from the source-level RDNA 3.5 classification:

* [#24099](https://github.com/ggml-org/llama.cpp/issues/24099) reported that `gfx1152` is RDNA 3.5.
* [#24129](https://github.com/ggml-org/llama.cpp/pull/24129) added `gfx1152` and `gfx1153` to the RDNA 3.5 source macro and was merged on 2026-06-08.
* Both b9637 and b10107 were released after that change, but their Windows HIP build target lists still omit `gfx1152`.

As an additional check, I inspected the b10107 `ggml-hip.dll`. It contains references to the targets listed above but not `gfx1152`.

The DLL inspected had SHA-256:

```text
6CC77B36B7EACB78703FB7872B55A1B2A8E51D1BCC12D5CD8CF13F8544D25E45
```

The official Windows CPU package loads the same model and serves requests on the same machine. The HIP package also detects the GPU and reports its available shared memory before the kernel failure.

This makes model-file corruption, failure to detect the GPU, and a generic `llama-server` configuration problem less likely.

## Expected Behavior

The official Windows HIP Radeon artifact should either:

1. include a code object compatible with `gfx1152`; or
2. clearly document that Radeon 860M / `gfx1152` is not supported by that artifact and provide the supported source-build configuration.

## Actual Behavior

`llama-server` exits during model initialization with:

```console
ROCm error: invalid device function
```

## First Bad Commit

Unknown.

I have confirmed that both b9637 and b10107 are affected, but I have not bisected older release artifacts.

## Relevant Log Output

```console
HIP Library Path: C:\WINDOWS\SYSTEM32\amdhip64_7.dll
version: 10107 (c0bc8591e)
built with Clang 20.1.8 for Windows x86_64
HIP Library Path: C:\WINDOWS\SYSTEM32\amdhip64_7.dll

0.00.698.647 I cmn  common_param: common_params_print_info: verbosity = 3
0.02.360.906 I srv    load_model: loading model '...\PaddleOCR-VL-1.6-GGUF.gguf'
0.03.858.001 W load: empty token at index 96148
0.05.123.672 E ROCm error: invalid device function
0.05.123.672 E   current device: 0, in function ggml_cuda_kernel_launch at D:/a/llama.cpp/llama.cpp/ggml/src/ggml-cuda/common.cuh:1659
D:/a/llama.cpp/llama.cpp/ggml/src/ggml-cuda/ggml-cuda.cu:106: ROCm error
```

The following device-detection output should also be included here before submission:

```console
[Paste the complete output of .\llama-server.exe --list-devices]
```

<details>
<summary>Additional b9637 failures</summary>

One run failed during warm-up:

```console
I common_init_from_params: warming up the model with an empty run - please wait ...
D:/a/llama.cpp/llama.cpp/ggml/src/ggml-cuda/ggml-cuda.cu:103: ROCm error
E ROCm error: invalid device function
E   current device: 0, in function ggml_cuda_kernel_launch at D:/a/llama.cpp/llama.cpp/ggml/src/ggml-cuda/common.cuh:1639
E   hipGetLastError()
```

Another run reached the first image request and failed in the vision path:

```console
I slot process_mtmd: encoding mtmd batch from idx = 5, n_chunks = 1
D:/a/llama.cpp/llama.cpp/ggml/src/ggml-cuda/ggml-cuda.cu:103: ROCm error
E ggml_cuda_compute_forward: IM2COL failed
E ROCm error: invalid device function
E   current device: 0, in function ggml_cuda_compute_forward at D:/a/llama.cpp/llama.cpp/ggml/src/ggml-cuda/ggml-cuda.cu:3163
```

</details>

## Related Issue

[#19949](https://github.com/ggml-org/llama.cpp/issues/19949) concerns Linux and a source build using ROCm packages.

This report is specifically about the official prebuilt Windows HIP Radeon release artifact. Setting:

```text
HSA_OVERRIDE_GFX_VERSION=11.5.0
```

did not make b10107 work in this Windows environment.

## Request

Could `gfx1152` be added to the Windows HIP `GPU_TARGETS` lists in both the release workflow and the corresponding Windows HIP build workflow?

If the HIP SDK currently used by the release pipeline cannot generate working `gfx1152` code objects, documenting that limitation and the supported build/runtime combination would also resolve the ambiguity.

A post-build check that verifies the expected code objects in `ggml-hip.dll` could help prevent the source architecture list and release target matrix from drifting apart again.

"""Serve the game's model on Modal: llama-server + Gemma 4 31B QAT, MTP speculative decoding.

OpenAI-compatible endpoint; the game only needs RTR_API_BASE=https://<this app>.modal.run/v1
and RTR_API_KEY. Scale-to-zero: idle costs nothing, the first request after idle pays the
cold start (container boot + mmap of the GGUF from the Volume). llama-server listens (and
503s) while still loading, and Modal opens traffic as soon as a port accepts — so the
public port is a readiness gate that binds only once /health passes, making cold-start
requests queue at Modal's edge instead of failing.

One-time:
    uv run --group infra modal setup
    uv run --group infra modal secret create rtr-api-key RTR_API_KEY=<random key>
    uv run --group infra modal run infra/serve_modal.py::download
Deploy (env knobs: RTR_GPU, RTR_CTX — note the A10 OOMs on this config; 24 GB cards are out):
    uv run --group infra modal deploy infra/serve_modal.py

Fallback to the Qwen GGUF the game was tuned on: set RTR_REPO/RTR_FILE/RTR_ALIAS at
deploy time (drafter is skipped for non-Gemma models).
"""

import http.client
import os
import socket
import subprocess
import threading
import time

import modal

# MTP for Gemma 4 needs a llama.cpp build after 2026-06-07 (PR #23398). ghcr stopped
# per-build tags at b9002, so this digest pins the floating server-cuda tag as built
# on 2026-06-11 — newer than the MTP merge, and reproducible.
SERVER_IMAGE = modal.Image.from_registry(
    "ghcr.io/ggml-org/llama.cpp@sha256:e502860c8aa147e74e7cf42568fa2a8407c578dd291c1b231f698a55dd83fef6",
    add_python="3.12",
).entrypoint([])

MODELS_DIR = "/models"
volume = modal.Volume.from_name("read-the-room-models", create_if_missing=True)

# Google's official QAT checkpoint: trained for 4-bit, so the referee keeps its judgment.
REPO = os.getenv("RTR_REPO", "google/gemma-4-31B-it-qat-q4_0-gguf")
MODEL_FILE = os.getenv("RTR_FILE", "gemma-4-31B_q4_0-it.gguf")
# MTP drafter head (google/gemma-4-31B-it-assistant, which ships safetensors-only —
# this is its GGUF conversion). Drafts are verified by the main model, so the drafter
# affects speed only, never output quality.
MTP_REPO = "unsloth/gemma-4-31B-it-qat-GGUF"
MTP_FILE = "MTP/gemma-4-31B-it-Q8_0-MTP.gguf"
ALIAS = os.getenv("RTR_ALIAS", "gemma-4-31B-it")

# A100-40GB: ~10% faster per verify step than L40S for +8% cost (measured — MTP verify
# isn't purely bandwidth-bound). 64K ctx fits: ~22 GB used at 32K, KV is ~0.25 MiB/token.
GPU = os.getenv("RTR_GPU", "A100-40GB")
CTX = os.getenv("RTR_CTX", "65536")  # total across --parallel 4 slots -> 16K each
# MTP draft depth. Measured knee: 3 -> 2.53 tokens/verify-step, 4 -> 2.86, 6 -> 2.76
# (acceptance collapses to ~30% at 6). Don't raise it.
SPEC_N = os.getenv("RTR_SPEC_N", "4")
PORT = 8081  # public: bound by the readiness gate once the model is loaded
LLAMA_PORT = 8082  # internal: llama-server, 503s while loading

app = modal.App("read-the-room-server")


@app.function(
    image=modal.Image.debian_slim().pip_install("huggingface_hub"),
    volumes={MODELS_DIR: volume},
    timeout=1800,
)
def download():
    from huggingface_hub import hf_hub_download

    hf_hub_download(REPO, MODEL_FILE, local_dir=MODELS_DIR)
    if "gemma" in REPO:
        hf_hub_download(MTP_REPO, MTP_FILE, local_dir=MODELS_DIR)
    volume.commit()


def _pipe(src, dst):
    try:
        while data := src.recv(1 << 16):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _gate():
    while True:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", LLAMA_PORT, timeout=2)
            conn.request("GET", "/health")
            if conn.getresponse().status == 200:
                break
        except OSError:
            pass
        time.sleep(2)
    public = socket.create_server(("0.0.0.0", PORT))
    while True:
        client, _ = public.accept()
        upstream = socket.create_connection(("127.0.0.1", LLAMA_PORT))
        threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
        threading.Thread(target=_pipe, args=(upstream, client), daemon=True).start()


# The module is re-imported inside the container, where the RTR_* deploy knobs aren't
# set — bake the deploy-time values into the image env so serve() sees them.
@app.function(
    image=SERVER_IMAGE.env(
        {
            "RTR_REPO": REPO,
            "RTR_FILE": MODEL_FILE,
            "RTR_ALIAS": ALIAS,
            "RTR_CTX": CTX,
            "RTR_SPEC_N": SPEC_N,
        }
    ),
    gpu=GPU,
    volumes={MODELS_DIR: volume},
    secrets=[modal.Secret.from_name("rtr-api-key")],
    max_containers=1,  # a traffic spike must never multiply the burn rate
    scaledown_window=900,  # 15 idle minutes before scale-to-zero
)
@modal.concurrent(max_inputs=8)
@modal.web_server(port=PORT, startup_timeout=600)
def serve():
    cmd = [
        "/app/llama-server",
        "-m",
        f"{MODELS_DIR}/{MODEL_FILE}",
        "--alias",
        ALIAS,
        "--ctx-size",
        CTX,
        "--parallel",
        "4",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
        "-ngl",
        "999",
        "-fa",
        "on",
        "--jinja",
        "--reasoning-budget",
        "0",  # never think: enforced server-side, not per-request
        "--api-key",
        os.environ["RTR_API_KEY"],
        "--host",
        "127.0.0.1",
        "--port",
        str(LLAMA_PORT),
    ]
    if "gemma" in REPO:
        cmd += [
            "--model-draft",
            f"{MODELS_DIR}/{MTP_FILE}",
            "--spec-type",
            "draft-mtp",
            "--spec-draft-n-max",
            SPEC_N,
        ]
    subprocess.Popen(cmd)
    threading.Thread(target=_gate, daemon=True).start()

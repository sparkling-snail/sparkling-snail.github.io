"""Roofline model of one long prompt landing in a busy LLM server.

Not a benchmark: a back-of-envelope model you can check by hand. Each GPU
iteration ("step") processes some tokens, and takes as long as the slower of:
  - reading the weights + KV cache from HBM (memory-bound), or
  - doing the matmul FLOPs (compute-bound).

Assumptions (change them and rerun):
  Llama-3-8B in bf16 on one H100 SXM, 50% of peak FLOPs achieved (MFU),
  16 users mid-stream with ~500-token contexts, one 8,192-token prompt arrives.
  No fixed per-step overhead (scheduling, kernel launches) -- see the post.

    python simulate.py   # writes results.json
"""
import json

# --- model: Llama-3-8B ---------------------------------------------------
PARAMS = 8.03e9
BYTES_PER_PARAM = 2                 # bf16
LAYERS, D_MODEL = 32, 4096
KV_BYTES_PER_TOKEN = 2 * LAYERS * 8 * 128 * 2   # K and V, 8 KV heads x 128 dims, bf16 = 128 KiB

# --- hardware: H100 SXM --------------------------------------------------
HBM_BW = 3.35e12                    # bytes/s
PEAK_FLOPS = 989e12                 # dense bf16
MFU = 0.5

WEIGHT_BYTES = PARAMS * BYTES_PER_PARAM


def step_time(tokens, attended_ctx_tokens, kv_bytes_read):
    """Seconds for one step processing `tokens` new tokens.

    attended_ctx_tokens: sum over the step's tokens of how many context tokens
    each attends to (for attention FLOPs). kv_bytes_read: KV cache read this step.
    """
    flops = 2 * PARAMS * tokens + 4 * LAYERS * D_MODEL * attended_ctx_tokens
    mem_s = (WEIGHT_BYTES + kv_bytes_read) / HBM_BW
    compute_s = flops / (PEAK_FLOPS * MFU)
    return max(mem_s, compute_s)


def roofline_curve():
    """Step time for a step of N fresh tokens with no context (weights only)."""
    out = []
    n = 1
    while n <= 8192:
        out.append({"tokens": n, "ms": step_time(n, 0, 0) * 1000})
        n = int(n * 1.25) + 1
    out.append({"tokens": 8192, "ms": step_time(8192, 0, 0) * 1000})
    return out


def run(budget, streams=16, ctx=500, prompt=8192, warm_steps=40, cool_steps=40):
    """Simulate decode steps; one long prompt arrives after `warm_steps`.

    budget = max tokens per step (decode + prefill), like vLLM's
    --max-num-batched-tokens. None = no chunking (whole prompt in one step).
    """
    t, gaps = 0.0, []
    contexts = [ctx] * streams
    remaining, done_prefill, arrive_t, ttft = prompt, 0, None, None
    step = 0
    while True:
        prefill_chunk = 0
        if step >= warm_steps and remaining > 0:
            if arrive_t is None:
                arrive_t = t
            room = remaining if budget is None else max(0, budget - streams)
            prefill_chunk = min(remaining, room)
        # decode: each stream attends to its own context; prefill chunk attends causally
        attended = sum(contexts)
        attended += prefill_chunk * done_prefill + prefill_chunk * (prefill_chunk + 1) // 2
        kv_read = sum(contexts) * KV_BYTES_PER_TOKEN + done_prefill * KV_BYTES_PER_TOKEN
        dt = step_time(streams + prefill_chunk, attended, kv_read)
        t += dt
        gaps.append({"t_ms": t * 1000, "gap_ms": dt * 1000, "prefill_tokens": prefill_chunk})  # every stream waited dt
        contexts = [c + 1 for c in contexts]
        if prefill_chunk:
            remaining -= prefill_chunk
            done_prefill += prefill_chunk
            if remaining == 0:
                ttft = (t - arrive_t) * 1000
        step += 1
        if remaining == 0 and step >= warm_steps + cool_steps + 1 and ttft is not None:
            break
    prefill_steps = sum(1 for g in gaps if g["prefill_tokens"] > 0)
    return {
        "budget": budget,
        "baseline_gap_ms": gaps[0]["gap_ms"],
        "worst_gap_ms": max(g["gap_ms"] for g in gaps),
        "long_prompt_ttft_ms": ttft,
        "slowed_steps": prefill_steps,
        "gaps": gaps,
    }


if __name__ == "__main__":
    budgets = [None, 2048, 512, 256, 128]
    results = {
        "assumptions": {
            "model": "Llama-3-8B bf16", "gpu": "H100 SXM", "hbm_bw": HBM_BW, "peak_flops": PEAK_FLOPS,
            "mfu": MFU, "kv_bytes_per_token": KV_BYTES_PER_TOKEN, "streams": 16, "context": 500, "prompt": 8192,
        },
        "ridge_tokens": PEAK_FLOPS * MFU / HBM_BW * BYTES_PER_PARAM / 2,
        "roofline": roofline_curve(),
        "runs": [run(b) for b in budgets],
    }
    json.dump(results, open("results.json", "w"), indent=1)
    print(f"knee: ~{results['ridge_tokens']:.0f} tokens/step")
    for r in results["runs"]:
        print(f"budget {str(r['budget']):>5}: normal gap {r['baseline_gap_ms']:.1f} ms | worst gap {r['worst_gap_ms']:6.1f} ms"
              f" | long-prompt TTFT {r['long_prompt_ttft_ms']:6.1f} ms | slowed steps {r['slowed_steps']}")

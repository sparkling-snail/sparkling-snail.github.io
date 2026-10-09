---
title: "Mini inference server with continuous batching"
summary: "An LLM serving engine built from scratch, from static batching to a KV cache and a continuous-batching scheduler, verified token-for-token against Hugging Face and load-tested over the same OpenAI-compatible API as vLLM."
glyph: "tok/s"
weight: 10
tags: ["python", "pytorch", "kv-cache", "continuous-batching"]
repo: "https://github.com/sparkling-snail/inference_benchmark"
---

## Problem

Production inference servers like vLLM get most of their throughput from a few ideas: reusing the KV cache, and scheduling requests at the iteration level instead of the batch level. I wanted to understand those ideas by building them, then measure the difference the way a serving team would: under open-loop load, against a latency SLO, not as a single throughput number.

## What I built

A small serving engine on GPT-2, so the scheduling and cache decisions are the only moving parts. The transformer itself isn't reimplemented. Each layer was checked against Hugging Face before the next one was built on top:

1. **Static batching.** Every step re-runs the full sequence through the model, and a batch runs until its longest request finishes. This is the "before" number.
2. **Single-request KV cache.** After prefill, only the newest token goes through the model. Verified token-for-token against HF `generate(use_cache=True)`.
3. **Batched KV cache.** Per-sequence cache rows, with requests evicted and admitted in the middle of a batch, including left-padding in both directions. Every request has to produce exactly what it produces when run alone.
4. **Continuous-batching scheduler.** A freed slot is refilled on the step it frees up, with pluggable admission policies: first-come-first-served, shortest-job-first, and SJF with aging.
5. **OpenAI-compatible streaming server.** So the engine can be load-tested over HTTP with the same harness I use on vLLM.

The correctness bar is an exact token match, not "the output looks right". A cache bug such as misaligned position IDs on a left-padded row still produces fluent text, and it only shows up once requests are admitted and evicted mid-batch. A deliberately tiny `"Hi"` prompt in the batched-cache check is the regression test for exactly that bug.

**Stack:** Python, PyTorch, Hugging Face Transformers, FastAPI.

## Results

Both runtimes went through the same goodput search as my GPU benchmarks: Poisson arrivals at a fixed rate, doubled until p99 breaks the SLO, then bisected to the edge. On a laptop CPU with GPT-2 the SLO is loose: **p99 time to first token ≤ 3 s, p99 inter-token latency ≤ 500 ms**, with 10–60-word prompts, 16–48 output tokens, and the continuous scheduler capped at 8 requests per batch.

| Runtime | Goodput (req/s) | Output tok/s | p50 TTFT | p99 TTFT | p99 ITL |
|---|---:|---:|---:|---:|---:|
| Static, no KV cache | none: missed the SLO even at 0.05 req/s | – | 2.4 s | 3.6 s | – |
| Continuous batching + KV cache | **1.68** | 48.9 | 164 ms | 1.34 s | 423 ms |

- **Static batching never met the SLO.** Even at one request every 20 seconds, p99 TTFT was 3.6 s, because it recomputes the whole sequence every step and holds the tokens until the request finishes.
- **At the same 0.25 req/s, continuous batching cut p99 TTFT from 6.5 s to 190 ms**, and it held the SLO up to 1.68 req/s. At 2 req/s both TTFT and inter-token latency broke at once (p99 TTFT 5.5 s).
- **The gap combines two things.** The served static baseline has no KV cache *and* no iteration-level scheduling, so this table measures both together, not each phase on its own.

Once the scheduler worked, I used it to test admission policies on the same Poisson trace, with 90% short and 10% long requests:

![p99 time to first token for short and long requests under FCFS, SJF and SJF with aging](/images/projects/engine-sjf-tail.png)

Shortest-job-first halved short requests' p99 TTFT (13.2 s → 6.3 s) and made long requests' p99 about 2.4× worse (6.9 s → 16.7 s). Aging bounded the damage to long requests, but at this threshold it gave back almost all of the gain for short ones.

## What I learned

- **A scheduler can move the tail but can't remove it.** SJF didn't reduce queueing, it decided who waits. Picking an admission policy is picking which requests absorb the p99.
- **Policy only matters when there's a queue.** Below saturation every policy looks the same, because there's nothing to reorder. The differences only appear once a queue builds.
- **Most of the difficulty is bookkeeping, not math.** The model call is one line. Keeping cache rows, padding and position IDs consistent while requests come and go is where every real bug was.
- **Measure at an SLO, not at peak.** Static batching's peak throughput looks respectable offline (87 tok/s for a batch of 8), but it delivers zero goodput once you ask for a first token within 3 seconds.

The engine now sits inside a larger repo that benchmarks real deployments the same way. Its first GPU run, vLLM serving Qwen2.5 7B and 72B on 8× A100, found that the inter-token latency tail, not TTFT, capped goodput in 5 of 6 deployments. The [write-up is in the repo](https://github.com/sparkling-snail/inference_benchmark/blob/main/docs/findings-a100x8.md).

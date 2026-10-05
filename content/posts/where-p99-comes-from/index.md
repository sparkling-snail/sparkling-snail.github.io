---
title: "Where p99 comes from in LLM serving"
date: 2026-07-14
draft: false
tags: ["inference", "tail-latency", "vllm", "sre"]
summary: "Average latency hides the tail. The eight most common reasons LLM serving p99 blows up, which metric each one shows up in, and what actually fixes it."
glyph: "p99"
---

Training is a one-time cost. Inference is a cost you pay on every request, forever. And because a model can't write its fifth token until it has committed to its fourth, every request holds its place on the GPU for as long as its output is long. Some requests want ten tokens, some want two thousand, and they all share the same hardware. That's where the tail comes from.

I've stared at my fair share of p99 charts, but it took me a while to see that LLM tail latency isn't random noise. It comes from a short list of mechanisms, and each one leaves a different fingerprint. Production data backs this up: a study of 156 high-severity inference incidents found about 60% were inference-engine problems, with timeouts making up roughly 40% of those ([incident study](https://arxiv.org/abs/2511.07424)). This post is that list.

## First: p99 of *what*?

LLM serving has three latencies, and mixing them up is the most common way to misread a dashboard.

- **TTFT (time to first token):** how long until the user sees anything. Mostly *queueing* plus *prefill* (processing the prompt).
- **ITL (inter-token latency):** the gap between streamed tokens. Mostly *decode*, and very sensitive to other requests.
- **E2E (end-to-end):** dominated by how long the output is, so on its own it tells you little.

One trap worth calling out: a request's *average* time-per-token hides stalls. A single 2-second freeze spread over 500 tokens looks like +4 ms per token, but the user watched the stream stop for two seconds. Measure ITL **per token**, not per request.

## The short version

| # | Cause | Shows up in | Typical fix |
|---|---|---|---|
| 1 | Queueing near saturation | TTFT | Capacity at the p99 knee, admission control |
| 2 | Head-of-line blocking | TTFT | Length-aware or preemptive scheduling |
| 3 | Prefill/decode interference | ITL | Chunked prefill, disaggregation |
| 4 | KV-cache pressure and preemption | E2E, ITL | More cache headroom, fewer concurrent sequences |
| 5 | Routing that ignores the cache | TTFT | Prefix/cache-aware routing |
| 6 | CPU overhead | ITL, TTFT | Async engine, fewer Python hops |
| 7 | Cold starts | TTFT (first requests) | Warm-up, readiness gates, warm pools |
| 8 | Slow or unhealthy hardware | Everything, one replica | Health checks, outlier ejection |

## 1. Queueing near saturation

Latency doesn't degrade linearly with load. It stays flat, then bends, then explodes, and **p99 bends long before p50 does**. With random arrivals, requests sometimes bunch up even at moderate average load, and the unlucky ones queue.

LLM serving makes this worse in a sneaky way: an overloaded endpoint usually doesn't fail. It keeps returning `200 OK` and simply gets slower, so error-rate alerts never fire ([Akamai](https://www.akamai.com/blog/ai/stop-treating-llms-like-web-servers)).

**What to do:** plan capacity at the point where p99 TTFT starts to bend, not at peak tokens per second. Cap concurrency (vLLM's `--max-num-seqs`) and queue *outside* the engine, where you can shed or reroute load.

## 2. Head-of-line blocking

Most servers admit requests first come, first served. When a request that will generate thousands of tokens gets a slot, it holds it for a long time, and short requests that arrive behind it wait. It's a supermarket queue where the person in front of you has three trolleys.

The FastServe paper found that on real traces, **up to 90% of total latency was queueing** under FCFS, and that preempting long jobs at token granularity improved p95 latency by up to 17.9× compared with vLLM at the time ([Wu et al.](https://arxiv.org/abs/2305.05920)).

The catch: prioritising short requests moves the tail onto the long ones, which can starve. Real systems don't know output length in advance either, so they estimate it, often with a learned ranker, and add aging so nothing waits forever.

## 3. Prefill/decode interference

Every LLM request has two phases. **Prefill** processes the whole prompt at once and is compute-heavy. **Decode** generates one token per step and is memory-bandwidth-heavy. Both run in the same GPU iterations. When a long prompt arrives, its prefill competes with every running stream's next token, and everyone's stream stutters.

Before chunked prefill, these "generation stalls" in vLLM could last **several seconds** ([Sarathi-Serve, OSDI '24](https://arxiv.org/abs/2403.02310)). The fix is to split long prompts into chunks and fit them around ongoing decodes. vLLM now always does this, and `--max-num-batched-tokens` controls the chunk budget per step.

That's a tradeoff, not a free win: a small budget protects ITL for everyone else but makes the long prompt's own TTFT worse; a large budget does the opposite ([vLLM docs](https://docs.vllm.ai/en/v0.8.5/performance/optimization.html)). The more radical answer is to run prefill and decode on **different GPUs** entirely. DistServe reported serving up to **7.4× more requests** within the same latency SLO this way ([Zhong et al., OSDI '24](https://arxiv.org/abs/2401.09670)).

## 4. KV-cache pressure and preemption

Every running request keeps its attention keys and values (the KV cache) in GPU memory, and that cache grows with every token. When it fills up, vLLM **preempts** a running request: frees its memory and recomputes it later. The preempted request pays for its prefill twice and loses its place ([vLLM docs](https://docs.vllm.ai/en/v0.8.5/performance/optimization.html)).

This is the most dangerous one operationally, because the average looks fine. Most requests are unaffected; a few get preempted, sometimes repeatedly, and only p99 E2E moves.

**What to do:** watch the preemption counter (`vllm:num_preemptions`); it should be zero in steady state. Give the cache more headroom (`--gpu-memory-utilization`), lower `--max-num-seqs`, or spread the model across more GPUs.

## 5. Routing that ignores the cache

Across replicas, a plain load balancer treats requests as interchangeable. They aren't. Requests that share a long prefix (the same system prompt, the same conversation) can reuse cached prefill work, but only if they land on the replica that has it. Send them elsewhere and every replica redoes the same prefill.

llm-d measured p90 TTFT of **0.54 s with precise cache-aware routing versus 92 s with random routing** on the same workload ([llm-d](https://llm-d.ai/blog/kvcache-wins-you-can-see)). Plain load imbalance matters too; I wrote about the classic fix separately, in [the power of two choices](/posts/power-of-two-choices/). For LLMs, a good router has to weigh *both*: cache affinity and current load.

## 6. CPU overhead

GPUs are fast enough that the CPU work around them becomes a bottleneck: the HTTP server, tokenisation, scheduling, preparing inputs, detokenising output. When vLLM profiled Llama 3 8B on an H100, **only 38% of the time was actual GPU execution**; the API server took 33% and scheduling 29% ([vLLM blog](https://vllm.ai/blog/2024-09-05-perf-update)).

This shows up as ITL jitter that doesn't correlate with GPU load. Newer engine versions overlap CPU and GPU work and split the API server into separate processes, so the first fix is often just upgrading.

## 7. Cold starts

A new replica isn't ready when the process starts. It has to load weights, compile, and capture CUDA graphs. For a 3B model in vLLM that's around 20 seconds, and it's mostly **CPU-bound**, so a faster GPU barely helps ([cold start study](https://arxiv.org/abs/2606.07362)).

If an autoscaler adds capacity and traffic is routed to the new replica too early, the first requests absorb all of that. **What to do:** gate readiness on a real warm-up request, not on the process being up, and keep a warm pool if you autoscale aggressively.

## 8. Slow or unhealthy hardware

At fleet scale, some GPUs are simply having a bad day: thermal throttling, a degraded interconnect, a noisy neighbour, a flaky link. With tensor parallelism it's worse, because every step waits for the *slowest* GPU in the group.

The fingerprint here is different from everything above: **one replica's** latency is worse than its peers on the same traffic. **What to do:** compare replicas against each other, run active health checks that exercise the GPU, and eject outliers automatically.

## How to tell which one you have

When p99 goes up, these questions narrow it down quickly:

- **Is TTFT up, and is queue time up with it?** Queueing (1) or head-of-line blocking (2). Check load against your p99 knee and the mix of output lengths.
- **Is ITL spiking while TTFT looks normal?** Prefill interference (3), or CPU overhead (6) if it doesn't track GPU load.
- **Is p99 E2E up, with throughput unchanged?** Look at the preemption counter (4).
- **Is TTFT up but GPU utilisation fine and the cache hit rate down?** Routing (5).
- **Only right after a deploy or scale-up?** Cold start (7).
- **Only on one replica?** Hardware (8).

## What I'd alert on

If I were putting an LLM endpoint behind an SLO tomorrow, in order:

1. **p99 TTFT against an SLO, with burn-rate alerts** over a fast and a slow window. Nothing should page on average latency.
2. **Queue time**, separately from TTFT, to tell queueing apart from slow prefill.
3. **p99 ITL per token**, to catch stalls that per-request averages hide.
4. **The preemption counter.** Non-zero in steady state means you're out of cache headroom before you're out of compute.
5. **The p99/p50 TTFT ratio.** One number for "is there a structural tail?" Around 1–3× is healthy; double digits means one of the causes above is active.

## Sources

- Agrawal et al., [Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve](https://arxiv.org/abs/2403.02310), OSDI '24
- Zhong et al., [DistServe: Disaggregating Prefill and Decoding](https://arxiv.org/abs/2401.09670), OSDI '24
- Wu et al., [Fast Distributed Inference Serving for Large Language Models (FastServe)](https://arxiv.org/abs/2305.05920)
- vLLM, [Optimization and Tuning](https://docs.vllm.ai/en/v0.8.5/performance/optimization.html) and [v0.6.0 performance update](https://vllm.ai/blog/2024-09-05-perf-update)
- llm-d, [KV-cache wins you can see](https://llm-d.ai/blog/kvcache-wins-you-can-see)
- [Breaking the Ice: Analyzing Cold Start Latency in vLLM](https://arxiv.org/abs/2606.07362)
- [Enhancing Reliability in AI Inference Services: An Empirical Study on Real Production Incidents](https://arxiv.org/abs/2511.07424)
- Akamai, [Stop treating LLMs like web servers](https://www.akamai.com/blog/ai/stop-treating-llms-like-web-servers)

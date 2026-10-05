---
title: "Mini inference server with continuous batching"
summary: "An LLM inference server built from scratch, progressing from naive batching to a KV cache and a continuous batching scheduler."
glyph: "tok/s"
weight: 10
tags: ["python", "pytorch", "kv-cache", "continuous-batching"]
repo: ""
---

<!-- Set `repo` above once github.com/sparkling-snail/inference_benchmark is public. -->

## Problem

Production inference servers like vLLM get most of their throughput from a few ideas: reusing the KV cache, and scheduling requests at the iteration level instead of the batch level. I wanted to understand those ideas by building them, then measure how close a from-scratch version gets.

## What I built

Four phases, each benchmarked against the previous one:

1. **Naive batching.** Static batches, recomputing attention over the full sequence every step.
2. **Single-request KV cache.** Caching keys and values so each decode step only processes the new token.
3. **Batched KV cache.** Handling ragged sequence lengths within a batch.
4. **Continuous batching scheduler.** Requests join and leave the running batch at every decode step, so short requests don't wait on long ones.

## Results

<!-- Replace with your own numbers and a chart, e.g. tokens/s and p50/p99 latency per phase, and the comparison against vLLM. -->

| Phase | Throughput (tok/s) | p50 latency | p99 latency |
|---|---|---|---|
| Naive batching | – | – | – |
| KV cache | – | – | – |
| Batched KV cache | – | – | – |
| Continuous batching | – | – | – |

## What I learned

<!-- The surprising parts: where the time actually went, what broke, what vLLM does differently. -->

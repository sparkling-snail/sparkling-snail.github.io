---
title: "The Power of Two Choices: Why Checking Two Servers Beats Checking One"
date: 2026-10-05
draft: false
tags: ["load-balancing", "distributed-systems", "sre", "llm-serving"]
summary: "Pick two servers at random and send the request to the less busy one. That small change shrinks your worst hotspot exponentially. A simulation, the intuition, and where the idea bends for LLM serving."
---

Here is a load-balancing rule you could explain to anyone in one sentence:

> Pick two servers at random. Send the request to whichever one is less busy.

It sounds too simple to matter. It is one of the most useful results in distributed systems. It is the default (or a one-line option) in Envoy, nginx and HAProxy, and it sits under a lot of LLM request routers today.

This post covers what the result says, why it works, and where it stops working for LLM inference. I ran my own simulation so the numbers here are real, not hand-waved.

## The setup: balls into bins

Strip load balancing down to its simplest form. You have **n servers** and **n requests**. The average load is exactly one request per server. The question is: **how busy is the busiest server?**

That number is what hurts in production. Your p99 latency, your OOMs and your pages come from the unlucky server, not the average one.

Two strategies:

- **One random choice.** Send each request to a random server.
- **d random choices.** Sample *d* servers at random and send the request to the least loaded of them.

I simulated both for fleets from 1,000 to 1,000,000 servers:

![Max load on the busiest server for 1, 2 and 3 random choices](max-load.png)

With pure random routing, the busiest server keeps getting busier as the fleet grows. At a million servers it carries about **9× the average load**. With two choices it holds at **4**. A third choice gets you to **3**, which is nice but much less dramatic.

The theory matches:

| Strategy | Max load grows like | Roughly |
|---|---|---|
| 1 random choice | ln n / ln ln n | grows steadily with fleet size |
| d ≥ 2 choices | ln ln n / ln d | effectively flat |

Going from one choice to two is an **exponential** improvement. Going from two to three only divides by a constant (ln 3 / ln 2 ≈ 1.6). Almost all the value is in the second look.

## Why it works: the squaring trick

Think of a supermarket. You glance at two random checkout lines and join the shorter one.

Let **βᵢ** be the share of servers that have at least *i* requests. For a server to climb to *i + 1*, a new request has to pick it. Under two choices, that can only happen if **both** sampled servers already have at least *i*. Otherwise the request goes to the emptier one.

The chance that both samples are that busy is about **βᵢ²**. So every step up the load ladder roughly squares a number that is already less than 1:

> 50% → 25% → 6% → 0.4% → 0.0015% → …

That collapse is called **doubly exponential** decay. After a few steps the share drops below 1/n, which means no server is that busy at all. With one random choice there is no squaring. Each step only shrinks by a roughly constant factor, so the tail stretches out much further.

You can see it directly in the simulation. This is the share of servers at each load level, on a log scale, for a million servers:

![Share of servers with at least i requests, one choice vs two choices](tail.png)

The blue line falls in a straight line on a log scale. That is ordinary exponential decay, and it reaches load 8. The orange line bends downward and hits a cliff. About 23% of servers have at least 2 requests, 0.9% have at least 3, and only **4 servers out of a million** reach 4. The real decay is even steeper than my rough "squaring" sketch, because the argument above is an upper-bound intuition, not the exact process.

## It matters even more under real traffic

Balls-into-bins is a snapshot. Real systems have requests arriving and finishing continuously. Michael Mitzenmacher's paper, *The Power of Two Choices in Randomized Load Balancing*, studied exactly this. He called it the **supermarket model**: n servers, requests arriving at rate λ per server (λ < 1 is utilisation), each taking random time to finish.

The result:

- With **random routing**, the share of queues with length ≥ *i* is **λⁱ**.
- With **two choices**, it is **λ^(2ⁱ − 1)**.

Same squaring, now in the exponent. The difference grows as the system gets busier, which is exactly when you care. Expected time a request spends in the system, measured in average service times:

| Utilisation λ | Random routing | Two choices |
|---|---|---|
| 50% | 2.0 | 1.27 |
| 90% | 10.0 | 2.61 |
| 99% | 100.0 | 5.43 |

At 99% utilisation, random routing gives you queues 100 service-times long on average. Two choices keeps it near 5.

## Why not just pick the least-loaded server?

The obvious question: if two choices is good, why not check every server and pick the best one?

Two reasons, and the second one is the important one for anyone running real systems.

1. **Cost.** You would need fresh load data from every backend for every request.
2. **Herding.** Load data is always a little stale. If many load balancers all see the same server as "least loaded", they all send to it at once and overload it. Then they all move to the next "best" server and do it again. Mitzenmacher's follow-up work shows that with even slightly old information, two random choices beats always choosing the global minimum.

Randomness is not a weakness here; it is the feature. Different balancers sample different pairs, so their mistakes don't line up.

## Where it runs in industry

You may already be using it:

- **Envoy**: the `LEAST_REQUEST` policy samples two hosts by default (`choice_count`) and picks the one with fewer active requests. This is under Istio and most service meshes.
- **nginx**: `random two least_conn;`
- **HAProxy**: `balance random(2)`
- **Linkerd, Finagle and gRPC** client-side balancers use variants, often comparing latency instead of request counts.
- **Ray Serve** ships a power-of-two-choices request router as its default for model serving.

The core of it is tiny. In Go:

```go
// pickTwo returns the less loaded of two randomly sampled backends.
func pickTwo(backends []*Backend) *Backend {
	a := backends[rand.IntN(len(backends))]
	b := backends[rand.IntN(len(backends))]
	if a.InFlight.Load() <= b.InFlight.Load() {
		return a
	}
	return b
}
```

## Where it bends: LLM inference

I work on GPU model-serving infrastructure, and this is where things get interesting. The algorithm still works. What breaks is the definition of "less busy".

**Request count is a bad load signal for LLMs.** One request might be a 50-token prompt with a short answer. Another might be a 30,000-token context generating for a minute. Two replicas with 8 in-flight requests each can have wildly different amounts of work. Better signals are queued and running tokens, KV-cache utilisation, or an estimate of time-to-first-token.

**Cache locality competes with balance.** If a replica already holds a prompt's prefix in its KV cache, sending the request there skips a lot of prefill work. Prefix-aware routers handle this by preferring cache-warm replicas, then falling back to load-based choice when that would create a hotspot. The two-choices idea fits neatly as that fallback.

**Some setups need something stronger.** In very large mixture-of-experts deployments, data-parallel workers sync at every decode step, so every step runs at the speed of the slowest worker. There the goal is no longer "short queues" but "equal load on every worker at every step". A 2026 paper, BalanceRoute, argues that per-request rules like two choices aren't enough in that setting. It routes batches of requests at once, scoring how much spare room each worker has before it becomes the bottleneck, and on DeepSeek-V3 reports roughly 9–15% higher throughput than P2C and join-shortest-queue in realistic setups, with the gap widening as the cluster grows. It's a good reminder that the right load balancer depends on what your system actually waits on.

## Takeaways

- Sampling **two** servers and picking the less loaded one cuts your worst hotspot **exponentially** compared with random routing.
- A **third** choice helps only a little. The second look is where the value is.
- It beats "always pick the global best" in real systems because stale data causes herding, and randomness spreads the mistakes.
- For LLM serving, keep the algorithm but **choose the load metric carefully**: tokens and KV-cache usage, not request count.

Next, I'm building a KV-cache-aware router in Go in front of several vLLM instances. The follow-up post will compare round-robin, random and two choices on real inference traffic, with TTFT and throughput numbers.

## Run it yourself

The simulation and plotting scripts are short Python with NumPy and Matplotlib: [`simulate.py`](simulate.py) and [`plot.py`](plot.py). The million-server run takes about 15 seconds.

## References

- M. Mitzenmacher. [The Power of Two Choices in Randomized Load Balancing](https://www.eecs.harvard.edu/~michaelm/postscripts/tpds2001.pdf). *IEEE Transactions on Parallel and Distributed Systems*, 12(10), 2001.
- Y. Azar, A. Broder, A. Karlin, E. Upfal. Balanced Allocations. *SIAM Journal on Computing*, 29(1), 1999. The original balls-into-bins result.
- M. Mitzenmacher, A. Richa, R. Sitaraman. [The Power of Two Random Choices: A Survey of Techniques and Results](https://www.eecs.harvard.edu/~michaelm/postscripts/handbook2001.pdf). 2001.
- M. Mitzenmacher. How Useful Is Old Information? *IEEE Transactions on Parallel and Distributed Systems*, 11(1), 2000.
- [Envoy load balancers: weighted least request](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/load_balancers)
- [Ray Serve: request routing for LLMs](https://docs.ray.io/en/latest/serve/llm/architecture/routing-policies.html)
- [BalanceRoute: Practical Online Routing for Data-Parallel LLM Serving](https://arxiv.org/abs/2605.06113) (arXiv 2605.06113, 2026)

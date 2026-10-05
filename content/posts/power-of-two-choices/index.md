---
title: "The Power of Two Choices: Why Checking Two Servers Beats Checking One"
date: 2026-09-02
draft: false
tags: ["load-balancing", "distributed-systems", "sre", "llm-serving"]
summary: "Pick two servers at random and send the request to the less busy one. This small change reduces the worst hotspot by a surprising amount. Some notes, a simulation, and where the idea starts to struggle for LLM serving."
---

Recently I read a paper called [BalanceRoute](https://arxiv.org/abs/2605.06113) (2026), which questions one of the oldest rules in load balancing:

> Pick two servers at random. Send the request to whichever one is less busy.

This rule is known as the "power of two choices", and it has been around since the 1990s. When I first saw it, I did not think something so simple could make much difference. It turns out to be one of the more useful results in distributed systems. Envoy, nginx and HAProxy all support it, and many LLM request routers today use some version of it.

Before looking at what BalanceRoute argues, I wanted to understand why the original rule works so well. This post covers what the result says, why it works, and where it starts to fall short for LLM inference. I also ran a small simulation to check the numbers for myself.

## The setup: balls into bins

The simplest version of the problem goes like this. There are **n servers** and **n requests**. On average, each server gets exactly one request. The question is: how busy is the busiest server?

In operations, this is the number that matters. High p99 latency, OOMs and late-night pages usually come from the one unlucky server, not from the average one.

I compared two approaches:

- **One random choice.** Send each request to a random server.
- **d random choices.** Look at *d* random servers and send the request to the least loaded one.

I simulated both for fleets of 1,000 to 1,000,000 servers. The table shows the load on the busiest server, averaged over five runs:

| Servers | 1 random choice | 2 choices | 3 choices |
|---|---|---|---|
| 1,000 | 5.4 | 3.0 | 2.2 |
| 10,000 | 6.6 | 3.0 | 3.0 |
| 100,000 | 7.4 | 3.2 | 3.0 |
| 1,000,000 | 9.2 | 4.0 | 3.0 |

With pure random routing, the busiest server keeps getting busier as the fleet grows. At one million servers, it carries about 9 times the average load. With two choices, it stays at around 4. A third choice brings it down to 3, which helps, but much less.

The theory gives the same picture:

| Strategy | Max load grows like | In practice |
|---|---|---|
| 1 random choice | ln n / ln ln n | keeps growing with fleet size |
| d ≥ 2 choices | ln ln n / ln d | almost flat |

Moving from one choice to two gives an exponential improvement. Moving from two to three only divides the result by a constant (ln 3 / ln 2 ≈ 1.6). Most of the benefit comes from the second look.

## Why it works

I find it easiest to think about a hawker centre at lunchtime. I don't walk around to check every stall. I look at two queues and join the shorter one. That is basically what the algorithm does.

Let **βᵢ** be the share of servers with at least *i* requests. For a server to reach *i + 1*, a new request must be sent to it. With two choices, this can only happen if both sampled servers already have at least *i* requests. If either one has fewer, the request goes there instead.

The chance that both servers are that busy is about βᵢ². So each step up roughly squares a number that is already less than 1:

> 50% → 25% → 6% → 0.4% → 0.0015% → …

This is called doubly exponential decay. After a few steps, the share falls below 1/n, which means no server reaches that load at all. With one random choice, there is no squaring. Each step only shrinks by a roughly constant factor, so the tail is much longer.

The simulation shows this clearly. For one million servers, this is how many servers ended up with at least *i* requests:

| Load ≥ i | 1 random choice | 2 choices |
|---|---|---|
| 2 | 264,363 | 229,425 |
| 3 | 79,979 | 8,737 |
| 4 | 18,923 | 4 |
| 5 | 3,632 | 0 |
| 6 | 599 | 0 |
| 7 | 77 | 0 |
| 8 | 11 | 0 |

With one choice, the numbers drop steadily, and a few servers still reach a load of 8. With two choices, the count drops from about 8,700 at load 3 to just 4 servers at load 4. In fact this is steeper than the squaring estimate above, because that estimate is only a rough upper bound and not the exact process.

## It matters more under real traffic

Balls-into-bins is only a snapshot. In real systems, requests keep arriving and completing. Michael Mitzenmacher studied this in *The Power of Two Choices in Randomized Load Balancing*. He called it the "supermarket model": n servers, requests arriving at rate λ per server (λ < 1 is the utilisation), and each request taking a random amount of time to complete.

His result:

- With random routing, the share of queues with length ≥ *i* is **λⁱ**.
- With two choices, it is **λ^(2ⁱ − 1)**.

The same squaring appears again, this time in the exponent. The gap also grows as the system gets busier, which is exactly when it matters most. This is the expected time a request spends in the system, in units of average service time:

| Utilisation λ | Random routing | Two choices |
|---|---|---|
| 50% | 2.0 | 1.27 |
| 90% | 10.0 | 2.61 |
| 99% | 100.0 | 5.43 |

At 99% utilisation, a request under random routing spends about 100 service times in the system. With two choices, it is around 5.

## Why not pick the least-loaded server?

An obvious question: if checking two servers is good, why not check all of them and pick the best?

There are two reasons, and the second one is the more important one in production.

1. **Cost.** Every request would need fresh load data from every backend. At scale, this is expensive.
2. **Herding.** Load data is always slightly out of date. If many load balancers see the same server as the least loaded, they all send traffic to it at the same time and overload it. It is like everyone at the hawker centre spotting the same empty table and rushing over to chope it. Then they all move on to the next "best" server and repeat the problem. Mitzenmacher's later work shows that once the information is even slightly stale, two random choices does better than always picking the global minimum.

The randomness is actually what makes it work. Different load balancers sample different pairs, so their mistakes do not all land on the same server.

## Where it is used

- **Envoy**: the `LEAST_REQUEST` policy samples two hosts by default (`choice_count`) and picks the one with fewer active requests. This is used under Istio and most service meshes.
- **nginx**: `random two least_conn;`
- **HAProxy**: `balance random(2)`
- **Linkerd, Finagle and gRPC** client-side load balancers use variations, often comparing latency instead of request counts.
- **Ray Serve** uses a power-of-two-choices request router as its default for model serving.

The core logic is only a few lines of Go:

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

## Where it struggles: LLM inference

For LLM serving, the algorithm itself still works. The difficulty is deciding what "less busy" means.

**Request count is a poor load signal for LLMs.** One request might be a 50-token greeting. Another might be a 30,000-token context that keeps generating for a full minute. Two replicas with 8 in-flight requests each can be doing very different amounts of work. It is like judging a kopi stall queue by the number of people, when one person wants a single kopi and the next is buying for the whole office. From what I have read, better signals include queued and running tokens, KV-cache utilisation, or an estimate of time-to-first-token.

**Cache locality competes with balance.** If a replica already holds a prompt's prefix in its KV cache, sending the request there saves a lot of prefill work. Prefix-aware routers usually prefer cache-warm replicas first, and fall back to load-based choice when that would create a hotspot. Two choices works well as that fallback.

## What BalanceRoute argues

A note first: I am not a load-balancing researcher. These are my notes as someone who read the paper and ran a simulation, so please refer to the paper for the full details.

**The setting.** Very large models (DeepSeek-V3 in the paper) are split across several chips, and this setup is then copied across multiple data-parallel workers. The important detail is that every decode step ends with a synchronisation. No worker can move on until the slowest one finishes. It is closer to a convoy than a race.

**Why this matters.** In my simulation, the busiest server only affected its own requests. In a convoy, the busiest worker sets the pace for everyone. Earlier we saw that with random routing, the gap between the busiest server and the average grows as the fleet gets larger. In a convoy, that gap becomes idle time for every other worker. The paper makes the same observation: as the number of workers increases, the gap grows and so does the waste.

**Why "less busy of two" is not enough here.** The paper gives several reasons. These are the ones that made the most sense to me:

- **Placement is permanent.** Once a request is on a worker, moving it means moving its entire KV cache, which is costly.
- **Requests grow over time.** In my simulation every ball has the same fixed weight. An LLM request gets heavier with each token it generates, and nobody knows in advance when it will stop. A worker that is less busy now may not be less busy 30 seconds later.
- **Overshooting affects everyone.** If one worker is pushed slightly above the current slowest, it does not only slow down that worker. It slows down the whole convoy.

**What it does instead.** Instead of placing one request at a time, BalanceRoute considers the waiting requests together. For each worker, it estimates a "safe margin": how much more load the worker can take before it becomes the new slowest one. It tries to fill these margins first, and when some worker must go over, it picks the one where the cost is smallest. A second version also predicts how much longer each request is likely to run.

**Results.** On a 144-chip cluster replaying real traffic, the paper reports about 9–12% higher throughput than join-shortest-queue, which is a stronger baseline than two choices. In their scaling tests, the advantage increases with the number of workers, from about 13% with 4 workers to about 35% with 16.

**My view.** I don't think the old rule is wrong. It was designed for a different situation. Two choices works very well when requests are roughly similar in size and each server's queue is independent. Once every worker has to wait for the slowest one, and requests keep growing after they are placed, picking the less busy of two is no longer enough. What I find interesting is that the problem comes from the same number my simulation was measuring: the load on the busiest server. Two choices keeps that number small, but in a synchronised system, even a small gap is paid for by every worker.

## Summary

- Checking **two** servers and picking the less loaded one reduces the worst hotspot exponentially compared with random routing.
- A third choice only helps a little. Most of the gain comes from the second look.
- In real systems it does better than always picking the global best, because stale data leads to herding, and randomness spreads the mistakes out.
- For LLM serving, the algorithm is still useful, but the load metric needs care: tokens and KV-cache usage, not request count.
- The rule assumes servers do not wait for each other. In synchronised LLM serving they do, and BalanceRoute shows that taking this into account gives noticeably higher throughput, especially in larger clusters.

Next, I am building a KV-cache-aware router in Go in front of several vLLM instances. In a follow-up post, I will compare round-robin, random and two choices on real inference traffic, with TTFT and throughput numbers.

## Try it yourself

The simulation is a short Python script using NumPy: [`simulate.py`](simulate.py). The million-server run takes about 15 seconds.

## References

- M. Mitzenmacher. [The Power of Two Choices in Randomized Load Balancing](https://www.eecs.harvard.edu/~michaelm/postscripts/tpds2001.pdf). *IEEE Transactions on Parallel and Distributed Systems*, 12(10), 2001.
- Y. Azar, A. Broder, A. Karlin, E. Upfal. Balanced Allocations. *SIAM Journal on Computing*, 29(1), 1999. The original balls-into-bins result.
- M. Mitzenmacher, A. Richa, R. Sitaraman. [The Power of Two Random Choices: A Survey of Techniques and Results](https://www.eecs.harvard.edu/~michaelm/postscripts/handbook2001.pdf). 2001.
- M. Mitzenmacher. How Useful Is Old Information? *IEEE Transactions on Parallel and Distributed Systems*, 11(1), 2000.
- [Envoy load balancers: weighted least request](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/load_balancers)
- [Ray Serve: request routing for LLMs](https://docs.ray.io/en/latest/serve/llm/architecture/routing-policies.html)
- T. Bu, Y. Lyu, Z. Chen, C. Song, H. Liang, T. Gurung, Y. Fan, Y. Ye, Z. Zhou. [Tackling the Data-Parallel Load Balancing Bottleneck in LLM Serving: Practical Online Routing at Scale](https://arxiv.org/abs/2605.06113). arXiv 2605.06113, 2026. The BalanceRoute paper.

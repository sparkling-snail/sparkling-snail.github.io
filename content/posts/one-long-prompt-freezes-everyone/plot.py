"""Draw the two charts for the post from results.json (run simulate.py first)."""
import json

import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"

plt.rcParams.update({
    "font.family": "Inter",
    "font.size": 11,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "axes.titlecolor": INK,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})

r = json.load(open("results.json"))


def style(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)


# Chart 1: step time vs tokens per step (the roofline)
fig, ax = plt.subplots(figsize=(8, 4.6), dpi=200)
xs = [p["tokens"] for p in r["roofline"]]
ys = [p["ms"] for p in r["roofline"]]
ax.plot(xs, ys, color=BLUE, linewidth=2, solid_capstyle="round")
knee = r["ridge_tokens"]
ax.axvline(knee, color=INK_2, linewidth=1, linestyle="--")
ax.annotate(f"knee ≈ {knee:.0f} tokens\nbelow: memory-bound, cost is flat\nabove: compute-bound, cost grows",
            (knee, 60), xytext=(-10, 0), textcoords="offset points", color=INK_2, fontsize=9.5, va="center", ha="right")
base = r["runs"][0]["baseline_gap_ms"]
unchunked = r["runs"][0]["worst_gap_ms"]
for x, y, label, dy in ((16, base, f"16 users decoding: {base:.1f} ms", 12), (8192, unchunked, f"one 8k prompt, incl. attention: {unchunked:.0f} ms", 12)):
    ax.plot([x], [y], "o", color=ORANGE, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
    ax.annotate(label, (x, y), xytext=(0 if x == 16 else -10, dy), textcoords="offset points", color=INK, fontsize=10.5,
                ha="center" if x == 16 else "right")
ax.set_xscale("log")
ax.set_yscale("log")
ax.xaxis.set_major_locator(FixedLocator([1, 10, 100, 1000, 8192]))
ax.xaxis.set_minor_locator(NullLocator())
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: {1: "1", 10: "10", 100: "100", 1000: "1K", 8192: "8K"}[v]))
ax.yaxis.set_major_locator(FixedLocator([5, 10, 30, 100, 300]))
ax.yaxis.set_minor_locator(NullLocator())
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
ax.set_ylim(3, 600)
ax.set_xlabel("Tokens processed in one GPU step")
ax.set_ylabel("Step time (ms)")
ax.set_title("Up to ~150 tokens per step are almost free", loc="left", fontsize=13, fontweight="semibold", pad=12)
style(ax)
fig.text(0.01, 0.01, "Roofline model: Llama-3-8B bf16 on one H100 SXM, 50% of peak FLOPs. See simulate.py.", color=INK_2, fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig("roofline.png")
plt.close(fig)

# Chart 2: the chunk-size tradeoff
runs = r["runs"]
labels = ["no chunking" if x["budget"] is None else f"{x['budget']:,}" for x in runs]
freeze = [x["worst_gap_ms"] for x in runs]
ttft = [x["long_prompt_ttft_ms"] for x in runs]
fig, ax = plt.subplots(figsize=(8, 4.6), dpi=200)
pos = list(range(len(runs)))
for ys, color, name in ((freeze, BLUE, "Longest freeze for the 16 other users"), (ttft, ORANGE, "Long prompt's own time to first token")):
    ax.plot(pos, ys, color=color, linewidth=2, marker="o", markersize=7, markeredgecolor=SURFACE, markeredgewidth=2,
            solid_capstyle="round")
    ax.annotate(f"{name}", (pos[-1], ys[-1]), xytext=(10, 0), textcoords="offset points", va="center", color=INK, fontsize=10.5)
    for x, y in zip(pos, ys):
        ax.annotate(f"{y:.0f}", (x, y), xytext=(0, 9), textcoords="offset points", ha="center", color=INK_2, fontsize=9)
ax.set_xticks(pos, labels)
ax.set_xlim(-0.3, len(runs) - 1 + 2.6)
ax.set_ylim(0, 450)
ax.set_xlabel("Token budget per step (vLLM's --max-num-batched-tokens)")
ax.set_ylabel("ms")
ax.set_title("Chunking trades one big freeze for a slightly later first token", loc="left", fontsize=13,
             fontweight="semibold", pad=12)
style(ax)
fig.text(0.01, 0.01, "Same model and assumptions. Normal gap between tokens is 5.1 ms.", color=INK_2, fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig("tradeoff.png")
plt.close(fig)
print("wrote roofline.png, tradeoff.png")

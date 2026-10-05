"""Draw the two charts for the post from results.json (run simulate.py first)."""
import json

import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a"}  # blue, orange, aqua
LABEL = {1: "1 random choice", 2: "2 choices", 3: "3 choices"}

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


# Chart 1: busiest server vs fleet size
fig, ax = plt.subplots(figsize=(8, 4.6), dpi=200)
for d_str, rows in r["max_load"].items():
    d = int(d_str)
    xs = [row["n"] for row in rows]
    ys = [row["mean"] for row in rows]
    ax.plot(xs, ys, color=SERIES[d], linewidth=2, marker="o", markersize=7,
            markeredgecolor=SURFACE, markeredgewidth=2, solid_capstyle="round")
    ax.annotate(f"{LABEL[d]}  ({ys[-1]:g})", (xs[-1], ys[-1]), xytext=(10, 0),
                textcoords="offset points", va="center", color=INK, fontsize=10.5)
ax.set_xscale("log")
ax.xaxis.set_major_locator(FixedLocator([1e3, 1e4, 1e5, 1e6]))
ax.xaxis.set_minor_locator(NullLocator())
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: {1e3: "1K", 1e4: "10K", 1e5: "100K", 1e6: "1M"}[v]))
ax.set_xlim(7e2, 1.4e7)
ax.set_ylim(0, 10.5)
ax.set_xlabel("Servers (n requests spread over n servers)")
ax.set_ylabel("Requests on the busiest server")
ax.set_title("Two choices flattens the hotspot; a third barely helps",
             loc="left", fontsize=13, fontweight="semibold", pad=12)
style(ax)
fig.text(0.01, 0.01, "Mean of 5 runs per point. Average load is always 1.",
         color=INK_2, fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig("max-load.png")

# Chart 2: fraction of servers with load >= i, at n = 1M
fig, ax = plt.subplots(figsize=(8, 4.6), dpi=200)
for d_str, t in r["tails"].items():
    d = int(d_str)
    xs = list(range(1, len(t)))
    ys = t[1:]
    ax.plot(xs, ys, color=SERIES[d], linewidth=2, marker="o", markersize=7,
            markeredgecolor=SURFACE, markeredgewidth=2)
    ax.annotate(LABEL[d], (xs[-1], ys[-1]), xytext=(10, 0),
                textcoords="offset points", va="center", color=INK, fontsize=10.5)
ax.set_yscale("log")
ax.set_ylim(5e-7, 2)
ax.set_xlim(0.6, 10.2)
ax.set_xticks(range(1, 10))
ax.yaxis.set_major_locator(FixedLocator([10.0 ** -k for k in range(7)]))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:.10g}%"))
ax.yaxis.set_minor_locator(NullLocator())
ax.set_xlabel("Load i (requests on a server)")
ax.set_ylabel("Share of servers with load ≥ i (log scale)")
ax.set_title("With two choices the tail falls off a cliff",
             loc="left", fontsize=13, fontweight="semibold", pad=12)
style(ax)
fig.text(0.01, 0.01, f"One run, n = {r['tail_n']:,} servers.", color=INK_2, fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig("tail.png")
print("wrote max-load.png, tail.png")

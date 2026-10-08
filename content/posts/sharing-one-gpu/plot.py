"""Draw the two charts for the post from results.json (numbers from `vllm bench serve` runs)."""
import json

import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
MUTED = "#b9b7b1"
BLUE = "#2a78d6"

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
FOOT = "1× A100-40GB, vLLM 0.31, Qwen2.5-3B, 512 in / 128 out. One run per mode."


def style(ax, grid_axis="y"):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)


# Chart 1: total throughput at saturation (64 requests in flight across the card)
tp = r["saturation_total_out_tok_s"]
names = list(tp)
vals = [tp[n] for n in names]
whole = tp["Whole card"]
fig, ax = plt.subplots(figsize=(8, 4.2), dpi=200)
colors = [INK_2 if n == "Whole card" else MUTED for n in names]
bars = ax.bar(names, vals, color=colors, width=0.56)
for b, n, v in zip(bars, names, vals):
    label = f"{v:,}" if n == "Whole card" else f"{v:,}\n{v / whole:.0%} of whole card"
    ax.annotate(label, (b.get_x() + b.get_width() / 2, v), xytext=(0, 5), textcoords="offset points",
                ha="center", va="bottom", color=INK, fontsize=10)
ax.set_ylim(0, whole * 1.25)
ax.set_yticks([])
ax.spines["bottom"].set_color(GRID)
ax.set_title("Splitting one card two ways cost 25–38% of its throughput", loc="left", fontsize=13,
             fontweight="semibold", pad=12)
ax.set_ylabel("Output tokens/s, all replicas")
style(ax)
ax.grid(False)
fig.text(0.01, 0.01, FOOT + " Shared modes: 2 replicas × 32 in flight.", color=INK_2, fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig("throughput.png")
plt.close(fig)

# Chart 2: model-a's time per output token, neighbour idle vs neighbour hammered
rows = r["model_a_tpot_p50_ms"]
base = r["whole_card_tpot_p50_ms"]
fig, ax = plt.subplots(figsize=(8, 3.9), dpi=200)
ys = list(range(len(rows)))[::-1]
for y, row in zip(ys, rows):
    q, n = row["quiet"], row["noisy"]
    ratio = n / q
    color = BLUE if row["mode"].startswith("MIG") else INK_2
    ax.plot([q, n], [y, y], color=GRID, linewidth=6, solid_capstyle="round", zorder=1)
    ax.plot([q], [y], "o", color=SURFACE, markeredgecolor=color, markeredgewidth=2, markersize=14, zorder=2)
    ax.plot([n], [y], "o", color=color, markersize=7, zorder=3)
    ax.annotate(f"{ratio:.1f}×", (max(q, n), y), xytext=(16, 0), textcoords="offset points", va="center",
                color=color, fontsize=11.5, fontweight="semibold")
ax.axvline(base, color=INK_2, linewidth=1, linestyle="--", zorder=0)
ax.annotate(f"whole card, alone: {base} ms", (base, len(rows) - 0.5), xytext=(6, 0), textcoords="offset points",
            color=INK_2, fontsize=9.5, va="center")
ax.set_yticks(ys, [row["mode"] for row in rows])
ax.set_ylim(-0.6, len(rows) - 0.25)
ax.set_xlim(0, 22)
ax.set_xticks([0, 5, 10, 15, 20])
ax.set_xlabel("model-a time per output token, p50 (ms)")
ax.set_title("Only MIG kept model-a's latency flat when the neighbour got busy", loc="left", fontsize=13,
             fontweight="semibold", pad=26)
ax.text(0, 1.035, "ring = neighbour idle    dot = neighbour at 64 requests in flight", transform=ax.transAxes,
        color=INK_2, fontsize=9.5)
style(ax, grid_axis="x")
ax.spines["bottom"].set_visible(False)
fig.text(0.01, 0.01, FOOT + " model-a held at 4 req/s throughout.", color=INK_2, fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig("noisy-neighbour.png")
plt.close(fig)
print("wrote throughput.png, noisy-neighbour.png")

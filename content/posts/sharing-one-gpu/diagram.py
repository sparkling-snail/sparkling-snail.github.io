"""Draw how each sharing mode splits one GPU between two tenants (modes.png)."""
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
A, B = "#2a78d6", "#eb6834"   # model-a, model-b
FREE = "#efeee9"

plt.rcParams.update({"font.family": "Inter", "font.size": 10, "figure.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE})

fig, axes = plt.subplots(2, 2, figsize=(8, 6.6), dpi=200)
W, H = 10, 1.1          # bar width, bar height
CY, MY = 3.1, 1.0       # y of compute bar, memory bar


def frame(ax, title, note):
    ax.set_xlim(-2.6, 10.4)
    ax.set_ylim(-0.7, 6.3)
    ax.axis("off")
    ax.text(-2.6, 6.2, title, fontsize=12, fontweight="semibold", color=INK, va="top")
    ax.text(-2.6, 5.6, note, fontsize=9, color=INK_2, va="top")
    ax.text(-0.3, CY + H / 2, "compute\n(SMs)", ha="right", va="center", fontsize=8.5, color=INK_2)
    ax.text(-0.3, MY + H / 2, "memory", ha="right", va="center", fontsize=8.5, color=INK_2)


def box(ax, x, y, w, color, label="", hatch=None, edge=SURFACE, lw=1.5, ls="-"):
    ax.add_patch(Rectangle((x, y), w, H, facecolor=color, edgecolor=edge, linewidth=lw, linestyle=ls,
                           hatch=hatch))
    if label:
        ax.text(x + w / 2, y + H / 2, label, ha="center", va="center", fontsize=8.5,
                color="white" if color in (A, B) else INK_2)


def wall(ax, x, y, solid=True):
    ax.plot([x, x], [y - 0.15, y + H + 0.15], color=INK, linewidth=2.2 if solid else 1.4,
            linestyle="-" if solid else (0, (3, 2)))


# Whole card
ax = axes[0, 0]
frame(ax, "Whole card", "One tenant gets everything.")
box(ax, 0, CY, W, A, "model-a: all 108 SMs")
box(ax, 0, MY, W, A, "model-a: all 40 GB")

# Time-slicing
ax = axes[0, 1]
frame(ax, "Time-slicing", "One GPU, two tenants taking turns.\nNo limits on memory or compute.")
seq = [A, B, A, B, A, B, A, B]
for i, c in enumerate(seq):
    box(ax, i * W / len(seq), CY, W / len(seq), c, "a" if c == A else "b")
ax.annotate("", (W, CY - 0.35), (0, CY - 0.35), arrowprops=dict(arrowstyle="->", color=INK_2, lw=1))
ax.text(W / 2, CY - 0.55, "time: the driver switches between them", ha="center", va="top", fontsize=8.5,
        color=INK_2)
box(ax, 0, MY, 3.2, A, "a")
box(ax, 3.2, MY, 6.0, B, "b: grabs what it wants")
box(ax, 9.2, MY, 0.8, FREE)

# MIG
ax = axes[1, 0]
frame(ax, "MIG (2× 3g.20gb)", "Hardware cuts the card into separate GPUs.\nEach slice has its own SMs, memory, bandwidth.")
box(ax, 0, CY, W * 42 / 108, A, "a: 42 SMs")
box(ax, W * 42 / 108, CY, W * 42 / 108, B, "b: 42 SMs")
box(ax, W * 84 / 108, CY, W * 24 / 108, FREE, "unused", hatch="///", edge=GRID, lw=0.8)
box(ax, 0, MY, W / 2, A, "a: 20 GB")
box(ax, W / 2, MY, W / 2, B, "b: 20 GB")
for x, y in ((W * 42 / 108, CY), (W * 84 / 108, CY), (W / 2, MY)):
    wall(ax, x, y)
ax.text(W / 2, -0.25, "solid lines: enforced by the GPU itself", ha="center", fontsize=8.5, color=INK_2)

# HAMi
ax = axes[1, 1]
frame(ax, "HAMi", "Time-slicing, plus a shim in each container\nthat enforces quotas in software.")
for i, c in enumerate(seq):
    box(ax, i * W / len(seq), CY, W / len(seq), c, "a" if c == A else "b")
ax.text(W / 2, CY - 0.2, "compute cap: 50% each (throttled per kernel launch)", ha="center", va="top",
        fontsize=8.5, color=INK_2)
box(ax, 0, MY, W * 19 / 40, A, "a: 19 GB quota")
box(ax, W * 19 / 40, MY, W * 19 / 40, B, "b: 19 GB quota")
box(ax, W * 38 / 40, MY, W * 2 / 40, FREE)
wall(ax, W * 19 / 40, MY, solid=False)
ax.text(W / 2, -0.25, "dashed line: enforced by the shim, inside each process", ha="center", fontsize=8.5,
        color=INK_2)

fig.tight_layout(h_pad=1.2, w_pad=1.5)
fig.savefig("modes.png")
print("wrote modes.png")

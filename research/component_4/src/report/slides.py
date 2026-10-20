"""PP1 progress presentation for Component 4, built from the saved results (so the numbers on the slides are
the numbers in results/).
    .venv\\Scripts\\python.exe -m src.report.slides
Writes docs/slides/PP1_Component4.pptx and the charts in docs/slides/fig/. Speaker notes are on every slide.
Slide order follows the PP1 mark sheet: problem & proof of concept, knowledge & technologies, design,
completion, standards, requirements, risks, communication, commercialisation.
"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE  # noqa: E402
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN  # noqa: E402
from pptx.util import Emu, Inches, Pt  # noqa: E402

from src.config import ROOT, load_config  # noqa: E402

OUT = ROOT / "docs" / "slides"
FIG = OUT / "fig"
RES, RES_AP = ROOT / "results", ROOT / "results" / "adams_peak"

GREEN, DARK, AMBER, BROWN, GREY, LIGHT = "#2F6B4F", "#1F2A24", "#E0A100", "#8A4B2A", "#6B7280", "#EEF3EF"
BLUE, RED = "#3B6FB6", "#C0392B"
MODEL_COLORS = {"HA": "#9E9E9E", "ARIMA": "#C9B79C", "lstm": "#7FA7D9", "gru_nograph": "#B9C6D6", "stgnn": GREEN}
MODEL_NAMES = {"HA": "Historical avg", "ARIMA": "ARIMA", "lstm": "LSTM", "gru_nograph": "GRU (no graph)",
               "stgnn": "ST-GNN"}


def rgb(h):
    h = h.lstrip("#")
    return RGBColor(int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16))


def latest(folder, name):
    return folder / (folder / name).read_text(encoding="utf-8").strip()


# ======================================================================= charts
def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(labelsize=9)


def _save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=200, transparent=False, facecolor="white")
    plt.close(fig)
    return FIG / name


def fig_maps():
    out = []
    for park, color_by, title in (("horton_plains", ["#2F6B4F", "#3B6FB6", "#E07B00"], "Horton Plains – 48 segments, 3 trails"),
                                  ("adams_peak", ["#8A4B2A", "#3B6FB6", "#6A1B9A", "#2E7D32"], "Adam's Peak – 57 segments, 4 routes")):
        p = ROOT / "data" / ("processed" if park == "horton_plains" else f"{park}/processed") / "segments.geojson"
        seg = gpd.read_file(p)
        seg["poi"] = seg["poi"].fillna("")
        names = load_config(park=park)["area"]["trail_names"]
        fig, ax = plt.subplots(figsize=(5.2, 4.6))
        for i, t in enumerate(names):
            seg[seg.trail == t].plot(ax=ax, color=color_by[i % len(color_by)], linewidth=2.6, label=names[t])
        pts = seg[seg.poi != ""].copy()
        pts["geometry"] = pts.geometry.interpolate(0.5, normalized=True)
        for _, r in pts.iterrows():
            kind = ("summit" if r.poi == "summit" else "check" if r.poi.startswith("half_") else
                    "start" if r.poi.startswith("head_") or r.poi in ("entrance", "thotupola_head") else "view")
            m, c, s = {"summit": ("*", RED, 260), "check": ("s", "#111111", 55), "start": ("o", "white", 55),
                       "view": ("^", AMBER, 80)}[kind]
            ax.scatter(r.geometry.x, r.geometry.y, marker=m, c=c, s=s, edgecolors="black", linewidths=0.8, zorder=5)
        ax.set_title(title, fontsize=11)
        ax.set_axis_off()
        ax.legend(fontsize=7.5, loc="lower left", frameon=False)
        out.append(_save(fig, f"map_{park}.png"))
    return out


def bench(folder):
    """Temporal and spatial-CV metrics of a park: the full benchmark run, overridden by the 3-seed tagged runs
    (_p04 = temporal, _p04s = spatial) where they exist."""
    base = latest(folder, "LATEST")
    t = pd.read_csv(base / "metrics_temporal.csv").set_index("model")
    s = pd.read_csv(base / "metrics_spatial.csv", header=[0, 1], index_col=0)
    for run in sorted(folder.glob("*_benchmark_p04")):
        t2 = pd.read_csv(run / "metrics_temporal.csv").set_index("model")
        t = pd.concat([t.drop(t2.index, errors="ignore"), t2])
    for run in sorted(folder.glob("*_benchmark_p04s")):
        if (run / "metrics_spatial.csv").exists():
            s2 = pd.read_csv(run / "metrics_spatial.csv", header=[0, 1], index_col=0)
            s = pd.concat([s.drop(s2.index, errors="ignore"), s2])
    return t, s


def fig_rq1():
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.6))
    for ax, folder, title in ((axes[0], RES, "Horton Plains"), (axes[1], RES_AP, "Adam's Peak")):
        t, s = bench(folder)
        models = [m for m in ["HA", "ARIMA", "lstm", "gru_nograph", "stgnn"] if m in t.index]
        x = np.arange(len(models))
        ax.bar(x - 0.2, t.loc[models, "MAE"], 0.4, color=[MODEL_COLORS[m] for m in models], edgecolor="white",
               label="All segments counted")
        sp = [s.loc[m, ("MAE", "mean")] if m in s.index else np.nan for m in models]
        ax.bar(x + 0.2, sp, 0.4, color=[MODEL_COLORS[m] for m in models], hatch="///", edgecolor="white", alpha=0.75,
               label="Unseen segments (spatial CV)")
        for xi, v in zip(x, t.loc[models, "MAE"]):
            ax.text(xi - 0.2, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7.5)
        for xi, v in zip(x, sp):
            if np.isfinite(v):
                ax.text(xi + 0.2, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(x, [MODEL_NAMES[m] for m in models], rotation=15)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel("MAE (people per segment-hour)", fontsize=9)
        _style(ax)
    axes[0].legend(fontsize=8, frameon=False)
    return _save(fig, "rq1.png")


def fig_example_day():
    from src.eval.data import TrailData
    run = latest(RES, "LATEST")
    d = np.load(run / "predictions_temporal.npz")
    data = TrailData(load_config(park="horton_plains"), path=ROOT / "data" / "processed" / "dataset.npz")
    y, _ = data.targets(d["origins"])
    node = int(np.where(data.segment_poi == "worlds_end")[0][0])
    peak = y[:, :, node].max(1)
    typical = int(np.argsort(peak)[int(0.75 * len(peak))])        # a busy-ish day (75th percentile of peaks)
    busiest = int(np.argmax(peak))
    hours = np.arange(5, 19)
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2), sharey=False)
    stats = {}
    for ax, day, what in ((axes[0], typical, "A typical busy day"), (axes[1], busiest, "The busiest day")):
        ax.plot(hours, y[day, hours, node], color="black", lw=2.2, label="Actual (simulated)")
        ax.plot(hours, d["stgnn"][day, hours, node], color=GREEN, lw=2.2, label="ST-GNN, day ahead")
        ax.plot(hours, d["HA"][day, hours, node], color="#9E9E9E", lw=1.8, ls="--", label="Historical average")
        date = pd.Timestamp(data.times[d["origins"][day]]).strftime("%a %d %b %Y")
        ax.set_title(f"{what} ({date})", fontsize=9)
        ax.set_xlabel("Hour", fontsize=8)
        _style(ax)
        stats[what] = {m: float(np.abs(d[m][day, hours, node] - y[day, hours, node]).mean()) for m in ("stgnn", "HA")}
        stats[what]["peak"] = float(y[day, hours, node].max())
        stats[what]["stgnn_peak"] = float(d["stgnn"][day, hours, node].max())
    axes[0].set_ylabel("People at World's End", fontsize=8)
    axes[0].legend(fontsize=7, frameon=False)
    return _save(fig, "example_day.png"), stats


def fig_control_horton():
    s = pd.read_csv(latest(RES, "LATEST_CONTROL") / "summary.csv")
    labels = ["No limit", "Daily quota\n(today)", "Slot tickets", "Slot tickets\n+ moving"]
    fig, ax = plt.subplots(1, 2, figsize=(9.6, 3.4))
    cols = ["#9E9E9E", AMBER, BLUE, GREEN]
    ax[0].bar(labels, s.person_hours_over_capacity / 1000, color=cols)
    for i, v in enumerate(s.person_hours_over_capacity):
        ax[0].text(i, v / 1000, f"{v / 1000:,.1f}k", ha="center", va="bottom", fontsize=8)
    ax[0].set_ylabel("Person-hours over capacity, 2025 (k)", fontsize=9)
    ax[1].bar(labels, s.admitted_pct, color=cols)
    for i, v in enumerate(s.admitted_pct):
        ax[1].text(i, v, f"{v:.0f}%", ha="center", va="bottom", fontsize=8)
    ax[1].set_ylabel("Visitors who get to walk that day (%)", fontsize=9)
    for a in ax:
        _style(a)
        a.tick_params(axis="x", labelsize=8)
    return _save(fig, "control_horton.png")


def fig_control_ap():
    s = pd.read_csv(latest(RES_AP, "LATEST_ADVISORY") / "summary.csv")
    labels = ["Nothing", "Start times", "Halfway checks", "Both"]
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    x = np.arange(4)
    ax.bar(x, s.person_hours_waiting_final_steps / 1000, color=RED, label="Waiting on the steep final steps")
    ax.bar(x, s.person_hours_waiting_halfway / 1000, bottom=s.person_hours_waiting_final_steps / 1000,
           color="#F3B562", label="Waiting at a halfway rest stop")
    tot = (s.person_hours_waiting_final_steps + s.person_hours_waiting_halfway) / 1000
    for xi, v in zip(x, tot):
        ax.text(xi, v, f"{v:.1f}k", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, labels, fontsize=8.5)
    ax.set_ylabel("Person-hours waiting, 2025 season (k)", fontsize=9)
    ax.set_ylim(0, tot.max() * 1.35)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    _style(ax)
    return _save(fig, "control_ap.png")


def fig_rq3():
    s = pd.read_csv(latest(RES_AP, "LATEST_FORECAST_VALUE") / "summary.csv")
    labels = ["No advice", "Calendar\naverage", "Forecast\n30 d (P50)", "Forecast\n1 d (P50)", "Forecast\n1 d (P90)",
              "Perfect\nknowledge"]
    cols = ["#9E9E9E", "#C9B79C", "#9DB8D9", "#6B97CF", GREEN, DARK]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.bar(labels, s.person_hours_waiting / 1000, color=cols)
    for i, (v, sh) in enumerate(zip(s.person_hours_waiting, s.share_of_perfect_benefit_pct)):
        ax.text(i, v / 1000, f"{v / 1000:.1f}k\n{sh:.0f}% of\nperfect" if i not in (0, 5) else f"{v / 1000:.1f}k",
                ha="center", va="bottom", fontsize=7.5)
    ax.set_ylabel("Person-hours waiting on the final steps (k)", fontsize=9)
    ax.set_ylim(0, s.person_hours_waiting.max() / 1000 * 1.32)
    ax.tick_params(axis="x", labelsize=8)
    _style(ax)
    return _save(fig, "rq3.png")


def fig_rq2():
    m = pd.read_csv(latest(RES, "LATEST_TRANSFER") / "metrics.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.5))
    bars = [("HA", "Hist. average, 2 years", "#9E9E9E"), ("stgnn_in_domain", "ST-GNN, own 2 years", GREEN),
            ("stgnn_zero_shot", "ST-GNN, other park unchanged", RED), ("HA_90", "Hist. average, 90 days", "#C9C9C9"),
            ("stgnn_scratch_90", "ST-GNN, 90 days from scratch", "#9DB8D9"),
            ("stgnn_finetune_90", "ST-GNN, pre-trained + 90 days", BLUE)]
    for ax, tgt, title in ((axes[0], "horton_plains", "Target: Horton Plains"), (axes[1], "adams_peak", "Target: Adam's Peak")):
        g = m[m.target == tgt].set_index("model").MAE
        y = np.arange(len(bars))[::-1]
        ax.barh(y, [g[b[0]] for b in bars], color=[b[2] for b in bars])
        for yi, b in zip(y, bars):
            ax.text(g[b[0]], yi, f" {g[b[0]]:.1f}", va="center", fontsize=7)
        ax.set_yticks(y, [b[1] for b in bars] if ax is axes[0] else [""] * len(bars), fontsize=7.5)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("MAE", fontsize=8)
        ax.set_xlim(0, g[[b[0] for b in bars]].max() * 1.18)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="x", alpha=0.25)
        ax.tick_params(labelsize=8)
    return _save(fig, "rq2.png")


def fig_rq5():
    m = pd.read_csv(latest(RES, "LATEST_PRETRAIN_TRANSFER") / "metrics.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.5))
    ks = ["30", "90", "365", "full"]
    for ax, park, title in ((axes[0], "horton_plains", "Horton Plains"), (axes[1], "adams_peak", "Adam's Peak")):
        g = m[m.park == park].set_index("model").MAE
        x = np.arange(len(ks))
        sc = [g[f"scratch_{k}"] for k in ks]
        pt = [g[f"pretrained_{k}"] for k in ks]
        ha = [g[f"HA_{k}"] if k != "full" else g["HA"] for k in ks]
        ax.bar(x - 0.2, sc, 0.4, color="#9DB8D9", label="Trained from scratch")
        ax.bar(x + 0.2, pt, 0.4, color=GREEN, label="Pretrained on traffic + fine-tuned")
        ax.plot(x, ha, "k_", markersize=26, mew=2.2, label="Historical average, same days")
        for xi, a, b in zip(x, sc, pt):
            ax.text(xi - 0.2, a, f"{a:.2f}", ha="center", va="bottom", fontsize=7)
            ax.text(xi + 0.2, b, f"{b:.2f}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks(x, ["30 days", "90 days", "365 days", "all (2 y)"])
        ax.set_title(f"{title}  (zero-shot: {g['traffic_zero_shot']:.1f})", fontsize=10)
        ax.set_ylabel("MAE (people per segment-hour)", fontsize=8.5)
        ax.set_xlabel("Counts available from the park", fontsize=8.5)
        _style(ax)
    axes[0].legend(fontsize=7.5, frameon=False, loc="upper right")
    return _save(fig, "rq5.png")


def fig_rq8():
    s = pd.read_csv(latest(RES, "LATEST_ADVICE") / "summary.csv").set_index("policy")
    comp = [0.25, 0.5, 0.75, 1.0]
    fig, ax = plt.subplots(figsize=(6.6, 3.7))
    ax.plot([100 * c for c in comp], [s.loc[f"H{c}", "cut_vs_no_control_pct"] for c in comp], marker="o", color=RED,
            lw=2.2, label="Same advice on every phone (herd)")
    ax.plot([100 * c for c in comp], [s.loc[f"S{c}", "cut_vs_no_control_pct"] for c in comp], marker="o", color=GREEN,
            lw=2.2, label="Each phone draws a good option (spread)")
    for p, ls, lab in (("Q", "--", "Daily Cifuentes limit"), ("QS", ":", "Limit + spread advice")):
        v = s.loc[p, "cut_vs_no_control_pct"]
        ax.axhline(v, color=DARK, ls=ls, lw=1.3)
        ax.text(101, v, f" {lab}\n {v:.0f} %, {s.loc[p, 'refused_pct']:.0f} % turned away", fontsize=7, va="center")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlim(20, 135)
    ax.set_xticks([25, 50, 75, 100])
    ax.set_xlabel("Hikers with a crowded plan who follow the advice (%)", fontsize=9)
    ax.set_ylabel("Overcrowding removed (%)", fontsize=9)
    ax.legend(fontsize=7.5, frameon=False, loc="lower left")
    _style(ax)
    return _save(fig, "rq8.png")


def fig_rq4():
    df = pd.read_csv(latest(RES_AP, "LATEST_ADVISORY_SWEEP") / "sweep.csv")
    fig, ax = plt.subplots(figsize=(5.4, 3.3))
    for comp, c in zip([0.25, 0.5, 0.75, 1.0], ["#B9C6D6", "#7FA7D9", BLUE, "#1F3F73"]):
        g = df[(df.policy == "B") & np.isclose(df.compliance, comp)]
        ax.plot(g.flow_per_min, g.final_steps_cut_pct_vs_A, marker="o", color=c, label=f"{comp:.0%} follow advice")
    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(25, color=GREY, ls=":", lw=1)
    ax.text(25.3, ax.get_ylim()[1] * 0.92, "assumed", fontsize=7, color=GREY)
    ax.set_xlabel("Final-steps flow (people per minute)", fontsize=9)
    ax.set_ylabel("Waiting cut by start times (%)", fontsize=9)
    ax.legend(fontsize=7.5, frameon=False)
    _style(ax)
    return _save(fig, "rq4.png")


# ======================================================================= slide helpers
class Deck:
    W, H = Inches(13.333), Inches(7.5)

    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = self.W, self.H
        self.blank = self.prs.slide_layouts[6]
        self.n = 0

    def slide(self, title, kicker="", notes=""):
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.18), self.H)
        self._fill(bar, GREEN)
        if kicker:
            self.text(s, kicker.upper(), Inches(0.55), Inches(0.32), Inches(9), Inches(0.35), 12, GREEN, bold=True)
        self.text(s, title, Inches(0.55), Inches(0.62), Inches(12.3), Inches(0.8), 28, DARK, bold=True)
        self.text(s, f"Component 4 · IT23343948 · {self.n}", Inches(9.8), Inches(7.05), Inches(3.3), Inches(0.3), 9,
                  GREY, align=PP_ALIGN.RIGHT)
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    @staticmethod
    def _fill(shape, color, line=None):
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(color)
        if line:
            shape.line.color.rgb = rgb(line)
        else:
            shape.line.fill.background()

    def text(self, s, txt, x, y, w, h, size=16, color=DARK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        for i, line in enumerate(txt.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            r = p.add_run()
            r.text = line
            r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, rgb(color)
        return tb

    def bullets(self, s, items, x, y, w, h, size=16, gap=6):
        """items: str or (str, level). '**x**' at the start of an item makes the part before ':' bold."""
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        for i, it in enumerate(items):
            txt, lvl = (it, 0) if isinstance(it, str) else it
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(gap)
            bullet = "•  " if lvl == 0 else "–  "
            head, _, rest = txt.partition("::")
            r = p.add_run()
            r.text = ("      " * lvl) + bullet + (head + ":" if rest else txt)
            r.font.size, r.font.color.rgb = Pt(size - 2 * lvl), rgb(DARK if lvl == 0 else GREY)
            r.font.bold = bool(rest)
            if rest:
                r2 = p.add_run()
                r2.text = rest
                r2.font.size, r2.font.color.rgb = Pt(size - 2 * lvl), rgb(DARK)
        return tb

    def image(self, s, path, x, y, w=None, h=None):
        return s.shapes.add_picture(str(path), x, y, width=w, height=h)

    def box(self, s, txt, x, y, w, h, fill=LIGHT, color=DARK, size=13, bold=False, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
        b = s.shapes.add_shape(shape, x, y, w, h)
        self._fill(b, fill, line)
        if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            b.adjustments[0] = 0.12
        tf = b.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        for m in ("margin_left", "margin_right"):
            setattr(tf, m, Inches(0.08))
        for i, line_ in enumerate(txt.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = line_
            r.font.size, r.font.color.rgb = Pt(size if i == 0 else size - 2), rgb(color)
            r.font.bold = bold and i == 0
        return b

    def arrow(self, s, x1, y1, x2, y2, color=GREY):
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
        c.line.color.rgb = rgb(color)
        c.line.width = Pt(2)
        ln = c.line._get_or_add_ln()
        from pptx.oxml.ns import qn
        tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle"})
        ln.append(tail)
        return c

    def table(self, s, rows, x, y, w, col_w=None, size=12, header=GREEN, row_h=0.36):
        t = s.shapes.add_table(len(rows), len(rows[0]), x, y, w, Inches(row_h * len(rows))).table
        if col_w:
            for i, cw in enumerate(col_w):
                t.columns[i].width = Inches(cw)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                cell = t.cell(r, c)
                cell.text = str(val)
                cell.margin_left = cell.margin_right = Inches(0.06)
                cell.margin_top = cell.margin_bottom = Inches(0.03)
                p = cell.text_frame.paragraphs[0]
                p.runs[0].font.size = Pt(size)
                p.runs[0].font.bold = r == 0
                p.runs[0].font.color.rgb = rgb("#FFFFFF" if r == 0 else DARK)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(header if r == 0 else ("#FFFFFF" if r % 2 else "#F4F7F5"))
        return t

    def callout(self, s, txt, x, y, w, h, fill=GREEN, size=17):
        return self.box(s, txt, x, y, w, h, fill=fill, color="#FFFFFF", size=size, bold=True)


# ======================================================================= the deck
def build():
    maps = fig_maps()
    f_rq1, f_hc, f_ap = fig_rq1(), fig_control_horton(), fig_control_ap()
    f_day, day_stats = fig_example_day()
    f_rq3, f_rq2, f_rq4, f_rq5 = fig_rq3(), fig_rq2(), fig_rq4(), fig_rq5()
    (hp_t, hp_s), (ap_t, ap_s) = bench(RES), bench(RES_AP)
    edge = {p: json.loads((latest(f, "LATEST_EDGE") / "metrics.json").read_text(encoding="utf-8"))
            for p, f in (("hp", RES), ("ap", RES_AP))}
    rq5 = pd.read_csv(latest(RES, "LATEST_PRETRAIN_TRANSFER") / "metrics.csv").set_index(["park", "model"]).MAE

    hp_ctl = pd.read_csv(latest(RES, "LATEST_CONTROL") / "summary.csv")
    cut_quota = 100 * (1 - hp_ctl.person_hours_over_capacity[1] / hp_ctl.person_hours_over_capacity[0])
    cut_slots = 100 * (1 - hp_ctl.person_hours_over_capacity[3] / hp_ctl.person_hours_over_capacity[0])
    ap_ctl = pd.read_csv(latest(RES_AP, "LATEST_ADVISORY") / "summary.csv")
    ap_a = ap_ctl.person_hours_waiting_final_steps[0]
    ap_b_cut = 100 * (1 - ap_ctl.person_hours_waiting_final_steps[1] / ap_a)
    ap_d_cut = 100 * (1 - ap_ctl.person_hours_waiting_halfway[3] / ap_a)
    fv = pd.read_csv(latest(RES_AP, "LATEST_FORECAST_VALUE") / "summary.csv")
    ptests = json.loads((latest(RES_AP, "LATEST_FORECAST_VALUE") / "tests.json").read_text(encoding="utf-8"))["tests"]

    d = Deck()
    W = Deck.W

    # 1 ---------------------------------------------------------------- title
    s = d.prs.slides.add_slide(d.blank)
    d.n += 1
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Deck.H)
    d._fill(bg, DARK)
    band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(5.25), W, Inches(0.08))
    d._fill(band, AMBER)
    d.text(s, "PROGRESS PRESENTATION 1 · J26-IT-363 · COMPONENT 4", Inches(0.8), Inches(1.0), Inches(11), Inches(0.4),
           14, AMBER, bold=True)
    d.text(s, "Forecasting trail bottlenecks and\ncontrolling crowds with a Spatio-Temporal GNN", Inches(0.8),
           Inches(1.6), Inches(11.8), Inches(2.0), 38, "#FFFFFF", bold=True)
    d.text(s, "Horton Plains National Park  ·  Adam's Peak (Sri Pada)", Inches(0.8), Inches(3.75), Inches(11),
           Inches(0.5), 20, "#CFE3D7")
    d.text(s, "Weerasekera J.V.  ·  IT23343948\nDecentralized Hiking AI", Inches(0.8), Inches(5.6), Inches(8),
           Inches(1.0), 16, "#FFFFFF")
    s.notes_slide.notes_text_frame.text = (
        "Introduce yourself and the component in one sentence: I forecast where and when trails get crowded, a day "
        "to 90 days ahead, and turn that forecast into crowd control – at two very different sites. (~20 s)")

    # 2 ---------------------------------------------------------------- problem
    s = d.slide("Crowding is managed with a fixed daily number", "Problem definition",
                "Current implementation: Horton Plains uses a daily permit cap; Adam's Peak has no limit at all and "
                "relies on police on the night. Neither knows WHERE on the trail or WHEN the crowd will be. "
                "Stress the gap: no segment-level data exists, and nobody installs sensors – so it has to work from "
                "open data. (~60 s)")
    d.bullets(s, [
        "Horton Plains today::  a static daily permit quota (DWC). It cannot tell 300 people on a dry Poya morning "
        "from 50 in the rain, or where they bunch up – World's End fills up between 08:00 and 10:00.",
        "Adam's Peak today::  no limit and no tickets. On Poya nights thousands queue for hours on the steep final "
        "steps below the summit – a safety risk.",
        "Data gap::  authorities publish only park-level visitor totals. There are no counts per trail section, "
        "and no sensors on the trails.",
        "Missing tool::  nothing forecasts where and when a bottleneck will form, or turns that into a decision "
        "(how many to let in, when to start, when to hold groups).",
    ], Inches(0.6), Inches(1.6), Inches(7.6), Inches(5.0), 17, 12)
    d.callout(s, "Research question\n\nCan a Spatio-Temporal GNN, using only the trail graph, terrain, weather and "
                 "calendar, forecast segment-level crowding and drive crowd control that replaces a static quota?",
              Inches(8.6), Inches(1.8), Inches(4.2), Inches(3.6), GREEN, 15)

    # 3 ---------------------------------------------------------------- objectives & novelty
    s = d.slide("Proposal objectives and where each one stands", "Proven gap / creative solution",
                "These are the six objectives exactly as numbered in the proposal. Every one has working code and "
                "results; what is still open is said in the status column - field counts (December), two more "
                "traffic datasets, CHIRPS, and a real phone measurement. Novelty: ST-GNNs are proven on city "
                "traffic with hundreds of sensors; here 48-57 nodes and no sensors, and the forecast is judged by "
                "the decisions it improves. (~60 s)")
    d.table(s, [
        ["Proposal objective", "What was built", "Status"],
        ["O1  Trail graph + terrain + weather (open data)", "OSM graph, Copernicus DEM (slope, TWI), Open-Meteo/ERA5, calendar; 2 parks", "Done – CHIRPS / NASA POWER next"],
        ["O2  Synthetic target, validated with field counts", "Group-walking simulator; agreement criteria fixed before the visits", "Method done – counts Dec"],
        ["O3  Pretrain on traffic, adapt to the trail", "METR-LA → PEMS-BAY pretraining, fine-tuned on both parks (RQ5)", "Done – PeMS04/08 next"],
        ["O4  Benchmark vs HA, ARIMA, LSTM, paired t-test", "3 seeds, spatial block CV, Holm-corrected tests (RQ1)", "Done"],
        ["O5  Cifuentes PCC → RCC → ECC with the forecast", "Daily safe limit per trail: rain, wet ground, crowding, trail condition", "Done"],
        ["O6  Package for on-device inference", "ONNX + int8 tested; ST-GNN runs in Dart on the phone, offline (RQ6)", "Done – phone timing next"],
    ], Inches(0.6), Inches(1.6), Inches(12.1), [4.3, 5.3, 2.5], 12)
    d.box(s, "Novelty 1\nST-GNN on a tiny (48–57 node), sensor-free trail graph – tested against baselines, not assumed",
          Inches(0.6), Inches(4.9), Inches(3.9), Inches(1.5), size=13, bold=True)
    d.box(s, "Novelty 2\nForecast judged by the decision it improves (crowd control), not only by its error",
          Inches(4.7), Inches(4.9), Inches(3.9), Inches(1.5), size=13, bold=True)
    d.box(s, "Novelty 3\nOne pipeline, two kinds of site: ticketed park and no-ticket pilgrimage",
          Inches(8.8), Inches(4.9), Inches(3.9), Inches(1.5), size=13, bold=True)

    # 4 ---------------------------------------------------------------- system overview
    s = d.slide("System overview", "Design",
                "Left to right: open data becomes a graph; the simulator makes the training target; two forecasters "
                "(day-ahead ST-GNN, 2-90 day planning model); capacity and control turn forecasts into decisions; "
                "the API serves the app. Every park is one config file. (~60 s)")
    y0, h = Inches(1.9), Inches(1.15)
    cols = [("Open data\nOSM · DEM · weather\ncalendar · Poya", LIGHT), ("Trail graph\n300–500 m segments\nterrain features", LIGHT),
            ("Simulator\ngroups walk the graph\n→ occupancy target", "#FFF4D6"),
            ("Forecasting\nST-GNN (day ahead)\nplanning model (90 d)", "#DCEBE2"),
            ("Capacity & control\nCifuentes · slot LP\nstart times · holds", "#DCEBE2"),
            ("Service\nFastAPI per park\ngateway · Flutter app", "#E3EAF5")]
    bw, gap = Inches(1.9), Inches(0.18)
    for i, (t, f) in enumerate(cols):
        x = Inches(0.55) + i * (bw + gap)
        d.box(s, t, x, y0, bw, h, fill=f, size=13, bold=True)
        if i:
            d.arrow(s, x - gap, y0 + h // 2, x, y0 + h // 2)
    d.bullets(s, [
        "Per park::  one YAML file (configs/parks/*.yaml) – adding a destination needs no code or app change",
        "Two horizons::  day-ahead hourly occupancy per segment (ST-GNN) and a 2–90 day outlook with a P10–P90 range",
        "Two control styles::  Horton Plains – timed tickets per trail and 30-min slot; Adam's Peak – advice only "
        "(recommended start times + officer holds at halfway rest stops)",
        "Users::  visitors / pilgrims (plan, book, start times), rangers (gate, halfway counts), officers (season plan, "
        "closures), admin (audit)",
    ], Inches(0.6), Inches(3.45), Inches(12.2), Inches(3.4), 16, 10)

    # 5 ---------------------------------------------------------------- study sites
    s = d.slide("Two study sites, built from open data only", "Application of knowledge",
                "Horton: three trails sharing an entrance, day visits. Adam's Peak: four OSM-mapped routes that "
                "meet at one summit, climbed at night – the bottleneck is a queue, not a crowded viewpoint. The last "
                "~350 m to the summit is missing from OSM and is approximated (stated as a limitation). (~45 s)")
    d.image(s, maps[0], Inches(0.5), Inches(1.5), h=Inches(4.3))
    d.image(s, maps[1], Inches(5.4), Inches(1.5), h=Inches(4.3))
    d.bullets(s, [
        "Graph::  OpenStreetMap paths split into ~300 m (Horton) / ~500 m (Adam's Peak) segments",
        "Terrain::  Copernicus 30 m DEM – slope, TWI, Tobler walking time, stairs",
        "Weather::  Open-Meteo archive + 16-day forecast",
        "Calendar::  public holidays, Poya days (estimated after 2026), school holidays, pilgrimage season",
        "No personal data::  counts only",
    ], Inches(10.0), Inches(1.6), Inches(3.1), Inches(5.2), 12, 8)
    d.text(s, "▲ viewpoint   ★ summit   ■ halfway checkpoint   ○ start", Inches(0.6), Inches(5.95), Inches(9), Inches(0.4),
           11, GREY)

    # 6 ---------------------------------------------------------------- model & technologies
    s = d.slide("The ST-GNN and the technologies behind it", "Application of technologies",
                "Explain the architecture: per hour, a GCN mixes neighbouring segments, a GRU runs over the last 24 h, a "
                "decoder uses the known future weather and calendar. Key design choice: segments without counts "
                "send no messages in the first graph layer, so missing data is not read as 'empty'. Segments are "
                "described (viewpoint? minutes from trailhead? share of visitors?) instead of named, so the same "
                "model shape fits any park. (~75 s)")
    steps = [("Last 24 h\ncounts + weather\n+ calendar", LIGHT), ("GCN × 2\nneighbouring\nsegments", "#DCEBE2"),
             ("GRU\nover time", "#DCEBE2"), ("GCN\nspread state", "#DCEBE2"),
             ("Decoder\nnext 24 h weather\n+ calendar", LIGHT), ("Occupancy\nper segment\nper hour", "#FFF4D6")]
    bw = Inches(1.85)
    for i, (t, f) in enumerate(steps):
        x = Inches(0.55) + i * (bw + Inches(0.22))
        d.box(s, t, x, Inches(1.65), bw, Inches(1.1), fill=f, size=12, bold=True)
        if i:
            d.arrow(s, x - Inches(0.22), Inches(2.2), x, Inches(2.2))
    d.table(s, [
        ["Area", "Technology", "Why"],
        ["Graph learning", "PyTorch 2 + PyTorch Geometric (DenseGCNConv)", "small dense graph: fast, exact"],
        ["Baselines", "statsmodels SARIMAX, historical average, LSTM/GRU", "mandatory comparison"],
        ["Pretraining", "METR-LA, PEMS-BAY (h5py), same GCN+GRU core", "proposal objective O3"],
        ["On-device", "ONNX Runtime (export, int8 test), pure-Dart forward pass", "offline, any phone"],
        ["Planning (90 d)", "scikit-learn gradient boosting, conformal P10–P90", "inputs exist weeks ahead"],
        ["Optimisation", "SciPy linprog (HiGHS)", "tickets per slot under capacity"],
        ["Geo / terrain", "OSMnx, GeoPandas, Rasterio", "graph + DEM features"],
        ["Service / app", "FastAPI, SQLite, Flutter (Android / web)", "offline-capable visitor app"],
    ], Inches(0.6), Inches(3.15), Inches(8.3), [1.9, 3.9, 2.5], 12)
    d.bullets(s, [
        "Missing counts::  unsensed segments send no messages in the first GCN layer",
        "Transferable inputs::  segments described, not named (13 features)",
        "Loss::  masked L1, early stopping on the 2024 year",
    ], Inches(9.15), Inches(3.2), Inches(3.9), Inches(3.5), 13, 10)

    # 7 ---------------------------------------------------------------- evaluation & standards
    s = d.slide("Evaluation protocol and best practices", "Standards / best practices",
                "This slide answers 'how do you know it works'. Time split avoids leakage; spatial block CV tests the "
                "real deployment case (segments with no counts); pairs are forecast days because hourly errors are "
                "correlated; Holm correction for several baselines. Every run saves config, seed and git hash. (~45 s)")
    d.bullets(s, [
        "No leakage::  train 2022–23 · validate 2024 · test 2025; scalers fitted on training data only",
        "Spatial block CV::  4 contiguous blocks of segments held out – no history and no training loss there",
        "Fair statistics::  paired t-test + Wilcoxon over forecast days (not hours), Holm-corrected, effect size d_z",
        "Clean ablation::  the same network with the graph removed (GRU-no-graph) isolates what the graph adds",
        "Decision-focused::  forecasts also judged by the waiting / overcrowding they prevent (RQ3)",
        "Pre-registered::  field agreement criteria (A1–A3) fixed on 20 Oct, before any counts are taken",
        "Reproducible::  seeds logged; every run = results/<time>_<tag>/ with config + git hash; 65 Python + 24 Flutter tests",
        "Secure & ethical::  roles checked on the server, hashed passwords, lockout, audit log; no personal visitor data",
    ], Inches(0.6), Inches(1.6), Inches(12.2), Inches(5.3), 16, 9)

    # 8 ---------------------------------------------------------------- RQ1
    def sp(df, m):
        return df.loc[m, ("MAE", "mean")]

    def p_vs(folder, glob, protocol, base):
        for run in sorted(folder.glob(glob), reverse=True):
            st = json.loads((run / "stats.json").read_text(encoding="utf-8")) if (run / "stats.json").exists() else {}
            for r in st.get(protocol, {}).get("tests_vs_stgnn", []):
                if r["baseline"] == base:
                    return r["p_holm"], r["mean_diff_MAE"]
        return None, None

    def ptxt(p):
        return "n/a" if p is None else ("p < 0.001" if p < 0.001 else f"p = {p:.2f}")

    hp_p, _ = p_vs(RES, "*_benchmark", "spatial", "lstm")
    ap_tp, _ = p_vs(RES_AP, "*_benchmark_p04", "temporal", "lstm")
    hp_tp, _ = p_vs(RES, "*_benchmark_p04", "temporal", "lstm")
    ap_sp, ap_sd = p_vs(RES_AP, "*_benchmark_p04s", "spatial", "lstm")
    ap_word = ("better" if ap_sd is not None and ap_sd < 0 and ap_sp < 0.05 else
               "worse" if ap_sd is not None and ap_sd > 0 and ap_sp < 0.05 else "not different")
    s = d.slide("RQ1 – Does the graph help?  On ordinary trail without counts, yes", "Proof of concept",
                f"Hatched bars are the deployment case: segments with no counts. At Horton Plains the ST-GNN is best "
                f"there ({sp(hp_s, 'stgnn'):.2f} vs LSTM {sp(hp_s, 'lstm'):.2f} vs historical average "
                f"{sp(hp_s, 'HA'):.2f}, {ptxt(hp_p)}). With counts on every segment the networks tie at both parks "
                f"(3 seeds; {ptxt(hp_tp)} and {ptxt(ap_tp)}) - the earlier 'LSTM wins at Adam's Peak' was seed noise. "
                f"An ST-GNN with an LSTM cell was tried and was worse, so it was dropped. At Adam's Peak on unseen "
                f"segments the ST-GNN is {ap_word} vs the LSTM ({ptxt(ap_sp)}) overall: it is best on the two blocks "
                f"of ordinary trail but loses on the block with the summit queue, which forms from the capacity "
                f"of the final steps, not from what neighbouring segments look like. Next: give the model the queue "
                f"state. (~75 s)")
    d.image(s, f_rq1, Inches(0.45), Inches(1.45), w=Inches(12.4))
    d.bullets(s, [
        f"Horton, unseen segments::  ST-GNN {sp(hp_s, 'stgnn'):.2f} · LSTM {sp(hp_s, 'lstm'):.2f} · GRU without graph "
        f"{sp(hp_s, 'gru_nograph'):.2f} · historical average {sp(hp_s, 'HA'):.2f}  (vs LSTM {ptxt(hp_p)})",
        f"Adam's Peak, unseen segments (3 seeds)::  ST-GNN {sp(ap_s, 'stgnn'):.2f} · LSTM {sp(ap_s, 'lstm'):.2f} · "
        f"GRU without graph {sp(ap_s, 'gru_nograph'):.2f}  (vs LSTM {ptxt(ap_sp)}) – best on ordinary trail, "
        f"worse at the summit queue",
        f"Every segment counted (3 seeds)::  tie with the LSTM – Horton {hp_t.loc['stgnn', 'MAE']:.2f} vs "
        f"{hp_t.loc['lstm', 'MAE']:.2f} ({ptxt(hp_tp)}), Adam's Peak {ap_t.loc['stgnn', 'MAE']:.2f} vs "
        f"{ap_t.loc['lstm', 'MAE']:.2f} ({ptxt(ap_tp)})",
    ], Inches(0.6), Inches(5.6), Inches(12.2), Inches(1.4), 13, 3)

    # 8b --------------------------------------------------------------- one day
    ty, bz = day_stats["A typical busy day"], day_stats["The busiest day"]
    s = d.slide("What a day-ahead forecast looks like", "Proof of concept",
                f"Left: a typical busy day – the ST-GNN error at World's End is {ty['stgnn']:.0f} people per hour vs "
                f"{ty['HA']:.0f} for the historical average. Right: the busiest day of 2025 – the actual peak is "
                f"{bz['peak']:.0f}, the forecast only {bz['stgnn_peak']:.0f}. Rare extreme days are underpredicted; "
                f"that is exactly why the control side plans on the busy case (P90), see RQ3. (~45 s)")
    d.image(s, f_day, Inches(0.45), Inches(1.5), w=Inches(8.3))
    d.bullets(s, [
        f"Typical busy day::  ST-GNN off by {ty['stgnn']:.1f} people/h at World's End, historical average by {ty['HA']:.1f}",
        f"Busiest day::  peak {bz['peak']:.0f} people, forecast {bz['stgnn_peak']:.0f} – extremes are underpredicted",
        "Consequence::  decisions use the forecast's busy case (P90), not its middle (RQ3)",
        "Input::  yesterday's counts, tomorrow's weather forecast and the calendar – no sensors on the trail",
    ], Inches(9.0), Inches(1.6), Inches(4.1), Inches(5.2), 14, 10)

    # 9 ---------------------------------------------------------------- Horton control
    s = d.slide("From forecast to control – Horton Plains", "Proof of concept",
                f"A ticket fixes a trail and an entry time, so the simulator tells us where its holder will be. A "
                f"linear programme sells tickets only while every segment stays under its Cifuentes capacity in every "
                f"half hour. Replaying 2025: the current daily quota removes {cut_quota:.0f} % of over-capacity "
                f"person-hours; slot tickets with moving remove {cut_slots:.1f} %, and let more people walk. "
                f"(~45 s)")
    d.image(s, f_hc, Inches(0.45), Inches(1.5), w=Inches(8.6))
    d.bullets(s, [
        "Capacity::  Cifuentes PCC → RCC → ECC; the forecast adds a crowding factor next to rain",
        "Tickets::  per trail and 30-min slot from a linear programme (SciPy HiGHS)",
        "Full slot::  later slot, another trail, or another day – booked up to 90 days ahead",
        f"Result::  over-capacity time −{cut_quota:.0f} % (quota) vs −{cut_slots:.1f} % (slot tickets)",
    ], Inches(9.25), Inches(1.6), Inches(3.9), Inches(5.2), 14, 10)

    # 10 --------------------------------------------------------------- Adam's Peak control
    s = d.slide("Adam's Peak – no tickets, so advise and hold", "Creative solution",
                f"Turning pilgrims away is not acceptable. The danger is the queue on the steep final steps. Two "
                f"measures: recommended start times per route (spread so the advice does not create a new peak – we "
                f"found naive advice made queues 22 % worse), and officers at halfway rest stops who count passers and "
                f"hold groups. Start times alone: −{ap_b_cut:.0f} %. Both: no waiting on the final steps and "
                f"−{ap_d_cut:.0f} % waiting overall. (~60 s)")
    d.image(s, f_ap, Inches(0.45), Inches(1.5), w=Inches(6.6))
    d.bullets(s, [
        "Recommended start times::  per route, wait ≤ 20 min and summit before sunrise",
        "Herding-aware::  movers spread batch by batch – naive advice made the queue 22 % worse",
        "Halfway checks::  rangers enter counts; the app says HOLD and how many to release per 10 min",
        f"Result (2025 season)::  start times −{ap_b_cut:.0f} % waiting; both together move all waiting off the "
        f"final steps and cut it by {ap_d_cut:.0f} %",
    ], Inches(7.3), Inches(1.6), Inches(5.8), Inches(5.2), 15, 10)

    # 11 --------------------------------------------------------------- RQ3
    p90 = fv.iloc[4]
    p50 = fv.iloc[3]
    ci = ptests["plan_lead1_p90_vs_plan_lead1"]["ci95"]
    s = d.slide("RQ3 – Better forecasts help only with the right decision rule", "Key finding",
                f"Same 132 nights, advice computed before each night from different forecasts. The median forecast "
                f"gets only {p50.share_of_perfect_benefit_pct:.0f} % of what perfect knowledge would, because it is "
                f"too low on exactly the rare peak nights. Planning on the busy case (P90) gets all of it. Bootstrap "
                f"95 % interval of P90 vs P50 advice: {ci[0]:,.0f} to {ci[1]:,.0f} person-hours. This is why the "
                f"officer console plans halfway checks on the busy case. (~60 s)")
    d.image(s, f_rq3, Inches(0.45), Inches(1.5), w=Inches(7.6))
    d.callout(s, f"Median forecast →\n{p50.share_of_perfect_benefit_pct:.0f} % of the possible benefit\n\n"
                 f"Busy-case (P90) forecast →\n{p90.share_of_perfect_benefit_pct:.0f} % of it,\n"
                 f"moving {p90.moved_pct:.1f} % of pilgrims", Inches(8.5), Inches(1.7), Inches(4.4), Inches(2.7), GREEN, 16)
    d.text(s, "Forecasts should be evaluated by the decisions they drive, not only by their error.", Inches(8.5),
           Inches(4.7), Inches(4.4), Inches(1.2), 15, DARK, bold=True)
    d.text(s, "Over 100 % is possible: 'perfect knowledge' means the true number of climbers, not the exact time each "
              "group starts; the cautious P90 advice also covers that uncertainty.", Inches(0.6), Inches(5.7),
           Inches(12), Inches(0.8), 11, GREY)

    # 12 --------------------------------------------------------------- RQ2 + RQ4
    s = d.slide("RQ2 transfer · RQ4 robustness", "Proof of concept – limits",
                "RQ2: a model from one park used unchanged at the other fails – the parks differ too much (day hike "
                "vs night pilgrimage). Pre-training does help a new park learn from little data (7 of 8 settings), "
                "but with under 90 days a historical average is as good: start a new park on the average and switch "
                "later. RQ4: start-time advice works when the final steps really are a bottleneck (≤ 25 people/min) "
                "and fades above 30; the flow is the number to measure in the field. (~60 s)")
    d.image(s, f_rq2, Inches(0.4), Inches(1.5), w=Inches(7.1))
    d.image(s, f_rq4, Inches(7.6), Inches(1.5), w=Inches(5.5))
    d.bullets(s, [
        "Transfer::  unchanged → worse than the average; pre-trained + a few days beats scratch (7/8, p < 0.05)",
        "Robustness::  halfway checks clear the final steps at every flow (15–35/min); start times help at ≤ 25/min",
        "Most important unknown::  final-steps flow – waiting changes 26-fold between 15 and 35 people/min",
    ], Inches(0.6), Inches(4.95), Inches(12.3), Inches(1.9), 14, 6)

    # 12b -------------------------------------------------------------- RQ5 pretraining
    def gain(park, k):      # "+6 %" with no line break inside
        v = 100 * (rq5[(park, f"pretrained_{k}")] / rq5[(park, f"scratch_{k}")] - 1)
        return f"{v:+.0f} ".replace("-", "−")

    s = d.slide("RQ5 – Does pretraining on city traffic help a tiny trail graph?", "The proposal's research gap",
                f"Proposal objective O3. Same ST-GNN core pretrained on METR-LA (207 sensors) then PEMS-BAY (325), "
                f"target = congestion. Then three ways to use it at each park, 3 seeds, paired tests over 365 test "
                f"days. Answer: only at Horton Plains, only with 30-90 days of counts ({gain('horton_plains', '30')}% "
                f"and {gain('horton_plains', '90')}% vs scratch, p < 0.001). Not at Adam's Peak - a night "
                f"pilgrimage with a summit queue looks nothing like road traffic. Zero-shot fails everywhere. With a "
                f"full year the pretrained start slightly hurts (negative transfer). Honest, publishable answer to "
                f"the gap. Next: freeze layers / gradual unfreezing and PeMS04/08. (~75 s)")
    d.image(s, f_rq5, Inches(0.45), Inches(1.45), w=Inches(8.4))
    d.bullets(s, [
        f"Horton Plains::  pretraining helps with 30 days ({gain('horton_plains', '30')}%) and 90 days "
        f"({gain('horton_plains', '90')}%), p < 0.001",
        f"Adam's Peak::  no help at any amount of data ({gain('adams_peak', '30')}% at 30 days)",
        f"Zero-shot::  traffic weights unchanged are 4–5× worse than the historical average",
        "But::  ≤ 90 days of counts → a historical average still wins at both parks",
        "So::  start a new park on the average; pretraining shortens the wait only where crowds behave like traffic peaks",
    ], Inches(9.0), Inches(1.55), Inches(4.1), Inches(5.3), 13, 9)
    d.text(s, "METR-LA → PEMS-BAY pretraining · 3 seeds · paired t-tests over 365 test days, Holm-corrected",
           Inches(0.6), Inches(4.85), Inches(8.2), Inches(0.4), 11, GREY)

    # 12c -------------------------------------------------------------- RQ6 on-device
    eh, ea = edge["hp"], edge["ap"]
    s = d.slide("RQ6 – The ST-GNN runs on the phone, offline", "Edge-native (objective O6, NFR1)",
                f"Proposal objective O6 and NFR1 (< 2 s). Exported to ONNX: {eh['latency_one_forecast_1_thread']['onnx_fp32']['median_ms']} ms "
                f"for 24 hours x every segment on one laptop core, 13,665 parameters, about 100 KB. int8 "
                f"quantisation was tested and rejected: it saves 2 KB and raises the error by "
                f"{ea['mae_change_int8_pct']:.0f} % at Adam's Peak. On the phone the same network runs in plain Dart "
                f"from a 175 KB daily pack - identical to PyTorch within 0.0001 people - so tomorrow's forecast works "
                f"with no signal on the mountain. Next: time it on a real Android phone. (~60 s)")
    pic = d.image(s, OUT / "screens" / "10_on_device.png", Inches(0.55), Inches(1.45), h=Inches(5.4))
    pic.line.color.rgb = rgb("#C9D3CD")
    flow = [("Server, every evening\ntrain · publish 175 KB\nedge pack (weights + inputs)", LIGHT),
            ("Phone\ndownloads once a day,\nkeeps the last pack", "#E3EAF5"),
            ("Phone, no signal\nST-GNN in Dart →\nbusiest sections tomorrow", "#DCEBE2")]
    for i, (t_, f_) in enumerate(flow):
        x = Inches(3.35) + i * Inches(3.25)
        d.box(s, t_, x, Inches(1.55), Inches(2.95), Inches(1.15), fill=f_, size=12, bold=True)
        if i:
            d.arrow(s, x - Inches(0.3), Inches(2.12), x, Inches(2.12))
    d.table(s, [
        ["Measure", "Horton Plains", "Adam's Peak"],
        ["Latency, ONNX (1 laptop core)", f"{eh['latency_one_forecast_1_thread']['onnx_fp32']['median_ms']} ms",
         f"{ea['latency_one_forecast_1_thread']['onnx_fp32']['median_ms']} ms"],
        ["Model file / extra memory", f"{eh['memory']['onnx_fp32']['file_kb']:.0f} KB / {eh['memory']['onnx_fp32']['process_increase_mb']} MB",
         f"{ea['memory']['onnx_fp32']['file_kb']:.0f} KB / {ea['memory']['onnx_fp32']['process_increase_mb']} MB"],
        ["int8 quantisation: error change", f"{eh['mae_change_int8_pct']:+.1f} %", f"{ea['mae_change_int8_pct']:+.1f} % → not used"],
        ["Dart on the phone vs PyTorch", "≤ 0.0001 people", "same engine"],
        ["NFR1 target", "< 2 s  ✓", "< 2 s  ✓"],
    ], Inches(3.35), Inches(3.05), Inches(9.7), [4.1, 2.8, 2.8], 13, row_h=0.42)
    d.text(s, "Dart forward pass ≈ 140–210 ms in the test runner (unoptimised); real-phone timing is the next step.",
           Inches(3.35), Inches(5.75), Inches(9.7), Inches(0.5), 12, GREY)

    # 12d -------------------------------------------------------------- RQ7 field validation
    s = d.slide("RQ7 – Field validation, criteria fixed before the counts", "Proof of concept – next step",
                "Proposal objective O2 says the agreement level is defined in the evaluation plan - it is now, and "
                "it was fixed today, before any counting, so it cannot be tuned afterwards. Both the simulated "
                "target and the forecast are compared. One visit day is held back: if the simulator is recalibrated "
                "with the counts, the held-back day is the honest test. The comparison tool is built and tested; "
                "it reads a simple counting sheet. (~45 s)")
    d.table(s, [
        ["#", "Criterion (pre-registered 20 Oct 2026)", "Pass if"],
        ["A1", "MAE ÷ mean observed daily peak (typical error vs a busy moment)", "≤ 0.25"],
        ["A2", "Spearman rank correlation of counts and predictions", "≥ 0.6"],
        ["A3", "Hour of the highest count vs highest prediction, per place and day", "±1 h on ≥ half"],
    ], Inches(0.6), Inches(1.6), Inches(7.6), [0.6, 5.4, 1.6], 13, row_h=0.5)
    d.bullets(s, [
        "Horton Plains (Dec)::  2–3 days, weekday + weekend; entrance, Mini World's End, World's End, "
        "Baker's Falls every 30 min, 06:00–13:00",
        "Adam's Peak (23 Dec, Unduvap Poya)::  final-steps flow every 15 min (the most important unknown, RQ4), "
        "halfway counts, summit headcount, climb times",
        "Then::  recalibrate the simulator on all but one day, re-run RQ1–RQ5",
        "Tool ready::  python -m src.eval.field_validation <counting sheets> → report with A1–A3",
        "Ethics::  counts only, no names or faces; permission from the warden and Sri Pada trust",
    ], Inches(0.6), Inches(3.9), Inches(7.6), Inches(3.0), 13, 7)
    d.callout(s, "Main objective:\n“significant improvement … on at least one field-validated pilot trail”\n\n"
                 "→ the December counts turn the simulated results into that claim",
              Inches(8.6), Inches(1.7), Inches(4.3), Inches(3.4), GREEN, 15)

    # 13 --------------------------------------------------------------- prototype: visitors
    screens = OUT / "screens"

    def phones(s, items):
        for i, (name, cap) in enumerate(items):
            x = Inches(0.55) + i * Inches(2.3)
            pic = d.image(s, screens / f"{name}.png", x, Inches(1.45), h=Inches(4.55))
            pic.line.color.rgb = rgb("#C9D3CD")
            pic.line.width = Pt(1)
            d.text(s, cap, x - Inches(0.05), Inches(6.05), Inches(2.25), Inches(0.9), 11, DARK, align=PP_ALIGN.CENTER)

    s = d.slide("The proposal's output: bottlenecks and safe numbers per section", "Proof of concept – FR2, FR3, NFR4",
                "This is the core of the proposal on one screen. Left: every trail section coloured by how full the "
                "ST-GNN expects it to be at the chosen hour - forecast people divided by what the section holds at "
                "Cifuentes spacing - computed on the phone, so it also works in airplane mode. Drag the hour slider: "
                "at 08:00 World's End and Baker's Falls are over capacity. Right: the safe number per trail and for "
                "the park, set by the most limiting section, instead of one fixed quota. Officers get the same view "
                "as their first tab. (~60 s)")
    phones(s, [("11_bottleneck_map", "Today + 6 days, hour by hour:\nevery section coloured"),
               ("12_safe_numbers", "Safe number per trail,\nset by its limiting section")])
    d.bullets(s, [
        "Per section::  ST-GNN forecast ÷ people it holds at once (groups of 10, 50 m apart)",
        "Per trail::  Cifuentes PCC → RCC → ECC; the most limiting section sets the safe number",
        "Instead of a fixed quota::  690 tomorrow (weather, wet ground, crowding) vs 719 fixed",
        "A week, offline::  today and tomorrow forecast by the ST-GNN on the phone (RQ6); days 3-7 from the planning model, saved",
        "Users::  officers (first tab), rangers, hikers (Crowding tab) · whole app works offline",
    ], Inches(5.3), Inches(1.6), Inches(7.8), Inches(5.2), 15, 12)

    adv = pd.read_csv(latest(RES, "LATEST_ADVICE") / "summary.csv").set_index("policy")
    s = d.slide("RQ8 – Can offline advice to hikers prevent overcrowding?", "Hiker guidance (feeds Module 3)",
                f"Same 2025 visitors as the entry-control test. Every phone has tomorrow's ST-GNN forecast and works "
                f"out, for each trail, direction and start hour, how full the sections will be when the hiker is on "
                f"them. Hikers whose plan meets a busy section follow the advice with some probability. If every "
                f"phone gives the SAME best option, the crowd moves together and at full compliance it is worse than "
                f"no advice ({adv.loc['H1.0', 'cut_vs_no_control_pct']:.0f} %). If each phone draws one of the good "
                f"options, weighted by room left, overcrowding falls by up to "
                f"{adv.loc['S0.75', 'cut_vs_no_control_pct']:.0f} % - as much as the daily limit - without turning "
                f"anyone away. Advice alone is not enough; limit plus spread advice removes "
                f"{adv.loc['QS', 'cut_vs_no_control_pct']:.0f} %. Answers 'can offline route suggestions solve "
                f"overcrowding': they help a lot, if they are spread, and work best with the dynamic limit. (~75 s)")
    d.image(s, fig_rq8(), Inches(0.45), Inches(1.5), w=Inches(7.6))
    pic = d.image(s, screens / "13_your_walk.png", Inches(8.4), Inches(1.45), h=Inches(4.6))
    pic.line.color.rgb = rgb("#C9D3CD")
    d.text(s, "On the phone, offline:\nsuggested plan + other good options", Inches(8.3), Inches(6.1), Inches(2.4),
           Inches(0.7), 11, DARK, align=PP_ALIGN.CENTER)
    d.bullets(s, [
        f"Herd advice::  {adv.loc['H0.5', 'cut_vs_no_control_pct']:.0f} % at half compliance, "
        f"{adv.loc['H1.0', 'cut_vs_no_control_pct']:.0f} % at full",
        f"Spread advice::  up to {adv.loc['S0.75', 'cut_vs_no_control_pct']:.0f} %, nobody turned away",
        f"Limit + spread::  {adv.loc['QS', 'cut_vs_no_control_pct']:.0f} % (limit alone "
        f"{adv.loc['Q', 'cut_vs_no_control_pct']:.0f} %)",
    ], Inches(10.9), Inches(1.6), Inches(2.3), Inches(4.8), 12, 10)
    d.text(s, "2025 test year, simulation · p < 0.001 for every policy vs no control (Wilcoxon over days)",
           Inches(0.6), Inches(5.65), Inches(7.6), Inches(0.4), 11, GREY)

    s = d.slide("Working prototype – visitors plan a trip", "Completion of prototype",
                "Screens rendered from the real API output. Trip planner: any number of destinations, read from "
                "config. Overview: week ahead and the quietest days. Calendar: 90-day crowd outlook. Day: expected "
                "crowd with a range and suggestions (other trail, later start, other day). Show the live demo if "
                "time allows – RUN_APP.md. (~45 s)")
    phones(s, [("01_destinations", "Where to? – every destination,\nits next 7 days"),
               ("02_overview_adams_peak", "Destination overview,\nquietest days, how to get there"),
               ("03_calendar_horton", "90-day crowd calendar"),
               ("04_day_horton", "One day: expected crowd\n+ how to avoid it")])
    d.bullets(s, [
        "Offline::  outlook and tickets cached; tomorrow's forecast computed on the phone",
        "Safe limit::  expected / safe number per trail for the day, with “Why this limit?”",
        "Booking::  slot ticket with QR code; full slot → later slot, other trail, other day",
        "Languages::  English · සිංහල · தமிழ் (drafts under native review)",
        "Map::  OpenStreetMap trails, starts, checkpoints",
    ], Inches(9.8), Inches(1.6), Inches(3.3), Inches(5.0), 13, 10)

    # 13b -------------------------------------------------------------- prototype: Adam's Peak
    s = d.slide("Working prototype – pilgrims and staff at Adam's Peak", "Completion of prototype",
                "Start times per route with the expected wait. Ranger at a halfway rest stop enters counts; the app "
                "turns red (HOLD) and gives the release rate. The officer sees which nights may need checks (here: "
                "Christmas, stand by) and a night plan with hold windows. (~45 s)")
    phones(s, [("05_start_times", "Pilgrim: best start times\nand wait near the top"),
               ("06_halfway_hold", "Ranger: halfway count →\nHOLD + release rate"),
               ("08_officer_season", "Officer: nights that may\nneed halfway checks"),
               ("09_night_plan", "Officer: night plan,\nhold windows per checkpoint")])
    d.bullets(s, [
        "Backend::  FastAPI per park + gateway, 25+ endpoints",
        "Security::  roles ranger < officer < admin checked on the server; hashed passwords, lockout, audit log",
        "Quality::  65 Python tests · 24 Flutter tests · analyzer clean",
    ], Inches(9.8), Inches(1.6), Inches(3.3), Inches(5.0), 13, 10)

    # 14 --------------------------------------------------------------- requirements
    s = d.slide("Requirements and their status", "User & functional requirements",
                "Numbered exactly as in the proposal (section 5). Two are partial and say why: FR4 needs the data "
                "contract agreed with Module 3, NFR1 is measured on a laptop and in the Dart engine but not yet on "
                "a real phone. Extensions beyond the proposal are listed separately. Requirements are still "
                "provisional until the surveys come back - say this before you are asked. (~45 s)")
    d.table(s, [
        ["ID", "Requirement (proposal, section 5)", "Status", "Evidence"],
        ["FR1", "Trail graph from OSM with terrain + weather per node", "Done", "2 parks, 48 / 57 segments"],
        ["FR2", "Forecast occupancy per segment, next 24 h, with the ST-GNN", "Done", "server + on the phone (RQ1, RQ6)"],
        ["FR3", "Dynamic capacity per segment with Cifuentes PCC-RCC-ECC", "Done", "daily safe limit per trail"],
        ["FR4", "Output usable by the dashboard and Module 3", "Done", "JSON Schema c4-module3-feed-1, /module3/feed"],
        ["FR5", "Synthetic-target limitation logged with every output", "Done", "disclaimer in every forecast"],
        ["NFR1", "On-device inference < 2 s", "Done (laptop)", "2 ms ONNX; Dart on phone; real phone next"],
        ["NFR2", "Graceful fallback without a weather forecast", "Done", "historical average + typical weather"],
        ["NFR3", "Other OSM parks without architectural change", "Done", "Adam's Peak = 1 config file"],
        ["NFR4", "Actionable for a non-technical official", "Done", "safe limit + 'why', night plan, HOLD"],
        ["NFR5", "No personally identifiable data", "Done", "booking code only, no names"],
        ["Ext.", "Slot tickets (Horton) · start times + halfway holds (Adam's Peak)", "Done", "−99.6 % overcrowding; final steps cleared"],
        ["Ext.", "90-day planning outlook, staff roles, Sinhala / Tamil", "Done", "P10–P90; ranger / officer / admin"],
    ], Inches(0.6), Inches(1.5), Inches(12.1), [0.8, 5.4, 1.6, 4.3], 12, row_h=0.4)
    d.text(s, "Requirements are provisional until the stakeholder surveys return (DWC, rangers, operators, hikers).",
           Inches(0.6), Inches(6.75), Inches(9), Inches(0.3), 11, GREY)

    # 15 --------------------------------------------------------------- risks
    s = d.slide("Risks and mitigation", "Risk mitigation",
                "Lead with R1 – it is the question examiners will ask. The mitigation is already in motion: every "
                "assumption is listed and parameterised, sensitivity analysis shows which ones matter, and field "
                "counts are planned. (~45 s)")
    d.table(s, [
        ["#", "Risk", "Impact", "Mitigation (status)"],
        ["R1", "No real segment-level counts: the target is synthetic", "High",
         "Assumptions listed; RQ4 sensitivity; agreement criteria fixed and tool built; counts Dec (Horton) + 23 Dec (Adam's Peak)"],
        ["R2", "ST-GNN not better than the LSTM", "Medium",
         "Reported either way: better on segments without counts, tie elsewhere (3 seeds); periodic inputs + tuning next"],
        ["R3", "Last part of the Adam's Peak trail missing in OSM", "Medium",
         "Approximate link flagged; replace with a GPS track"],
        ["R4", "Authorities do not adopt tickets / advice", "Medium",
         "Advice-only mode for pilgrim sites; decisions to confirm with DWC and Sri Pada Trust"],
        ["R5", "Holiday calendar not published for 2027", "Low", "Estimated Poya days (62/62 within 1 day); swap in gazette"],
        ["R6", "CPU-only training time", "Low", "Small graph, early stopping; seeds run overnight"],
        ["R7", "Translations inaccurate", "Low", "Marked as drafts; native-speaker review"],
        ["R8", "Traffic pretraining does not transfer", "Medium",
         "Happened at Adam's Peak (RQ5) – reported as a finding; layer freezing and PeMS04/08 next"],
        ["R9", "Module 3 integration late (FR4)", "Medium",
         "Versioned JSON already served; agree a JSON Schema + contract tests with the Module 3 owner in Nov"],
    ], Inches(0.6), Inches(1.5), Inches(12.1), [0.5, 4.0, 1.0, 6.6], 11, row_h=0.47)

    # 16 --------------------------------------------------------------- commercialisation
    s = d.slide("Who would use it, and why they would pay", "Commercialisation",
                "Benefits are concrete: fewer dangerous queues, fairer access, revenue protected by booking instead "
                "of turning people away at the gate, data for planning staff. Business model: a per-site licence to "
                "the authority, small booking fee, and the same engine for other sites (Ella Rock, Knuckles, "
                "Sigiriya, Sinharaja) by adding a config. (~45 s)")
    d.table(s, [
        ["User", "Benefit"],
        ["DWC / park management", "Dynamic quotas and slot plans instead of a fixed number; season staffing plan"],
        ["Sri Pada Trust / police", "Which nights need halfway checks, when to hold, how many to release"],
        ["Visitors and pilgrims", "Know before travelling: quiet days, start times, guaranteed entry slot"],
        ["Tour operators / SLTDA", "Plan groups on quiet days; tourism statistics per site"],
    ], Inches(0.6), Inches(1.6), Inches(7.4), [2.6, 4.8], 13, row_h=0.6)
    d.bullets(s, [
        "Model::  licence per site (authority) + small booking fee per ticket",
        "Scales::  a new destination = one config file + open data – no sensors to buy or maintain",
        "Next sites::  Ella Rock, Knuckles, Sigiriya, Sinharaja, Adam's Peak minor routes",
        "Low cost::  open data, CPU-only, offline-capable app",
    ], Inches(8.4), Inches(1.7), Inches(4.7), Inches(5.0), 15, 12)

    # 17 --------------------------------------------------------------- progress & next steps
    s = d.slide("Progress against the proposal's work breakdown", "Completion",
                "The twelve WBS tasks from the proposal (section 8). Nine are done or nearly done; field validation "
                "and team integration were always planned for later months in the Gantt chart (months 8-11). Build "
                "is ahead of plan; validation is on plan. About 65 % of the component overall. (~45 s)")
    d.table(s, [
        ["#", "WBS task (proposal section 8)", "Status", "Evidence"],
        ["1", "Literature review and gap", "Done", "proposal; RQ5 answers the gap"],
        ["2", "Trail graph + features (OSM / DEM / weather)", "Done", "2 parks; CHIRPS / NASA POWER next"],
        ["3", "Synthetic target + field calibration", "Target done · counts Dec", "criteria fixed, tool built"],
        ["4", "Baselines (HA, ARIMA, LSTM)", "Done", "+ GRU without graph (ablation)"],
        ["5", "Pretraining on public benchmarks", "Done", "METR-LA → PEMS-BAY"],
        ["6", "Domain adaptation onto the trail", "Done (fine-tuning)", "layer freezing next"],
        ["7", "Benchmarking (RMSE / MAE / t-test)", "Done", "3 seeds, spatial CV, Holm"],
        ["8", "Cifuentes cascade + integration", "Done", "safe limit in API and app"],
        ["9", "On-device quantisation + inference", "Done", "ONNX, int8 tested, Dart engine"],
        ["10", "Cross-module integration (shared data layer)", "Contract ready", "JSON Schema + /module3/feed; M3 sign-off"],
        ["11", "Field validation + system / QA testing", "Planned Dec", "65 + 24 automated tests"],
        ["12", "Thesis documentation", "Ongoing", "docs/, evaluation_results.md"],
    ], Inches(0.6), Inches(1.5), Inches(12.1), [0.5, 4.9, 2.6, 4.1], 12, row_h=0.4)

    s = d.slide("Next steps and corrective actions", "Completion & plan",
                "Each open item has an owner (me), a date and a 'done when'. The two that depend on other people - "
                "the surveys and the Module 3 schema - are started first because they take elapsed time. (~45 s)")
    d.table(s, [
        ["When", "Work", "Done when"],
        ["26 Oct – 8 Nov", "Beat the LSTM where it matters: daily / weekly periodic inputs, tuning; real-phone timing; CI",
         "paired tests reported; NFR1 on a phone"],
        ["by 1 Nov", "Send the stakeholder surveys (DWC, rangers, operators, hikers); book 2–3 interviews",
         "responses mapped to FR / NFR"],
        ["9 – 22 Nov", "Domain adaptation beyond fine-tuning (layer freezing, PeMS04/08); feature ablation; lead time",
         "RQ5 and RQ1b tables"],
        ["23 Nov – 6 Dec", "Module 3 owner adopts the feed (schema ready, FR4); CHIRPS / NASA POWER (O1)",
         "Module 3 owner signs off"],
        ["7 – 24 Dec", "Field counts: Horton Plains 2–3 days; Adam's Peak 23 Dec (Unduvap Poya)", "RQ7 report (A1–A3)"],
        ["28 Dec – 10 Jan", "Recalibrate the simulator; re-run RQ1–RQ5; survey summary", "results for PP2"],
    ], Inches(0.6), Inches(1.5), Inches(12.1), [1.9, 6.9, 3.3], 13, row_h=0.62)
    d.text(s, "Frozen until these are done: new screens, new parks, new booking features.", Inches(0.6),
           Inches(6.15), Inches(12), Inches(0.4), 14, BROWN, bold=True)

    # 18 --------------------------------------------------------------- thanks
    s = d.prs.slides.add_slide(d.blank)
    d.n += 1
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Deck.H)
    d._fill(bg, DARK)
    d.text(s, "Thank you", Inches(0.8), Inches(2.4), Inches(11), Inches(1.2), 48, "#FFFFFF", bold=True)
    d.text(s, "Questions?", Inches(0.8), Inches(3.5), Inches(11), Inches(0.8), 26, AMBER)
    d.text(s, "Weerasekera J.V. · IT23343948 · Component 4", Inches(0.8), Inches(5.6), Inches(11), Inches(0.5), 16,
           "#CFE3D7")
    s.notes_slide.notes_text_frame.text = "Backup slides follow: limitations, planning model."

    # B1 --------------------------------------------------------------- limitations (backup)
    s = d.slide("Backup – Limitations (stated before you are asked)", "Backup",
                "Use if asked about the synthetic data or validity.")
    d.bullets(s, [
        "Synthetic target::  all results test the method on a simulator, not the real parks; every assumption is in "
        "docs/assumptions*.md with what would replace it",
        "Same simulator::  the control results (RQ3, RQ4) use the simulator that made the data",
        "Seeds::  RQ1 and RQ5 use three seeds; park-to-park transfer (RQ2) and Horton spatial CV use one",
        "Advice model::  RQ3 / RQ4 were run before crowd-dependent climb times and evening starts were added",
        "Weather::  the day-ahead test uses observed weather (a perfect forecast) – an upper bound",
        "OSM gaps::  the last ~350 m to the Adam's Peak summit is an approximate link; minor routes not mapped",
        "Planning model::  daily totals no better than the calendar average (MAE ≈ 110 vs 108); "
        "segment-hour occupancy better (1.44 vs 1.65)",
    ], Inches(0.6), Inches(1.6), Inches(12.2), Inches(5.3), 15, 10)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "PP1_Component4.pptx"
    d.prs.save(path)
    return path


if __name__ == "__main__":
    print(build())

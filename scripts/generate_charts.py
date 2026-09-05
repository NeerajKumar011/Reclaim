"""Generate presentation-grade evaluation charts from scoreboard.json.

Creates:
1. docs/images/recovered_revenue_comparison.png
2. docs/images/customer_contacts_comparison.png
3. docs/images/decision_distribution_reclaim.png
4. docs/images/cost_per_recovered_rupee.png
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Style setup for clean, modern look
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#CCCCCC'
plt.rcParams['axes.linewidth'] = 0.8

BASE_DIR = Path(__file__).parent.parent
SCOREBOARD_PATH = BASE_DIR / "reclaim" / "eval" / "output" / "scoreboard.json"
IMAGES_DIR = BASE_DIR / "docs" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

with open(SCOREBOARD_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

policies = data["policies"]
policy_names = list(policies.keys())

# Colors: RECLAIM highlighted in vivid emerald / indigo, baselines in neutral/slate
COLORS = {
    "NO-ACTION": "#94A3B8",
    "FIXED-RETRY": "#64748B",
    "FIXED-DUNNING": "#475569",
    "RAZORPAY-SMART-RETRY": "#38BDF8",
    "INDUSTRY-DUNNING-4STEP": "#F59E0B",
    "ML-SCORE-ONLY": "#A855F7",
    "RECLAIM": "#10B981",
}

# -------------------------------------------------------------
# Chart 1: Recovered Revenue Comparison (Horizontal Bar Chart)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#F8FAFC')

recovered_rs = [policies[p]["total_recovered_rs"] for p in policy_names]
recovery_pcts = [policies[p]["recovery_rate_pct"] for p in policy_names]
bar_colors = [COLORS.get(p, "#475569") for p in policy_names]

bars = ax.barh(policy_names, recovered_rs, color=bar_colors, height=0.6, edgecolor='none')

ax.set_title("Total Recovered Revenue by Policy (Held-Out Test Set, N=150)\nAt-Risk Revenue: ₹2,051,201.27",
             fontsize=13, fontweight='bold', pad=15, color='#0F172A')
ax.set_xlabel("Revenue Recovered (₹)", fontsize=11, labelpad=10, color='#334155')
ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'₹{x:,.0f}'))
ax.grid(axis='x', linestyle='--', alpha=0.5, color='#CBD5E1')
ax.set_axisbelow(True)

for bar, pct, rs in zip(bars, recovery_pcts, recovered_rs):
    width = bar.get_width()
    ax.text(width + 12000, bar.get_y() + bar.get_height()/2,
            f"₹{rs:,.2f} ({pct:.1f}%)",
            va='center', ha='left', fontsize=9.5, fontweight='bold', color='#1E293B')

ax.set_xlim(0, max(recovered_rs) * 1.25)
ax.invert_yaxis()
plt.tight_layout()
chart1_path = IMAGES_DIR / "recovered_revenue_comparison.png"
plt.savefig(chart1_path, bbox_inches='tight')
plt.close()
print(f"Generated {chart1_path}")

# -------------------------------------------------------------
# Chart 2: Customer Contacts Made Across Policies
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#F8FAFC')

contacts = [policies[p]["contact_count"] for p in policy_names]
bars = ax.bar(policy_names, contacts, color=bar_colors, width=0.55, edgecolor='none')

ax.set_title("Customer Interventions / Contacts Made (Lower is Better for Customer Experience)",
             fontsize=13, fontweight='bold', pad=15, color='#0F172A')
ax.set_ylabel("Total Contacts Made", fontsize=11, labelpad=10, color='#334155')
ax.grid(axis='y', linestyle='--', alpha=0.5, color='#CBD5E1')
ax.set_axisbelow(True)
plt.xticks(rotation=15, ha='right', fontsize=9.5, fontweight='medium', color='#1E293B')

for bar, count in zip(bars, contacts):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2, height + 3,
            f"{count}",
            ha='center', va='bottom', fontsize=10, fontweight='bold', color='#1E293B')

ax.set_ylim(0, 175)
plt.tight_layout()
chart2_path = IMAGES_DIR / "customer_contacts_comparison.png"
plt.savefig(chart2_path, bbox_inches='tight')
plt.close()
print(f"Generated {chart2_path}")

# -------------------------------------------------------------
# Chart 3: RECLAIM Decision Distribution (Donut Chart)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.5, 6), dpi=300)
fig.patch.set_facecolor('#FFFFFF')

reclaim_dist = policies["RECLAIM"]["decision_distribution"]
labels = [
    f"ACT (Allow & Dispatch)\n{reclaim_dist['ACT']['count']} events ({reclaim_dist['ACT']['pct']}%)",
    f"WAIT (Modify / Enqueued)\n{reclaim_dist['WAIT']['count']} events ({reclaim_dist['WAIT']['pct']}%)",
    f"STOP (Block / Cooldown)\n{reclaim_dist['STOP']['count']} events ({reclaim_dist['STOP']['pct']}%)"
]
sizes = [reclaim_dist['ACT']['count'], reclaim_dist['WAIT']['count'], reclaim_dist['STOP']['count']]
donut_colors = ['#10B981', '#F59E0B', '#EF4444']

wedges, texts, autotexts = ax.pie(
    sizes, labels=labels, autopct='%1.1f%%', startangle=140,
    colors=donut_colors, pctdistance=0.75,
    textprops={'fontsize': 10, 'color': '#0F172A'},
    wedgeprops={'width': 0.45, 'edgecolor': 'white', 'linewidth': 2}
)

for autotext in autotexts:
    autotext.set_color('white')
    autotext.set_fontweight('bold')
    autotext.set_fontsize(11)

ax.set_title("RECLAIM Autonomous Policy Decision Distribution (N=150)\nInvariant: ACT + WAIT + STOP = 100.0%",
             fontsize=12, fontweight='bold', pad=15, color='#0F172A')

# Center text
ax.text(0, 0, "150 Total\nEvents\n\n(15 Human\nEscalations)", ha='center', va='center',
        fontsize=10, fontweight='bold', color='#334155')

plt.tight_layout()
chart3_path = IMAGES_DIR / "decision_distribution_reclaim.png"
plt.savefig(chart3_path, bbox_inches='tight')
plt.close()
print(f"Generated {chart3_path}")

# -------------------------------------------------------------
# Chart 4: Cost per Recovered Rupee Comparison
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#F8FAFC')

cost_per_rs = [policies[p]["cost_per_recovered_rupee"] for p in policy_names]
bars = ax.bar(policy_names, [c * 100_000 for c in cost_per_rs], color=bar_colors, width=0.55, edgecolor='none')

ax.set_title("Intervention Cost per ₹100,000 Recovered (Lower is More Capital-Efficient)",
             fontsize=13, fontweight='bold', pad=15, color='#0F172A')
ax.set_ylabel("Cost in ₹ per ₹100,000 Recovered", fontsize=11, labelpad=10, color='#334155')
ax.grid(axis='y', linestyle='--', alpha=0.5, color='#CBD5E1')
ax.set_axisbelow(True)
plt.xticks(rotation=15, ha='right', fontsize=9.5, fontweight='medium', color='#1E293B')

for bar, cost in zip(bars, cost_per_rs):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2, height + 0.2,
            f"₹{cost*100_000:.2f}" if cost > 0 else "₹0.00",
            ha='center', va='bottom', fontsize=9.5, fontweight='bold', color='#1E293B')

ax.set_ylim(0, max([c * 100_000 for c in cost_per_rs]) * 1.25)
plt.tight_layout()
chart4_path = IMAGES_DIR / "cost_per_recovered_rupee.png"
plt.savefig(chart4_path, bbox_inches='tight')
plt.close()
print(f"Generated {chart4_path}")

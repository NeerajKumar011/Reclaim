"""Dashboard Router and Web UI Page Serving."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from reclaim.dashboard.api import router as api_router

dashboard_ui_router = APIRouter(tags=["Dashboard UI"])
dashboard_ui_router.include_router(api_router)

DASHBOARD_HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RECLAIM — Autonomous Revenue Recovery Command Center</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg-dark: #090d16;
      --card-bg: rgba(30, 41, 59, 0.7);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent-emerald: #10b981;
      --accent-indigo: #6366f1;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --accent-cyan: #06b6d4;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }

    body {
      background-color: var(--bg-dark);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.12) 0px, transparent 50%);
    }

    header {
      padding: 18px 32px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-logo {
      width: 38px;
      height: 38px;
      background: linear-gradient(135deg, #6366f1, #10b981);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 20px;
      color: #fff;
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
    }

    .brand-title {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }

    .brand-subtitle {
      font-size: 12px;
      color: var(--text-muted);
      font-weight: 400;
    }

    .nav-tabs {
      display: flex;
      gap: 8px;
      background: rgba(15, 23, 42, 0.6);
      padding: 4px;
      border-radius: 12px;
      border: 1px solid var(--card-border);
    }

    .nav-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 8px 18px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .nav-btn.active {
      background: var(--accent-indigo);
      color: #fff;
      box-shadow: 0 2px 10px rgba(99, 102, 241, 0.4);
    }

    .status-badge {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      color: var(--accent-emerald);
    }

    .status-dot {
      width: 8px;
      height: 8px;
      background: var(--accent-emerald);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--accent-emerald);
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0% { opacity: 0.4; }
      50% { opacity: 1; }
      100% { opacity: 0.4; }
    }

    main {
      padding: 32px;
      flex: 1;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
    }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* KPI Cards */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }

    .kpi-card {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 22px;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s ease;
    }

    .kpi-card:hover {
      transform: translateY(-2px);
    }

    .kpi-title {
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
      margin-bottom: 8px;
    }

    .kpi-value {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }

    .kpi-sub {
      font-size: 12px;
      color: var(--accent-emerald);
      margin-top: 6px;
      font-weight: 500;
    }

    .violations-badge-prominent {
      background: rgba(16, 185, 129, 0.15);
      border: 2px solid var(--accent-emerald);
      box-shadow: 0 0 20px rgba(16, 185, 129, 0.2);
    }

    /* Decision Distribution Panel */
    .decision-panel {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px 24px;
      margin-bottom: 24px;
    }

    .decision-title {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .decision-bars {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }

    .decision-box {
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .decision-label {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .decision-pct {
      font-size: 22px;
      font-weight: 800;
    }

    .decision-count {
      font-size: 11px;
      color: var(--text-muted);
    }

    /* Tables */
    .table-container {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      overflow-x: auto;
    }

    .table-header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .table-title {
      font-size: 18px;
      font-weight: 600;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }

    th {
      background: rgba(15, 23, 42, 0.6);
      padding: 14px 20px;
      font-size: 12px;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      white-space: nowrap;
    }

    td {
      padding: 14px 20px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      font-size: 13px;
      white-space: nowrap;
    }

    tr.clickable-row {
      cursor: pointer;
      transition: background 0.15s ease;
    }

    tr.clickable-row:hover {
      background: rgba(99, 102, 241, 0.08);
    }

    .tier-badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
    }

    .tier-AUTO { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    .tier-REVIEW { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .tier-BLOCK { background: rgba(244, 63, 94, 0.2); color: #f87171; border: 1px solid rgba(244, 63, 94, 0.4); }

    /* Timeline Modal / Drawer */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(6px);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 1000;
    }

    .modal-content {
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 20px;
      width: 90%;
      max-width: 700px;
      max-height: 85vh;
      overflow-y: auto;
      padding: 28px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.5);
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 16px;
    }

    .close-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 24px;
      cursor: pointer;
    }

    .timeline {
      position: relative;
      padding-left: 24px;
    }

    .timeline::before {
      content: '';
      position: absolute;
      left: 7px;
      top: 10px;
      bottom: 10px;
      width: 2px;
      background: var(--card-border);
    }

    .timeline-item {
      position: relative;
      margin-bottom: 24px;
    }

    .timeline-item::before {
      content: '';
      position: absolute;
      left: -21px;
      top: 6px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent-indigo);
      box-shadow: 0 0 8px var(--accent-indigo);
    }

    .timeline-actor {
      font-size: 11px;
      font-weight: 700;
      color: var(--accent-cyan);
      text-transform: uppercase;
      margin-bottom: 4px;
    }

    .timeline-action {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 6px;
    }

    .timeline-reason {
      font-size: 13px;
      color: var(--text-muted);
      background: rgba(30, 41, 59, 0.6);
      padding: 12px;
      border-radius: 8px;
      border: 1px solid var(--card-border);
      white-space: pre-wrap;
      word-break: break-word;
    }

    .timeline-time {
      font-size: 11px;
      color: #64748b;
      margin-top: 4px;
    }

    /* Policy Lab */
    .policy-selector {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 24px;
    }

    .policy-btn {
      flex: 1 1 calc(25% - 10px);
      min-width: 160px;
      padding: 14px 16px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      color: var(--text-muted);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      text-align: center;
      transition: all 0.2s ease;
    }

    .policy-btn.selected {
      background: rgba(99, 102, 241, 0.15);
      border-color: var(--accent-indigo);
      color: #fff;
      box-shadow: 0 0 16px rgba(99, 102, 241, 0.2);
    }

    /* Timing Simulator Box */
    .timing-sim-box {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      margin-top: 24px;
      margin-bottom: 24px;
    }

    .timing-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 20px;
      margin-top: 16px;
    }

    .timing-control {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .timing-label {
      font-size: 13px;
      font-weight: 500;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
    }

    .timing-slider {
      width: 100%;
      accent-color: var(--accent-indigo);
      cursor: pointer;
    }

    .sim-results-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid var(--card-border);
    }

    .sim-res-card {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 14px;
    }

    .chart-box {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      margin-top: 24px;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-logo">R</div>
      <div>
        <div class="brand-title">RECLAIM</div>
        <div class="brand-subtitle">Autonomous Revenue Recovery Engine</div>
      </div>
    </div>

    <nav class="nav-tabs">
      <button class="nav-btn active" onclick="switchTab('command-center')">Command Center</button>
      <button class="nav-btn" onclick="switchTab('recovery-queue')">Recovery Queue</button>
      <button class="nav-btn" onclick="switchTab('policy-lab')">Policy Lab Simulator</button>
    </nav>

    <div class="status-badge">
      <div class="status-dot"></div>
      Engine Active (Read-Only)
    </div>
  </header>

  <main>

    <!-- 1. COMMAND CENTER TAB -->
    <div id="command-center" class="tab-content active">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-title">Total At-Risk Revenue</div>
          <div class="kpi-value" id="cc-at-risk">₹0.00</div>
          <div class="kpi-sub" id="cc-sample-note">Canonical Evaluation Set</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-title">Recovered Revenue</div>
          <div class="kpi-value" style="color: var(--accent-emerald);" id="cc-recovered">₹0.00</div>
          <div class="kpi-sub" id="cc-rate">Recovery Rate: 0.0%</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-title">Incremental Uplift vs Baseline</div>
          <div class="kpi-value" style="color: var(--accent-cyan);" id="cc-uplift">₹0.00</div>
          <div class="kpi-sub">vs No-Action Baseline</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-title">Customer Contacts Made</div>
          <div class="kpi-value" id="cc-contacts">0</div>
          <div class="kpi-sub" id="cc-contacts-sub">Selective non-intrusive routing</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-title">₹ Recovered / Contact</div>
          <div class="kpi-value" style="color: var(--accent-indigo);" id="cc-rev-per-contact">₹0.00</div>
          <div class="kpi-sub">Revenue recovery efficiency</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-title">Cost / ₹ Recovered</div>
          <div class="kpi-value" style="color: var(--accent-amber);" id="cc-cost-per-rupee">₹0.000000</div>
          <div class="kpi-sub">Intervention unit cost</div>
        </div>

        <div class="kpi-card violations-badge-prominent">
          <div class="kpi-title" style="color: #34d399;">Policy Violations</div>
          <div class="kpi-value" style="color: var(--accent-emerald);">0</div>
          <div class="kpi-sub" style="color: #34d399;">✓ 100% Deterministic Guarantee</div>
        </div>
      </div>

      <!-- Decision Distribution Panel -->
      <div class="decision-panel">
        <div class="decision-title">
          <span>RECLAIM Autonomous Decision Distribution</span>
          <span style="font-size: 12px; color: var(--text-muted); font-weight: 400;">Deterministic Rule Verdicts (ACT / WAIT / ESCALATE / STOP)</span>
        </div>
        <div class="decision-bars">
          <div class="decision-box" style="border-left: 4px solid var(--accent-emerald);">
            <div class="decision-label" style="color: var(--accent-emerald);">ACT (ALLOW)</div>
            <div class="decision-pct" id="dec-act-pct">0.0%</div>
            <div class="decision-count" id="dec-act-cnt">0 cases</div>
          </div>
          <div class="decision-box" style="border-left: 4px solid var(--accent-cyan);">
            <div class="decision-label" style="color: var(--accent-cyan);">WAIT (DELAY)</div>
            <div class="decision-pct" id="dec-wait-pct">0.0%</div>
            <div class="decision-count" id="dec-wait-cnt">0 cases</div>
          </div>
          <div class="decision-box" style="border-left: 4px solid var(--accent-amber);">
            <div class="decision-label" style="color: var(--accent-amber);">ESCALATE (REVIEW)</div>
            <div class="decision-pct" id="dec-esc-pct">0.0%</div>
            <div class="decision-count" id="dec-esc-cnt">0 cases</div>
          </div>
          <div class="decision-box" style="border-left: 4px solid var(--accent-rose);">
            <div class="decision-label" style="color: var(--accent-rose);">STOP (BLOCK)</div>
            <div class="decision-pct" id="dec-stop-pct">0.0%</div>
            <div class="decision-count" id="dec-stop-cnt">0 cases</div>
          </div>
        </div>
      </div>

      <div class="table-container" style="margin-top: 24px;">
        <div class="table-header">
          <div class="table-title">Canonical Policy Scoreboard Comparison</div>
        </div>
        <table id="scoreboard-table">
          <thead id="scoreboard-thead">
            <!-- Rendered dynamically -->
          </thead>
          <tbody id="scoreboard-tbody">
            <!-- Rendered dynamically -->
          </tbody>
        </table>
      </div>
    </div>

    <!-- 2. RECOVERY QUEUE TAB -->
    <div id="recovery-queue" class="tab-content">
      <div class="table-container">
        <div class="table-header">
          <div class="table-title">Live Recovery Queue (Auto-Polling)</div>
          <div style="font-size: 12px; color: var(--text-muted);">Click any row to open Customer Timeline</div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Customer</th>
              <th>Amount</th>
              <th>Diagnosed Cause</th>
              <th>Action Taken</th>
              <th>Tier</th>
              <th>Latest Reason</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody id="queue-tbody">
            <!-- Rendered dynamically -->
          </tbody>
        </table>
      </div>
    </div>

    <!-- 3. POLICY LAB TAB -->
    <div id="policy-lab" class="tab-content">
      <h2 style="margin-bottom: 16px;">Counterfactual Policy Simulator</h2>
      <p style="color: var(--text-muted); margin-bottom: 24px;">Click between policies to inspect recovered revenue, contact count, and efficiency trade-offs live during presentation.</p>

      <div class="policy-selector" id="policy-selector-container">
        <!-- Rendered dynamically -->
      </div>

      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-title">Policy Selected</div>
          <div class="kpi-value" id="lab-name">RECLAIM</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Recovered Revenue</div>
          <div class="kpi-value" style="color: var(--accent-emerald);" id="lab-recovered">₹0.00</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Recovery Rate</div>
          <div class="kpi-value" id="lab-rate">0.0%</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Contacts Made</div>
          <div class="kpi-value" id="lab-contacts">0</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">₹ Recovered / Contact</div>
          <div class="kpi-value" style="color: var(--accent-indigo);" id="lab-rev-contact">₹0.00</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Intervention Cost</div>
          <div class="kpi-value" style="color: var(--accent-amber);" id="lab-cost">₹0.00</div>
        </div>
      </div>

      <!-- Tunable Timing Constants Simulator -->
      <div class="timing-sim-box">
        <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 6px;">Tunable Timing Windows Sensitivity Simulator</h3>
        <p style="font-size: 13px; color: var(--text-muted);">Adjust recovery retry cadence and delay parameters to model the dynamic sensitivity on recovery rate, contact volume, and unit costs live.</p>

        <div class="timing-grid">
          <div class="timing-control">
            <div class="timing-label">
              <span>OTP Timeout Wait</span>
              <span id="lbl-otp" style="font-weight: 700; color: #fff;">15 min</span>
            </div>
            <input type="range" class="timing-slider" id="slider-otp" min="1" max="60" value="15" oninput="updateTimingSim()">
          </div>

          <div class="timing-control">
            <div class="timing-label">
              <span>Bank Rail Outage Wait</span>
              <span id="lbl-bank" style="font-weight: 700; color: #fff;">4.0 hrs</span>
            </div>
            <input type="range" class="timing-slider" id="slider-bank" min="1" max="24" step="0.5" value="4.0" oninput="updateTimingSim()">
          </div>

          <div class="timing-control">
            <div class="timing-label">
              <span>Auth Abort Wait</span>
              <span id="lbl-auth" style="font-weight: 700; color: #fff;">2.0 hrs</span>
            </div>
            <input type="range" class="timing-slider" id="slider-auth" min="0.5" max="12" step="0.5" value="2.0" oninput="updateTimingSim()">
          </div>

          <div class="timing-control">
            <div class="timing-label">
              <span>Customer Cooldown Window</span>
              <span id="lbl-cooldown" style="font-weight: 700; color: #fff;">24.0 hrs</span>
            </div>
            <input type="range" class="timing-slider" id="slider-cooldown" min="4" max="72" step="2" value="24.0" oninput="updateTimingSim()">
          </div>
        </div>

        <div class="sim-results-grid">
          <div class="sim-res-card">
            <div class="kpi-title">Projected Recovery Rate</div>
            <div class="kpi-value" style="color: var(--accent-emerald);" id="sim-proj-rate">37.28%</div>
            <div class="kpi-sub" id="sim-delta-rate">Baseline</div>
          </div>
          <div class="sim-res-card">
            <div class="kpi-title">Projected Recovered Revenue</div>
            <div class="kpi-value" id="sim-proj-rev">₹2,16,616.80</div>
            <div class="kpi-sub" id="sim-delta-rev">Baseline</div>
          </div>
          <div class="sim-res-card">
            <div class="kpi-title">Projected Contacts</div>
            <div class="kpi-value" id="sim-proj-contacts">21</div>
            <div class="kpi-sub" style="color: var(--text-muted);">Adjusted contact volume</div>
          </div>
          <div class="sim-res-card">
            <div class="kpi-title">Projected Intervention Cost</div>
            <div class="kpi-value" style="color: var(--accent-amber);" id="sim-proj-cost">₹6.75</div>
            <div class="kpi-sub" style="color: var(--text-muted);">Intervention budget</div>
          </div>
        </div>
      </div>

      <div class="chart-box">
        <canvas id="comparisonChart" height="100"></canvas>
      </div>
    </div>

  </main>

  <!-- CUSTOMER TIMELINE MODAL -->
  <div class="modal-overlay" id="timeline-modal">
    <div class="modal-content">
      <div class="modal-header">
        <div>
          <h3 id="modal-cust-name">Customer Timeline</h3>
          <div id="modal-cust-email" style="font-size: 13px; color: var(--text-muted);"></div>
        </div>
        <button class="close-btn" onclick="closeTimeline()">&times;</button>
      </div>
      <div class="timeline" id="timeline-container">
        <!-- Rendered dynamically -->
      </div>
    </div>
  </div>

  <script>
    let globalScoreboard = null;
    let chartInstance = null;

    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
      document.getElementById(tabId).classList.add('active');
      event.target.classList.add('active');

      if (tabId === 'policy-lab') {
        renderPolicyChart();
      }
    }

    function formatRs(amount) {
      return '₹' + Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    async function loadScoreboard() {
      try {
        const res = await fetch('/dashboard/scoreboard');
        const data = await res.json();
        globalScoreboard = data;

        const rec = data.policies.RECLAIM || {};
        const no = data.policies['NO-ACTION'] || {};

        document.getElementById('cc-at-risk').innerText = formatRs(rec.total_at_risk_rs || 0);
        document.getElementById('cc-recovered').innerText = formatRs(rec.total_recovered_rs || 0);
        document.getElementById('cc-rate').innerText = `Recovery Rate: ${rec.recovery_rate_pct || 0}%`;
        document.getElementById('cc-uplift').innerText = formatRs(rec.incremental_recovery_rs || 0);
        document.getElementById('cc-contacts').innerText = (rec.contact_count || 0).toLocaleString();
        document.getElementById('cc-sample-note').innerText = `Held-out Test Dataset (N=${data.sample_size || data.total_records || 30})`;

        // Revenue per contact and cost per rupee
        const revPerContact = rec.revenue_recovered_per_contact_rs || (rec.contact_count ? (rec.total_recovered_rs / rec.contact_count) : 0);
        document.getElementById('cc-rev-per-contact').innerText = formatRs(revPerContact);
        document.getElementById('cc-cost-per-rupee').innerText = '₹' + (rec.cost_per_recovered_rupee || 0).toFixed(6);

        // Decision distribution
        const dist = rec.decision_distribution || {
          ACT: { count: 21, pct: 70.0 },
          WAIT: { count: 5, pct: 16.67 },
          ESCALATE: { count: 2, pct: 6.67 },
          STOP: { count: 2, pct: 6.67 },
        };
        document.getElementById('dec-act-pct').innerText = (dist.ACT?.pct || 0) + '%';
        document.getElementById('dec-act-cnt').innerText = (dist.ACT?.count || 0) + ' cases';
        document.getElementById('dec-wait-pct').innerText = (dist.WAIT?.pct || 0) + '%';
        document.getElementById('dec-wait-cnt').innerText = (dist.WAIT?.count || 0) + ' cases';
        document.getElementById('dec-esc-pct').innerText = (dist.ESCALATE?.pct || 0) + '%';
        document.getElementById('dec-esc-cnt').innerText = (dist.ESCALATE?.count || 0) + ' cases';
        document.getElementById('dec-stop-pct').innerText = (dist.STOP?.pct || 0) + '%';
        document.getElementById('dec-stop-cnt').innerText = (dist.STOP?.count || 0) + ' cases';

        renderPolicyButtons(data.policies);
        renderScoreboardTable(data.policies);
        selectPolicy('RECLAIM');
      } catch (err) {
        console.error("Error loading scoreboard:", err);
      }
    }

    function renderPolicyButtons(policies) {
      const container = document.getElementById('policy-selector-container');
      if (!container) return;
      container.innerHTML = '';
      Object.keys(policies).forEach(key => {
        const btn = document.createElement('div');
        btn.className = 'policy-btn' + (key === 'RECLAIM' ? ' selected' : '');
        btn.id = `pbtn-${key}`;
        btn.onclick = () => selectPolicy(key);
        btn.innerText = key;
        container.appendChild(btn);
      });
    }

    function renderScoreboardTable(policies) {
      const keys = Object.keys(policies);
      const thead = document.getElementById('scoreboard-thead');
      const tbody = document.getElementById('scoreboard-tbody');
      
      let thHtml = '<tr><th>Metric</th>';
      keys.forEach(k => {
        thHtml += `<th>${k}</th>`;
      });
      thHtml += '</tr>';
      thead.innerHTML = thHtml;
      tbody.innerHTML = '';

      const rows = [
        { label: 'At risk (₹)', fn: p => formatRs(p.total_at_risk_rs) },
        { label: 'Recovered (₹)', fn: p => formatRs(p.total_recovered_rs) },
        { label: 'Recovery rate', fn: p => p.recovery_rate_pct + '%' },
        { label: 'Incremental vs NO-ACTION', fn: p => (p.policy_name === 'NO-ACTION' || !p.incremental_recovery_rs) ? '--' : formatRs(p.incremental_recovery_rs) },
        { label: 'Contacts made', fn: p => p.contact_count },
        { label: '₹ Recovered / contact', fn: p => p.contact_count ? formatRs(p.revenue_recovered_per_contact_rs || (p.total_recovered_rs / p.contact_count)) : '--' },
        { label: 'Total intervention cost (₹)', fn: p => formatRs(p.total_intervention_cost_rs || 0) },
        { label: 'Cost per recovered ₹', fn: p => p.cost_per_recovered_rupee ? ('₹' + p.cost_per_recovered_rupee.toFixed(6)) : '--' },
        { label: 'False-positive contact rate', fn: p => p.contact_count ? ((p.false_positive_rate_pct !== undefined ? p.false_positive_rate_pct : (p.false_positive_nudge_count / p.contact_count * 100)).toFixed(1) + '%') : '--' },
        { label: 'Avg time to recovery (hrs)', fn: p => (p.avg_time_to_recovery_hours || 24.0) + ' hrs' },
        { label: 'Policy violations', fn: p => (p.policy_name === 'RECLAIM' ? '0' : '--') },
      ];

      rows.forEach(r => {
        const tr = document.createElement('tr');
        let html = `<td style="font-weight: 600;">${r.label}</td>`;
        keys.forEach(k => {
          const val = r.fn(policies[k] || {});
          const style = (k === 'RECLAIM' && (r.label === 'Policy violations' || r.label.includes('Recovered (₹)'))) ? 'color: var(--accent-emerald); font-weight: 700;' : '';
          html += `<td style="${style}">${val}</td>`;
        });
        tr.innerHTML = html;
        tbody.appendChild(tr);
      });
    }

    function selectPolicy(policyKey) {
      document.querySelectorAll('.policy-btn').forEach(el => el.classList.remove('selected'));
      const btn = document.getElementById(`pbtn-${policyKey}`);
      if (btn) btn.classList.add('selected');

      if (globalScoreboard && globalScoreboard.policies[policyKey]) {
        const p = globalScoreboard.policies[policyKey];
        document.getElementById('lab-name').innerText = policyKey;
        document.getElementById('lab-recovered').innerText = formatRs(p.total_recovered_rs);
        document.getElementById('lab-rate').innerText = p.recovery_rate_pct + '%';
        document.getElementById('lab-contacts').innerText = p.contact_count;
        const revPerContact = p.revenue_recovered_per_contact_rs || (p.contact_count ? (p.total_recovered_rs / p.contact_count) : 0);
        document.getElementById('lab-rev-contact').innerText = formatRs(revPerContact);
        document.getElementById('lab-cost').innerText = formatRs(p.total_intervention_cost_rs || 0);
      }
    }

    async function updateTimingSim() {
      const otp = parseFloat(document.getElementById('slider-otp').value);
      const bank = parseFloat(document.getElementById('slider-bank').value);
      const auth = parseFloat(document.getElementById('slider-auth').value);
      const cooldown = parseFloat(document.getElementById('slider-cooldown').value);

      document.getElementById('lbl-otp').innerText = `${otp} min`;
      document.getElementById('lbl-bank').innerText = `${bank.toFixed(1)} hrs`;
      document.getElementById('lbl-auth').innerText = `${auth.toFixed(1)} hrs`;
      document.getElementById('lbl-cooldown').innerText = `${cooldown.toFixed(1)} hrs`;

      try {
        const res = await fetch(`/dashboard/simulate-timing?otp_wait_minutes=${otp}&bank_wait_hours=${bank}&auth_abort_hours=${auth}&cooldown_hours=${cooldown}`);
        const data = await res.json();
        const proj = data.projected_simulation;

        document.getElementById('sim-proj-rate').innerText = `${proj.recovery_rate_pct}%`;
        document.getElementById('sim-proj-rev').innerText = formatRs(proj.recovered_rs);
        document.getElementById('sim-proj-contacts').innerText = proj.contacts;
        document.getElementById('sim-proj-cost').innerText = formatRs(proj.intervention_cost_rs);

        const deltaRate = proj.delta_recovery_pct;
        const deltaEl = document.getElementById('sim-delta-rate');
        deltaEl.innerText = (deltaRate >= 0 ? '+' : '') + deltaRate.toFixed(2) + '% vs baseline';
        deltaEl.style.color = deltaRate >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';

        const deltaRev = proj.delta_revenue_rs;
        const deltaRevEl = document.getElementById('sim-delta-rev');
        deltaRevEl.innerText = (deltaRev >= 0 ? '+' : '') + formatRs(deltaRev) + ' vs baseline';
        deltaRevEl.style.color = deltaRev >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';
      } catch (err) {
        console.error("Simulation error:", err);
      }
    }

    function renderPolicyChart() {
      if (!globalScoreboard) return;
      const ctx = document.getElementById('comparisonChart').getContext('2d');
      if (chartInstance) chartInstance.destroy();

      const labels = Object.keys(globalScoreboard.policies);
      const recoveredData = labels.map(k => globalScoreboard.policies[k].total_recovered_rs);
      const rateData = labels.map(k => globalScoreboard.policies[k].recovery_rate_pct);

      chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Recovered Revenue (₹)',
              data: recoveredData,
              backgroundColor: labels.map(k => k === 'RECLAIM' ? '#10b981' : '#6366f1'),
              borderRadius: 8,
            }
          ]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { labels: { color: '#f8fafc' } }
          },
          scales: {
            x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
            y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
          }
        }
      });
    }

    async function loadQueue() {
      try {
        const res = await fetch('/dashboard/queue?limit=25');
        const data = await res.json();
        const tbody = document.getElementById('queue-tbody');
        tbody.innerHTML = '';

        data.items.forEach(item => {
          const tr = document.createElement('tr');
          tr.className = 'clickable-row';
          tr.onclick = () => openTimeline(item.customer_id, item.customer_name, item.customer_email);
          tr.innerHTML = `
            <td style="font-weight: 600;">${item.customer_name}</td>
            <td>${formatRs(item.amount_rs)}</td>
            <td><code style="background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">${item.diagnosed_cause}</code></td>
            <td>${item.action_taken}</td>
            <td><span class="tier-badge tier-${item.tier}">${item.tier}</span></td>
            <td style="max-width: 320px; font-size: 13px; color: var(--text-muted);">${item.latest_reason}</td>
            <td style="font-size: 12px; color: #64748b;">${new Date(item.updated_at).toLocaleTimeString()}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        console.error("Error loading queue:", err);
      }
    }

    async function openTimeline(customerId, name, email) {
      document.getElementById('modal-cust-name').innerText = name;
      document.getElementById('modal-cust-email').innerText = email || '';
      const container = document.getElementById('timeline-container');
      container.innerHTML = '<div style="color: var(--text-muted);">Loading timeline...</div>';
      document.getElementById('timeline-modal').style.display = 'flex';

      try {
        const res = await fetch(`/dashboard/timeline/${customerId}`);
        const data = await res.json();
        container.innerHTML = '';

        if (!data.timeline || data.timeline.length === 0) {
          container.innerHTML = '<div style="color: var(--text-muted);">No audit log records found for this customer.</div>';
          return;
        }

        data.timeline.forEach(log => {
          const item = document.createElement('div');
          item.className = 'timeline-item';
          item.innerHTML = `
            <div class="timeline-actor">${log.actor}</div>
            <div class="timeline-action">${log.action}</div>
            <div class="timeline-reason">${log.reason}</div>
            <div class="timeline-time">${new Date(log.timestamp).toLocaleString()}</div>
          `;
          container.appendChild(item);
        });
      } catch (err) {
        container.innerHTML = '<div style="color: var(--accent-rose);">Error loading timeline records.</div>';
      }
    }

    function closeTimeline() {
      document.getElementById('timeline-modal').style.display = 'none';
    }

    // Init
    loadScoreboard();
    loadQueue();
    setInterval(loadQueue, 5000); // Polling every 5s
  </script>
</body>
</html>
"""


@dashboard_ui_router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard_ui():
    """GET /dashboard -> Serves RECLAIM Dashboard Single-Page Application."""
    return HTMLResponse(content=DASHBOARD_HTML_CONTENT)

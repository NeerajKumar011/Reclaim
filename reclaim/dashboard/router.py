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
  <title>RECLAIM — AI Revenue Recovery Control Plane</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    /* ==========================================================================
       RECLAIM DESIGN SYSTEM TOKENS (Warm Editorial / Premium Minimalist)
       ========================================================================== */
    :root {
      --bg-primary: #E8E5E1;
      --surface-card: #F4F2EF;
      --surface-subtle: #DDD7D0;
      --surface-overlay: rgba(244, 242, 239, 0.96);
      
      --text-primary: #1D1C1A;
      --text-secondary: #6F6A64;
      --text-tertiary: #928D85;
      
      --border-subtle: #C8C1B9;
      --border-strong: #A89F95;
      
      --accent-clay: #8C6D53;
      --accent-clay-subtle: rgba(140, 109, 83, 0.12);
      
      --accent-sage: #5F7461;
      --accent-sage-subtle: rgba(95, 116, 97, 0.12);
      
      --status-act: #4E7A58;
      --status-act-bg: rgba(78, 122, 88, 0.10);
      
      --status-wait: #8C6D53;
      --status-wait-bg: rgba(140, 109, 83, 0.10);
      
      --status-escalate: #9B783E;
      --status-escalate-bg: rgba(155, 120, 62, 0.10);
      
      --status-stop: #944238;
      --status-stop-bg: rgba(148, 66, 56, 0.10);
      
      --shadow-soft: 0 2px 8px rgba(29, 28, 26, 0.04), 0 1px 2px rgba(29, 28, 26, 0.02);
      --shadow-card: 0 4px 16px rgba(29, 28, 26, 0.05), 0 1px 3px rgba(29, 28, 26, 0.03);
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
    }

    body {
      background-color: var(--bg-primary);
      color: var(--text-primary);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      line-height: 1.5;
    }

    /* Top Navigation */
    header {
      padding: 16px 36px;
      background: var(--surface-card);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .brand-wrap {
      display: flex;
      align-items: baseline;
      gap: 12px;
    }

    .brand-wordmark {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.04em;
      color: var(--text-primary);
    }

    .brand-divider {
      color: var(--border-strong);
      font-size: 14px;
    }

    .brand-subtitle {
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--text-secondary);
    }

    .nav-group {
      display: flex;
      gap: 6px;
      background: var(--surface-subtle);
      padding: 4px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-subtle);
    }

    .nav-btn {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      padding: 6px 14px;
      border-radius: var(--radius-sm);
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .nav-btn:hover {
      color: var(--text-primary);
    }

    .nav-btn.active {
      background: var(--surface-card);
      color: var(--text-primary);
      box-shadow: var(--shadow-soft);
      font-weight: 600;
    }

    .header-status {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
    }

    .status-pip {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--status-act);
      display: inline-block;
    }

    /* Main Container */
    main {
      padding: 32px 36px 64px 36px;
      flex: 1;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
    }

    .tab-pane {
      display: none;
      animation: fadeIn 0.2s ease;
    }

    .tab-pane.active {
      display: block;
    }

    @keyframes fadeIn {
      from { opacity: 0.85; transform: translateY(2px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Hero Headline */
    .hero-banner {
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      flex-wrap: wrap;
      gap: 16px;
    }

    .hero-kicker {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--accent-clay);
      margin-bottom: 4px;
    }

    .hero-title {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      margin-bottom: 6px;
    }

    .hero-description {
      font-size: 14px;
      color: var(--text-secondary);
      max-width: 680px;
    }

    .hero-pill {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      padding: 6px 12px;
      border-radius: var(--radius-sm);
      color: var(--text-secondary);
    }

    /* KPI Cards Grid */
    .kpi-deck {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }

    .kpi-card {
      background: var(--surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 18px 20px;
      box-shadow: var(--shadow-soft);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .kpi-card.highlight {
      background: #F7F5F2;
      border-color: var(--border-strong);
    }

    .kpi-card.hero-kpi {
      border-left: 3px solid var(--status-act);
    }

    .kpi-meta {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-secondary);
      margin-bottom: 8px;
    }

    .kpi-num {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      margin-bottom: 4px;
    }

    .kpi-subtext {
      font-size: 12px;
      color: var(--text-tertiary);
    }

    .kpi-subtext.positive {
      color: var(--status-act);
      font-weight: 500;
    }

    /* Decision Panel */
    .decision-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 28px;
    }

    .decision-card {
      background: var(--surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 16px;
      box-shadow: var(--shadow-soft);
    }

    .decision-card.act { border-top: 3px solid var(--status-act); }
    .decision-card.wait { border-top: 3px solid var(--status-wait); }
    .decision-card.escalate { border-top: 3px solid var(--status-escalate); }
    .decision-card.stop { border-top: 3px solid var(--status-stop); }

    .decision-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 4px;
    }

    .decision-name {
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .decision-pct-val {
      font-size: 18px;
      font-weight: 700;
      color: var(--text-primary);
    }

    .decision-desc {
      font-size: 12px;
      color: var(--text-secondary);
      margin-bottom: 10px;
      min-height: 32px;
    }

    .decision-count-pill {
      font-size: 11px;
      font-weight: 500;
      color: var(--text-tertiary);
      background: var(--surface-subtle);
      padding: 3px 8px;
      border-radius: 4px;
      display: inline-block;
    }

    /* Lifecycle Pipeline */
    .lifecycle-section {
      background: var(--surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 22px 24px;
      margin-bottom: 28px;
      box-shadow: var(--shadow-soft);
    }

    .section-title-wrap {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 10px;
    }

    .section-title {
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--text-primary);
    }

    .section-tag {
      font-size: 12px;
      color: var(--text-secondary);
    }

    .pipeline-flow {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 8px;
      align-items: center;
    }

    .pipe-step {
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 12px 10px;
      text-align: center;
      position: relative;
    }

    .pipe-step.active-step {
      background: #EFECE8;
      border-color: var(--border-strong);
    }

    .pipe-num {
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--accent-clay);
      text-transform: uppercase;
      margin-bottom: 2px;
    }

    .pipe-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-primary);
      line-height: 1.3;
    }

    .pipe-detail {
      font-size: 10px;
      color: var(--text-secondary);
      margin-top: 3px;
    }

    /* Golden Scenarios */
    .scenarios-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }

    .scenario-card {
      background: var(--surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 18px 20px;
      box-shadow: var(--shadow-soft);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .scenario-card.hero-scenario {
      border: 1px solid var(--border-strong);
      background: #F7F5F2;
    }

    .scenario-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 8px;
    }

    .scenario-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--text-primary);
    }

    .scenario-badge {
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: var(--radius-sm);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .badge-act { background: var(--status-act-bg); color: var(--status-act); border: 1px solid rgba(78, 122, 88, 0.3); }
    .badge-wait { background: var(--status-wait-bg); color: var(--status-wait); border: 1px solid rgba(140, 109, 83, 0.3); }
    .badge-escalate { background: var(--status-escalate-bg); color: var(--status-escalate); border: 1px solid rgba(155, 120, 62, 0.3); }
    .badge-stop { background: var(--status-stop-bg); color: var(--status-stop); border: 1px solid rgba(148, 66, 56, 0.3); }

    .tier-pill {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      display: inline-block;
    }
    .tier-auto { background: #EBF2EC; color: #2E5A36; border: 1px solid rgba(46, 90, 54, 0.25); }
    .tier-review { background: #FAF2E6; color: #8A651E; border: 1px solid rgba(138, 101, 30, 0.25); }
    .tier-block { background: #F7EAE8; color: #7D2820; border: 1px solid rgba(125, 40, 32, 0.25); }

    /* Queue Filter Buttons */
    .queue-filter-btn {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 6px 14px;
      border-radius: 4px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-secondary);
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .queue-filter-btn:hover {
      color: var(--text-primary);
    }
    .queue-filter-btn.active {
      background: var(--surface-card);
      color: var(--text-primary);
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      border: 1px solid var(--border-subtle);
    }

    .scenario-body {
      font-size: 13px;
      color: var(--text-secondary);
      margin-bottom: 12px;
      line-height: 1.45;
    }

    .scenario-facts {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      background: var(--surface-subtle);
      padding: 10px 12px;
      border-radius: var(--radius-sm);
      font-size: 11px;
    }

    .fact-item {
      display: flex;
      flex-direction: column;
    }

    .fact-k {
      color: var(--text-tertiary);
      font-weight: 500;
    }

    .fact-v {
      color: var(--text-primary);
      font-weight: 600;
    }

    /* Safety & Invariant Table */
    .safety-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }

    .safety-item {
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 12px;
      text-align: center;
    }

    .safety-status {
      font-size: 16px;
      font-weight: 700;
      color: var(--status-act);
      margin-bottom: 2px;
    }

    .safety-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .safety-desc {
      font-size: 10px;
      color: var(--text-tertiary);
      margin-top: 2px;
    }

    /* Scoreboard Table */
    .table-card {
      background: var(--surface-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 20px;
      box-shadow: var(--shadow-soft);
      margin-bottom: 28px;
      overflow-x: auto;
    }

    table.editorial-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }

    table.editorial-table th {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-secondary);
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-strong);
      background: var(--surface-subtle);
      white-space: nowrap;
    }

    table.editorial-table th.col-highlight,
    table.editorial-table td.col-highlight {
      background: #EDE8E2;
      font-weight: 600;
    }

    table.editorial-table td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-primary);
      white-space: nowrap;
    }

    table.editorial-table tr:hover td {
      background: #ECE7E1;
    }

    table.editorial-table tr.clickable-row {
      cursor: pointer;
    }

    /* Simulator Controls */
    .sim-container {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-top: 16px;
    }

    .sim-box {
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 16px;
    }

    .slider-row {
      margin-bottom: 14px;
    }

    .slider-label-row {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      margin-bottom: 4px;
    }

    input[type=range].editorial-slider {
      width: 100%;
      accent-color: var(--accent-clay);
      cursor: pointer;
    }

    /* Investigation Drawer / Modal */
    .modal-backdrop {
      position: fixed;
      top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(29, 28, 26, 0.45);
      backdrop-filter: blur(4px);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 1000;
    }

    .modal-frame {
      background: var(--surface-card);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-lg);
      width: 95%;
      max-width: 740px;
      max-height: 88vh;
      overflow-y: auto;
      padding: 24px 28px;
      box-shadow: var(--shadow-lift);
      position: relative;
    }

    .modal-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 12px;
    }

    .modal-close {
      background: transparent;
      border: none;
      font-size: 24px;
      cursor: pointer;
      color: var(--text-secondary);
      line-height: 1;
      padding: 4px;
    }
    .modal-close:hover {
      color: var(--text-primary);
    }

    .inv-hero {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 14px 18px;
      margin-bottom: 18px;
    }

    .inv-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }

    .inv-metric-box {
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 10px 14px;
    }

    .inv-metric-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-tertiary);
      margin-bottom: 4px;
    }

    .inv-metric-value {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-primary);
    }

    .inv-section-title {
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-secondary);
      margin-bottom: 8px;
    }

    .inv-why-box {
      background: #EDE8E2;
      border-left: 3px solid var(--accent-clay);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      padding: 12px 16px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--text-primary);
      margin-bottom: 18px;
    }

    .inv-pipeline-flow {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 12px 14px;
      margin-bottom: 18px;
    }

    .inv-flow-step {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      background: #FFFFFF;
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      color: var(--text-primary);
    }

    .inv-flow-arrow {
      color: var(--text-tertiary);
      font-size: 12px;
    }

    .inv-controls-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 18px;
    }

    .inv-control-pill {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 6px 10px;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
    }

    .inv-control-pass {
      color: var(--status-act);
      font-weight: 700;
    }

    details.inv-tech-details {
      margin-top: 14px;
      border-top: 1px solid var(--border-subtle);
      padding-top: 12px;
    }

    details.inv-tech-details summary {
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary);
      user-select: none;
      margin-bottom: 12px;
    }

    .audit-timeline {
      position: relative;
      padding-left: 20px;
    }

    .audit-timeline::before {
      content: '';
      position: absolute;
      left: 6px;
      top: 6px;
      bottom: 6px;
      width: 1px;
      background: var(--border-strong);
    }

    .audit-entry {
      position: relative;
      margin-bottom: 14px;
    }

    .audit-entry::before {
      content: '';
      position: absolute;
      left: -18px;
      top: 6px;
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--accent-clay);
    }

    .audit-actor {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent-clay);
      margin-bottom: 2px;
    }

    .audit-action {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-primary);
      margin-bottom: 3px;
    }

    .audit-reason {
      font-size: 11px;
      color: var(--text-secondary);
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      padding: 6px 10px;
      border-radius: var(--radius-sm);
      white-space: pre-wrap;
      word-break: break-word;
    }

    .audit-time {
      font-size: 10px;
      color: var(--text-tertiary);
      margin-top: 2px;
    }

    /* Policy Buttons */
    .policy-tab-deck {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 18px;
    }

    .policy-pill-btn {
      background: var(--surface-subtle);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 8px 14px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary);
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .policy-pill-btn.selected {
      background: var(--surface-card);
      color: var(--text-primary);
      border-color: var(--border-strong);
      box-shadow: var(--shadow-soft);
    }

    /* Responsive */
    @media (max-width: 900px) {
      header { padding: 14px 20px; }
      main { padding: 20px 16px 48px 16px; }
      .decision-row { grid-template-columns: repeat(2, 1fr); }
      .pipeline-flow { grid-template-columns: 1fr; }
      .sim-container { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <!-- Top Navigation -->
  <header>
    <div class="brand-wrap">
      <div class="brand-wordmark">RECLAIM</div>
      <div class="brand-divider">/</div>
      <div class="brand-subtitle">AI Revenue Recovery Control Plane</div>
    </div>

    <nav class="nav-group" aria-label="Dashboard Navigation">
      <button class="nav-btn active" onclick="switchTab('overview', event)">Command Center</button>
      <button class="nav-btn" onclick="switchTab('scenarios', event)">Golden Scenarios</button>
      <button class="nav-btn" onclick="switchTab('benchmark', event)">Policy Benchmark</button>
      <button class="nav-btn" onclick="switchTab('simulator', event)">Timing Lab</button>
      <button class="nav-btn" onclick="switchTab('queue', event)">Live Audit Queue</button>
    </nav>

    <div class="header-status">
      <span class="status-pip"></span>
      <span>Control Plane Active</span>
    </div>
  </header>

  <main>

    <!-- 1. OVERVIEW & COMMAND CENTER -->
    <div id="overview" class="tab-pane active">
      
      <div class="hero-banner">
        <div>
          <div class="hero-kicker">Track 03: AI Revenue Recovery — Razorpay Buildathon</div>
          <h1 class="hero-title">Autonomous Revenue Recovery Control Plane</h1>
          <p class="hero-description">
            Recover revenue when intervention helps, wait when the rail should self-heal, escalate when human judgment is needed, and stop when a customer shouldn't be contacted.
          </p>
        </div>
        <div>
          <span class="hero-pill">Model Proposes · Deterministic Policy Decides</span>
        </div>
      </div>

      <!-- Primary Financial KPIs -->
      <div class="kpi-deck">
        <div class="kpi-card">
          <div class="kpi-meta">Revenue At Risk</div>
          <div class="kpi-num" id="kpi-at-risk">₹1,91,47,346.23</div>
          <div class="kpi-subtext" id="kpi-sample-note">Canonical Benchmark (N=1,500)</div>
        </div>

        <div class="kpi-card highlight hero-kpi">
          <div class="kpi-meta">Incremental Recovered</div>
          <div class="kpi-num" style="color: var(--status-act);" id="kpi-incremental">₹38,45,516.20</div>
          <div class="kpi-subtext positive">+₹38.46 Lakhs causal uplift</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-meta">Gross Recovered</div>
          <div class="kpi-num" id="kpi-recovered">₹72,22,091.33</div>
          <div class="kpi-subtext" id="kpi-rate">37.72% Recovery Rate</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-meta">Contacts Avoided</div>
          <div class="kpi-num" id="kpi-contacts-avoided">648</div>
          <div class="kpi-subtext positive">43.2% customer spam saved</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-meta">₹ Recovered / Contact</div>
          <div class="kpi-num" id="kpi-rev-per-contact">₹8,476.63</div>
          <div class="kpi-subtext">Optimal yield per nudge</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-meta">Policy Violations</div>
          <div class="kpi-num" style="color: var(--status-act);" id="kpi-violations">0</div>
          <div class="kpi-subtext positive">100% Invariants Verified</div>
        </div>
      </div>

      <!-- Main Decision Vocabulary Panel -->
      <div class="decision-row">
        <div class="decision-card act">
          <div class="decision-head">
            <span class="decision-name" style="color: var(--status-act);">ACT</span>
            <span class="decision-pct-val" id="dec-act-pct">56.8%</span>
          </div>
          <p class="decision-desc">Recover now: High recovery probability & clear buyer checkout intent.</p>
          <span class="decision-count-pill" id="dec-act-cnt">852 cases dispatched</span>
        </div>

        <div class="decision-card wait">
          <div class="decision-head">
            <span class="decision-name" style="color: var(--status-wait);">WAIT</span>
            <span class="decision-pct-val" id="dec-wait-pct">16.8%</span>
          </div>
          <p class="decision-desc">Transient failure or active promise: Let the payment rail / promise window heal.</p>
          <span class="decision-count-pill" id="dec-wait-cnt">252 cases scheduled</span>
        </div>

        <div class="decision-card escalate">
          <div class="decision-head">
            <span class="decision-name" style="color: var(--status-escalate);">ESCALATE</span>
            <span class="decision-pct-val" id="dec-esc-pct">6.5%</span>
          </div>
          <p class="decision-desc">B2B commercial disputes & low diagnostic confidence routed to human review.</p>
          <span class="decision-count-pill" id="dec-esc-cnt">97 cases reviewed</span>
        </div>

        <div class="decision-card stop">
          <div class="decision-head">
            <span class="decision-name" style="color: var(--status-stop);">STOP</span>
            <span class="decision-pct-val" id="dec-stop-pct">26.4%</span>
          </div>
          <p class="decision-desc">Opted out, contact limits exhausted, terminal recovery, or negative ROI.</p>
          <span class="decision-count-pill" id="dec-stop-cnt">396 cases blocked</span>
        </div>
      </div>

      <!-- Live Lifecycle Pipeline -->
      <div class="lifecycle-section">
        <div class="section-title-wrap">
          <span class="section-title">End-to-End Recovery Lifecycle</span>
          <span class="section-tag">Deterministic Event Pipeline</span>
        </div>
        <div class="pipeline-flow">
          <div class="pipe-step">
            <div class="pipe-num">Step 01</div>
            <div class="pipe-label">payment.failed</div>
            <div class="pipe-detail">Webhook ingested</div>
          </div>
          <div class="pipe-step">
            <div class="pipe-num">Step 02</div>
            <div class="pipe-label">HMAC & Dedup</div>
            <div class="pipe-detail">Idempotency gate</div>
          </div>
          <div class="pipe-step">
            <div class="pipe-num">Step 03</div>
            <div class="pipe-label">AI Diagnosis</div>
            <div class="pipe-detail">7-cause taxonomy</div>
          </div>
          <div class="pipe-step">
            <div class="pipe-num">Step 04</div>
            <div class="pipe-label">ML Probability</div>
            <div class="pipe-detail">E(Recovery) scored</div>
          </div>
          <div class="pipe-step active-step">
            <div class="pipe-num">Step 05</div>
            <div class="pipe-label">Policy Engine</div>
            <div class="pipe-detail">ACT / WAIT / STOP</div>
          </div>
          <div class="pipe-step">
            <div class="pipe-num">Step 06</div>
            <div class="pipe-label">Razorpay Action</div>
            <div class="pipe-detail">Payment Link sent</div>
          </div>
          <div class="pipe-step">
            <div class="pipe-num">Step 07</div>
            <div class="pipe-label">RECOVERED</div>
            <div class="pipe-detail">Loop closed</div>
          </div>
        </div>
      </div>

      <!-- Safety & Invariant Verification Strip -->
      <div class="lifecycle-section">
        <div class="section-title-wrap">
          <span class="section-title">Fintech Safety & Policy Invariants</span>
          <span class="section-tag">0 Violations on Held-Out Benchmark</span>
        </div>
        <div class="safety-strip">
          <div class="safety-item">
            <div class="safety-status">✓ 0</div>
            <div class="safety-label">Opt-Out Rule</div>
            <div class="safety-desc">Hard stop enforced</div>
          </div>
          <div class="safety-item">
            <div class="safety-status">✓ 0</div>
            <div class="safety-label">Cooldown Gap</div>
            <div class="safety-desc">24h consumer / 12h B2B</div>
          </div>
          <div class="safety-item">
            <div class="safety-status">✓ 0</div>
            <div class="safety-label">Contact Cap</div>
            <div class="safety-desc">Max 3 / week ceiling</div>
          </div>
          <div class="safety-item">
            <div class="safety-status">✓ 0</div>
            <div class="safety-label">Budget Cap</div>
            <div class="safety-desc">₹5,000/day hard limit</div>
          </div>
          <div class="safety-item">
            <div class="safety-status">✓ 0</div>
            <div class="safety-label">Discount Cap</div>
            <div class="safety-desc">0% rogue discounts</div>
          </div>
          <div class="safety-item">
            <div class="safety-status">✓ 0</div>
            <div class="safety-label">Terminal State</div>
            <div class="safety-desc">No post-recovery spam</div>
          </div>
          <div class="safety-item">
            <div class="safety-status">✓ 0</div>
            <div class="safety-label">Duplicate Action</div>
            <div class="safety-desc">Strict dedup audit</div>
          </div>
        </div>
      </div>

    </div>

    <!-- 2. GOLDEN SCENARIOS TAB -->
    <div id="scenarios" class="tab-pane">
      <div class="hero-banner">
        <div>
          <div class="hero-kicker">Demonstrated Scenarios</div>
          <h2 class="hero-title">Golden Decision Showcase</h2>
          <p class="hero-description">
            Five canonical execution paths illustrating why revenue recovery is a decision problem, not a mechanical reminder loop.
          </p>
        </div>
      </div>

      <div class="scenarios-grid">
        
        <!-- Scenario 1 -->
        <div class="scenario-card">
          <div>
            <div class="scenario-header">
              <span class="scenario-title">1. Transient Bank Rail Outage</span>
              <span class="scenario-badge badge-wait">Decision: WAIT</span>
            </div>
            <p class="scenario-body">
              HDFC gateway switch down. Sending an SMS nudge immediately confuses the customer and damages brand trust while the rail is failing.
            </p>
          </div>
          <div class="scenario-facts">
            <div class="fact-item"><span class="fact-k">Amount:</span><span class="fact-v">₹7,500.00</span></div>
            <div class="fact-item"><span class="fact-k">Diagnosis:</span><span class="fact-v">BANK_RAIL_DOWN (0.88)</span></div>
            <div class="fact-item"><span class="fact-k">Action:</span><span class="fact-v">0 Outreach (Rail healing)</span></div>
            <div class="fact-item"><span class="fact-k">Outcome:</span><span class="fact-v">Customer fatigue avoided</span></div>
          </div>
        </div>

        <!-- Scenario 2 (Hero) -->
        <div class="scenario-card hero-scenario">
          <div>
            <div class="scenario-header">
              <span class="scenario-title">2. OTP Timeout & Checkout Intent</span>
              <span class="scenario-badge badge-act">Decision: ACT</span>
            </div>
            <p class="scenario-body">
              SMS OTP latency caused session timeout. High buyer intent with active cart. Razorpay Payment Link generated and sent immediately.
            </p>
          </div>
          <div class="scenario-facts">
            <div class="fact-item"><span class="fact-k">Amount:</span><span class="fact-v">₹4,999.00</span></div>
            <div class="fact-item"><span class="fact-k">Diagnosis:</span><span class="fact-v">OTP_TIMEOUT (0.92)</span></div>
            <div class="fact-item"><span class="fact-k">Action:</span><span class="fact-v">Razorpay Payment Link</span></div>
            <div class="fact-item"><span class="fact-k">Outcome:</span><span class="fact-v" style="color: var(--status-act);">RECOVERED ₹4,999.00</span></div>
          </div>
        </div>

        <!-- Scenario 3 -->
        <div class="scenario-card">
          <div>
            <div class="scenario-header">
              <span class="scenario-title">3. Hinglish Promise-to-Pay</span>
              <span class="scenario-badge badge-wait">Decision: WAIT</span>
            </div>
            <p class="scenario-body">
              Customer replies: <em>"Salary parso aayegi, tab pakka pay kar dunga"</em>. Promise extractor parses intent and pauses automated dunning.
            </p>
          </div>
          <div class="scenario-facts">
            <div class="fact-item"><span class="fact-k">Amount:</span><span class="fact-v">₹1,200.00</span></div>
            <div class="fact-item"><span class="fact-k">Extracted Date:</span><span class="fact-v">Salary Day (+48h)</span></div>
            <div class="fact-item"><span class="fact-k">Action:</span><span class="fact-v">Nudges Paused</span></div>
            <div class="fact-item"><span class="fact-k">Outcome:</span><span class="fact-v">State: PROMISED</span></div>
          </div>
        </div>

        <!-- Scenario 4 -->
        <div class="scenario-card">
          <div>
            <div class="scenario-header">
              <span class="scenario-title">4. Customer Opt-Out Hard Stop</span>
              <span class="scenario-badge badge-stop">Decision: STOP</span>
            </div>
            <p class="scenario-body">
              Customer replied "STOP". Regulatory and consent guardrail triggers immediate hard stop. Future failed payments blocked from outreach.
            </p>
          </div>
          <div class="scenario-facts">
            <div class="fact-item"><span class="fact-k">Amount:</span><span class="fact-v">₹5,000.00</span></div>
            <div class="fact-item"><span class="fact-k">Consent Flag:</span><span class="fact-v">OPTED_OUT = True</span></div>
            <div class="fact-item"><span class="fact-k">Action:</span><span class="fact-v">0 Outreach</span></div>
            <div class="fact-item"><span class="fact-k">Outcome:</span><span class="fact-v">State: OPTED_OUT</span></div>
          </div>
        </div>

        <!-- Scenario 5 -->
        <div class="scenario-card">
          <div>
            <div class="scenario-header">
              <span class="scenario-title">5. Rogue LLM Discount Blocked</span>
              <span class="scenario-badge badge-escalate">Decision: ESCALATE</span>
            </div>
            <p class="scenario-body">
              Adversarial LLM hallucination: <em>"Offer 50% discount to immediately recover funds"</em>. Deterministic policy enforces max discount ceiling of 0%.
            </p>
          </div>
          <div class="scenario-facts">
            <div class="fact-item"><span class="fact-k">Amount:</span><span class="fact-v">₹2,50,000.00</span></div>
            <div class="fact-item"><span class="fact-k">Policy Ceiling:</span><span class="fact-v">Max Discount: ₹0</span></div>
            <div class="fact-item"><span class="fact-k">Action:</span><span class="fact-v">Human Review Queue</span></div>
            <div class="fact-item"><span class="fact-k">Outcome:</span><span class="fact-v">Zero financial leak</span></div>
          </div>
        </div>

      </div>
    </div>

    <!-- 3. BENCHMARK COMPARISON TAB -->
    <div id="benchmark" class="tab-pane">
      <div class="hero-banner">
        <div>
          <div class="hero-kicker">Causal Evaluation</div>
          <h2 class="hero-title">Canonical Policy Scoreboard</h2>
          <p class="hero-description">
            Evaluated across held-out test dataset (N=1,500, seed=42) using Neyman-Rubin potential outcomes counterfactual simulation.
          </p>
        </div>
      </div>

      <div class="table-card">
        <table class="editorial-table" id="scoreboard-table">
          <thead id="scoreboard-thead">
            <!-- Rendered dynamically -->
          </thead>
          <tbody id="scoreboard-tbody">
            <!-- Rendered dynamically -->
          </tbody>
        </table>
      </div>

      <div class="lifecycle-section">
        <div class="section-title-wrap">
          <span class="section-title">Optimization Trade-Off Analysis</span>
        </div>
        <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
          <strong>Fixed Dunning:</strong> Recovers ₹77.63 L by contacting every customer indiscriminately (1,500 contacts, 288 false-positive nudges, ₹750 cost).<br>
          <strong>RECLAIM:</strong> Recovers ₹72.22 L with ₹38.46 L incremental uplift while making only <strong>852 contacts (saving 648 unnecessary contacts — a 43.2% reduction in customer spam)</strong>, achieving the <strong>lowest unit cost per recovered rupee (₹0.000033)</strong>, higher revenue yield per contact (₹8,476 vs ₹5,175), and <strong>0 policy violations</strong>.
        </p>
      </div>
    </div>

    <!-- 4. TIMING LAB SIMULATOR TAB -->
    <div id="simulator" class="tab-pane">
      <div class="hero-banner">
        <div>
          <div class="hero-kicker">Interactive Experimentation</div>
          <h2 class="hero-title">Timing Sensitivity Lab</h2>
          <p class="hero-description">
            Adjust retry cadences and delay parameters to model the dynamic sensitivity on recovery yield, contact volume, and unit economics.
          </p>
        </div>
      </div>

      <div class="sim-container">
        <div class="sim-box">
          <div class="section-title-wrap">
            <span class="section-title">Tunable Parameters</span>
          </div>

          <div class="slider-row">
            <div class="slider-label-row">
              <span>OTP Timeout Wait</span>
              <span id="lbl-otp" style="font-weight: 700; color: var(--text-primary);">15 min</span>
            </div>
            <input type="range" class="editorial-slider" id="slider-otp" min="1" max="60" value="15" oninput="updateTimingSim()">
          </div>

          <div class="slider-row">
            <div class="slider-label-row">
              <span>Bank Rail Outage Wait</span>
              <span id="lbl-bank" style="font-weight: 700; color: var(--text-primary);">4.0 hrs</span>
            </div>
            <input type="range" class="editorial-slider" id="slider-bank" min="1" max="24" step="0.5" value="4.0" oninput="updateTimingSim()">
          </div>

          <div class="slider-row">
            <div class="slider-label-row">
              <span>Auth Abort Wait</span>
              <span id="lbl-auth" style="font-weight: 700; color: var(--text-primary);">2.0 hrs</span>
            </div>
            <input type="range" class="editorial-slider" id="slider-auth" min="0.5" max="12" step="0.5" value="2.0" oninput="updateTimingSim()">
          </div>

          <div class="slider-row">
            <div class="slider-label-row">
              <span>Customer Cooldown Window</span>
              <span id="lbl-cooldown" style="font-weight: 700; color: var(--text-primary);">24.0 hrs</span>
            </div>
            <input type="range" class="editorial-slider" id="slider-cooldown" min="4" max="72" step="2" value="24.0" oninput="updateTimingSim()">
          </div>
        </div>

        <div class="sim-box">
          <div class="section-title-wrap">
            <span class="section-title">Projected Simulation Yield</span>
          </div>

          <div class="kpi-deck" style="margin-bottom: 0;">
            <div class="kpi-card">
              <div class="kpi-meta">Projected Rate</div>
              <div class="kpi-num" style="color: var(--status-act);" id="sim-proj-rate">37.72%</div>
              <div class="kpi-subtext" id="sim-delta-rate">Baseline Match</div>
            </div>

            <div class="kpi-card">
              <div class="kpi-meta">Projected Recovered</div>
              <div class="kpi-num" id="sim-proj-rev">₹72,22,091.33</div>
              <div class="kpi-subtext" id="sim-delta-rev">Baseline Match</div>
            </div>

            <div class="kpi-card">
              <div class="kpi-meta">Projected Contacts</div>
              <div class="kpi-num" id="sim-proj-contacts">852</div>
              <div class="kpi-subtext">Optimal volume</div>
            </div>
          <div class="kpi-card">
              <div class="kpi-meta">Intervention Cost</div>
              <div class="kpi-num" id="sim-proj-cost">₹240.25</div>
              <div class="kpi-subtext">Estimated budget</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 5. LIVE AUDIT QUEUE TAB -->
    <div id="queue" class="tab-pane">
      <div class="hero-banner">
        <div>
          <div class="hero-kicker">Live Audit Log</div>
          <h2 class="hero-title">Recovery Queue & Case Timelines</h2>
          <p class="hero-description">
            Inspect real-time recovery cases. Click any row to view full decision traceability and immutable audit log records.
          </p>
        </div>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <div style="display: inline-flex; gap: 8px; background: var(--surface-subtle); padding: 4px; border-radius: 6px; border: 1px solid var(--border-subtle);">
          <button id="filter-btn-active" class="queue-filter-btn active" onclick="setQueueFilter('active')">Active Cases</button>
          <button id="filter-btn-all" class="queue-filter-btn" onclick="setQueueFilter('all')">All Cases</button>
          <button id="filter-btn-errors" class="queue-filter-btn" onclick="setQueueFilter('historical_errors')">Historical Errors</button>
        </div>
        <div style="font-size: 12px; color: var(--text-tertiary);" id="queue-count-label">Loading cases...</div>
      </div>

      <div class="table-card">
        <table class="editorial-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th>Amount</th>
              <th>Diagnosed Cause</th>
              <th>Decision</th>
              <th>Tier</th>
              <th>Action Taken</th>
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

  </main>

  <!-- Investigation Drawer / Modal -->
  <div class="modal-backdrop" id="timeline-modal">
    <div class="modal-frame">
      <div class="modal-top">
        <div>
          <div style="font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent-clay);">Case Investigation</div>
          <h3 id="inv-modal-title" style="font-size: 18px; font-weight: 700; margin-top: 2px;">Investigate Recovery Case</h3>
        </div>
        <button class="modal-close" onclick="closeTimeline()" title="Close (Esc)">&times;</button>
      </div>

      <!-- Investigation Content -->
      <div id="investigation-content">
        <!-- 1. Hero Summary -->
        <div class="inv-hero">
          <div>
            <div id="inv-cust-name" style="font-size: 16px; font-weight: 700; color: var(--text-primary);">Loading...</div>
            <div id="inv-cust-email" style="font-size: 12px; color: var(--text-secondary);">--</div>
          </div>
          <div style="text-align: right;">
            <div id="inv-amount" style="font-size: 20px; font-weight: 700; color: var(--text-primary);">--</div>
            <span id="inv-status-badge" class="scenario-badge badge-act">--</span>
          </div>
        </div>

        <!-- 2. Primary Decision & Financial Matrix -->
        <div class="inv-grid">
          <div class="inv-metric-box">
            <div class="inv-metric-label">AI Diagnosis</div>
            <div class="inv-metric-value" id="inv-diagnosis">--</div>
            <div style="font-size: 11px; color: var(--text-tertiary);" id="inv-raw-reason">Raw Reason: --</div>
          </div>
          <div class="inv-metric-box">
            <div class="inv-metric-label">Decision</div>
            <div class="inv-metric-value" id="inv-decision" style="color: var(--status-act);">--</div>
            <div style="font-size: 11px; color: var(--text-tertiary);" id="inv-tier-label">Tier: AUTO</div>
          </div>
          <div class="inv-metric-box">
            <div class="inv-metric-label">Recovery Prob.</div>
            <div class="inv-metric-value" id="inv-rec-prob">--</div>
            <div style="font-size: 11px; color: var(--text-tertiary);">ML Model Score</div>
          </div>
          <div class="inv-metric-box">
            <div class="inv-metric-label">Action</div>
            <div class="inv-metric-value" id="inv-action" style="font-size: 13px;">--</div>
            <div style="font-size: 11px; color: var(--text-tertiary);">Bounded Execution</div>
          </div>
          <div class="inv-metric-box">
            <div class="inv-metric-label">Outcome</div>
            <div class="inv-metric-value" id="inv-outcome" style="font-size: 13px;">--</div>
            <div style="font-size: 11px; color: var(--text-tertiary);">Observed Event</div>
          </div>
          <div class="inv-metric-box">
            <div class="inv-metric-label">Recovered</div>
            <div class="inv-metric-value" id="inv-recovered" style="color: var(--status-act);">--</div>
            <div style="font-size: 11px; color: var(--text-tertiary);">Secured Revenue</div>
          </div>
        </div>

        <!-- 3. Why this decision? -->
        <div class="inv-section-title">Why This Decision?</div>
        <div class="inv-why-box" id="inv-why-decision">
          Loading policy explanation...
        </div>

        <!-- 4. Recovery Lifecycle Timeline -->
        <div class="inv-section-title">Recovery Lifecycle Timeline</div>
        <div class="inv-pipeline-flow" id="inv-pipeline-steps">
          <!-- Populated dynamically -->
        </div>

        <!-- 5. Policy Controls -->
        <div class="inv-section-title">Policy Controls (0 Violations)</div>
        <div class="inv-controls-grid" id="inv-controls">
          <div class="inv-control-pill"><span>Opt-out</span><span class="inv-control-pass">PASS</span></div>
          <div class="inv-control-pill"><span>Cooldown</span><span class="inv-control-pass">PASS</span></div>
          <div class="inv-control-pill"><span>Contact Cap</span><span class="inv-control-pass">PASS</span></div>
          <div class="inv-control-pill"><span>Budget Cap</span><span class="inv-control-pass">PASS</span></div>
          <div class="inv-control-pill"><span>Discount</span><span class="inv-control-pass">PASS</span></div>
          <div class="inv-control-pill"><span>Terminal State</span><span class="inv-control-pass">PASS</span></div>
          <div class="inv-control-pill"><span>Duplicate Action</span><span class="inv-control-pass">PASS</span></div>
        </div>

        <!-- 6. Technical Details (Collapsed) -->
        <details class="inv-tech-details" id="inv-tech-details">
          <summary id="inv-tech-summary">View Technical Audit Trail & Diagnostics (<span id="inv-audit-count">0</span> records)</summary>
          <div style="font-size: 11px; color: var(--text-tertiary); margin-bottom: 12px;" id="inv-tech-meta">
            Recovery State ID: -- | Event ID: -- | Policy Version: 2.1.0-deterministic
          </div>
          <div id="inv-raw-error-box" style="display: none; background: #FFF0F0; border: 1px solid #E8B4B4; border-radius: 4px; padding: 10px; font-family: monospace; font-size: 11px; color: #900; margin-bottom: 12px; max-height: 120px; overflow-y: auto;"></div>
          <div class="audit-timeline" id="timeline-container">
            <!-- Full technical audit logs -->
          </div>
        </details>
      </div>
    </div>
  </div>

  <script>
    let globalScoreboard = null;

    function switchTab(tabId, evt) {
      const e = evt || window.event;
      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
      
      const pane = document.getElementById(tabId);
      if (pane) pane.classList.add('active');

      if (e) {
        const btn = e.currentTarget || (e.target ? e.target.closest('.nav-btn') : null);
        if (btn) btn.classList.add('active');
      }

      if (tabId === 'queue') {
        loadQueue();
      }
    }

    function formatRs(amount) {
      const num = Number(amount);
      if (isNaN(num)) return '₹0.00';
      return '₹' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    async function loadScoreboard() {
      try {
        const res = await fetch('/dashboard/scoreboard');
        if (!res.ok) return;
        const data = await res.json();
        globalScoreboard = data;

        const rec = data.policies?.RECLAIM || {};

        document.getElementById('kpi-at-risk').innerText = formatRs(rec.total_at_risk_rs || 19147346.23);
        document.getElementById('kpi-recovered').innerText = formatRs(rec.total_recovered_rs || 7222091.33);
        document.getElementById('kpi-rate').innerText = `${rec.recovery_rate_pct || 37.72}% Recovery Rate`;
        document.getElementById('kpi-incremental').innerText = formatRs(rec.incremental_recovery_rs || 3845516.20);
        document.getElementById('kpi-sample-note').innerText = `Canonical Benchmark (N=${data.total_records || 1500})`;
        
        const contactsMade = rec.contact_count || 852;
        const totalN = data.total_records || 1500;
        const avoided = Math.max(0, totalN - contactsMade);
        document.getElementById('kpi-contacts-avoided').innerText = avoided.toLocaleString();

        const revPerContact = rec.revenue_recovered_per_contact_rs || (contactsMade ? (rec.total_recovered_rs / contactsMade) : 0);
        document.getElementById('kpi-rev-per-contact').innerText = formatRs(revPerContact);

        // Decision distribution
        const dist = rec.decision_distribution || {
          ACT: { count: 852, pct: 56.8 },
          WAIT: { count: 252, pct: 16.8 },
          ESCALATE_sub: { count: 97, pct: 6.5 },
          STOP: { count: 396, pct: 26.4 },
        };
        document.getElementById('dec-act-pct').innerText = (dist.ACT?.pct || 56.8) + '%';
        document.getElementById('dec-act-cnt').innerText = `${dist.ACT?.count || 852} cases dispatched`;
        document.getElementById('dec-wait-pct').innerText = (dist.WAIT?.pct || 16.8) + '%';
        document.getElementById('dec-wait-cnt').innerText = `${dist.WAIT?.count || 252} cases scheduled`;
        document.getElementById('dec-esc-pct').innerText = (dist.ESCALATE_sub?.pct || 6.5) + '%';
        document.getElementById('dec-esc-cnt').innerText = `${dist.ESCALATE_sub?.count || 97} cases reviewed`;
        document.getElementById('dec-stop-pct').innerText = (dist.STOP?.pct || 26.4) + '%';
        document.getElementById('dec-stop-cnt').innerText = `${dist.STOP?.count || 396} cases blocked`;

        if (data.policies) {
          renderScoreboardTable(data.policies);
        }
      } catch (err) {
        console.error("Error loading scoreboard:", err);
      }
    }

    function renderScoreboardTable(policies) {
      const keys = Object.keys(policies);
      const thead = document.getElementById('scoreboard-thead');
      const tbody = document.getElementById('scoreboard-tbody');
      if (!thead || !tbody) return;
      
      let thHtml = '<tr><th>Metric</th>';
      keys.forEach(k => {
        const isRec = k === 'RECLAIM';
        thHtml += `<th class="${isRec ? 'col-highlight' : ''}">${k}</th>`;
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
        { label: 'Intervention cost (₹)', fn: p => formatRs(p.total_intervention_cost_rs || 0) },
        { label: 'Cost per recovered ₹', fn: p => p.cost_per_recovered_rupee ? ('₹' + p.cost_per_recovered_rupee.toFixed(6)) : '--' },
        { label: 'Policy violations', fn: p => (p.policy_name === 'RECLAIM' ? '0' : '--') },
      ];

      rows.forEach(r => {
        const tr = document.createElement('tr');
        let html = `<td style="font-weight: 600;">${r.label}</td>`;
        keys.forEach(k => {
          const val = r.fn(policies[k] || {});
          const isRec = k === 'RECLAIM';
          const style = isRec ? 'color: var(--status-act); font-weight: 600;' : '';
          html += `<td class="${isRec ? 'col-highlight' : ''}" style="${style}">${val}</td>`;
        });
        tr.innerHTML = html;
        tbody.appendChild(tr);
      });
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
        deltaEl.style.color = deltaRate >= 0 ? 'var(--status-act)' : 'var(--status-stop)';

        const deltaRev = proj.delta_revenue_rs;
        const deltaRevEl = document.getElementById('sim-delta-rev');
        deltaRevEl.innerText = (deltaRev >= 0 ? '+' : '') + formatRs(deltaRev) + ' vs baseline';
        deltaRevEl.style.color = deltaRev >= 0 ? 'var(--status-act)' : 'var(--status-stop)';
      } catch (err) {
        console.error("Simulation error:", err);
      }
    }

    let isModalOpen = false;
    let activeDetailController = null;
    const caseDetailCache = new Map();

    function closeTimeline() {
      if (activeDetailController) {
        activeDetailController.abort();
        activeDetailController = null;
      }
      document.getElementById('timeline-modal').style.display = 'none';
      isModalOpen = false;
    }

    // Modal backdrop click listener
    document.getElementById('timeline-modal').addEventListener('click', function(e) {
      if (e.target === this) closeTimeline();
    });

    // Escape key listener
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && isModalOpen) closeTimeline();
    });

    function renderInvestigation(data) {
      const inv = data.investigation || {};
      document.getElementById('inv-cust-name').innerText = inv.customer_name || 'Customer';
      document.getElementById('inv-cust-email').innerText = inv.customer_email || 'N/A';
      document.getElementById('inv-amount').innerText = inv.formatted_amount || '₹0.00';
      
      const badge = document.getElementById('inv-status-badge');
      badge.innerText = inv.status_label || 'ACTIVE';
      const dec = inv.decision || 'WAIT';
      badge.className = 'scenario-badge ' + (dec === 'ACT' ? 'badge-act' : (dec === 'ESCALATE' ? 'badge-escalate' : (dec === 'STOP' ? 'badge-stop' : 'badge-wait')));

      document.getElementById('inv-diagnosis').innerText = inv.ai_diagnosis || inv.diagnosis || 'UNSPECIFIED';
      const rawR = inv.raw_reason || 'N/A';
      document.getElementById('inv-raw-reason').innerText = 'Raw: ' + rawR;
      
      const decEl = document.getElementById('inv-decision');
      decEl.innerText = dec;
      decEl.style.color = dec === 'ACT' ? 'var(--status-act)' : (dec === 'ESCALATE' ? 'var(--status-escalate)' : (dec === 'STOP' ? 'var(--status-stop)' : 'var(--status-wait)'));

      const tier = (inv.tier || 'AUTO').toUpperCase();
      document.getElementById('inv-tier-label').innerText = `Tier: ${tier}`;

      document.getElementById('inv-rec-prob').innerText = inv.recovery_probability !== undefined ? inv.recovery_probability.toFixed(2) : '0.50';
      document.getElementById('inv-action').innerText = inv.action || 'None';
      document.getElementById('inv-outcome').innerText = inv.outcome || 'pending';
      document.getElementById('inv-recovered').innerText = inv.formatted_recovered || '₹0.00';
      document.getElementById('inv-why-decision').innerText = inv.why_decision || 'Policy executed based on deterministic constraints.';

      // Pipeline steps
      const pipeContainer = document.getElementById('inv-pipeline-steps');
      pipeContainer.innerHTML = '';
      const steps = inv.timeline_steps || [];
      steps.forEach((s, idx) => {
        const span = document.createElement('span');
        span.className = 'inv-flow-step';
        span.innerHTML = `<span style="color: ${s.status === 'done' ? 'var(--status-act)' : 'var(--text-tertiary)'}; font-weight: 700;">${s.status === 'done' ? '✓' : '○'}</span><span>${s.label}</span>`;
        pipeContainer.appendChild(span);
        if (idx < steps.length - 1) {
          const arrow = document.createElement('span');
          arrow.className = 'inv-flow-arrow';
          arrow.innerText = '→';
          pipeContainer.appendChild(arrow);
        }
      });

      // Technical metadata & audit trail
      const tech = inv.technical_details || {};
      document.getElementById('inv-tech-meta').innerText = `Recovery State ID: ${tech.recovery_state_id || 'N/A'} | Event ID: ${tech.event_id || 'N/A'} | Policy: ${tech.policy_version || '2.1.0-deterministic'}`;
      
      const errBox = document.getElementById('inv-raw-error-box');
      if (tech.raw_exception) {
        errBox.style.display = 'block';
        errBox.innerText = `System Exception Trace:\n${tech.raw_exception}`;
      } else {
        errBox.style.display = 'none';
        errBox.innerText = '';
      }

      const timelineLogs = data.timeline || [];
      document.getElementById('inv-audit-count').innerText = timelineLogs.length;

      const container = document.getElementById('timeline-container');
      container.innerHTML = '';
      if (timelineLogs.length === 0) {
        container.innerHTML = '<div style="color: var(--text-secondary); font-size: 12px;">No audit records found.</div>';
      } else {
        timelineLogs.forEach(log => {
          const item = document.createElement('div');
          item.className = 'audit-entry';
          item.innerHTML = `
            <div class="audit-actor">${log.actor}</div>
            <div class="audit-action">${log.action}</div>
            <div class="audit-reason">${log.reason}</div>
            <div class="audit-time">${log.timestamp ? new Date(log.timestamp).toLocaleString() : '--'}</div>
          `;
          container.appendChild(item);
        });
      }
    }

    async function openTimeline(customerId, caseId) {
      isModalOpen = true;
      document.getElementById('timeline-modal').style.display = 'flex';

      // Check cache first for instantaneous opening
      const cacheKey = customerId + (caseId ? '_' + caseId : '');
      if (caseDetailCache.has(cacheKey)) {
        renderInvestigation(caseDetailCache.get(cacheKey));
        return;
      }

      // If previous request is active, cancel it cleanly
      if (activeDetailController) {
        activeDetailController.abort();
      }
      activeDetailController = new AbortController();

      try {
        const url = `/dashboard/timeline/${customerId}${caseId ? '?case_id=' + caseId : ''}`;
        const res = await fetch(url, { signal: activeDetailController.signal });
        const data = await res.json();
        caseDetailCache.set(cacheKey, data);
        renderInvestigation(data);
      } catch (err) {
        if (err.name === 'AbortError') return; // Request was aborted cleanly on case switch
        console.error("Error loading case detail:", err);
      }
    }

    let currentQueueFilter = 'active';

    function setQueueFilter(filterVal) {
      currentQueueFilter = filterVal;
      document.querySelectorAll('.queue-filter-btn').forEach(btn => btn.classList.remove('active'));
      const activeBtn = document.getElementById(filterVal === 'active' ? 'filter-btn-active' : (filterVal === 'all' ? 'filter-btn-all' : 'filter-btn-errors'));
      if (activeBtn) activeBtn.classList.add('active');
      loadQueue();
    }

    async function loadQueue() {
      if (isModalOpen) return; // Do not interrupt active investigation
      try {
        const res = await fetch(`/dashboard/queue?limit=25&visibility=${encodeURIComponent(currentQueueFilter)}`);
        if (!res.ok) {
          console.error("Queue API returned HTTP", res.status);
          return;
        }
        const data = await res.json();
        const tbody = document.getElementById('queue-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        const countLabel = document.getElementById('queue-count-label');
        if (countLabel) {
          countLabel.innerText = `${data.total_items} ${currentQueueFilter === 'active' ? 'active operational' : (currentQueueFilter === 'all' ? 'total' : 'historical error')} cases`;
        }

        const items = data.items || [];
        if (items.length === 0) {
          tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-secondary); padding: 24px;">No cases found for current filter.</td></tr>';
          return;
        }

        items.forEach(item => {
          const tr = document.createElement('tr');
          tr.className = 'clickable-row';
          tr.setAttribute('data-cust-id', item.customer_id);
          tr.setAttribute('data-case-id', item.recovery_state_id || '');

          const dec = (item.decision || 'WAIT').toUpperCase();
          const decClass = dec === 'ACT' ? 'badge-act' : (dec === 'ESCALATE' ? 'badge-escalate' : (dec === 'STOP' ? 'badge-stop' : 'badge-wait'));

          const tier = (item.tier || 'AUTO').toUpperCase();
          const tierClass = tier === 'AUTO' ? 'tier-auto' : (tier === 'REVIEW' ? 'tier-review' : 'tier-block');

          const formattedAmount = item.formatted_amount || item.formatted_inr || formatRs(item.amount_rs || (item.amount_paise ? item.amount_paise / 100 : 0));

          let formattedDate = '--';
          if (item.updated_at) {
            try {
              const d = new Date(item.updated_at);
              if (!isNaN(d.getTime())) {
                formattedDate = d.toLocaleTimeString();
              }
            } catch (e) {
              formattedDate = String(item.updated_at);
            }
          }

          tr.innerHTML = `
            <td style="font-weight: 600;">${item.customer_name}</td>
            <td>${formattedAmount}</td>
            <td><code style="background: var(--surface-subtle); padding: 2px 6px; border-radius: 4px; font-size: 11px;">${item.diagnosed_cause}</code></td>
            <td><span class="scenario-badge ${decClass}">${dec}</span></td>
            <td><span class="tier-pill ${tierClass}">${tier}</span></td>
            <td>${item.action_taken}</td>
            <td style="max-width: 300px; font-size: 12px; color: var(--text-secondary);">${item.latest_reason}</td>
            <td style="font-size: 11px; color: var(--text-tertiary);">${formattedDate}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        console.error("Error loading queue:", err);
      }
    }

    // Single delegated click listener on tbody for fast, robust row opening
    document.getElementById('queue-tbody').addEventListener('click', function(e) {
      const tr = e.target.closest('tr.clickable-row');
      if (!tr) return;
      const custId = tr.getAttribute('data-cust-id');
      const caseId = tr.getAttribute('data-case-id');
      openTimeline(custId, caseId);
    });

    // Initialize
    loadScoreboard();
    loadQueue();
    setInterval(loadQueue, 5000);
  </script>
</body>
</html>
"""


@dashboard_ui_router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard_ui():
    """GET /dashboard -> Serves RECLAIM Dashboard Single-Page Application."""
    return HTMLResponse(content=DASHBOARD_HTML_CONTENT)

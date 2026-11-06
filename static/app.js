/* ============================================================
   Customer Intelligence & Churn Analytics Hub — Frontend Engine (LTR)
   Talks directly to FastAPI endpoints with Chart.js visualizations
   ============================================================ */

const API = {
  health: "/health",
  dashboard: "/api/dataset/dashboard",
  extract: "/api/extract",
  analyze: "/api/analyze",
  chatCustomer: "/api/chat",
  uploadCsv: "/api/dataset/upload-csv",
  clearUpload: "/api/dataset/current-upload",
  datasetChat: "/api/dataset/chat",
  customers: "/api/dataset/customers",
  customerDetail: id => `/api/dataset/customer/${encodeURIComponent(id)}`,
  compare: "/api/compare",
  override: "/api/override",
  sessions: "/api/sessions",
  session: id => `/api/sessions/${encodeURIComponent(id)}`,
};

// Global Helpers
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtPct = p => (p == null ? "—" : (p * 100).toFixed(1) + "%");
const fmtMoney = v => (v == null ? "—" : "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }));

// Markdown Parser Helper
function parseMarkdown(text) {
  if (!text) return "";
  let html = esc(text);
  // Headings
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Inline code
  html = html.replace(/`(.*?)`/g, '<code>$1</code>');
  // Lists
  html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
  html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
  // Paragraph splits
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');
  return `<div class="markdown-content" dir="auto"><p>${html}</p></div>`;
}

// State Management
const state = {
  activeTab: "dashboard",
  dashboardData: null,
  customer: {
    analysis: null,
    customerId: null,
    thread: [],
    history: [],
    collected: {},
    askedFields: [],
  },
  batch: {
    file: null,
  },
  directory: {
    customers: [],
    total: 0,
    offset: 0,
    limit: 10,
    search: "",
  },
  chat: {
    thread: [],
    history: [],
    sessionId: null,
    sessions: [],
  }
};

// Chart Instance Registry
const chartInstances = {};

function destroyChart(name) {
  if (chartInstances[name]) {
    chartInstances[name].destroy();
    chartInstances[name] = null;
  }
}

// Global Chart Defaults
if (window.Chart) {
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.borderColor = "rgba(255, 255, 255, 0.08)";
}

// ================================================================
// ROUTER & NAVIGATION
// ================================================================
function initNavigation() {
  document.querySelectorAll(".nav-tab").forEach(tabBtn => {
    tabBtn.addEventListener("click", () => {
      const tabName = tabBtn.dataset.tab;
      switchTab(tabName);
    });
  });
}

function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".nav-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-view").forEach(view => {
    view.classList.toggle("active", view.id === `view-${tabName}`);
  });

  // Tab specific activations & dynamic chart resize
  if (tabName === "dashboard") {
    loadDashboard();
  }
  if (tabName === "customer" && state.customer.analysis) {
    setTimeout(() => {
      renderCustomerGauge(state.customer.analysis.prediction?.churn_probability);
    }, 100);
  }
  if (tabName === "directory") {
    loadCustomerDirectory();
  }
}

// ================================================================
// HEALTH CHECK
// ================================================================
async function checkHealth() {
  const dot = $("statusDot");
  const txt = $("statusText");
  try {
    const res = await fetch(API.health);
    if (!res.ok) throw new Error();
    dot.className = "status-dot ok";
    txt.textContent = "Server Online";
  } catch {
    dot.className = "status-dot err";
    txt.textContent = "Server Offline";
  }
}

// ================================================================
// 1. EXECUTIVE DASHBOARD & CHARTS
// ================================================================
async function loadDashboard() {
  try {
    const res = await fetch(API.dashboard);
    if (!res.ok) throw new Error("Failed to load dashboard data");
    const data = await res.json();
    state.dashboardData = data;

    const emptyHost = $("dashboardEmptyState");
    const kpiGrid = $("kpiGrid");
    const chartsGrid = document.querySelector(".charts-grid");
    const topRiskCard = $("topRiskCard");

    if (!data.has_current_upload || !data.total_customers) {
      if (emptyHost) emptyHost.hidden = false;
      if (kpiGrid) kpiGrid.hidden = true;
      if (chartsGrid) chartsGrid.hidden = true;
      if (topRiskCard) topRiskCard.hidden = true;
    } else {
      if (emptyHost) emptyHost.hidden = true;
      if (kpiGrid) kpiGrid.hidden = false;
      if (chartsGrid) chartsGrid.hidden = false;
      if (topRiskCard) topRiskCard.hidden = false;

      renderDashboardKPIs(data);
      renderTopRiskTable(data.top_risk_customers || []);
      setTimeout(() => renderDashboardCharts(data), 50);
    }
  } catch (err) {
    console.error(err);
  }
}

$("btnGoToUpload")?.addEventListener("click", () => switchTab("directory"));

function renderDashboardKPIs(d) {
  $("kpiTotalCustomers").textContent = d.total_customers != null ? d.total_customers.toLocaleString() : "0";
  $("kpiChurnRate").textContent = fmtPct(d.churn_rate);
  $("kpiChurnAvgProb").textContent = `Mean Probability: ${fmtPct(d.avg_churn_probability)}`;
  $("kpiExpectedLoss").textContent = fmtMoney(d.total_expected_churn_loss);
  $("kpiNetROI").textContent = fmtMoney(d.retainable_revenue_net_roi);
  $("kpiRetainableSub").textContent = `Retainable Benefit: ${fmtMoney(d.total_retainable_value)}`;
}

function renderTopRiskTable(topList) {
  const tbody = $("topRiskTableBody");
  if (!tbody) return;
  if (!topList || !topList.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center">No at-risk customers found.</td></tr>`;
    return;
  }
  tbody.innerHTML = topList.slice(0, 5).map(c => `
    <tr>
      <td><strong>${esc(c.customer_id)}</strong></td>
      <td><span class="text-rose font-bold">${fmtPct(c.churn_probability)}</span></td>
      <td><span class="badge badge-high">${esc(c.risk_band)}</span></td>
      <td>${fmtMoney(c.estimated_customer_value)}</td>
      <td><span class="chip">${esc(c.behavioral_segment)}</span></td>
      <td>
        <button class="btn btn-sm btn-outline" onclick="inspectCustomer('${esc(c.customer_id)}')">Inspect Profile</button>
      </td>
    </tr>
  `).join("");
}

function renderDashboardCharts(d) {
  if (!window.Chart) return;

  // CHART 1: Risk Band Distribution (Donut)
  destroyChart("riskDist");
  const riskCanvas = $("chartRiskDistribution");
  if (riskCanvas) {
    const counts = d.risk_counts || {};
    chartInstances.riskDist = new Chart(riskCanvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: ["High Risk", "Medium Risk", "Low Risk"],
        datasets: [{
          data: [counts.HIGH || 0, counts.MEDIUM || 0, counts.LOW || 0],
          backgroundColor: ["#f43f5e", "#f59e0b", "#10b981"],
          borderWidth: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } }
        },
        cutout: "68%"
      }
    });
  }

  // CHART 2: Financial Impact & ROI (Grouped Bar)
  destroyChart("financial");
  const finCanvas = $("chartFinancialImpact");
  if (finCanvas) {
    chartInstances.financial = new Chart(finCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: ["Total Revenue at Risk", "Retainable Revenue", "Net Campaign ROI"],
        datasets: [{
          label: "Financial Value ($)",
          data: [
            d.total_expected_churn_loss || 0,
            d.total_retainable_value || 0,
            d.retainable_revenue_net_roi || 0
          ],
          backgroundColor: ["rgba(244, 63, 94, 0.75)", "rgba(16, 185, 129, 0.75)", "rgba(99, 102, 241, 0.75)"],
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { ticks: { callback: v => "$" + Number(v).toLocaleString() } }
        }
      }
    });
  }

  // CHART 3: Churn Rate by Contract Type (Bar)
  destroyChart("contract");
  const contractCanvas = $("chartContractChurn");
  if (contractCanvas) {
    const cData = d.churn_rate_by_contract || {};
    chartInstances.contract = new Chart(contractCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: ["Month-to-Month", "One Year", "Two Year"],
        datasets: [{
          label: "Churn Rate (%)",
          data: [
            ((cData["Month-to-month"] || cData["Month-to-Month"] || 0) * 100).toFixed(1),
            ((cData["One year"] || cData["One Year"] || 0) * 100).toFixed(1),
            ((cData["Two year"] || cData["Two Year"] || 0) * 100).toFixed(1)
          ],
          backgroundColor: "rgba(99, 102, 241, 0.75)",
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { ticks: { callback: v => v + "%" }, max: 100 }
        }
      }
    });
  }

  // CHART 4: Behavioral Commercial Segments (Horizontal Bar)
  destroyChart("behavioral");
  const behCanvas = $("chartBehavioralSegments");
  if (behCanvas) {
    const behDist = d.behavioral_segment_distribution || {};
    const labels = Object.keys(behDist);
    const dataVals = Object.values(behDist);
    chartInstances.behavioral = new Chart(behCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: labels.length ? labels : ["No segment data"],
        datasets: [{
          label: "Customer Count",
          data: dataVals.length ? dataVals : [0],
          backgroundColor: [
            "rgba(99, 102, 241, 0.8)",
            "rgba(6, 182, 212, 0.8)",
            "rgba(245, 158, 11, 0.8)",
            "rgba(16, 185, 129, 0.8)",
            "rgba(236, 72, 153, 0.8)",
            "rgba(139, 92, 246, 0.8)",
            "rgba(59, 130, 246, 0.8)",
            "rgba(244, 63, 94, 0.8)"
          ],
          borderRadius: 6,
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { stepSize: 1, precision: 0 } }
        }
      }
    });
  }

  // CHART 5: Next Best Action Allocation (Pie)
  destroyChart("nba");
  const nbaCanvas = $("chartNextBestAction");
  if (nbaCanvas) {
    const nbaDist = d.next_best_action_distribution || {};
    const labels = Object.keys(nbaDist);
    const dataVals = Object.values(nbaDist);
    chartInstances.nba = new Chart(nbaCanvas.getContext("2d"), {
      type: "pie",
      data: {
        labels: labels.length ? labels : ["No action"],
        datasets: [{
          data: dataVals.length ? dataVals : [1],
          backgroundColor: ["#10b981", "#6366f1", "#f59e0b", "#06b6d4", "#f43f5e", "#a855f7"],
          borderWidth: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, padding: 12, font: { size: 11 } } }
        }
      }
    });
  }

  // CHART 6: Top Risk Drivers (Horizontal Bar)
  destroyChart("drivers");
  const driversCanvas = $("chartRiskDrivers");
  if (driversCanvas) {
    const drivers = d.top_risk_factors || [];
    const labels = drivers.slice(0, 5).map(item => Array.isArray(item) ? item[0] : item);
    const values = drivers.slice(0, 5).map(item => Array.isArray(item) ? item[1] : 1);

    chartInstances.drivers = new Chart(driversCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: labels.length ? labels : ["No elevated risk factors"],
        datasets: [{
          label: "Frequency",
          data: values.length ? values : [0],
          backgroundColor: "rgba(245, 158, 11, 0.75)",
          borderRadius: 6,
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } }
      }
    });
  }

  // CHART 7: Tailored Retention & Growth Campaigns Distribution (Horizontal Bar)
  destroyChart("campaignDist");
  const campCanvas = $("chartCampaignDistribution");
  if (campCanvas) {
    const campDist = d.campaign_distribution || {};
    const labels = Object.keys(campDist);
    const dataVals = Object.values(campDist);
    chartInstances.campaignDist = new Chart(campCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: labels.length ? labels : ["No campaign data"],
        datasets: [{
          label: "Customers Targeted",
          data: dataVals.length ? dataVals : [0],
          backgroundColor: [
            "rgba(6, 182, 212, 0.8)",
            "rgba(99, 102, 241, 0.8)",
            "rgba(16, 185, 129, 0.8)",
            "rgba(245, 158, 11, 0.8)",
            "rgba(236, 72, 153, 0.8)",
            "rgba(139, 92, 246, 0.8)",
            "rgba(59, 130, 246, 0.8)",
            "rgba(244, 63, 94, 0.8)"
          ],
          borderRadius: 6,
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { stepSize: 1, precision: 0 } }
        }
      }
    });
  }
}

$("btnRefreshDashboard")?.addEventListener("click", loadDashboard);

// ================================================================
// 2. SINGLE CUSTOMER ANALYSIS
// ================================================================
$("custSearchBtn")?.addEventListener("click", () => {
  const id = $("custSearchInput").value.trim();
  if (id) fetchCustomerDetail(id);
});

$("custSearchInput")?.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    const id = $("custSearchInput").value.trim();
    if (id) fetchCustomerDetail(id);
  }
});

async function fetchCustomerDetail(id) {
  const msgHost = $("custSearchMsgHost");
  msgHost.innerHTML = "";
  try {
    const res = await fetch(API.customerDetail(id));
    if (res.status === 404) throw new Error(`Customer ID "${id}" was not found in the dataset.`);
    if (!res.ok) throw new Error("Failed to fetch customer profile.");
    const data = await res.json();
    renderSingleCustomer(data, id);
  } catch (err) {
    msgHost.innerHTML = `<div class="badge badge-high margin-top">${esc(err.message)}</div>`;
  }
}

function renderSingleCustomer(data, id) {
  state.customer.analysis = data;
  state.customer.customerId = id || data.customer_id;

  $("customerEmptyState").hidden = true;
  $("customerCollectSection").hidden = true;
  $("customerResult").hidden = false;

  const pred = data.prediction || {};
  const cust = data.customer || {};
  const fin = data.financial || {};
  const seg = data.segmentation || {};
  const act = data.recommended_action || {};
  const isChurn = pred.decision === "CHURN";

  // HERO HEADER
  $("customerHeaderCard").innerHTML = `
    <div class="customer-id-block">
      <div class="customer-avatar">${esc(String(id).slice(0, 2).toUpperCase())}</div>
      <div>
        <div class="customer-id-title">Customer #${esc(id)}</div>
        <div class="customer-id-sub">Contract: ${esc(cust.contract || "N/A")} · Monthly Fee: ${fmtMoney(cust.monthly_charges)}</div>
      </div>
    </div>
    <div class="badge ${isChurn ? "badge-high" : "badge-low"}" style="font-size:14px; padding: 8px 16px;">
      ${isChurn ? "At Risk of Churn" : "Likely Retained"} · ${fmtPct(pred.churn_probability)}
    </div>
  `;

  // GAUGE CHART
  renderCustomerGauge(pred.churn_probability);

  // CUSTOMER ECONOMICS CARD
  $("dqBadge").textContent = `Data Quality: ${esc(data.data_quality || "GOOD")}`;
  $("customerEconomicsList").innerHTML = `
    <div class="detail-row"><span class="detail-key">Estimated Customer Value:</span><span class="detail-val">${fmtMoney(seg.estimated_customer_value)}</span></div>
    <div class="detail-row"><span class="detail-key">Est. Future 12-Mo Revenue:</span><span class="detail-val">${fmtMoney(fin.estimated_future_revenue)}</span></div>
    <div class="detail-row"><span class="detail-key">Est. Future 12-Mo Margin:</span><span class="detail-val text-emerald">${fmtMoney(fin.estimated_future_margin)}</span></div>
    <div class="detail-row"><span class="detail-key">Expected Churn Loss:</span><span class="detail-val text-rose">${fmtMoney(fin.expected_churn_loss)}</span></div>
  `;

  // DETAILS LIST
  $("customerDetailsList").innerHTML = `
    <div class="detail-row"><span class="detail-key">Tenure:</span><span class="detail-val">${cust.tenure ?? "—"} months</span></div>
    <div class="detail-row"><span class="detail-key">Internet Service:</span><span class="detail-val">${esc(cust.internet_service || "None")}</span></div>
    <div class="detail-row"><span class="detail-key">Payment Method:</span><span class="detail-val">${esc(cust.payment_method || "Electronic Check")}</span></div>
    <div class="detail-row"><span class="detail-key">Online Security:</span><span class="detail-val">${esc(cust.online_security || "No")}</span></div>
    <div class="detail-row"><span class="detail-key">Tech Support:</span><span class="detail-val">${esc(cust.tech_support || "No")}</span></div>
    <div class="detail-row"><span class="detail-key">Total Charges:</span><span class="detail-val">${fmtMoney(cust.total_charges || (cust.monthly_charges * cust.tenure))}</span></div>
  `;

  // ACTIVE VS MISSING SERVICES CHIPS
  const currentServices = cust.current_services || [];
  const missingServices = cust.missing_services || [];
  $("activeServicesChips").innerHTML = currentServices.length
    ? currentServices.map(s => `<span class="chip" style="background:rgba(16,185,129,0.15); border-color:var(--accent-emerald); color:#ffffff;">✓ ${esc(s)}</span>`).join("")
    : `<span class="chip">No active add-ons</span>`;

  $("missingServicesChips").innerHTML = missingServices.length
    ? missingServices.map(s => `<span class="chip" style="background:rgba(244,63,94,0.1); border-color:rgba(244,63,94,0.3); color:#fecdd3;">+ ${esc(s)}</span>`).join("")
    : `<span class="chip">Full service adoption</span>`;

  // SEGMENTS & DRIVERS
  const chips = [seg.behavioral_segment, seg.value_risk_segment, pred.risk_band].filter(Boolean);
  $("segmentChips").innerHTML = chips.map(c => `<span class="chip">${esc(c)}</span>`).join("");

  $("behSegmentName").textContent = `Segment: ${seg.behavioral_segment || "Unclassified"}`;
  $("behSegmentReason").textContent = seg.behavioral_segment_reason || "No strategic rationale provided.";

  const drivers = data.churn_drivers || [];
  $("driversCard").innerHTML = drivers.length
    ? drivers.map(d => `<div class="driver-item"><span>⚠️ ${esc(d)}</span></div>`).join("")
    : `<p style="color:var(--text-muted);">No elevated risk factors detected.</p>`;

  // RECOMMENDED ACTION
  const camp = act.campaign || {};
  $("actionsCard").innerHTML = `
    <h3>Recommended Action: ${esc(data.next_best_action || "Retention Offer")}</h3>
    <div class="chip-group margin-top">
      <span class="badge badge-outline">${esc(act.type || "Retention Offer")}</span>
      <span class="badge badge-pending">Priority: ${esc(act.priority || "High")}</span>
    </div>
    <p style="margin-top:10px; font-size:14px; color:var(--text-main);">${esc(act.reason || "")}</p>
    ${camp.campaign ? `
      <div class="card margin-top" style="background:rgba(15,23,42,0.6);">
        <div style="font-weight:600; color:var(--accent-indigo);">${esc(camp.campaign)}</div>
        <div style="font-size:13px; color:var(--text-muted); margin-top:4px;">Cost: ${fmtMoney(camp.campaign_cost)} | Expected Net Benefit: ${fmtMoney(camp.expected_net_benefit)}</div>
      </div>
    ` : ""}
  `;

  // TAILORED CAMPAIGN EVALUATION & ALTERNATIVES
  const evalCard = $("campaignEvalCard");
  const reasonsHost = $("campaignReasonsHost");
  const otherTbody = $("otherCampaignsTableBody");

  if (act.type === "RETENTION" && typeof camp === "object") {
    evalCard.hidden = false;
    const reasons = camp.success_probability_reasons || [];
    reasonsHost.innerHTML = reasons.length
      ? reasons.map(r => `<div style="font-size:13px; color:var(--text-muted); margin-bottom:4px;">🔹 ${esc(r)}</div>`).join("")
      : `<p style="font-size:13px; color:var(--text-sub);">Default economic ranking applied.</p>`;

    const others = camp.other_candidates_considered || [];
    if (others.length) {
      otherTbody.innerHTML = others.map(oc => `
        <tr>
          <td><strong>${esc(oc.campaign)}</strong></td>
          <td>${fmtMoney(oc.campaign_cost)}</td>
          <td>${fmtPct(oc.expected_success_probability)}</td>
          <td><span class="${oc.expected_net_benefit > 0 ? "text-emerald" : "text-rose"}">${fmtMoney(oc.expected_net_benefit)}</span></td>
          <td>${oc.expected_roi ? (oc.expected_roi * 100).toFixed(0) + "%" : "—"}</td>
        </tr>
      `).join("");
    } else {
      otherTbody.innerHTML = `<tr><td colspan="5" class="text-center">No alternative campaigns qualified.</td></tr>`;
    }
  } else {
    evalCard.hidden = true;
  }

  // UPSELL / GROWTH CANDIDATES
  const upsellHost = $("upsellCard");
  const upsellList = $("upsellList");
  if (act.type === "GROWTH" && typeof camp === "object" && camp.Service) {
    upsellHost.hidden = false;
    upsellList.innerHTML = `
      <div class="detail-row"><span class="detail-key">Opportunity Service:</span><span class="detail-val text-indigo">${esc(camp.Service)}</span></div>
      <div class="detail-row"><span class="detail-key">Opportunity Score:</span><span class="detail-val">${camp.OpportunityScore} / 100</span></div>
      <div class="detail-row"><span class="detail-key">Est. Monthly Revenue:</span><span class="detail-val">${fmtMoney(camp.EstimatedMonthlyRevenue)}/mo</span></div>
      <div class="detail-row"><span class="detail-key">Est. Annual Margin:</span><span class="detail-val text-emerald">${fmtMoney(camp.EstimatedAnnualMargin)}/yr</span></div>
      <p style="font-size:12px; color:var(--text-muted); margin-top:8px;">${esc(camp.Reason)}</p>
    `;
  } else {
    upsellHost.hidden = true;
  }

  // SEED SINGLE CUSTOMER AI CHAT
  state.customer.thread = [{
    role: "assistant",
    text: `Analyzed customer #${id}. Churn probability is **${fmtPct(pred.churn_probability)}** (${pred.risk_band}). Ask me anything about this customer's risk profile or best retention action.`
  }];
  renderChatThread($("customerThread"), state.customer.thread);
}

function renderCustomerGauge(probVal) {
  destroyChart("customerGauge");
  const gaugeCanvas = $("chartCustomerGauge");
  if (gaugeCanvas && window.Chart) {
    const prob = Math.round((probVal || 0) * 100);
    chartInstances.customerGauge = new Chart(gaugeCanvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: ["Churn Risk", "Retention"],
        datasets: [{
          data: [prob, 100 - prob],
          backgroundColor: [prob > 50 ? "#f43f5e" : "#10b981", "#1e293b"],
          borderWidth: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        cutout: "75%"
      }
    });
  }
}

// NATURAL LANGUAGE CUSTOMER EXTRACTION FLOW
$("btnDescribeNew")?.addEventListener("click", () => {
  $("customerEmptyState").hidden = true;
  $("customerResult").hidden = true;
  $("customerCollectSection").hidden = false;
  state.customer.collected = {};
  state.customer.askedFields = [];
  state.customer.thread = [{
    role: "assistant",
    text: "Welcome! Describe the customer in natural language (e.g. *customer with fiber internet, monthly contract, paying $90/mo, 2 months tenure*), and I will extract their parameters automatically."
  }];
  renderChatThread($("collectThread"), state.customer.thread);
});

$("collectSend")?.addEventListener("click", sendCollectMessage);
$("collectInput")?.addEventListener("keydown", e => { if (e.key === "Enter") sendCollectMessage(); });

async function sendCollectMessage() {
  const input = $("collectInput");
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  state.customer.thread.push({ role: "user", text: message });
  renderChatThread($("collectThread"), state.customer.thread);

  appendTypingIndicator("collectThread");

  try {
    const res = await fetch(API.extract, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        asked_fields: state.customer.askedFields,
        collected: state.customer.collected
      })
    });
    const data = await res.json();
    removeTypingIndicator("collectThread");

    if (!res.ok) throw new Error(data.detail || "Parameter extraction failed");

    state.customer.collected = data.collected;
    state.customer.askedFields = data.missing_fields;

    state.customer.thread.push({ role: "assistant", text: data.reply });
    renderChatThread($("collectThread"), state.customer.thread);

    if (data.ready) {
      appendTypingIndicator("collectThread");
      const ar = await fetch(API.analyze, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ collected: state.customer.collected })
      });
      const analysis = await ar.json();
      removeTypingIndicator("collectThread");
      renderSingleCustomer(analysis, analysis.customer_id || "New-Customer");
    }
  } catch (err) {
    removeTypingIndicator("collectThread");
    state.customer.thread.push({ role: "assistant", text: "⚠️ " + err.message });
    renderChatThread($("collectThread"), state.customer.thread);
  }
}

// SINGLE CUSTOMER CHAT
$("customerComposerSend")?.addEventListener("click", sendCustomerChatMessage);
$("customerComposerInput")?.addEventListener("keydown", e => { if (e.key === "Enter") sendCustomerChatMessage(); });

async function sendCustomerChatMessage() {
  const input = $("customerComposerInput");
  const q = input.value.trim();
  if (!q || !state.customer.analysis) return;

  input.value = "";
  state.customer.thread.push({ role: "user", text: q });
  renderChatThread($("customerThread"), state.customer.thread);

  appendTypingIndicator("customerThread");

  try {
    const res = await fetch(API.chatCustomer, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        analysis: state.customer.analysis,
        question: q,
        history: state.customer.history
      })
    });
    const data = await res.json();
    removeTypingIndicator("customerThread");

    if (!res.ok) throw new Error(data.detail || "Could not generate answer");

    state.customer.thread.push({ role: "assistant", text: data.answer });
    state.customer.history.push({ role: "user", content: q }, { role: "assistant", content: data.answer });
    renderChatThread($("customerThread"), state.customer.thread);
  } catch (err) {
    removeTypingIndicator("customerThread");
    state.customer.thread.push({ role: "assistant", text: "⚠️ " + err.message });
    renderChatThread($("customerThread"), state.customer.thread);
  }
}

// MODALS & DRAWER CONTROLS
$("btnToggleAiDrawer")?.addEventListener("click", () => {
  $("aiAssistantDrawer").hidden = false;
  loadChatSessions();
});
$("btnCloseAiDrawer")?.addEventListener("click", () => {
  $("aiAssistantDrawer").hidden = true;
});

$("btnOpenCompareModal")?.addEventListener("click", () => { $("compareModal").hidden = false; });
$("btnCloseCompareModal")?.addEventListener("click", () => { $("compareModal").hidden = true; });

$("btnRunComparison")?.addEventListener("click", async () => {
  const host = $("compareResultHost");
  host.innerHTML = `<div class="badge badge-pending">Running campaign simulation...</div>`;
  const ca = { campaign: $("campAName").value, campaign_cost: parseFloat($("campACost").value), expected_success_probability: parseFloat($("campASucc").value)/100 };
  const cb = { campaign: $("campBName").value, campaign_cost: parseFloat($("campBCost").value), expected_success_probability: parseFloat($("campBSucc").value)/100 };

  try {
    const res = await fetch(API.compare, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campaign_a: ca, campaign_b: cb })
    });
    const data = await res.json();
    host.innerHTML = `
      <div class="card margin-top" style="background:rgba(16,185,129,0.1); border-color:var(--accent-emerald);">
        <h4 style="color:var(--accent-emerald);">Recommended Campaign: ${esc(data.recommended_campaign)}</h4>
        <p style="font-size:13px; margin-top:4px;">Expected Net Benefit Differential: ${fmtMoney(data.net_benefit_difference)}</p>
      </div>
    `;
  } catch (err) {
    host.innerHTML = `<div class="badge badge-high">${esc(err.message)}</div>`;
  }
});

$("btnOpenOverrideModal")?.addEventListener("click", () => {
  $("overrideAiRec").value = state.customer.analysis?.recommended_action?.campaign?.campaign || "Standard Retention Offer";
  $("overrideModal").hidden = false;
});
$("btnCloseOverrideModal")?.addEventListener("click", () => { $("overrideModal").hidden = true; });

$("btnSubmitOverride")?.addEventListener("click", async () => {
  const host = $("overrideMsgHost");
  try {
    const res = await fetch(API.override, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_id: state.customer.customerId || "manual",
        ai_recommendation: $("overrideAiRec").value,
        employee_decision: $("overrideEmployeeDec").value,
        reason: $("overrideReason").value
      })
    });
    if (!res.ok) throw new Error("Failed to record decision");
    host.innerHTML = `<div class="badge badge-low">Employee decision logged successfully!</div>`;
    setTimeout(() => { $("overrideModal").hidden = true; host.innerHTML = ""; }, 1500);
  } catch (err) {
    host.innerHTML = `<div class="badge badge-high">${esc(err.message)}</div>`;
  }
});

// ================================================================
// 3. BATCH CSV UPLOAD & DIRECTORY
// ================================================================
const dropzone = $("dropzone");
const csvInput = $("csvInput");

$("dropzoneClick")?.addEventListener("click", () => csvInput.click());
dropzone?.addEventListener("click", () => csvInput.click());
dropzone?.addEventListener("dragover", e => { e.preventDefault(); dropzone.classList.add("over"); });
dropzone?.addEventListener("dragleave", () => dropzone.classList.remove("over"));
dropzone?.addEventListener("drop", e => {
  e.preventDefault();
  dropzone.classList.remove("over");
  if (e.dataTransfer.files[0]) setBatchFile(e.dataTransfer.files[0]);
});
csvInput?.addEventListener("change", () => { if (csvInput.files[0]) setBatchFile(csvInput.files[0]); });

function setBatchFile(f) {
  state.batch.file = f;
  $("fileCardHost").innerHTML = `
    <div class="card margin-top" style="display:flex; align-items:center; justify-content:space-between;">
      <div>📁 <strong>${esc(f.name)}</strong> (${(f.size/1024).toFixed(1)} KB)</div>
      <span class="badge badge-pending">Ready for Processing</span>
    </div>
  `;
  $("uploadActions").hidden = false;
}

$("btnClearFile")?.addEventListener("click", () => {
  state.batch.file = null;
  csvInput.value = "";
  $("fileCardHost").innerHTML = "";
  $("uploadActions").hidden = true;
  $("uploadMsgHost").innerHTML = "";
});

$("btnAnalyze")?.addEventListener("click", async () => {
  if (!state.batch.file) return;
  const msgHost = $("uploadMsgHost");
  msgHost.innerHTML = `<div class="badge badge-pending margin-top">Analyzing CSV dataset rows with ML engine...</div>`;

  const fd = new FormData();
  fd.append("file", state.batch.file);

  try {
    const res = await fetch(API.uploadCsv + "?save_to_dataset=true", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload analysis failed");

    msgHost.innerHTML = `<div class="badge badge-low margin-top">Successfully analyzed ${data.rows_analyzed} customers!</div>`;
    switchTab("dashboard");
    loadDashboard();
  } catch (err) {
    msgHost.innerHTML = `<div class="badge badge-high margin-top">${esc(err.message)}</div>`;
  }
});

// DIRECTORY TABLE & PAGINATION
async function loadCustomerDirectory() {
  const tbody = $("dirTableBody");
  tbody.innerHTML = `<tr><td colspan="8" class="text-center">Loading customer records...</td></tr>`;

  try {
    const res = await fetch(`${API.customers}?search=${encodeURIComponent(state.directory.search)}&limit=${state.directory.limit}&offset=${state.directory.offset}`);
    if (!res.ok) throw new Error("Could not fetch customer directory");
    const data = await res.json();

    state.directory.customers = data.customers || [];
    state.directory.total = data.total || 0;

    $("dirTableCount").textContent = `Total Customers: ${state.directory.total}`;
    $("pageIndicator").textContent = `Page ${Math.floor(state.directory.offset / state.directory.limit) + 1} of ${Math.ceil(state.directory.total / state.directory.limit) || 1}`;

    $("btnPrevPage").disabled = state.directory.offset === 0;
    $("btnNextPage").disabled = state.directory.offset + state.directory.limit >= state.directory.total;

    if (!state.directory.customers.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center">No matching customer records found.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.directory.customers.map(c => {
      const isChurn = c.decision === "CHURN" || (c.churn_probability != null && c.churn_probability >= 0.5);
      const probText = c.churn_probability != null ? fmtPct(c.churn_probability) : "—";
      const riskBand = c.risk_band || (c.churn_probability >= 0.5 ? "High Risk" : (c.churn_probability >= 0.35 ? "Medium Risk" : "Low Risk"));
      const badgeClass = c.churn_probability >= 0.5 ? "badge-high" : (c.churn_probability >= 0.35 ? "badge-med" : "badge-low");

      return `
        <tr>
          <td><strong>${esc(c.customerID)}</strong></td>
          <td>${c.tenure ?? "—"} mo</td>
          <td>${esc(c.Contract || c.contract || "—")}</td>
          <td><span class="chip" style="font-size:11.5px;">${esc(c.behavioral_segment || "Unclassified")}</span></td>
          <td>${fmtMoney(c.MonthlyCharges || c.monthly_charges)}</td>
          <td>${esc(c.InternetService || c.internet_service || "None")}</td>
          <td>${isChurn ? '<span class="text-rose">At Risk (Churn)</span>' : '<span class="text-emerald">Retained</span>'}</td>
          <td><span class="badge ${badgeClass}">${esc(riskBand)} (${probText})</span></td>
          <td>
            <button class="btn btn-sm btn-outline" onclick="inspectCustomer('${esc(c.customerID)}')">Inspect Profile</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-rose">${esc(err.message)}</td></tr>`;
  }
}

window.inspectCustomer = id => {
  switchTab("customer");
  $("custSearchInput").value = id;
  fetchCustomerDetail(id);
};

$("dirSearchInput")?.addEventListener("input", e => {
  state.directory.search = e.target.value.trim();
  state.directory.offset = 0;
  loadCustomerDirectory();
});

$("btnPrevPage")?.addEventListener("click", () => {
  if (state.directory.offset >= state.directory.limit) {
    state.directory.offset -= state.directory.limit;
    loadCustomerDirectory();
  }
});

$("btnNextPage")?.addEventListener("click", () => {
  if (state.directory.offset + state.directory.limit < state.directory.total) {
    state.directory.offset += state.directory.limit;
    loadCustomerDirectory();
  }
});

// ================================================================
// 4. AI CHAT ASSISTANT & SESSIONS
// ================================================================
async function loadChatSessions() {
  try {
    const res = await fetch(`${API.sessions}?kind=dataset`);
    if (!res.ok) return;
    const data = await res.json();
    state.chat.sessions = data.sessions || [];

    const host = $("chatSessionList");
    if (!state.chat.sessions.length) {
      host.innerHTML = `<div style="font-size:12px; color:var(--text-sub);">No saved sessions</div>`;
      return;
    }
    host.innerHTML = state.chat.sessions.map(s => `
      <button class="session-item ${s.id === state.chat.sessionId ? "active" : ""}" onclick="loadChatSession('${s.id}')">
        💬 ${esc(s.title || "Dataset Chat")}
      </button>
    `).join("");
  } catch {}
}

window.loadChatSession = async id => {
  state.chat.sessionId = id;
  try {
    const res = await fetch(API.session(id));
    if (!res.ok) return;
    const data = await res.json();
    const st = data.state || {};
    state.chat.thread = st.thread || [];
    state.chat.history = st.history || [];
    renderChatThread($("datasetThread"), state.chat.thread);
    loadChatSessions();
  } catch {}
};

$("btnNewChatSession")?.addEventListener("click", () => {
  state.chat.sessionId = null;
  state.chat.thread = [{ role: "assistant", text: "Welcome! I am your Dataset Intelligence Assistant. Ask me anything about customer churn patterns or segment risks." }];
  state.chat.history = [];
  renderChatThread($("datasetThread"), state.chat.thread);
  loadChatSessions();
});

$("datasetComposerSend")?.addEventListener("click", sendDatasetChatMessage);
$("datasetComposerInput")?.addEventListener("keydown", e => { if (e.key === "Enter") sendDatasetChatMessage(); });

async function sendDatasetChatMessage() {
  const input = $("datasetComposerInput");
  const q = input.value.trim();
  if (!q) return;

  input.value = "";
  state.chat.thread.push({ role: "user", text: q });
  renderChatThread($("datasetThread"), state.chat.thread);

  appendTypingIndicator("datasetThread");

  try {
    const res = await fetch(API.datasetChat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, history: state.chat.history })
    });
    const data = await res.json();
    removeTypingIndicator("datasetThread");

    if (!res.ok) throw new Error(data.detail || "Could not process request");

    state.chat.thread.push({ role: "assistant", text: data.answer });
    state.chat.history.push({ role: "user", content: q }, { role: "assistant", content: data.answer });
    renderChatThread($("datasetThread"), state.chat.thread);

    // Save session
    const savePayload = {
      kind: "dataset",
      title: q.slice(0, 30),
      state: { thread: state.chat.thread, history: state.chat.history }
    };
    if (!state.chat.sessionId) {
      const sRes = await fetch(API.sessions, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(savePayload) });
      if (sRes.ok) { const rec = await sRes.json(); state.chat.sessionId = rec.id; }
    } else {
      await fetch(API.session(state.chat.sessionId), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(savePayload) });
    }
    loadChatSessions();
  } catch (err) {
    removeTypingIndicator("datasetThread");
    state.chat.thread.push({ role: "assistant", text: "⚠️ " + err.message });
    renderChatThread($("datasetThread"), state.chat.thread);
  }
}

// TYPING INDICATOR HELPERS
function appendTypingIndicator(boxId) {
  const box = $(boxId);
  if (!box) return;
  const el = document.createElement("div");
  el.className = "msg-row ai typing-row";
  el.id = `typing-${boxId}`;
  el.innerHTML = `
    <div class="msg-bubble">
      <div class="typing-dots"><span></span><span></span><span></span></div>
    </div>
  `;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}

function removeTypingIndicator(boxId) {
  const el = $(`typing-${boxId}`);
  if (el) el.remove();
}

// RENDER CHAT THREAD HELPER
function renderChatThread(box, thread) {
  if (!box) return;
  box.innerHTML = thread.map(msg => `
    <div class="msg-row ${msg.role === "user" ? "user" : "ai"}">
      <div class="msg-bubble" dir="auto">${msg.role === "user" ? esc(msg.text) : parseMarkdown(msg.text)}</div>
    </div>
  `).join("");
  box.scrollTop = box.scrollHeight;
}

// INITIALIZATION
document.addEventListener("DOMContentLoaded", async () => {
  initNavigation();
  checkHealth();
  setInterval(checkHealth, 30000);

  try {
    const res = await fetch(API.dashboard);
    const data = await res.json();
    if (!data.has_current_upload || !data.total_customers) {
      switchTab("directory");
    } else {
      loadDashboard();
    }
  } catch {
    switchTab("directory");
  }
});

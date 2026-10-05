const state = { actions: [], anomalies: [], selectedId: null, eventSource: null, principal: null };
const DEMO_PERSONAS = {
  admin: { userId: 'maya.chen', name: 'Maya Chen', summary: 'Admin · full control-plane access', description: 'Can manage budgets and take any permitted action.' },
  approver: { userId: 'priya.sharma', name: 'Priya Sharma', summary: 'Approver · approval decisions', description: 'Can approve or reject proposed cloud remediations.' },
  operator: { userId: 'alex.morgan', name: 'Alex Morgan', summary: 'Operator · operational workflows', description: 'Can submit signals and roll back completed remediations.' },
  viewer: { userId: 'jordan.lee', name: 'Jordan Lee', summary: 'Viewer · read-only access', description: 'Can inspect policy evidence and audit history, but cannot change decisions.' },
};

const elements = {
  actionTable: document.querySelector('#actions-table'),
  actionTotal: document.querySelector('#action-total'),
  anomalyTable: document.querySelector('#anomalies-table'),
  anomalyTotal: document.querySelector('#anomaly-total'),
  pendingCount: document.querySelector('#pending-count'),
  pendingCaption: document.querySelector('#pending-caption'),
  completedCount: document.querySelector('#completed-count'),
  savingsTotal: document.querySelector('#savings-total'),
  dailySpendTotal: document.querySelector('#daily-spend-total'),
  reviewedCaption: document.querySelector('#reviewed-caption'),
  priorityAction: document.querySelector('#priority-action'),
  deniedCount: document.querySelector('#denied-count'),
  policyReasons: document.querySelector('#policy-reasons'),
  reviewedDaily: document.querySelector('#reviewed-daily'),
  expectedDaily: document.querySelector('#expected-daily'),
  excessDaily: document.querySelector('#excess-daily'),
  scanTotal: document.querySelector('#scan-total'),
  profileName: document.querySelector('#profile-name'),
  profileRole: document.querySelector('#profile-role'),
  contextUser: document.querySelector('#context-user'),
  contextTenant: document.querySelector('#context-tenant'),
  contextRole: document.querySelector('#context-role'),
  accessSummary: document.querySelector('#access-summary'),
  todayDay: document.querySelector('#today-day'),
  todayMonth: document.querySelector('#today-month'),
  detail: document.querySelector('#action-detail'),
  refresh: document.querySelector('#refresh-button'),
  connectionStatus: document.querySelector('#connection-status'),
  toast: document.querySelector('#toast'),
  authGate: document.querySelector('#auth-gate'),
  dashboardContent: document.querySelector('#dashboard-content'),
  loginForm: document.querySelector('#login-form'),
  tenantInput: document.querySelector('#tenant-input'),
  roleInput: document.querySelector('#role-input'),
  rolePreviewTitle: document.querySelector('#role-preview-title'),
  rolePreviewDescription: document.querySelector('#role-preview-description'),
  logout: document.querySelector('#logout-button'),
};

function money(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);
}

function label(status) {
  return status.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, character => character.toUpperCase());
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add('visible');
  window.setTimeout(() => elements.toast.classList.remove('visible'), 2800);
}

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'x-actor': 'dashboard-user', ...(options.headers || {}) } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'The request could not be completed.');
  }
  return response.json();
}

function renderMetrics() {
  const pendingActions = state.actions.filter(action => action.status === 'PENDING_APPROVAL');
  const pending = pendingActions.length;
  const completed = state.actions.filter(action => action.status === 'SUCCEEDED' || action.status === 'ROLLED_BACK').length;
  const pendingSavings = pendingActions
    .reduce((total, action) => total + Number(action.projected_monthly_savings), 0);
  const dailySpend = state.anomalies.reduce((total, anomaly) => total + Number(anomaly.current_daily_cost || 0), 0);
  const expectedDaily = state.anomalies.reduce((total, anomaly) => total + Number(anomaly.expected_daily_cost || 0), 0);
  const dailyExcess = Math.max(dailySpend - expectedDaily, 0);
  const eligible = state.anomalies.filter(anomaly => Boolean(anomaly.verdict_eligible)).length;
  const rejected = state.anomalies.length - eligible;
  elements.pendingCount.textContent = pending;
  elements.pendingCaption.textContent = pending ? 'A human approval is required before work can run' : 'No cloud action is waiting for approval';
  elements.completedCount.textContent = completed;
  elements.savingsTotal.textContent = state.anomalies.length;
  elements.dailySpendTotal.textContent = money(pendingSavings);
  elements.reviewedCaption.textContent = `${eligible} eligible · ${rejected} rejected by policy`;
  elements.scanTotal.textContent = `${money(dailyExcess)} excess / day`;
  elements.reviewedDaily.textContent = money(dailySpend);
  elements.expectedDaily.textContent = money(expectedDaily);
  elements.excessDaily.textContent = money(dailyExcess);
  renderPriorityAction(pendingActions);
  renderPolicyReasons(rejected);
  elements.actionTotal.textContent = `${state.actions.length} action${state.actions.length === 1 ? '' : 's'}`;
}

function renderPriorityAction(pendingActions) {
  const action = pendingActions[0];
  if (!action) {
    elements.priorityAction.innerHTML = '<p class="eyebrow">Decision inbox</p><h2>No cloud action needs approval.</h2><p>Radar has evaluated the current signals and there is nothing waiting for a human decision.</p>';
    return;
  }
  const canApprove = ['approver', 'admin'].includes(state.principal?.role);
  const control = canApprove
    ? `<button class="button button-primary" data-priority-select="${action.id}">Review decision <span aria-hidden="true">↗</span></button>`
    : '<span class="permission-note">🔒 Switch to Approver to make this decision.</span>';
  elements.priorityAction.innerHTML = `<div><p class="eyebrow">Decision inbox · action required</p><h2>${escapeHtml(action.resource_id)} could save ${money(action.projected_monthly_savings)}/month.</h2><p>${escapeHtml(action.policy_reason)}</p></div><div class="priority-action-controls"><span class="status-badge status-pending_approval">Awaiting approval</span>${control}</div>`;
  document.querySelector('[data-priority-select]')?.addEventListener('click', () => selectAction(action.id));
}

function renderPolicyReasons(rejected) {
  elements.deniedCount.textContent = `${rejected} rejected`;
  const reasons = state.anomalies
    .filter(anomaly => !anomaly.verdict_eligible)
    .reduce((counts, anomaly) => {
      const reason = anomaly.verdict_reason || 'No policy reason recorded.';
      counts[reason] = (counts[reason] || 0) + 1;
      return counts;
    }, {});
  const entries = Object.entries(reasons).sort((left, right) => right[1] - left[1]);
  elements.policyReasons.innerHTML = entries.length
    ? entries.slice(0, 3).map(([reason, count]) => `<div class="policy-reason"><span>${escapeHtml(reason)}</span><b>${count}</b></div>`).join('')
    : '<p class="ai-empty">Every reviewed signal matched the current policy.</p>';
}

function renderSessionContext() {
  if (!state.principal) return;
  const tenant = state.principal.tenant_id.replaceAll('-', ' ');
  const role = label(state.principal.role);
  const persona = DEMO_PERSONAS[state.principal.role];
  const initials = tenant.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase();
  document.querySelector('.profile-avatar').textContent = initials;
  elements.profileName.textContent = persona?.name || state.principal.user_id;
  elements.profileRole.textContent = `${role} access`;
  elements.contextUser.textContent = persona?.name || state.principal.user_id;
  elements.contextTenant.textContent = tenant;
  elements.contextRole.textContent = role;
  elements.accessSummary.textContent = persona?.summary || `${role} access`;
}

function renderPersonaPreview() {
  const persona = DEMO_PERSONAS[elements.roleInput.value];
  elements.rolePreviewTitle.textContent = `${persona.name} — ${persona.description}`;
  elements.rolePreviewDescription.textContent = persona.summary;
}

function renderToday() {
  const now = new Date();
  elements.todayDay.textContent = now.toLocaleDateString('en-US', { day: '2-digit' });
  elements.todayMonth.textContent = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short' });
}

function renderTable() {
  if (!state.actions.length) {
    elements.actionTable.innerHTML = '<tr><td colspan="5" class="empty-state">No qualifying remediation actions yet. Submit an anomaly through the API to begin.</td></tr>';
    return;
  }
  elements.actionTable.innerHTML = state.actions.map(action => `
    <tr>
      <td><span class="resource-name">${escapeHtml(action.resource_id)}</span><span class="resource-type">${escapeHtml(action.action_type)}</span></td>
      <td>${escapeHtml(action.tenant_id)}</td>
      <td><span class="status-badge status-${action.status.toLowerCase()}">${label(action.status)}</span></td>
      <td class="savings">${money(action.projected_monthly_savings)}</td>
      <td><button class="button button-secondary" data-select="${action.id}">View</button></td>
    </tr>
  `).join('');
  document.querySelectorAll('[data-select]').forEach(button => button.addEventListener('click', () => selectAction(button.dataset.select)));
}

function renderAnomalies() {
  elements.anomalyTotal.textContent = `${state.anomalies.length} anomal${state.anomalies.length === 1 ? 'y' : 'ies'}`;
  if (!state.anomalies.length) {
    elements.anomalyTable.innerHTML = '<tr><td colspan="5" class="empty-state">No anomaly decisions yet.</td></tr>';
    return;
  }
  elements.anomalyTable.innerHTML = state.anomalies.map(anomaly => {
    const eligible = Boolean(anomaly.verdict_eligible);
    return `<tr>
      <td><span class="resource-name">${escapeHtml(anomaly.resource_id)}</span><span class="resource-type">${escapeHtml(anomaly.resource_type)}</span></td>
      <td>${escapeHtml(anomaly.environment)}</td>
      <td class="savings">${money(anomaly.current_daily_cost)}/day</td>
      <td><span class="status-badge verdict-${eligible ? 'eligible' : 'ineligible'}">${eligible ? 'Eligible' : 'Ineligible'}</span></td>
      <td class="reason-cell">${escapeHtml(anomaly.verdict_reason || 'Pending evaluation')}</td>
    </tr>`;
  }).join('');
}

function escapeHtml(value) {
  const node = document.createElement('span');
  node.textContent = value ?? '';
  return node.innerHTML;
}

function actionButtons(action) {
  const controls = [];
  const canApprove = ['approver', 'admin'].includes(state.principal?.role);
  const canOperate = ['operator', 'admin'].includes(state.principal?.role);
  if (action.status === 'PENDING_APPROVAL' && canApprove) {
    controls.push('<button class="button button-primary" data-command="approve">Approve</button>');
    controls.push('<button class="button button-danger" data-command="reject">Reject</button>');
  } else if (action.status === 'PENDING_APPROVAL') {
    controls.push('<span class="permission-note">🔒 Approval requires the Approver role.</span>');
  }
  if (action.status === 'APPROVED') controls.push('<span class="count-pill">Queued for background execution</span>');
  if (action.status === 'SUCCEEDED' && canOperate) controls.push('<button class="button button-quiet" data-command="rollback">Rollback / start instance</button>');
  if (action.status === 'SUCCEEDED' && !canOperate) controls.push('<span class="permission-note">🔒 Rollback requires the Operator role.</span>');
  return controls.join('');
}

async function selectAction(actionId) {
  state.selectedId = actionId;
  const action = state.actions.find(item => item.id === actionId);
  if (!action) return;
  elements.detail.innerHTML = '<p class="eyebrow">Action detail</p><p>Loading audit evidence…</p>';
  try {
    const audit = await request(`/v1/actions/${action.id}/audit`);
    renderDetail(action, audit);
  } catch (error) {
    elements.detail.innerHTML = `<p class="eyebrow">Action detail</p><h2>Could not load action</h2><p>${escapeHtml(error.message)}</p>`;
  }
}

function renderDetail(action, audit) {
  elements.detail.innerHTML = `
    <div class="detail-title">
      <div><p class="eyebrow">Action detail</p><h2>${escapeHtml(action.action_type.replaceAll('_', ' '))}</h2></div>
      <span class="status-badge status-${action.status.toLowerCase()}">${label(action.status)}</span>
    </div>
    <p class="detail-id">${escapeHtml(action.id)}</p>
    <div class="detail-grid">
      <div class="detail-item"><span>Resource</span><strong>${escapeHtml(action.resource_id)}</strong></div>
      <div class="detail-item"><span>Tenant</span><strong>${escapeHtml(action.tenant_id)}</strong></div>
      <div class="detail-item"><span>Projected monthly savings</span><strong>${money(action.projected_monthly_savings)}</strong></div>
      <div class="detail-item"><span>Created</span><strong>${new Date(action.created_at).toLocaleString()}</strong></div>
    </div>
    <div class="reason"><strong>Policy evidence</strong><br>${escapeHtml(action.policy_reason)}</div>
    <div class="action-row">${actionButtons(action) || '<span class="count-pill">No action available in this state</span>'}</div>
    <h3 class="audit-heading">Audit trail</h3>
    <ol class="audit-list">${audit.map(event => `<li><strong>${escapeHtml(label(event.event_type))}</strong><span>${new Date(event.created_at).toLocaleString()} · ${escapeHtml(event.actor)}</span></li>`).join('')}</ol>
  `;
  document.querySelectorAll('[data-command]').forEach(button => button.addEventListener('click', () => performAction(action.id, button.dataset.command)));
}

async function performAction(actionId, command) {
  try {
    await request(`/v1/actions/${actionId}/${command}`, { method: 'POST' });
    showToast(`${label(command)} completed.`);
    await loadActions();
    await selectAction(actionId);
  } catch (error) {
    showToast(error.message);
  }
}

async function loadActions() {
  if (!state.principal) return;
  elements.connectionStatus.textContent = 'Refreshing data';
  try {
    const [actions, anomalies] = await Promise.all([request('/v1/actions'), request('/v1/anomalies')]);
    state.actions = actions;
    state.anomalies = anomalies;
    renderMetrics();
    renderTable();
    renderAnomalies();
    elements.connectionStatus.textContent = state.eventSource?.readyState === EventSource.OPEN
      ? 'Live updates connected'
      : 'Connected to local API';
    document.querySelector('.connection-dot').classList.add('connected');
  } catch (error) {
    elements.connectionStatus.textContent = 'API unavailable';
    document.querySelector('.connection-dot').classList.remove('connected');
    showToast(error.message);
  }
}

async function fetchSession() {
  try {
    state.principal = await request('/v1/session');
    elements.authGate.hidden = true;
    elements.dashboardContent.hidden = false;
    renderSessionContext();
    renderToday();
    await loadActions();
    connectEventStream();
  } catch (error) {
    state.principal = null;
    elements.connectionStatus.textContent = 'Sign in to load tenant data';
    elements.authGate.hidden = false;
  }
}

async function signIn(event) {
  event.preventDefault();
  const persona = DEMO_PERSONAS[elements.roleInput.value];
  const response = await fetch('/v1/auth/demo-login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ tenant_id: elements.tenantInput.value, role: elements.roleInput.value, user_id: persona.userId }),
  });
  if (!response.ok) {
    showToast('Demo sign-in is unavailable.');
    return;
  }
  showToast('Demo session started.');
  await fetchSession();
}

async function logout() {
  try {
    await request('/v1/auth/logout', { method: 'POST' });
  } finally {
    state.eventSource?.close();
    state.eventSource = null;
    state.principal = null;
    state.selectedId = null;
    elements.dashboardContent.hidden = true;
    elements.authGate.hidden = false;
    elements.connectionStatus.textContent = 'Choose a demo role';
    renderPersonaPreview();
    showToast('Session cleared. Choose another role to continue.');
  }
}

function displayEventName(type) {
  const names = {
    'action.approval_required': 'A remediation action needs approval.',
    'anomaly.ineligible': 'An anomaly was received but did not match a remediation policy.',
    'action.approved': 'Remediation action approved.',
    'action.rejected': 'Remediation action rejected.',
    'action.succeeded': 'Simulated cloud action completed.',
    'action.rolled_back': 'Action rollback completed.',
    'job.queued': 'Action queued for background execution.',
    'job.failed': 'A background job needs attention.',
  };
  return names[type] || 'Dashboard data updated.';
}

function connectEventStream() {
  if (!window.EventSource || state.eventSource) return;
  const source = new EventSource('/v1/events');
  state.eventSource = source;
  source.addEventListener('connected', () => {
    elements.connectionStatus.textContent = 'Live updates connected';
    document.querySelector('.connection-dot').classList.add('connected');
  });
  ['action.approval_required', 'anomaly.ineligible', 'action.approved', 'action.rejected', 'action.succeeded', 'action.rolled_back', 'job.queued', 'job.failed'].forEach(type => {
    source.addEventListener(type, async () => {
      showToast(displayEventName(type));
      await loadActions();
      if (state.selectedId) await selectAction(state.selectedId);
    });
  });
  source.onerror = () => {
    elements.connectionStatus.textContent = 'Live updates reconnecting';
    document.querySelector('.connection-dot').classList.remove('connected');
  };
}

elements.refresh.addEventListener('click', loadActions);
elements.loginForm.addEventListener('submit', signIn);
elements.roleInput.addEventListener('change', renderPersonaPreview);
elements.logout.addEventListener('click', logout);
renderPersonaPreview();
fetchSession();

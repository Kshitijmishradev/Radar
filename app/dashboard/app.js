const state = { actions: [], selectedId: null, eventSource: null, principal: null };

const elements = {
  actionTable: document.querySelector('#actions-table'),
  actionTotal: document.querySelector('#action-total'),
  pendingCount: document.querySelector('#pending-count'),
  completedCount: document.querySelector('#completed-count'),
  savingsTotal: document.querySelector('#savings-total'),
  detail: document.querySelector('#action-detail'),
  refresh: document.querySelector('#refresh-button'),
  connectionStatus: document.querySelector('#connection-status'),
  toast: document.querySelector('#toast'),
  authGate: document.querySelector('#auth-gate'),
  dashboardContent: document.querySelector('#dashboard-content'),
  loginForm: document.querySelector('#login-form'),
  tenantInput: document.querySelector('#tenant-input'),
  roleInput: document.querySelector('#role-input'),
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
  const pending = state.actions.filter(action => action.status === 'PENDING_APPROVAL').length;
  const completed = state.actions.filter(action => action.status === 'SUCCEEDED' || action.status === 'ROLLED_BACK').length;
  const savings = state.actions
    .filter(action => action.status !== 'REJECTED')
    .reduce((total, action) => total + Number(action.projected_monthly_savings), 0);
  elements.pendingCount.textContent = pending;
  elements.completedCount.textContent = completed;
  elements.savingsTotal.textContent = money(savings);
  elements.actionTotal.textContent = `${state.actions.length} action${state.actions.length === 1 ? '' : 's'}`;
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
  }
  if (action.status === 'APPROVED') controls.push('<span class="count-pill">Queued for background execution</span>');
  if (action.status === 'SUCCEEDED' && canOperate) controls.push('<button class="button button-quiet" data-command="rollback">Rollback / start instance</button>');
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
    state.actions = await request('/v1/actions');
    renderMetrics();
    renderTable();
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
  const response = await fetch('/v1/auth/demo-login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ tenant_id: elements.tenantInput.value, role: elements.roleInput.value }),
  });
  if (!response.ok) {
    showToast('Demo sign-in is unavailable.');
    return;
  }
  showToast('Demo session started.');
  await fetchSession();
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
fetchSession();

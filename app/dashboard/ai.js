const state = { principal: null, overview: null, usage: [], source: null, preflightScenario: 'allow' };
const DEMO_PERSONAS = {
  admin: { userId: 'maya.chen', name: 'Maya Chen', summary: 'Admin · full control-plane access', description: 'Can manage budgets and run any permitted AI cost-control workflow.' },
  approver: { userId: 'priya.sharma', name: 'Priya Sharma', summary: 'Approver · cloud decisions', description: 'Can approve cloud remediations, but cannot initiate AI spend checks.' },
  operator: { userId: 'alex.morgan', name: 'Alex Morgan', summary: 'Operator · AI cost operations', description: 'Can run AI preflight and local model validation workflows.' },
  viewer: { userId: 'jordan.lee', name: 'Jordan Lee', summary: 'Viewer · read-only access', description: 'Can inspect cost data but cannot make or trigger cost decisions.' },
};
const PREFLIGHT_SCENARIOS = {
  allow: {
    label: 'Safe request',
    hint: 'Claims Copilot using GPT-4o mini is safely below its monthly budget.',
    app: 'claims-copilot', customer: 'northstar-health', end_user: 'kai@northstar.com',
    provider: 'openai', model: 'gpt-4o-mini', input_tokens: 120000, output_tokens: 18000,
    cached_input_tokens: 20000, compute_cost: 0.03, data_cost: 0.01,
  },
  warn: {
    label: 'Near budget',
    hint: 'Support Assistant is already above its warning threshold, so a small request is allowed but flagged.',
    app: 'support-assistant', customer: 'acme-corp', end_user: 'jane@acme.com',
    provider: 'openai', model: 'gpt-4o-mini', input_tokens: 400000, output_tokens: 50000,
    cached_input_tokens: 80000, compute_cost: 0.10, data_cost: 0.03,
  },
  block: {
    label: 'Over budget',
    hint: 'A premium GPT-4o request would exceed Support Assistant’s monthly guardrail and offers an explicit fallback.',
    app: 'support-assistant', customer: 'acme-corp', end_user: 'jane@acme.com',
    provider: 'openai', model: 'gpt-4o', input_tokens: 900000, output_tokens: 140000,
    cached_input_tokens: 250000, compute_cost: 1.20, data_cost: 0.35,
  },
};
const elements = {
  authGate: document.querySelector('#auth-gate'), dashboard: document.querySelector('#dashboard-content'),
  form: document.querySelector('#login-form'), tenant: document.querySelector('#tenant-input'), role: document.querySelector('#role-input'),
  totalCost: document.querySelector('#total-cost'), requestCount: document.querySelector('#request-count'),
  costToServe: document.querySelector('#cost-to-serve'), costBreakdown: document.querySelector('#cost-breakdown'),
  budgetHealth: document.querySelector('#budget-health'), budgetCaption: document.querySelector('#budget-caption'),
  averageRequestCost: document.querySelector('#average-request-cost'), costPerThousand: document.querySelector('#cost-per-thousand'), cacheEfficiency: document.querySelector('#cache-efficiency'), premiumModelShare: document.querySelector('#premium-model-share'),
  policyDecisionTotal: document.querySelector('#policy-decision-total'), policyDecisionBreakdown: document.querySelector('#policy-decision-breakdown'), blockedExposure: document.querySelector('#blocked-exposure'), fallbackAccepted: document.querySelector('#fallback-accepted'), fallbackSavings: document.querySelector('#fallback-savings'), policyLedgerCount: document.querySelector('#policy-ledger-count'), policyDecisionList: document.querySelector('#policy-decision-list'),
  modelList: document.querySelector('#model-list'), budgetList: document.querySelector('#budget-list'), customerList: document.querySelector('#customer-list'),
  usageTable: document.querySelector('#usage-table'), usageCount: document.querySelector('#usage-count'), preflight: document.querySelector('#run-preflight'),
  preflightResult: document.querySelector('#preflight-result'), ollamaTest: document.querySelector('#run-ollama-test'), ollamaResult: document.querySelector('#ollama-result'), rentalScenario: document.querySelector('#run-rental-scenario'), rentalResult: document.querySelector('#rental-result'), status: document.querySelector('#connection-status'), toast: document.querySelector('#toast'),
  profileName: document.querySelector('#profile-name'), profileRole: document.querySelector('#profile-role'), accessNote: document.querySelector('#ai-access-note'), scenarioHint: document.querySelector('#preflight-scenario-hint'),
  rolePreviewTitle: document.querySelector('#role-preview-title'), rolePreviewDescription: document.querySelector('#role-preview-description'), logout: document.querySelector('#logout-button'),
};
const money = value => Number(value) > 0 && Number(value) < 0.01
  ? `$${Number(value).toFixed(4)}`
  : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);
const escapeHtml = value => { const node = document.createElement('span'); node.textContent = value ?? ''; return node.innerHTML; };

function toast(message) { elements.toast.textContent = message; elements.toast.classList.add('visible'); window.setTimeout(() => elements.toast.classList.remove('visible'), 2800); }
async function request(path, options = {}) { const response = await fetch(path, { ...options, headers: { 'content-type': 'application/json', ...(options.headers || {}) } }); if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || 'Request failed.'); } return response.status === 204 ? null : response.json(); }
function profile() { const tenant = state.principal.tenant_id.replaceAll('-', ' '); const persona = DEMO_PERSONAS[state.principal.role]; elements.profileName.textContent = persona?.name || state.principal.user_id; elements.profileRole.textContent = `${state.principal.role} access`; document.querySelector('.profile-avatar').textContent = tenant.split(' ').map(part => part[0]).join('').slice(0, 2).toUpperCase(); }
function renderPersonaPreview() { const persona = DEMO_PERSONAS[elements.role.value]; elements.rolePreviewTitle.textContent = `${persona.name} — ${persona.description}`; elements.rolePreviewDescription.textContent = persona.summary; }
function renderAIAccess() { const canOperate = ['operator', 'admin'].includes(state.principal?.role); [elements.preflight, elements.ollamaTest, elements.rentalScenario].forEach(button => { button.disabled = !canOperate; }); elements.accessNote.textContent = canOperate ? '✓ Your role can run AI policy and telemetry checks.' : '🔒 Your role is read-only for AI spend controls. Switch to Operator or Admin to run a check.'; }
function selectPreflightScenario(name) { state.preflightScenario = name; const scenario = PREFLIGHT_SCENARIOS[name]; elements.scenarioHint.textContent = scenario.hint; document.querySelectorAll('[data-preflight-scenario]').forEach(button => button.classList.toggle('active', button.dataset.preflightScenario === name)); }

function renderList(target, items, label) { if (!items.length) { target.innerHTML = `<p class="ai-empty">No ${label} recorded yet.</p>`; return; } const max = Math.max(...items.map(item => Number(item.cost)), 1); target.innerHTML = items.slice(0, 4).map(item => `<div class="rank-row"><div><strong>${escapeHtml(item.name)}</strong><span><i style="width:${Math.max(5, Number(item.cost) / max * 100)}%"></i></span></div><b>${money(item.cost)}</b></div>`).join(''); }
function renderPolicyDecisions(summary) {
  const counts = summary.policy_summary.by_decision;
  elements.policyDecisionTotal.textContent = summary.policy_summary.total_decisions;
  elements.policyDecisionBreakdown.textContent = `Allow ${counts.ALLOW || 0} · Warn ${counts.WARN || 0} · Block ${counts.BLOCK || 0}`;
  elements.blockedExposure.textContent = money(summary.policy_summary.blocked_request_exposure);
  elements.fallbackAccepted.textContent = summary.policy_summary.fallback_accepted_count;
  elements.fallbackSavings.textContent = money(summary.policy_summary.fallback_savings);
  const decisions = summary.policy_summary.recent;
  elements.policyLedgerCount.textContent = `${summary.policy_summary.total_decisions} decision${summary.policy_summary.total_decisions === 1 ? '' : 's'}`;
  elements.policyDecisionList.innerHTML = decisions.length ? decisions.map(item => {
    const route = item.fallback_accepted ? `${item.requested_model} → ${item.effective_model}` : item.requested_model;
    const fallback = item.fallback_accepted ? ' · fallback accepted' : item.fallback_offered ? ' · fallback offered' : '';
    return `<div class="policy-decision-row"><span class="decision-badge decision-${String(item.decision).toLowerCase()}">${escapeHtml(item.decision)}</span><div><strong>${escapeHtml(item.app)} · ${escapeHtml(route)}</strong><small>${escapeHtml(item.requested_provider)} · estimated ${money(item.estimated_cost)}${fallback}</small></div><b>${money(item.projected_month_spend)}</b></div>`;
  }).join('') : '<p class="ai-empty">No policy checks recorded yet.</p>';
}
function render() {
  const overview = state.overview;
  elements.totalCost.textContent = money(overview.total_cost);
  elements.requestCount.textContent = `${overview.request_count} attributed request${overview.request_count === 1 ? '' : 's'}`;
  elements.costToServe.textContent = money(overview.total_cost);
  elements.costBreakdown.textContent = `${money(overview.inference_cost)} inference · ${money(overview.compute_cost)} compute · ${money(overview.data_cost)} data`;
  const atRisk = overview.budgets.filter(item => Number(item.percent_used) >= Number(item.warning_percent));
  elements.budgetHealth.textContent = atRisk.length ? `${atRisk.length} alert` : 'Healthy';
  elements.budgetCaption.textContent = atRisk.length ? 'One or more application budgets need attention' : `${overview.budgets.length} app guardrail${overview.budgets.length === 1 ? '' : 's'} within policy`;
  elements.averageRequestCost.textContent = money(overview.average_request_cost);
  elements.costPerThousand.textContent = money(overview.cost_per_thousand_tokens);
  elements.cacheEfficiency.textContent = `${overview.cache_efficiency_percent}%`;
  elements.premiumModelShare.textContent = `${overview.premium_model_spend_percent}%`;
  renderPolicyDecisions(overview);
  renderList(elements.modelList, overview.by_model, 'model costs'); renderList(elements.customerList, overview.by_customer, 'customer costs');
  elements.budgetList.innerHTML = overview.budgets.length ? overview.budgets.map(budget => `<div class="budget-row"><div><strong>${escapeHtml(budget.app)}</strong><span>${money(budget.month_to_date_spend)} of ${money(budget.monthly_limit)}</span></div><b>${budget.percent_used}%</b><i><em style="width:${Math.min(100, Number(budget.percent_used))}%"></em></i></div>`).join('') : '<p class="ai-empty">No app budgets configured.</p>';
  elements.usageCount.textContent = `${state.usage.length} request${state.usage.length === 1 ? '' : 's'}`;
  elements.usageTable.innerHTML = state.usage.length ? state.usage.slice(0, 7).map(item => `<tr><td><span class="resource-name">${escapeHtml(item.app)}</span><span class="resource-type">${escapeHtml(item.customer_name)} · ${escapeHtml(item.end_user)}</span></td><td>${escapeHtml(item.provider)} / ${escapeHtml(item.model)}</td><td>${Number(item.input_tokens + item.output_tokens).toLocaleString()}</td><td class="savings">${money(item.total_cost)}</td></tr>`).join('') : '<tr><td colspan="4" class="empty-state">No attributed AI requests yet.</td></tr>';
}
async function load() { if (!state.principal) return; try { [state.overview, state.usage] = await Promise.all([request('/v1/ai/overview'), request('/v1/ai/usage')]); render(); elements.status.textContent = state.source?.readyState === EventSource.OPEN ? 'Live updates connected' : 'Connected to local API'; } catch (error) { elements.status.textContent = 'API unavailable'; toast(error.message); } }
async function session() { try { state.principal = await request('/v1/session'); elements.authGate.hidden = true; elements.dashboard.hidden = false; profile(); renderAIAccess(); await load(); connect(); } catch (_) { elements.authGate.hidden = false; } }
async function login(event) { event.preventDefault(); const persona = DEMO_PERSONAS[elements.role.value]; const response = await fetch('/v1/auth/demo-login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ tenant_id: elements.tenant.value, role: elements.role.value, user_id: persona.userId }) }); if (!response.ok) return toast('Demo sign-in is unavailable.'); toast('Demo session started.'); await session(); }
async function logout() { try { await request('/v1/auth/logout', { method: 'POST' }); } finally { state.source?.close(); state.source = null; state.principal = null; elements.dashboard.hidden = true; elements.authGate.hidden = false; elements.status.textContent = 'Choose a demo role'; renderPersonaPreview(); toast('Session cleared. Choose another role to continue.'); } }
function connect() { if (state.source || !window.EventSource) return; state.source = new EventSource('/v1/events'); state.source.addEventListener('connected', () => { elements.status.textContent = 'Live updates connected'; }); ['ai.usage_recorded', 'ai.budget_updated', 'ai.preflight_warn', 'ai.preflight_block'].forEach(type => state.source.addEventListener(type, async () => { await load(); })); }
async function preflight(allowFallback = false) {
  if (!state.principal) return;
  const scenario = PREFLIGHT_SCENARIOS[state.preflightScenario];
  elements.preflight.disabled = true;
  try {
    const result = await request('/v1/ai/preflight', {
      method: 'POST',
      body: JSON.stringify({ tenant_id: state.principal.tenant_id, ...scenario, request_id: `sim-${Date.now()}`, allow_fallback: allowFallback }),
    });
    const fallback = result.recommended_fallback;
    const routeButton = fallback && fallback.permitted && !result.routed_to_fallback
      ? `<button class="fallback-button" id="use-fallback">Use ${escapeHtml(fallback.provider)} / ${escapeHtml(fallback.model)}</button>` : '';
    elements.preflightResult.className = `preflight-result decision-${result.decision.toLowerCase()}`;
    elements.preflightResult.innerHTML = `<strong>${escapeHtml(scenario.label)} · ${result.decision} · ${result.routed_to_fallback ? `routed to ${escapeHtml(result.effective_model)}` : result.permitted ? 'request may proceed' : 'request blocked'}</strong><span>${escapeHtml(result.reason)}</span><small>Estimated request cost ${money(result.estimate.total_cost)} · projected app spend ${money(result.projected_month_spend)} · app budget ${money(result.budget?.monthly_limit)}</small>${routeButton}`;
    document.querySelector('#use-fallback')?.addEventListener('click', () => preflight(true));
    await load();
  } catch (error) { toast(error.message); } finally { elements.preflight.disabled = false; }
}
async function runOllamaTest() { if (!state.principal) return; elements.ollamaTest.disabled = true; elements.ollamaResult.className = 'ollama-empty'; elements.ollamaResult.textContent = 'Running local model…'; try { const result = await request('/v1/ai/ollama/generate', { method: 'POST', body: JSON.stringify({ tenant_id: state.principal.tenant_id, app: 'support-assistant', customer: 'acme-corp', end_user: 'jane@acme.com', model: 'llama3.2:3b', prompt: 'Reply with exactly three short words about responsible AI cost control.', max_tokens: 30 }) }); elements.ollamaResult.className = 'ollama-result'; elements.ollamaResult.innerHTML = `<strong>Recorded real Ollama telemetry</strong><span>${escapeHtml(result.response)}</span><small>${result.usage.input_tokens} input · ${result.usage.output_tokens} output tokens · ${result.telemetry.total_duration_seconds}s · ${money(result.usage.total_cost)} runtime cost</small>`; await load(); } catch (error) { elements.ollamaResult.className = 'ollama-error'; elements.ollamaResult.textContent = error.message; } finally { elements.ollamaTest.disabled = false; } }
async function runRentalScenario() { if (!state.principal) return; elements.rentalScenario.disabled = true; elements.rentalResult.className = 'ollama-empty'; elements.rentalResult.textContent = 'Running three measured model steps…'; try { const result = await request('/v1/ai/ollama/scenarios/rental-replay', { method: 'POST', body: JSON.stringify({ tenant_id: state.principal.tenant_id, model: 'llama3.2:3b' }) }); elements.rentalResult.className = 'ollama-result'; elements.rentalResult.innerHTML = `<strong>${escapeHtml(result.profile.label)} · ${money(result.profile.hourly_capacity_cost)}/hour</strong><span>3 iterative steps · ${Number(result.total_tokens).toLocaleString()} measured tokens · ${result.total_duration_seconds}s local runtime</span><small>${money(result.total_cost)} lease-rate replay cost · local runtime is not claimed to equal RTX 4090 performance.</small>`; await load(); } catch (error) { elements.rentalResult.className = 'ollama-error'; elements.rentalResult.textContent = error.message; } finally { elements.rentalScenario.disabled = false; } }
elements.form.addEventListener('submit', login); elements.role.addEventListener('change', renderPersonaPreview); elements.logout.addEventListener('click', logout); elements.preflight.addEventListener('click', () => preflight()); document.querySelectorAll('[data-preflight-scenario]').forEach(button => button.addEventListener('click', () => selectPreflightScenario(button.dataset.preflightScenario))); elements.ollamaTest.addEventListener('click', runOllamaTest); elements.rentalScenario.addEventListener('click', runRentalScenario); renderPersonaPreview(); selectPreflightScenario('allow'); session();

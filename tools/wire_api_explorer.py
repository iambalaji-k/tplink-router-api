import os

SCRIPT = """
<script>
// --- TP-Link Archer AX12 Dynamic API Explorer Client ---
let endpoints = [];
let selectedEndpoint = null;
let currentFilter = 'all';
let allowDestructive = false;
let isPollingPaused = false;

async function init() {
  await fetchStatus();
  await loadEndpoints();
  setupPolling();
  setupUIHandlers();
}

async function fetchStatus() {
  try {
    const res = await fetch('/status');
    if (!res.ok) return;
    const data = await res.json();
    const hostEl = document.getElementById('header-host');
    if (hostEl && data.lan && data.lan.ipaddr) hostEl.textContent = data.lan.ipaddr;
    const stokEl = document.getElementById('header-stok');
    if (stokEl) stokEl.textContent = 'stok: verified';
  } catch (err) {
    console.debug('Status check pending router connection:', err);
  }
}

function setupPolling() {
  setInterval(() => {
    if (!isPollingPaused) fetchStatus();
  }, 8000);
}

async function loadEndpoints() {
  try {
    const res = await fetch('/api/inventory/endpoints');
    if (!res.ok) throw new Error('Failed to load inventory: ' + res.status);
    endpoints = await res.json();
    renderModuleTree();
    
    // Select first answered endpoint by default
    const first = endpoints.find(e => e.status === 'answered') || endpoints[0];
    if (first) selectEndpoint(first);
  } catch (err) {
    console.error('Inventory error:', err);
    const container = document.getElementById('module-tree');
    if (container) container.innerHTML = '<div class=\"p-3 text-error\">Could not load API inventory from server.</div>';
  }
}

function renderModuleTree() {
  const container = document.getElementById('module-tree');
  if (!container) return;

  const search = (document.getElementById('filter-search')?.value || '').toLowerCase().trim();
  
  // Filter endpoints
  const filtered = endpoints.filter(ep => {
    const matchesFilter = currentFilter === 'all' || ep.status === currentFilter;
    const matchesSearch = !search || ep.url.toLowerCase().includes(search) || ep.module.toLowerCase().includes(search) || ep.form.toLowerCase().includes(search);
    return matchesFilter && matchesSearch;
  });

  // Group by module
  const modules = {};
  filtered.forEach(ep => {
    if (!modules[ep.module]) modules[ep.module] = [];
    modules[ep.module].push(ep);
  });

  container.innerHTML = '';
  const moduleKeys = Object.keys(modules).sort();

  if (moduleKeys.length === 0) {
    container.innerHTML = '<div class=\"p-4 text-outline text-center\">No endpoints match current filter.</div>';
    return;
  }

  moduleKeys.forEach((mod, idx) => {
    const modForms = modules[mod];
    const isExpanded = idx === 0 || moduleKeys.length <= 3 || !!search;
    
    const modDiv = document.createElement('div');
    modDiv.className = 'rounded border border-outline-variant/60 bg-surface-container-lowest/40 overflow-hidden mb-1.5';
    
    const modHeader = document.createElement('div');
    modHeader.className = 'flex items-center justify-between px-2.5 py-1.5 bg-surface-container hover:bg-surface-container-high cursor-pointer transition-colors';
    modHeader.innerHTML = `
      <div class="flex items-center gap-1.5 text-primary">
        <span class="material-symbols-outlined text-[16px]">${isExpanded ? 'expand_more' : 'chevron_right'}</span>
        <span class="font-semibold">${mod}</span>
      </div>
      <span class="text-code-sm font-code-sm text-outline-variant">${modForms.length} forms</span>
    `;

    const formsDiv = document.createElement('div');
    formsDiv.className = 'py-1 space-y-0.5 border-t border-outline-variant/40 bg-surface-container-low ' + (isExpanded ? '' : 'hidden');

    modForms.forEach(ep => {
      const isSelected = selectedEndpoint && selectedEndpoint.url === ep.url;
      const formA = document.createElement('a');
      formA.href = '#';
      formA.className = 'flex items-center justify-between px-3 py-1.5 transition-colors ' + 
        (isSelected ? 'bg-surface-container-highest border-l-2 border-primary-container text-on-surface font-medium' : 'text-on-surface-variant hover:bg-surface-container');

      const dotColor = ep.status === 'answered' ? 'bg-secondary' : 
                       ep.status === 'not-implemented' ? 'bg-purple-400' : 
                       ep.status.includes('refused') ? 'bg-error' : 'bg-tertiary';

      formA.innerHTML = `
        <div class="flex items-center gap-2 truncate">
          <span class="w-2 h-2 rounded-full ${dotColor} inline-block shrink-0"></span>
          <span class="truncate ${isSelected ? 'text-primary-fixed' : ''}">${ep.form}</span>
        </div>
        <span class="text-[10px] text-outline font-mono shrink-0 ml-1">${ep.status === 'answered' ? 'OK' : ep.status}</span>
      `;

      formA.addEventListener('click', (e) => {
        e.preventDefault();
        selectEndpoint(ep);
      });

      formsDiv.appendChild(formA);
    });

    modHeader.addEventListener('click', () => {
      const isHidden = formsDiv.classList.toggle('hidden');
      const icon = modHeader.querySelector('.material-symbols-outlined');
      if (icon) icon.textContent = isHidden ? 'chevron_right' : 'expand_more';
    });

    modDiv.appendChild(modHeader);
    modDiv.appendChild(formsDiv);
    container.appendChild(modDiv);
  });
}

function selectEndpoint(ep) {
  selectedEndpoint = ep;

  // Title & Badges
  const titleEl = document.getElementById('endpoint-title');
  if (titleEl) titleEl.textContent = ep.url;

  const badgesEl = document.getElementById('endpoint-badges');
  if (badgesEl) {
    const statusClass = ep.status === 'answered' ? 'bg-secondary/15 text-secondary border-secondary/30' : 'bg-purple-500/15 text-purple-400 border-purple-500/30';
    badgesEl.innerHTML = `
      <span class="px-2 py-0.5 rounded text-code-sm font-code-sm ${statusClass} border flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full ${ep.status === 'answered' ? 'bg-secondary' : 'bg-purple-400'}"></span> [${ep.status.toUpperCase()}]
      </span>
      <span class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-primary/15 text-primary border border-primary/30">[ROW_FORM: ${ep.is_row_form ? 'TRUE' : 'FALSE'}]</span>
      <span class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-teal-500/15 text-teal-300 border border-teal-500/30">[BUNDLE: ${ep.in_bundles ? 'YES' : 'EXT'}]</span>
    `;
  }

  // Row fields
  const fieldsEl = document.getElementById('endpoint-row-fields');
  if (fieldsEl) {
    if (ep.row_fields && ep.row_fields.length > 0) {
      fieldsEl.innerHTML = '<span class="text-label-caps font-label-caps text-outline uppercase tracking-wider text-[10px]">Row Fields:</span>' +
        ep.row_fields.map(f => `<span class="px-2 py-0.5 rounded bg-surface-container-highest text-primary-fixed text-code-sm font-code-sm border border-outline-variant">${f}</span>`).join(' ');
    } else {
      fieldsEl.innerHTML = '<span class="text-label-caps font-label-caps text-outline uppercase tracking-wider text-[10px]">Settings Form</span>';
    }
  }

  // Operation selector
  const opSelect = document.getElementById('operation-select');
  if (opSelect) {
    opSelect.innerHTML = '';
    const ops = ep.ui_operations.length > 0 ? ep.ui_operations : ['read', 'write'];
    ops.forEach(op => {
      const opt = document.createElement('option');
      opt.value = op;
      opt.textContent = `${op} (${op === 'read' ? 'Inspect State' : op === 'write' ? 'Commit' : op})`;
      opSelect.appendChild(opt);
    });
  }

  // Resolved URL preview
  const urlEl = document.getElementById('resolved-url');
  if (urlEl) urlEl.textContent = `POST /cgi-bin/luci/;stok=<stok>/${ep.url}`;

  // Reset payload editor
  updatePayloadEditor();
  renderModuleTree();
}

function updatePayloadEditor() {
  const opSelect = document.getElementById('operation-select');
  const editor = document.getElementById('payload-editor');
  if (editor && opSelect) {
    editor.value = JSON.stringify({ operation: opSelect.value }, null, 2);
  }
}

async function executeRequest() {
  if (!selectedEndpoint) return;

  const btn = document.getElementById('execute-btn');
  const statusBadge = document.getElementById('response-status');
  const latencyBadge = document.getElementById('response-latency');
  const responseJsonEl = document.getElementById('response-json');
  const opSelect = document.getElementById('operation-select');
  const editor = document.getElementById('payload-editor');

  let params = {};
  try {
    params = JSON.parse(editor.value || '{}');
  } catch (err) {
    alert('Invalid JSON in payload editor: ' + err.message);
    return;
  }

  const operation = opSelect ? opSelect.value : (params.operation || 'read');
  delete params.operation; // sent separately

  // Destructive check
  const isDestructive = selectedEndpoint.form.includes('reboot') || selectedEndpoint.form.includes('reset') || operation === 'write' || operation === 'remove';
  if (isDestructive && !allowDestructive && operation !== 'read') {
    alert('Safety Warning: Please enable "Allow Destructive Operations" before committing writes or reboots.');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.classList.add('opacity-60');
  }

  const startTime = performance.now();
  try {
    const res = await fetch('/api/raw', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        module: selectedEndpoint.module,
        form: selectedEndpoint.form,
        operation: operation,
        params: params
      })
    });

    const elapsed = Math.round(performance.now() - startTime);
    if (latencyBadge) latencyBadge.textContent = `${elapsed}ms`;

    const data = await res.json();

    if (statusBadge) {
      statusBadge.textContent = `${res.status} ${res.statusText || 'OK'}`;
      statusBadge.className = res.ok ? 
        'px-2 py-0.5 rounded text-code-sm font-code-sm bg-secondary/15 text-secondary border border-secondary/30' :
        'px-2 py-0.5 rounded text-code-sm font-code-sm bg-error/15 text-error border border-error/30';
    }

    if (responseJsonEl) {
      responseJsonEl.textContent = JSON.stringify(data, null, 2);
    }
  } catch (err) {
    const elapsed = Math.round(performance.now() - startTime);
    if (latencyBadge) latencyBadge.textContent = `${elapsed}ms`;
    if (statusBadge) {
      statusBadge.textContent = 'Network Error';
      statusBadge.className = 'px-2 py-0.5 rounded text-code-sm font-code-sm bg-error/15 text-error border border-error/30';
    }
    if (responseJsonEl) {
      responseJsonEl.textContent = JSON.stringify({ error: err.message }, null, 2);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('opacity-60');
    }
  }
}

function setupUIHandlers() {
  // Search
  const searchEl = document.getElementById('filter-search');
  if (searchEl) {
    searchEl.addEventListener('input', () => renderModuleTree());
  }
  const clearSearchBtn = document.getElementById('clear-search-btn');
  if (clearSearchBtn && searchEl) {
    clearSearchBtn.addEventListener('click', () => {
      searchEl.value = '';
      renderModuleTree();
    });
  }

  // Filter pills
  document.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      currentFilter = btn.getAttribute('data-filter');
      document.querySelectorAll('[data-filter]').forEach(b => {
        b.className = 'px-2 py-0.5 rounded text-code-sm font-code-sm border border-outline-variant hover:bg-surface-bright transition-colors text-on-surface-variant';
      });
      btn.className = 'px-2 py-0.5 rounded text-code-sm font-code-sm bg-primary text-on-primary font-semibold border-transparent';
      renderModuleTree();
    });
  });

  // Operation change -> updates payload editor
  const opSelect = document.getElementById('operation-select');
  if (opSelect) {
    opSelect.addEventListener('change', updatePayloadEditor);
  }

  // Execute button
  const execBtn = document.getElementById('execute-btn');
  if (execBtn) {
    execBtn.addEventListener('click', executeRequest);
  }

  // Reset button
  const resetBtn = document.getElementById('reset-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', updatePayloadEditor);
  }

  // Destructive toggle
  const destToggle = document.getElementById('destructive-toggle');
  if (destToggle) {
    destToggle.addEventListener('click', () => {
      allowDestructive = !allowDestructive;
      const thumb = destToggle.querySelector('div');
      if (allowDestructive) {
        destToggle.classList.remove('bg-surface-variant');
        destToggle.classList.add('bg-error');
        if (thumb) thumb.classList.add('translate-x-5');
      } else {
        destToggle.classList.remove('bg-error');
        destToggle.classList.add('bg-surface-variant');
        if (thumb) thumb.classList.remove('translate-x-5');
      }
    });
  }

  // Copy JSON
  const copyBtn = document.getElementById('copy-json-btn');
  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const code = document.getElementById('response-json')?.textContent || '';
      navigator.clipboard.writeText(code).then(() => {
        copyBtn.innerText = 'Copied!';
        setTimeout(() => copyBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">content_copy</span><span>Copy JSON</span>', 1500);
      });
    });
  }

  // Copy Target URL
  const copyUrlBtn = document.getElementById('copy-url-btn');
  if (copyUrlBtn) {
    copyUrlBtn.addEventListener('click', () => {
      const urlText = document.getElementById('resolved-url')?.textContent || '';
      navigator.clipboard.writeText(urlText);
    });
  }

  // Polling toggle
  const pollBtn = document.getElementById('polling-btn');
  if (pollBtn) {
    pollBtn.addEventListener('click', () => {
      isPollingPaused = !isPollingPaused;
      const text = pollBtn.querySelector('span:not(.material-symbols-outlined)');
      const icon = pollBtn.querySelector('.material-symbols-outlined');
      if (isPollingPaused) {
        text.textContent = 'Resume Polling';
        icon.textContent = 'play_circle';
      } else {
        text.textContent = 'Pause Polling';
        icon.textContent = 'sync';
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', init);
</script>
"""

with open('ui/stitch_api_explorer.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace static elements with ID-tagged elements
html = html.replace('192.168.0.1</span>', '<span id="header-host">192.168.0.1</span>')
html = html.replace('stok: active</span>', '<span id="header-stok">stok: active</span>')

# Search input and clear button
html = html.replace(
    'placeholder="Filter 226 endpoints or 50 modules..." type="text" value=""/>',
    'id="filter-search" placeholder="Filter 226 endpoints or 50 modules..." type="text" value=""/>'
)
html = html.replace(
    'title="Clear filter">',
    'id="clear-search-btn" title="Clear filter">'
)

# Filter pills data attributes
html = html.replace('<button class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-primary text-on-primary font-semibold">All (226)</button>',
                    '<button data-filter="all" class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-primary text-on-primary font-semibold">All (226)</button>')
html = html.replace('<button class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-secondary/15 text-secondary border border-secondary/30 hover:bg-secondary/25 transition-colors">Answered (179)</button>',
                    '<button data-filter="answered" class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-secondary/15 text-secondary border border-secondary/30 hover:bg-secondary/25 transition-colors">Answered (179)</button>')
html = html.replace('<button class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-purple-500/15 text-purple-400 border border-purple-500/30 hover:bg-purple-500/25 transition-colors">Not Implemented (18)</button>',
                    '<button data-filter="not-implemented" class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-purple-500/15 text-purple-400 border border-purple-500/30 hover:bg-purple-500/25 transition-colors">Not Implemented (18)</button>')
html = html.replace('<button class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-tertiary/15 text-tertiary border border-tertiary/30 hover:bg-tertiary/25 transition-colors">Needs Params (4)</button>',
                    '<button data-filter="exists-needs-parameters" class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-tertiary/15 text-tertiary border border-tertiary/30 hover:bg-tertiary/25 transition-colors">Needs Params (4)</button>')
html = html.replace('<button class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-surface-variant text-on-surface-variant border border-outline-variant hover:bg-surface-bright transition-colors">Action (13)</button>',
                    '<button data-filter="not-probed" class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-surface-variant text-on-surface-variant border border-outline-variant hover:bg-surface-bright transition-colors">Action (13)</button>')

# Module tree list container ID
html = html.replace(
    '<div class="flex-1 overflow-y-auto custom-scroll p-space-sm space-y-1 font-code-sm">',
    '<div id="module-tree" class="flex-1 overflow-y-auto custom-scroll p-space-sm space-y-1 font-code-sm">'
)

# Endpoint title & badges & row fields
html = html.replace(
    '<span class="text-headline-md font-code-lg text-on-surface font-semibold">admin/wireless?form=wireless_2g</span>',
    '<span id="endpoint-title" class="text-headline-md font-code-lg text-on-surface font-semibold">admin/wireless?form=wireless_2g</span>'
)
html = html.replace(
    '<span class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-secondary/15 text-secondary border border-secondary/30 flex items-center gap-1">\n<span class="w-1.5 h-1.5 rounded-full bg-secondary"></span> [ANSWERED]\n                </span>',
    '<div id="endpoint-badges" class="flex items-center gap-2 flex-wrap"><span class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-secondary/15 text-secondary border border-secondary/30 flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-secondary"></span> [ANSWERED]</span></div>'
)
html = html.replace(
    '<div class="mt-space-sm flex items-center gap-space-xs flex-wrap">',
    '<div id="endpoint-row-fields" class="mt-space-sm flex items-center gap-space-xs flex-wrap">'
)

# Operation selector
html = html.replace(
    '<select class="w-full h-10 bg-surface-container-lowest text-on-surface text-code-md font-code-md rounded border border-outline-variant focus:border-primary-container focus:ring-1 focus:ring-primary-container">',
    '<select id="operation-select" class="w-full h-10 bg-surface-container-lowest text-on-surface text-code-md font-code-md rounded border border-outline-variant focus:border-primary-container focus:ring-1 focus:ring-primary-container">'
)

# Target URL
html = html.replace(
    '<span class="text-primary truncate">POST /cgi-bin/luci/;stok=ab12cd.../admin/wireless?form=wireless_2g</span>',
    '<span id="resolved-url" class="text-primary truncate font-mono">POST /cgi-bin/luci/;stok=ab12cd.../admin/wireless?form=wireless_2g</span>'
)
html = html.replace('title="Copy Target URL"', 'id="copy-url-btn" title="Copy Target URL"')

# Replace static pre with editable textarea for JSON payload
editor_static = '<pre class="text-on-surface leading-5 font-mono"><span class="text-outline">{</span>\n  <span class="text-primary">"operation"</span><span class="text-outline">:</span> <span class="text-secondary">"read"</span>\n<span class="text-outline">}</span></pre>'
editor_dynamic = '<textarea id="payload-editor" class="w-full h-24 bg-transparent text-primary font-mono text-code-md focus:outline-none resize-none">{\n  "operation": "read"\n}</textarea>'
html = html.replace(editor_static, editor_dynamic)

# Safety toggle ID
html = html.replace(
    '<div class="w-11 h-6 bg-surface-variant rounded-full relative cursor-pointer border border-outline-variant flex items-center px-0.5">',
    '<div id="destructive-toggle" class="w-11 h-6 bg-surface-variant rounded-full relative cursor-pointer border border-outline-variant flex items-center px-0.5 transition-colors">'
)

# Execute and Reset buttons
html = html.replace(
    '<button class="flex-1 flex items-center justify-center gap-2 py-2.5 px-space-md bg-primary-container text-on-primary-container font-code-lg font-semibold rounded-lg cyan-glow-button active:scale-95 transition-all">',
    '<button id="execute-btn" class="flex-1 flex items-center justify-center gap-2 py-2.5 px-space-md bg-primary-container text-on-primary-container font-code-lg font-semibold rounded-lg cyan-glow-button active:scale-95 transition-all">'
)
html = html.replace(
    '<button class="py-2.5 px-space-md bg-surface-container hover:bg-surface-bright text-on-surface rounded-lg border border-outline-variant font-code-md text-code-md transition-colors active:scale-95">\n                  Reset Form\n                </button>',
    '<button id="reset-btn" class="py-2.5 px-space-md bg-surface-container hover:bg-surface-bright text-on-surface rounded-lg border border-outline-variant font-code-md text-code-md transition-colors active:scale-95">Reset Form</button>'
)

# Response status & latency
html = html.replace(
    '<span class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-secondary/15 text-secondary border border-secondary/30">200 OK</span>',
    '<span id="response-status" class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-secondary/15 text-secondary border border-secondary/30">200 OK</span>'
)
html = html.replace(
    '<span class="text-code-sm font-code-sm text-outline">34ms</span>',
    '<span id="response-latency" class="text-code-sm font-code-sm text-secondary font-mono">--</span>'
)

# Response JSON pre
pre_idx = html.find('<pre class="text-code-sm font-code-sm font-mono leading-5 overflow-x-auto text-on-surface">')
if pre_idx != -1:
    end_pre = html.find('</pre>', pre_idx)
    html = html[:pre_idx] + '<pre id="response-json" class="text-code-sm font-code-sm font-mono leading-5 overflow-x-auto text-on-surface p-2 bg-surface-container-lowest/50 rounded">' + '{\n  "status": "Select an endpoint and click Execute Request"\n}' + html[end_pre:]

# Copy JSON button
html = html.replace(
    '<button class="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container hover:bg-surface-bright text-on-surface text-code-sm font-code-sm border border-outline-variant transition-colors active:scale-95">\n<span class="material-symbols-outlined text-[16px]" data-icon="content_copy">content_copy</span>\n<span>Copy JSON</span>\n</button>',
    '<button id="copy-json-btn" class="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container hover:bg-surface-bright text-on-surface text-code-sm font-code-sm border border-outline-variant transition-colors active:scale-95"><span class="material-symbols-outlined text-[16px]">content_copy</span><span>Copy JSON</span></button>'
)

# Append SCRIPT right before </body>
html = html.replace('</body>', SCRIPT + '\n</body>')

with open('ui/stitch_api_explorer.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Successfully wired ui/stitch_api_explorer.html to live backend!')

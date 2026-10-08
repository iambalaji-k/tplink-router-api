"""Tighten layout, remove excessive gaps, eliminate max-w-7xl, and wire full dynamic counters in stitch_preview.html."""

import re

def fix_preview():
    with open('ui/stitch_preview.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. Main container: remove max-w-7xl constraint and tighten gaps
    html = re.sub(
        r'<main class="md:ml-64 flex-1 p-4 md:p-space-xl flex flex-col gap-space-xl max-w-7xl">',
        '<main class="md:ml-64 flex-1 p-4 md:p-6 lg:p-7 flex flex-col gap-5 w-full">',
        html
    )

    # 2. Greeting banner: compact padding and spacing
    html = re.sub(
        r'<div class="flex flex-col md:flex-row md:items-center justify-between gap-space-md bg-surface-container border border-outline-variant p-space-lg rounded-xl shadow-lg relative overflow-hidden backdrop-blur-md">',
        '<div class="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-surface-container border border-outline-variant p-4 rounded-xl shadow-lg relative overflow-hidden backdrop-blur-md">',
        html
    )

    # 3. Section gaps: tighten gap-space-md (16px) to gap-3.5 or gap-4
    html = re.sub(r'<section class="flex flex-col gap-space-md" id="overview">',
                  '<section class="flex flex-col gap-3.5" id="overview">', html)
    html = re.sub(r'<div class="grid grid-cols-1 lg:grid-cols-12 gap-space-md">',
                  '<div class="grid grid-cols-1 lg:grid-cols-12 gap-4">', html)
    html = re.sub(r'<section class="flex flex-col gap-space-md" id="wireless">',
                  '<section class="flex flex-col gap-3.5" id="wireless">', html)
    html = re.sub(r'<div class="grid grid-cols-1 md:grid-cols-2 gap-space-md">',
                  '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">', html)
    html = re.sub(r'<section class="flex flex-col gap-space-md" id="clients">',
                  '<section class="flex flex-col gap-3.5" id="clients">', html)

    # 4. Make Wi-Fi card client count dynamic
    html = re.sub(
        r'<span class="text-outline">Connected Wireless Clients:</span>\s*<span class="text-primary font-bold">5 Devices active</span>',
        '<span class="text-outline">Connected Wireless Clients:</span> <span id="wifi-2g-clients-count" class="text-primary font-bold font-mono">--</span>',
        html
    )
    html = re.sub(
        r'<span class="text-outline">Connected Wireless Clients:</span>\s*<span class="text-primary font-bold">9 Devices active \(Wi-Fi 6\)</span>',
        '<span class="text-outline">Connected Wireless Clients:</span> <span id="wifi-5g-clients-count" class="text-primary font-bold font-mono">--</span>',
        html
    )

    # 5. Make client filter buttons dynamic and interactive
    old_filters = r'<div class="flex items-center gap-1 bg-surface-container-low p-1 rounded border border-outline-variant">[\s\S]*?</div>\s*<button class="h-9 px-3 bg-surface-container-low border border-outline-variant rounded hover:text-primary transition-colors flex items-center" onclick="flashSync\(this\)"'
    new_filters = '''<div class="flex items-center gap-1 bg-surface-container-low p-1 rounded border border-outline-variant">
<button onclick="setClientFilter('all')" id="filter-all-btn" class="px-2.5 py-1 rounded text-code-sm font-code-sm bg-surface-container-highest text-primary font-semibold">All: <span class="live-clients-count">--</span></button>
<button onclick="setClientFilter('5G')" id="filter-5g-btn" class="px-2.5 py-1 rounded text-code-sm font-code-sm text-outline hover:text-on-surface">5G: <span id="count-5g">--</span></button>
<button onclick="setClientFilter('2.4G')" id="filter-2g-btn" class="px-2.5 py-1 rounded text-code-sm font-code-sm text-outline hover:text-on-surface">2.4G: <span id="count-2g">--</span></button>
<button onclick="setClientFilter('wired')" id="filter-lan-btn" class="px-2.5 py-1 rounded text-code-sm font-code-sm text-outline hover:text-on-surface">LAN: <span id="count-lan">--</span></button>
</div>
<button class="h-9 px-3 bg-surface-container-low border border-outline-variant rounded hover:text-primary transition-colors flex items-center" onclick="updateLiveVitals(); flashSync(this)"'''
    html = re.sub(old_filters, new_filters, html)

    # Search input id & handler
    html = re.sub(
        r'<input class="h-9 pl-8 pr-3 text-code-sm font-code-sm bg-surface-container-lowest border border-outline-variant rounded focus:border-primary focus:ring-0 text-on-surface placeholder:text-outline w-52 sm:w-64" placeholder="Filter hostname or MAC\.\.\." type="text"/>',
        '<input id="client-search-input" oninput="applyClientFilters()" class="h-9 pl-8 pr-3 text-code-sm font-code-sm bg-surface-container-lowest border border-outline-variant rounded focus:border-primary focus:ring-0 text-on-surface placeholder:text-outline w-52 sm:w-64" placeholder="Filter hostname or MAC..." type="text"/>',
        html
    )

    # 6. Update JavaScript for live clients caching, searching, filtering, and SSID binding
    old_script_block = r'<script>\s*// --- TP-Link Archer AX12 Live Overview Telemetry Client ---[\s\S]*?</script>\s*</body>'

    new_script_block = '''<script>
// --- TP-Link Archer AX12 Live Overview Telemetry Client ---
let isOverviewPollingPaused = false;
let globalClientsList = [];
let activeClientFilter = 'all';

async function updateLiveVitals() {
  if (isOverviewPollingPaused) return;
  try {
    const res = await fetch('/status');
    if (!res.ok) return;
    const data = await res.json();
    
    // 1. CPU Usage
    if (data.system && typeof data.system.cpu_usage === 'number') {
      const cpuRatio = data.system.cpu_usage;
      const cpuPct = (cpuRatio * 100).toFixed(1);
      const textEl = document.getElementById('cpu-gauge-text');
      const circleEl = document.getElementById('cpu-gauge-circle');
      if (textEl) textEl.textContent = cpuPct + '%';
      if (circleEl) {
        const offset = 251.2 * (1 - cpuRatio);
        circleEl.style.strokeDashoffset = offset;
      }
    }

    // 2. RAM Usage
    if (data.system && typeof data.system.mem_usage === 'number') {
      const memRatio = data.system.mem_usage;
      const memPct = (memRatio * 100).toFixed(1);
      const textEl = document.getElementById('mem-gauge-text');
      const circleEl = document.getElementById('mem-gauge-circle');
      if (textEl) textEl.textContent = memPct + '%';
      if (circleEl) {
        const offset = 251.2 * (1 - memRatio);
        circleEl.style.strokeDashoffset = offset;
      }
    }

    // 3. WAN Info
    if (data.wan) {
      const wanIpEl = document.getElementById('wan-ipv4');
      if (wanIpEl && data.wan.ipaddr) wanIpEl.textContent = data.wan.ipaddr;
      const wanGwEl = document.getElementById('wan-gateway');
      if (wanGwEl && data.wan.gateway) wanGwEl.textContent = data.wan.gateway;
      const wanDnsEl = document.getElementById('wan-dns');
      if (wanDnsEl && data.wan.pridns) wanDnsEl.textContent = data.wan.pridns;
      
      // Uptime
      if (typeof data.wan.uptime === 'number') {
        const s = data.wan.uptime;
        const d = Math.floor(s / 86400);
        const h = Math.floor((s % 86400) / 3600);
        const m = Math.floor((s % 3600) / 60);
        const uptimeEl = document.getElementById('system-uptime');
        if (uptimeEl) uptimeEl.textContent = `${d}d ${h}h ${m}m`;
      }
    }

    // 4. Wireless SSIDs
    if (data.wireless_2g && data.wireless_2g.ssid) {
      const s2g = document.getElementById('wifi-2g-ssid');
      if (s2g) s2g.textContent = data.wireless_2g.ssid;
    }
    if (data.wireless_5g && data.wireless_5g.ssid) {
      const s5g = document.getElementById('wifi-5g-ssid');
      if (s5g) s5g.textContent = data.wireless_5g.ssid;
    }

    // 5. Clients Table & Counts
    let clientsList = Array.isArray(data.clients) ? data.clients : [];
    if (clientsList.length === 0) {
      try {
        const cRes = await fetch('/clients');
        if (cRes.ok) {
          const fetchedClients = await cRes.json();
          if (Array.isArray(fetchedClients) && fetchedClients.length > 0) {
            clientsList = fetchedClients;
          }
        }
      } catch (e) {
        console.debug('Secondary /clients fetch error:', e);
      }
    }

    globalClientsList = clientsList;
    updateClientCounts();
    applyClientFilters();

    // 6. Live Badge
    const pollBadge = document.getElementById('telemetry-status-badge');
    if (pollBadge) {
      pollBadge.textContent = 'Live Connected • ' + new Date().toLocaleTimeString();
      pollBadge.className = 'text-code-sm font-code-sm text-secondary font-mono';
    }
  } catch (err) {
    console.debug('Overview poll pending:', err);
    const pollBadge = document.getElementById('telemetry-status-badge');
    if (pollBadge) {
      pollBadge.textContent = 'Connecting to router...';
      pollBadge.className = 'text-code-sm font-code-sm text-outline font-mono';
    }
  }
}

function updateClientCounts() {
  const countEls = document.querySelectorAll('.live-clients-count');
  countEls.forEach(el => el.textContent = globalClientsList.length);

  const count5g = globalClientsList.filter(c => c.wire_type === '5G').length;
  const count2g = globalClientsList.filter(c => c.wire_type === '2.4G' || c.wire_type === 'wireless').length;
  const countLan = globalClientsList.filter(c => c.wire_type === 'wired').length;

  const el5g = document.getElementById('count-5g');
  if (el5g) el5g.textContent = count5g;
  const el2g = document.getElementById('count-2g');
  if (el2g) el2g.textContent = count2g;
  const elLan = document.getElementById('count-lan');
  if (elLan) elLan.textContent = countLan;

  const wifi2gCountEl = document.getElementById('wifi-2g-clients-count');
  if (wifi2gCountEl) wifi2gCountEl.textContent = `${count2g} Devices active`;
  const wifi5gCountEl = document.getElementById('wifi-5g-clients-count');
  if (wifi5gCountEl) wifi5gCountEl.textContent = `${count5g} Devices active (Wi-Fi 6)`;

  const footerCount = document.getElementById('live-devices-footer-count');
  if (footerCount) footerCount.textContent = `Showing ${globalClientsList.length} active connected devices`;
}

function setClientFilter(filter) {
  activeClientFilter = filter;
  ['all', '5g', '2g', 'lan'].forEach(k => {
    const btn = document.getElementById(`filter-${k}-btn`);
    if (btn) {
      if ((filter === 'all' && k === 'all') || (filter.toLowerCase() === k)) {
        btn.className = 'px-2.5 py-1 rounded text-code-sm font-code-sm bg-surface-container-highest text-primary font-semibold';
      } else {
        btn.className = 'px-2.5 py-1 rounded text-code-sm font-code-sm text-outline hover:text-on-surface';
      }
    }
  });
  applyClientFilters();
}

function applyClientFilters() {
  const searchInput = document.getElementById('client-search-input');
  const q = searchInput ? searchInput.value.trim().toLowerCase() : '';
  const tbody = document.getElementById('live-devices-tbody');
  if (!tbody) return;

  let filtered = globalClientsList.filter(c => {
    const matchesQuery = !q || (c.hostname && c.hostname.toLowerCase().includes(q)) || (c.ipaddr && c.ipaddr.includes(q)) || (c.macaddr && c.macaddr.toLowerCase().includes(q));
    if (!matchesQuery) return false;
    if (activeClientFilter === 'all') return true;
    if (activeClientFilter === '5G') return c.wire_type === '5G';
    if (activeClientFilter === '2.4G') return c.wire_type === '2.4G' || c.wire_type === 'wireless';
    if (activeClientFilter === 'wired') return c.wire_type === 'wired';
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-outline font-mono">No devices matching current filter.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(c => {
    const wireBadge = c.wire_type === 'wired' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-secondary/20 text-secondary font-bold border border-secondary/40 font-mono">Wired Ethernet</span>' :
                      c.wire_type === '5G' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-primary/20 text-primary font-bold border border-primary/40 font-mono">5 GHz Wi-Fi 6</span>' :
                      '<span class="px-2 py-0.5 rounded text-[10px] bg-surface-container-highest text-tertiary font-bold border border-outline-variant font-mono">2.4 GHz</span>';
    const icon = c.wire_type === 'wired' ? 'lan' : 'devices';
    return `
      <tr class="hover:bg-surface-container/60 transition-colors">
        <td class="py-3 px-4">
          <div class="flex items-center gap-2.5">
            <span class="material-symbols-outlined text-primary text-lg" data-icon="${icon}">${icon}</span>
            <span class="font-semibold text-on-surface">${c.hostname || '&lt;unknown&gt;'}</span>
          </div>
        </td>
        <td class="py-3 px-4 text-primary font-medium font-mono">${c.ipaddr || '--'}</td>
        <td class="py-3 px-4 text-outline font-mono">${c.macaddr || '--'}</td>
        <td class="py-3 px-4">${wireBadge}</td>
        <td class="py-3 px-4 text-secondary font-mono">Active Link</td>
        <td class="py-3 px-4 text-right">
          <button onclick="blockDevice('${c.macaddr}')" class="px-2.5 py-1 rounded border border-error/50 text-error hover:bg-error-container/20 text-[11px] font-semibold transition-colors active:scale-95 font-mono">Block</button>
        </td>
      </tr>
    `;
  }).join('');
}

// Initial fetch & interval
document.addEventListener('DOMContentLoaded', () => {
  updateLiveVitals();
  setInterval(updateLiveVitals, 3000);
  
  // Pause Polling Button
  const pollBtn = document.getElementById('polling-btn');
  if (pollBtn) {
    pollBtn.addEventListener('click', () => {
      isOverviewPollingPaused = !isOverviewPollingPaused;
      const text = pollBtn.querySelector('span:not(.material-symbols-outlined)');
      const icon = pollBtn.querySelector('.material-symbols-outlined');
      if (isOverviewPollingPaused) {
        if (text) text.textContent = 'Resume Polling';
        if (icon) {
          icon.textContent = 'play_circle';
          icon.classList.remove('text-secondary');
          icon.classList.add('text-tertiary');
        }
      } else {
        if (text) text.textContent = 'Pause Polling';
        if (icon) {
          icon.textContent = 'sync';
          icon.classList.remove('text-tertiary');
          icon.classList.add('text-secondary');
        }
        updateLiveVitals();
      }
    });
  }

  // Reboot confirmation
  const rebootBtns = document.querySelectorAll('button:has([data-icon="restart_alt"])');
  rebootBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
      if (confirm('Warning: Are you sure you want to REBOOT the Archer AX12 router? This will drop all active connections.')) {
        try {
          btn.disabled = true;
          const res = await fetch('/reboot', { method: 'POST' });
          const json = await res.json();
          alert('Reboot command sent to router: ' + JSON.stringify(json));
        } catch (err) {
          alert('Error sending reboot: ' + err.message);
        } finally {
          btn.disabled = false;
        }
      }
    });
  });
});

async function blockDevice(mac) {
  if (!confirm('Block device ' + mac + ' via Access Control?')) return;
  try {
    const res = await fetch('/access-control/block', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ macaddr: mac })
    });
    const d = await res.json();
    alert('Device blocked: ' + JSON.stringify(d));
    updateLiveVitals();
  } catch(e) {
    alert('Block error: ' + e.message);
  }
}
</script>
</body>'''

    html = re.sub(old_script_block, new_script_block, html)

    with open('ui/stitch_preview.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_preview.html layout tightened, max-w-7xl removed, dynamic filters wired.")

if __name__ == '__main__':
    fix_preview()

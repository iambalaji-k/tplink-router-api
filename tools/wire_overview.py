import os

SCRIPT = """
<script>
// --- TP-Link Archer AX12 Live Overview Telemetry Client ---
let isOverviewPollingPaused = false;

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

    // 4. Clients Count
    if (Array.isArray(data.clients)) {
      const countEls = document.querySelectorAll('.live-clients-count');
      countEls.forEach(el => el.textContent = data.clients.length);
    }

    // 5. Live Badge
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

// Initial fetch & interval
document.addEventListener('DOMContentLoaded', () => {
  updateLiveVitals();
  setInterval(updateLiveVitals, 3000); // Poll every 3 seconds for live responsiveness
  
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
</script>
"""

with open('ui/stitch_preview.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Add IDs to CPU gauge
html = html.replace(
    '<circle class="gauge-circle drop-shadow-[0_0_8px_rgba(0,167,225,0.6)]" cx="50" cy="50" fill="none" r="40" stroke="#00A7E1" stroke-dasharray="251.2" stroke-dashoffset="215.5" stroke-linecap="round" stroke-width="8"></circle>',
    '<circle id="cpu-gauge-circle" class="gauge-circle drop-shadow-[0_0_8px_rgba(0,167,225,0.6)] transition-all duration-700" cx="50" cy="50" fill="none" r="40" stroke="#00A7E1" stroke-dasharray="251.2" stroke-dashoffset="215.5" stroke-linecap="round" stroke-width="8"></circle>'
)
html = html.replace(
    '<span class="text-code-lg font-code-lg font-bold text-on-surface">14.2%</span>',
    '<span id="cpu-gauge-text" class="text-code-lg font-code-lg font-bold text-on-surface">--%</span>'
)

# Add IDs to RAM gauge
html = html.replace(
    '<circle class="gauge-circle drop-shadow-[0_0_8px_rgba(78,222,163,0.5)]" cx="50" cy="50" fill="none" r="40" stroke="#4edea3" stroke-dasharray="251.2" stroke-dashoffset="129.1" stroke-linecap="round" stroke-width="8"></circle>',
    '<circle id="mem-gauge-circle" class="gauge-circle drop-shadow-[0_0_8px_rgba(78,222,163,0.5)] transition-all duration-700" cx="50" cy="50" fill="none" r="40" stroke="#4edea3" stroke-dasharray="251.2" stroke-dashoffset="129.1" stroke-linecap="round" stroke-width="8"></circle>'
)
html = html.replace(
    '<span class="text-code-lg font-code-lg font-bold text-on-surface">48.6%</span>',
    '<span id="mem-gauge-text" class="text-code-lg font-code-lg font-bold text-on-surface">--%</span>'
)

# WAN fields
html = html.replace('<span class="text-primary font-bold">103.24.12.8</span>', '<span id="wan-ipv4" class="text-primary font-bold">--</span>')
html = html.replace('<span class="text-on-surface">103.24.12.1</span>', '<span id="wan-gateway" class="text-on-surface">--</span>')
html = html.replace('<span class="text-on-surface">1.1.1.1 (Cloudflare)</span>', '<span id="wan-dns" class="text-on-surface">--</span>')
html = html.replace('<span class="text-code-md font-code-md text-primary font-bold">14d 08h 22m</span>', '<span id="system-uptime" class="text-code-md font-code-md text-primary font-bold">--</span>')

# Telemetry status badge
html = html.replace(
    '<span class="text-code-sm font-code-sm text-outline">Telemetry poll rate: 1000ms</span>',
    '<span id="telemetry-status-badge" class="text-code-sm font-code-sm text-outline">Connecting live...</span>'
)

# Client counts
html = html.replace('<span class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-primary/10 text-primary border border-primary/30 font-medium">14 Total</span>',
                    '<span class="px-2 py-0.5 rounded text-code-sm font-code-sm bg-primary/10 text-primary border border-primary/30 font-medium"><span class="live-clients-count">--</span> Total</span>')

# Inject script before </body>
html = html.replace('</body>', SCRIPT + '\n</body>')

with open('ui/stitch_preview.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Successfully wired ui/stitch_preview.html to live router telemetry!')

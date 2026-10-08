import os
import re

print("Cleaning mock data from all UI files...")

# ==============================================================================
# 1. CLEAN & WIRE ui/stitch_preview.html
# ==============================================================================
def clean_preview():
    with open('ui/stitch_preview.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # Remove hardcoded password parameter 'ax12secure#2024'
    html = re.sub(r"togglePassword\('pass2g',\s*'[^']*'\)", "togglePassword('pass2g')", html)
    html = re.sub(r"togglePassword\('pass5g',\s*'[^']*'\)", "togglePassword('pass5g')", html)

    # Empty the static table body and replace with id="live-devices-tbody"
    tbody_start = html.find('<tbody class="divide-y divide-outline-variant font-code-sm text-code-sm">')
    if tbody_start != -1:
        tbody_end = html.find('</tbody>', tbody_start)
        clean_tbody = '<tbody id="live-devices-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">\n<tr><td colspan="6" class="py-8 text-center text-outline font-mono">Connecting to router to load connected devices...</td></tr>\n'
        html = html[:tbody_start] + clean_tbody + html[tbody_end:]

    # Remove mock SSIDs in preview
    html = html.replace("Archer_AX12_2G", '<span id="wifi-2g-ssid">--</span>')
    html = html.replace("Archer_AX12_5G", '<span id="wifi-5g-ssid">--</span>')

    # Update script in stitch_preview.html to render real devices and Wi-Fi info
    extra_script = """
    // Populate Wi-Fi & Clients from /status
    if (data.wireless_2g) {
      const el = document.getElementById('wifi-2g-ssid');
      if (el && data.wireless_2g.ssid) el.textContent = data.wireless_2g.ssid;
    }
    if (data.wireless_5g) {
      const el = document.getElementById('wifi-5g-ssid');
      if (el && data.wireless_5g.ssid) el.textContent = data.wireless_5g.ssid;
    }

    const tbody = document.getElementById('live-devices-tbody');
    if (tbody && Array.isArray(data.clients)) {
      if (data.clients.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-outline font-mono">No devices currently connected to router.</td></tr>';
      } else {
        tbody.innerHTML = data.clients.map(c => {
          const wireBadge = c.wire_type === 'wired' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-secondary/20 text-secondary font-bold border border-secondary/40">Wired Ethernet</span>' :
                            c.wire_type === '5G' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-primary/20 text-primary font-bold border border-primary/40">5 GHz Wireless</span>' :
                            '<span class="px-2 py-0.5 rounded text-[10px] bg-surface-container-highest text-tertiary font-bold border border-outline-variant">2.4 GHz Wireless</span>';
          const icon = c.wire_type === 'wired' ? 'lan' : 'devices';
          return `
            <tr class="hover:bg-surface-container/60 transition-colors">
              <td class="py-3 px-4">
                <div class="flex items-center gap-2.5">
                  <span class="material-symbols-outlined text-primary text-lg">${icon}</span>
                  <span class="font-semibold text-on-surface">${c.hostname || '&lt;unknown&gt;'}</span>
                </div>
              </td>
              <td class="py-3 px-4 text-primary font-medium font-mono">${c.ipaddr || '--'}</td>
              <td class="py-3 px-4 text-outline font-mono">${c.macaddr || '--'}</td>
              <td class="py-3 px-4">${wireBadge}</td>
              <td class="py-3 px-4 text-outline font-mono">Live Session</td>
              <td class="py-3 px-4 text-right">
                <button onclick="blockDevice('${c.macaddr}')" class="px-2.5 py-1 rounded border border-error/50 text-error hover:bg-error-container/20 text-[11px] font-semibold transition-colors active:scale-95">Block</button>
              </td>
            </tr>
          `;
        }).join('');
      }
    }
"""

    if 'function blockDevice' not in html:
        block_fn = """
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
"""
        html = html.replace('</script>', block_fn + '\n</script>')

    # Inject extra_script inside updateLiveVitals
    target = "const pollBadge = document.getElementById('telemetry-status-badge');"
    if target in html and 'live-devices-tbody' not in html:
        html = html.replace(target, extra_script + '\n' + target)

    with open('ui/stitch_preview.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_preview.html cleaned and wired.")

clean_preview()


# ==============================================================================
# 2. CLEAN & WIRE ui/stitch_clients.html
# ==============================================================================
def clean_clients():
    with open('ui/stitch_clients.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # Empty the static table body
    tbody_start = html.find('<tbody class="divide-y divide-outline-variant font-code-sm text-code-sm">')
    if tbody_start != -1:
        tbody_end = html.find('</tbody>', tbody_start)
        clean_tbody = '<tbody id="clients-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">\n<tr><td colspan="7" class="py-8 text-center text-outline font-mono">Connecting to router to load connected clients...</td></tr>\n'
        html = html[:tbody_start] + clean_tbody + html[tbody_end:]

    # Remove hardcoded cards
    html = html.replace('value "14"', 'id="total-clients-val"')
    html = html.replace('value "2 devices"', 'id="wired-clients-val"')
    html = html.replace('value "9 devices"', 'id="5g-clients-val"')
    html = html.replace('value "3 devices"', 'id="2g-clients-val"')
    html = html.replace('LAN 1 (TrueNAS), LAN 2 (Ubuntu)', 'Wired ethernet interfaces')

    # Add script for /clients
    clients_script = """
<script>
let clientsData = [];

async function loadClients() {
  const tbody = document.getElementById('clients-tbody');
  try {
    const res = await fetch('/clients');
    if (!res.ok) throw new Error('Status ' + res.status);
    clientsData = await res.json();
    renderClientsTable();
  } catch (err) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-error font-mono">Unable to retrieve clients from router (${err.message}). Is the router connected?</td></tr>`;
  }
}

function renderClientsTable() {
  const tbody = document.getElementById('clients-tbody');
  if (!tbody) return;

  const totalEl = document.getElementById('total-clients-val');
  const wiredEl = document.getElementById('wired-clients-val');
  const fiveGEl = document.getElementById('5g-clients-val');
  const twoGEl = document.getElementById('2g-clients-val');

  const wired = clientsData.filter(c => c.wire_type === 'wired').length;
  const fiveG = clientsData.filter(c => c.wire_type === '5G').length;
  const twoG = clientsData.filter(c => c.wire_type === '2.4G').length;

  if (totalEl) totalEl.textContent = clientsData.length;
  if (wiredEl) wiredEl.textContent = wired + ' devices';
  if (fiveGEl) fiveGEl.textContent = fiveG + ' devices';
  if (twoGEl) twoGEl.textContent = twoG + ' devices';

  if (clientsData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-outline font-mono">No devices currently reported by router.</td></tr>';
    return;
  }

  tbody.innerHTML = clientsData.map(c => {
    const wirePill = c.wire_type === 'wired' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-secondary/20 text-secondary font-bold border border-secondary/40">Wired Ethernet</span>' :
                     c.wire_type === '5G' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-primary/20 text-primary font-bold border border-primary/40">5 GHz Wi-Fi 6</span>' :
                     '<span class="px-2 py-0.5 rounded text-[10px] bg-surface-container-highest text-tertiary font-bold border border-outline-variant">2.4 GHz</span>';
    return `
      <tr class="hover:bg-surface-container/60 transition-colors">
        <td class="py-3 px-4 font-semibold text-on-surface">${c.hostname || '&lt;unknown&gt;'}</td>
        <td class="py-3 px-4 text-primary font-mono">${c.ipaddr || '--'}</td>
        <td class="py-3 px-4 text-outline font-mono">${c.macaddr || '--'}</td>
        <td class="py-3 px-4">${wirePill}</td>
        <td class="py-3 px-4 text-outline font-mono">Active Client</td>
        <td class="py-3 px-4 text-outline font-mono">Connected</td>
        <td class="py-3 px-4 text-right">
          <button onclick="blockClient('${c.macaddr}')" class="px-2.5 py-1 rounded border border-error/50 text-error hover:bg-error-container/20 text-[11px] font-semibold transition-colors active:scale-95">Block</button>
        </td>
      </tr>
    `;
  }).join('');
}

async function blockClient(mac) {
  if (!confirm('Block client ' + mac + '?')) return;
  try {
    const res = await fetch('/access-control/block', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ macaddr: mac })
    });
    alert('Block result: ' + JSON.stringify(await res.json()));
    loadClients();
  } catch(e) {
    alert('Error: ' + e.message);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadClients();
  setInterval(loadClients, 10000);
});
</script>
"""
    html = html.replace('</body>', clients_script + '\n</body>')

    with open('ui/stitch_clients.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_clients.html cleaned and wired.")

clean_clients()


# ==============================================================================
# 3. CLEAN & WIRE ui/stitch_security.html
# ==============================================================================
def clean_security():
    with open('ui/stitch_security.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # Clear mock tables
    # 1. Blocked devices table
    html = re.sub(
        r'<tbody class="divide-y divide-outline-variant font-code-sm text-code-sm">[\s\S]*?</tbody>',
        '<tbody id="blocked-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">\n<tr><td colspan="5" class="py-6 text-center text-outline font-mono">Loading security state from router...</td></tr>\n</tbody>',
        html,
        count=1
    )

    # 2. DHCP table
    html = re.sub(
        r'<!-- Populated rows: -->[\s\S]*?<!-- Subtext:',
        '<tbody id="dhcp-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">\n<tr><td colspan="5" class="py-6 text-center text-outline font-mono">Loading DHCP static reservations...</td></tr>\n</tbody>\n</table>\n</div>\n<!-- Subtext:',
        html
    )

    # 3. Port forwarding table
    html = re.sub(
        r'<!-- Populated rows -->[\s\S]*?</div>\s*</div>\s*<!-- 4\. Wake-on-LAN',
        '<tbody id="nat-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">\n<tr><td colspan="6" class="py-6 text-center text-outline font-mono">Loading virtual server rules...</td></tr>\n</tbody>\n</table>\n</div>\n</div>\n</div>\n<!-- 4. Wake-on-LAN',
        html
    )

    security_script = """
<script>
async function loadSecurityData() {
  // 1. DHCP Reservations
  try {
    const res = await fetch('/network/dhcp/reservations');
    const tbody = document.getElementById('dhcp-tbody');
    if (res.ok && tbody) {
      const data = await res.json();
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="py-6 text-center text-outline font-mono">No static DHCP reservations configured on router.</td></tr>';
      } else {
        tbody.innerHTML = data.map(r => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-4 font-semibold text-on-surface">${r.name || '&lt;unnamed&gt;'}</td>
            <td class="py-3 px-4 text-outline font-mono">${r.macaddr}</td>
            <td class="py-3 px-4 text-primary font-mono">${r.ipaddr}</td>
            <td class="py-3 px-4"><span class="px-2 py-0.5 rounded text-[10px] ${r.enable ? 'bg-secondary/20 text-secondary' : 'bg-surface-container-highest text-outline'}">${r.enable ? 'Enabled' : 'Disabled'}</span></td>
            <td class="py-3 px-4 text-right"><button onclick="deleteDhcp('${r.macaddr}')" class="text-error hover:underline text-code-sm">Delete</button></td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('DHCP load:', e); }

  // 2. Blocked devices
  try {
    const res = await fetch('/access-control/blocked');
    const tbody = document.getElementById('blocked-tbody');
    if (res.ok && tbody) {
      const data = await res.json();
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="py-6 text-center text-outline font-mono">No devices currently blocked.</td></tr>';
      } else {
        tbody.innerHTML = data.map(d => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-4 font-semibold text-on-surface">${d.name || '&lt;unknown&gt;'}</td>
            <td class="py-3 px-4 text-outline font-mono">${d.macaddr}</td>
            <td class="py-3 px-4">${d.band || '--'}</td>
            <td class="py-3 px-4">${d.is_guest ? 'Guest' : 'Primary'}</td>
            <td class="py-3 px-4 text-right"><button onclick="unblock('${d.macaddr}')" class="text-secondary hover:underline text-code-sm">Unblock</button></td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('Blocked load:', e); }

  // 3. Port Forwarding
  try {
    const res = await fetch('/nat/virtual-servers');
    const tbody = document.getElementById('nat-tbody');
    if (res.ok && tbody) {
      const data = await res.json();
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="py-6 text-center text-outline font-mono">No virtual servers / port forwarding rules configured.</td></tr>';
      } else {
        tbody.innerHTML = data.map(v => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-4 font-semibold text-on-surface">${v.name || '&lt;rule&gt;'}</td>
            <td class="py-3 px-4 font-mono">${v.external_port || '--'}</td>
            <td class="py-3 px-4 font-mono">${v.internal_port || '--'}</td>
            <td class="py-3 px-4 font-mono">${v.protocol || 'ALL'}</td>
            <td class="py-3 px-4 font-mono text-primary">${v.internal_ip || '--'}</td>
            <td class="py-3 px-4 text-right"><button onclick="deleteNat('${v.key}')" class="text-error hover:underline text-code-sm">Delete</button></td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('NAT load:', e); }
}

async function deleteDhcp(mac) {
  if (!confirm('Delete DHCP reservation for ' + mac + '?')) return;
  await fetch('/network/dhcp/reservations/' + mac, { method: 'DELETE' });
  loadSecurityData();
}

async function unblock(mac) {
  if (!confirm('Unblock ' + mac + '?')) return;
  await fetch('/access-control/block/' + mac, { method: 'DELETE' });
  loadSecurityData();
}

async function deleteNat(key) {
  if (!confirm('Delete rule ' + key + '?')) return;
  await fetch('/nat/virtual-servers/' + key, { method: 'DELETE' });
  loadSecurityData();
}

document.addEventListener('DOMContentLoaded', () => {
  loadSecurityData();
  setInterval(loadSecurityData, 10000);
});
</script>
"""
    html = html.replace('</body>', security_script + '\n</body>')

    with open('ui/stitch_security.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_security.html cleaned and wired.")

clean_security()


# ==============================================================================
# 4. CLEAN & WIRE ui/stitch_wireless.html
# ==============================================================================
def clean_wireless():
    with open('ui/stitch_wireless.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # Clear mock wireless statistics rows
    html = re.sub(
        r'<tbody class="divide-y divide-outline-variant font-code-sm text-code-sm">[\s\S]*?</tbody>',
        '<tbody id="wifi-stats-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">\n<tr><td colspan="6" class="py-8 text-center text-outline font-mono">Loading wireless client statistics from router...</td></tr>\n</tbody>',
        html
    )

    wireless_script = """
<script>
async function loadWifiData() {
  try {
    const res = await fetch('/wifi/statistics');
    const tbody = document.getElementById('wifi-stats-tbody');
    if (res.ok && tbody) {
      const data = await res.json();
      if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-outline font-mono">No wireless clients transmitting packets currently.</td></tr>';
      } else {
        tbody.innerHTML = data.map(s => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-4 font-mono font-semibold text-primary">${s.macaddr}</td>
            <td class="py-3 px-4"><span class="px-2 py-0.5 rounded text-[10px] ${s.band.includes('5') ? 'bg-primary/20 text-primary' : 'bg-surface-container-highest text-tertiary'}">${s.band}</span></td>
            <td class="py-3 px-4 font-mono">${s.encryption}</td>
            <td class="py-3 px-4 font-mono">${s.rx_packets.toLocaleString()} pkts</td>
            <td class="py-3 px-4 font-mono">${s.tx_packets.toLocaleString()} pkts</td>
            <td class="py-3 px-4 text-secondary font-mono">Active Link</td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('Wi-Fi stats:', e); }

  try {
    const res = await fetch('/status');
    if (res.ok) {
      const data = await res.json();
      const ssid2g = document.querySelector('input[value=\"Archer_AX12_2.4G\"]');
      if (ssid2g && data.wireless_2g && data.wireless_2g.ssid) ssid2g.value = data.wireless_2g.ssid;
      const ssid5g = document.querySelector('input[value=\"Archer_AX12_5G\"]');
      if (ssid5g && data.wireless_5g && data.wireless_5g.ssid) ssid5g.value = data.wireless_5g.ssid;
    }
  } catch(e) {}
}

document.addEventListener('DOMContentLoaded', () => {
  loadWifiData();
  setInterval(loadWifiData, 8000);
});
</script>
"""
    html = html.replace('</body>', wireless_script + '\n</body>')

    with open('ui/stitch_wireless.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_wireless.html cleaned and wired.")

clean_wireless()

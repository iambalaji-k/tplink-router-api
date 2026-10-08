"""Comprehensive script to purge all mock data and wire live API endpoints across all HTML views."""

import re

# ==============================================================================
# 1. PURGE & WIRE ui/stitch_clients.html
# ==============================================================================
def clean_clients():
    with open('ui/stitch_clients.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. Replace the entire static tbody with a dynamic clients-tbody
    table_tbody_regex = r'<tbody class="divide-y divide-outline-variant/40 text-body-sm font-body-sm">[\s\S]*?</tbody>'
    new_tbody = '''<tbody id="clients-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">
<tr><td colspan="7" class="py-12 text-center text-outline font-mono">Loading connected clients from router...</td></tr>
</tbody>'''
    html = re.sub(table_tbody_regex, new_tbody, html, count=1)

    # 2. Dynamic footer counter
    html = re.sub(
        r'<div>Showing \d+ of \d+ Active Leases</div>',
        '<div id="clients-footer-count">Connecting to router...</div>',
        html
    )

    # 3. Dynamic metric cards
    html = re.sub(r'<div class="text-headline-md font-headline-md text-on-surface font-bold">14</div>',
                  '<div id="total-clients-val" class="text-headline-md font-headline-md text-on-surface font-bold">--</div>', html)
    html = re.sub(r'<span class="text-on-surface font-semibold">2 devices</span>',
                  '<span id="wired-clients-val" class="text-on-surface font-semibold">--</span>', html)
    html = re.sub(r'<span class="text-on-surface font-semibold">9 devices</span>',
                  '<span id="5g-clients-val" class="text-on-surface font-semibold">--</span>', html)
    html = re.sub(r'<span class="text-on-surface font-semibold">3 devices</span>',
                  '<span id="2g-clients-val" class="text-on-surface font-semibold">--</span>', html)

    # 4. Clean up the Drawer to be dynamic based on selected client
    drawer_regex = r'<!-- Right Column: Dedicated Client Inspection Drawer \(4 Cols\) -->[\s\S]*?</section>'
    new_drawer = '''<!-- Right Column: Dedicated Client Inspection Drawer (4 Cols) -->
<div class="lg:col-span-4 bg-surface-container-low border border-primary/40 rounded-xl p-space-md shadow-[0_8px_32px_-4px_rgba(0,167,225,0.2)] flex flex-col space-y-space-md relative overflow-hidden backdrop-blur-xl">
  <div class="absolute -top-12 -right-12 w-32 h-32 bg-primary/10 rounded-full blur-2xl pointer-events-none"></div>
  
  <!-- Drawer Header -->
  <div class="border-b border-outline-variant pb-3 flex justify-between items-start">
    <div>
      <span class="text-label-caps font-label-caps text-outline uppercase tracking-wider block">Telemetry Inspector</span>
      <h3 id="drawer-hostname" class="text-headline-sm font-headline-sm text-primary font-bold mt-0.5">Select a Device</h3>
      <p id="drawer-status" class="text-code-sm font-code-sm text-outline flex items-center gap-1.5 mt-1">
        Click any client row to view live telemetry
      </p>
    </div>
    <div class="p-2 rounded bg-surface-container-highest text-primary">
      <span id="drawer-icon" class="material-symbols-outlined" data-icon="devices">devices</span>
    </div>
  </div>

  <!-- Technical Parameter Cards -->
  <div class="space-y-2.5" id="drawer-details">
    <div class="bg-surface-container p-2.5 rounded-lg border border-outline-variant/60">
      <div class="flex justify-between items-center text-code-sm font-code-sm mb-1">
        <span class="text-outline">IP Address</span>
        <span id="drawer-ip" class="text-primary font-mono font-semibold">--</span>
      </div>
      <div class="flex justify-between items-center text-code-sm font-code-sm">
        <span class="text-outline">MAC Address</span>
        <span id="drawer-mac" class="text-on-surface font-mono">--</span>
      </div>
    </div>

    <div class="bg-surface-container p-2.5 rounded-lg border border-outline-variant/60 flex justify-between items-center">
      <div>
        <span class="text-label-caps font-label-caps text-outline uppercase tracking-wider block">Physical Interface</span>
        <span id="drawer-medium" class="text-code-md font-code-md text-on-surface font-mono">--</span>
      </div>
      <span id="drawer-band-badge" class="px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/30 text-code-sm font-code-sm font-mono">
        Active
      </span>
    </div>

    <div class="bg-surface-container p-2.5 rounded-lg border border-outline-variant/60 text-code-sm font-code-sm">
      <span class="text-label-caps font-label-caps text-outline uppercase tracking-wider block mb-1">Subnet & Gateway</span>
      <div class="text-on-surface-variant font-mono">192.168.0.0/24 • Gateway: 192.168.0.1</div>
    </div>
  </div>

  <!-- Quick Actions -->
  <div class="pt-2 border-t border-outline-variant space-y-2">
    <button id="drawer-reserve-btn" onclick="reserveSelectedDevice()" class="w-full py-2 px-3 rounded bg-primary-container text-on-primary-fixed text-code-md font-code-md font-semibold hover:brightness-110 active:scale-98 transition-all flex items-center justify-center gap-2">
      <span class="material-symbols-outlined text-sm" data-icon="bookmark">bookmark</span>
      Reserve Static IP
    </button>
    <div class="grid grid-cols-2 gap-2">
      <button id="drawer-block-btn" onclick="blockSelectedDevice()" class="py-1.5 px-2 rounded bg-surface-container border border-error/50 hover:bg-error-container/20 text-code-sm font-code-sm text-error flex items-center justify-center gap-1.5 transition-all">
        <span class="material-symbols-outlined text-sm" data-icon="block">block</span>
        Block Device
      </button>
      <button id="drawer-wol-btn" onclick="wakeSelectedDevice()" class="py-1.5 px-2 rounded bg-surface-container border border-outline-variant hover:border-primary/50 text-code-sm font-code-sm text-on-surface flex items-center justify-center gap-1.5 transition-all">
        <span class="material-symbols-outlined text-sm" data-icon="bolt">bolt</span>
        Wake-on-LAN
      </button>
    </div>
  </div>
</div>
</section>'''
    html = re.sub(drawer_regex, new_drawer, html, count=1)

    # 5. Replace existing or inject dynamic clients script
    # Strip any previously appended script block
    html = re.sub(r'<script>\s*let clientsData = \[\];[\s\S]*?</script>', '', html)

    script_content = '''
<script>
let clientsData = [];
let selectedMac = null;

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

function selectClient(mac) {
  selectedMac = mac;
  const client = clientsData.find(c => c.macaddr === mac);
  if (!client) return;

  const hostnameEl = document.getElementById('drawer-hostname');
  const statusEl = document.getElementById('drawer-status');
  const ipEl = document.getElementById('drawer-ip');
  const macEl = document.getElementById('drawer-mac');
  const mediumEl = document.getElementById('drawer-medium');
  const bandBadgeEl = document.getElementById('drawer-band-badge');
  const iconEl = document.getElementById('drawer-icon');

  if (hostnameEl) hostnameEl.textContent = client.hostname || '<unknown device>';
  if (statusEl) statusEl.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-secondary animate-ping"></span> Live Connected Client';
  if (ipEl) ipEl.textContent = client.ipaddr || '--';
  if (macEl) macEl.textContent = client.macaddr || '--';
  if (mediumEl) mediumEl.textContent = client.wire_type === 'wired' ? 'Gigabit Ethernet (Wired)' : client.wire_type === '5G' ? '5 GHz 802.11ax (Wi-Fi 6)' : '2.4 GHz 802.11n/ax';
  if (bandBadgeEl) bandBadgeEl.textContent = client.wire_type;
  if (iconEl) iconEl.textContent = client.wire_type === 'wired' ? 'lan' : 'devices';

  renderClientsTable();
}

function renderClientsTable() {
  const tbody = document.getElementById('clients-tbody');
  if (!tbody) return;

  const totalEl = document.getElementById('total-clients-val');
  const wiredEl = document.getElementById('wired-clients-val');
  const fiveGEl = document.getElementById('5g-clients-val');
  const twoGEl = document.getElementById('2g-clients-val');
  const footerEl = document.getElementById('clients-footer-count');

  const wired = clientsData.filter(c => c.wire_type === 'wired').length;
  const fiveG = clientsData.filter(c => c.wire_type === '5G').length;
  const twoG = clientsData.filter(c => c.wire_type === '2.4G').length;

  if (totalEl) totalEl.textContent = clientsData.length;
  if (wiredEl) wiredEl.textContent = wired + ' devices';
  if (fiveGEl) fiveGEl.textContent = fiveG + ' devices';
  if (twoGEl) twoGEl.textContent = twoG + ' devices';
  if (footerEl) footerEl.textContent = `Showing ${clientsData.length} Active Connected Clients`;

  if (clientsData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-12 text-center text-outline font-mono">No devices currently connected to router.</td></tr>';
    return;
  }

  // Default select first client if none selected
  if (!selectedMac && clientsData.length > 0) {
    selectClient(clientsData[0].macaddr);
  }

  tbody.innerHTML = clientsData.map(c => {
    const isSelected = c.macaddr === selectedMac;
    const wirePill = c.wire_type === 'wired' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-secondary/20 text-secondary font-bold border border-secondary/40 font-mono">Wired Ethernet</span>' :
                     c.wire_type === '5G' ? '<span class="px-2 py-0.5 rounded text-[10px] bg-primary/20 text-primary font-bold border border-primary/40 font-mono">5 GHz Wi-Fi 6</span>' :
                     '<span class="px-2 py-0.5 rounded text-[10px] bg-surface-container-highest text-tertiary font-bold border border-outline-variant font-mono">2.4 GHz</span>';
    const rowClass = isSelected ? 'bg-primary-container/15 border-l-2 border-l-primary' : 'hover:bg-surface-container/60';

    return `
      <tr onclick="selectClient('${c.macaddr}')" class="${rowClass} transition-colors cursor-pointer">
        <td class="py-3 px-4 font-semibold text-on-surface">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full ${isSelected ? 'bg-primary' : 'bg-secondary'}"></span>
            <span>${c.hostname || '&lt;unknown&gt;'}</span>
          </div>
        </td>
        <td class="py-3 px-4 text-primary font-mono font-medium">${c.ipaddr || '--'}</td>
        <td class="py-3 px-4 text-outline font-mono">${c.macaddr || '--'}</td>
        <td class="py-3 px-4">${wirePill}</td>
        <td class="py-3 px-4 text-on-surface-variant font-mono">Active Client</td>
        <td class="py-3 px-4 text-secondary font-mono">Live Link</td>
        <td class="py-3 px-4 text-right" onclick="event.stopPropagation()">
          <div class="flex items-center justify-end gap-1.5">
            <button onclick="reserveDevice('${c.ipaddr}', '${c.macaddr}', '${c.hostname || ''}')" class="px-2 py-1 text-code-sm font-code-sm rounded border border-primary text-primary hover:bg-primary/20 transition-all">Reserve IP</button>
            <button onclick="blockDevice('${c.macaddr}')" class="px-2 py-1 text-code-sm font-code-sm rounded border border-error text-error hover:bg-error/20 transition-all">Block</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function blockDevice(mac) {
  if (!confirm('Block client ' + mac + ' in Access Control?')) return;
  try {
    const res = await fetch('/access-control/block', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ macaddr: mac })
    });
    const d = await res.json();
    alert('Device blocked: ' + JSON.stringify(d));
    loadClients();
  } catch(e) {
    alert('Block error: ' + e.message);
  }
}

async function reserveDevice(ip, mac, name) {
  if (!ip || !mac) return alert('Invalid IP or MAC');
  const reservationName = prompt('Enter name for DHCP reservation:', name || 'Device');
  if (!reservationName) return;
  try {
    const res = await fetch('/network/dhcp/reservations', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ ipaddr: ip, macaddr: mac, name: reservationName, enable: true })
    });
    alert('DHCP Reservation added: ' + JSON.stringify(await res.json()));
  } catch(e) {
    alert('Reservation error: ' + e.message);
  }
}

function reserveSelectedDevice() {
  const client = clientsData.find(c => c.macaddr === selectedMac);
  if (client) reserveDevice(client.ipaddr, client.macaddr, client.hostname);
}

function blockSelectedDevice() {
  if (selectedMac) blockDevice(selectedMac);
}

async function wakeSelectedDevice() {
  const client = clientsData.find(c => c.macaddr === selectedMac);
  if (!client) return;
  try {
    const res = await fetch('/wol/wake', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ macaddr: client.macaddr, name: client.hostname })
    });
    alert('Magic packet sent to ' + client.macaddr);
  } catch(e) {
    alert('WoL error: ' + e.message);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadClients();
  setInterval(loadClients, 8000);
});
</script>
'''
    html = html.replace('</body>', script_content + '\n</body>')

    with open('ui/stitch_clients.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_clients.html completely purged of mock data and wired.")


# ==============================================================================
# 2. PURGE & WIRE ui/stitch_security.html
# ==============================================================================
def clean_security():
    with open('ui/stitch_security.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. Protected Host Callout banner: remove hardcoded fake MAC AA-BB-CC-DD-EE-01
    html = re.sub(
        r'Device with MAC <span[^>]*>AA-BB-CC-DD-EE-01</span> is permanently immune',
        'Router default gateway (192.168.0.1) and management interface are permanently immune',
        html
    )

    # 2. Blocked devices count & table
    html = re.sub(
        r'<div class="text-label-caps font-label-caps text-outline uppercase">Target Enforcements \(\d+ Listed\)</div>',
        '<div id="blocked-count-badge" class="text-label-caps font-label-caps text-outline uppercase">Target Enforcements (0 Listed)</div>',
        html
    )
    # Replace blocked devices table body
    blocked_table_regex = r'<tbody class="divide-y divide-outline-variant/50 font-body-md text-body-md">[\s\S]*?</tbody>'
    new_blocked_tbody = '''<tbody id="blocked-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">
<tr><td colspan="5" class="py-6 text-center text-outline font-mono">Loading access control rules...</td></tr>
</tbody>'''
    html = re.sub(blocked_table_regex, new_blocked_tbody, html, count=1)

    # 3. DHCP Reservations search placeholder & table
    html = re.sub(r'placeholder="Filter \d+ reservations\.\.\."', 'placeholder="Filter static reservations..."', html)
    # Replace DHCP table body
    dhcp_table_regex = r'<tbody class="divide-y divide-outline-variant/50 font-body-md text-body-md">[\s\S]*?</tbody>'
    new_dhcp_tbody = '''<tbody id="dhcp-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">
<tr><td colspan="5" class="py-6 text-center text-outline font-mono">Loading DHCP static reservations...</td></tr>
</tbody>'''
    html = re.sub(dhcp_table_regex, new_dhcp_tbody, html, count=1)

    # 4. DMZ Host section - remove Home-Assistant linked and 192.168.0.50
    html = re.sub(
        r'<span class="text-secondary font-code-sm">Home-Assistant linked</span>',
        '<span id="dmz-status-label" class="text-outline font-code-sm font-mono">Status: Checking...</span>',
        html
    )
    html = re.sub(
        r'<input class="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 text-code-md font-code-md text-primary font-bold focus:border-primary focus:ring-1 focus:ring-primary outline-none" type="text" value="192\.168\.0\.50"/>',
        '<input id="dmz-ip-input" class="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 text-code-md font-code-md text-primary font-bold focus:border-primary focus:ring-1 focus:ring-primary outline-none font-mono" type="text" placeholder="e.g. 192.168.0.50" value=""/>',
        html
    )

    # 5. Virtual Servers / Port Forwarding table
    nat_table_regex = r'<tbody class="divide-y divide-outline-variant/50 text-code-md font-code-md">[\s\S]*?</tbody>'
    new_nat_tbody = '''<tbody id="nat-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">
<tr><td colspan="6" class="py-6 text-center text-outline font-mono">Loading virtual server rules...</td></tr>
</tbody>'''
    html = re.sub(nat_table_regex, new_nat_tbody, html, count=1)

    # 6. Wake-on-LAN saved targets card grid
    wol_grid_regex = r'<!-- Saved WoL targets list -->[\s\S]*?<!-- Quick Manual Wake Input Section -->'
    new_wol_grid = '''<!-- Saved WoL targets list -->
<div id="wol-targets-grid" class="grid grid-cols-1 md:grid-cols-2 gap-space-md">
  <div class="rounded bg-surface-container border border-outline-variant/70 p-space-md text-center text-outline font-mono col-span-2 py-8">
    Loading saved Wake-on-LAN targets from router...
  </div>
</div>
<!-- Quick Manual Wake Input Section -->'''
    html = re.sub(wol_grid_regex, new_wol_grid, html, count=1)

    # Replace WoL counter
    html = re.sub(r'<span class="text-code-sm font-code-sm px-2\.5 py-1 rounded bg-surface-container text-on-surface-variant border border-outline-variant self-start sm:self-auto">\s*\d+ / \d+ entries used\s*</span>',
                  '<span id="wol-count-badge" class="text-code-sm font-code-sm px-2.5 py-1 rounded bg-surface-container text-on-surface-variant border border-outline-variant font-mono">-- entries</span>',
                  html)

    # Manual wake input & button wire up
    html = re.sub(
        r'<input class="flex-1 bg-surface-container-lowest border border-outline-variant rounded px-3 py-1\.5 text-code-md font-code-md text-on-surface placeholder:text-outline focus:border-primary focus:ring-1 focus:ring-primary outline-none" placeholder="FF:EE:DD:CC:BB:AA" type="text"/>',
        '<input id="manual-wol-input" class="flex-1 bg-surface-container-lowest border border-outline-variant rounded px-3 py-1.5 text-code-md font-code-md text-on-surface font-mono placeholder:text-outline focus:border-primary focus:ring-1 focus:ring-primary outline-none" placeholder="FF:EE:DD:CC:BB:AA" type="text"/>',
        html
    )
    html = re.sub(
        r'<button class="px-4 py-2 rounded bg-primary-container text-on-primary-container font-code-md text-code-md flex items-center justify-center gap-1\.5 hover:brightness-110 active:scale-95 transition-all shadow-\[0_0_12px_rgba\(0,167,225,0\.3\)\] whitespace-nowrap">\s*<span class="material-symbols-outlined text-\[18px\]">bolt</span>\s*Broadcast WoL\s*</button>',
        '<button onclick="broadcastManualWol()" class="px-4 py-2 rounded bg-primary-container text-on-primary-container font-code-md text-code-md flex items-center justify-center gap-1.5 hover:brightness-110 active:scale-95 transition-all shadow-[0_0_12px_rgba(0,167,225,0.3)] whitespace-nowrap"><span class="material-symbols-outlined text-[18px]">bolt</span> Broadcast WoL</button>',
        html
    )

    # 7. Remove any old script and inject full live script
    html = re.sub(r'<script>\s*async function loadSecurityData[\s\S]*?</script>', '', html)

    security_script = '''
<script>
async function loadSecurityData() {
  // 1. DHCP Static Reservations
  try {
    const res = await fetch('/network/dhcp/reservations');
    const tbody = document.getElementById('dhcp-tbody');
    if (res.ok && tbody) {
      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="py-8 text-center text-outline font-mono">No static DHCP reservations configured on router.</td></tr>';
      } else {
        tbody.innerHTML = data.map(r => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-4 font-semibold text-on-surface">${r.name || '&lt;unnamed&gt;'}</td>
            <td class="py-3 px-4 text-outline font-mono">${r.macaddr}</td>
            <td class="py-3 px-4 text-primary font-mono">${r.ipaddr}</td>
            <td class="py-3 px-4"><span class="px-2 py-0.5 rounded text-[10px] ${r.enable ? 'bg-secondary/20 text-secondary' : 'bg-surface-container-highest text-outline'} font-mono">${r.enable ? 'Enabled' : 'Disabled'}</span></td>
            <td class="py-3 px-4 text-right"><button onclick="deleteDhcp('${r.macaddr}')" class="text-error hover:underline text-code-sm font-mono">Delete</button></td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('DHCP load error:', e); }

  // 2. Blocked Devices
  try {
    const res = await fetch('/access-control/blocked');
    const tbody = document.getElementById('blocked-tbody');
    const badge = document.getElementById('blocked-count-badge');
    if (res.ok && tbody) {
      const data = await res.json();
      if (badge) badge.textContent = `Target Enforcements (${data.length} Listed)`;
      if (!Array.isArray(data) || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="py-8 text-center text-outline font-mono">No devices currently blocked in Access Control list.</td></tr>';
      } else {
        tbody.innerHTML = data.map(d => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-4 font-semibold text-on-surface">${d.name || '&lt;unknown&gt;'}</td>
            <td class="py-3 px-4 text-outline font-mono">${d.macaddr}</td>
            <td class="py-3 px-4 font-mono">${d.band || '--'}</td>
            <td class="py-3 px-4 font-mono">${d.is_guest ? 'Guest' : 'Primary'}</td>
            <td class="py-3 px-4 text-right"><button onclick="unblock('${d.macaddr}')" class="text-secondary hover:underline text-code-sm font-mono">Unblock</button></td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('Blocked load error:', e); }

  // 3. Virtual Servers / Port Forwarding
  try {
    const res = await fetch('/nat/virtual-servers');
    const tbody = document.getElementById('nat-tbody');
    if (res.ok && tbody) {
      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-outline font-mono">No virtual server forwarding rules configured.</td></tr>';
      } else {
        tbody.innerHTML = data.map(r => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-3 font-semibold text-on-surface">${r.name || '&lt;rule&gt;'}</td>
            <td class="py-3 px-3 text-primary font-mono">${r.external_port}</td>
            <td class="py-3 px-3 text-primary font-mono">${r.internal_port}</td>
            <td class="py-3 px-3 font-mono"><span class="px-1.5 py-0.5 rounded bg-surface-container-highest text-code-sm">${r.protocol}</span></td>
            <td class="py-3 px-3 text-on-surface-variant font-mono">${r.internal_ip}</td>
            <td class="py-3 px-3 text-right"><button onclick="deleteNatRule('${r.name}')" class="text-error hover:underline text-code-sm font-mono">Delete</button></td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('NAT load error:', e); }

  // 4. Saved Wake-on-LAN Targets
  try {
    const res = await fetch('/wol/devices');
    const grid = document.getElementById('wol-targets-grid');
    const badge = document.getElementById('wol-count-badge');
    if (res.ok && grid) {
      const data = await res.json();
      if (badge) badge.textContent = `${data.length} entries saved`;
      if (!Array.isArray(data) || data.length === 0) {
        grid.innerHTML = '<div class="rounded bg-surface-container border border-outline-variant/70 p-space-md text-center text-outline font-mono col-span-2 py-8">No saved Wake-on-LAN targets on router.</div>';
      } else {
        grid.innerHTML = data.map(dev => `
          <div class="rounded bg-surface-container border border-outline-variant/70 p-space-md flex flex-col justify-between space-y-space-md">
            <div>
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span class="material-symbols-outlined text-primary text-[20px]">desktop_windows</span>
                  <span class="font-headline-sm text-headline-sm text-on-surface font-semibold">${dev.name || '&lt;device&gt;'}</span>
                </div>
                <span class="w-2 h-2 rounded-full bg-secondary"></span>
              </div>
              <div class="space-y-1 font-code-sm text-code-sm text-outline">
                <div class="flex justify-between">
                  <span>Target MAC:</span>
                  <span class="text-on-surface font-code-md font-mono">${dev.macaddr}</span>
                </div>
              </div>
            </div>
            <button onclick="wakeDevice('${dev.macaddr}', '${dev.name || ''}')" class="w-full py-2 px-3 rounded bg-surface-container-highest hover:bg-surface-bright text-primary border border-primary/30 font-code-md text-code-md flex items-center justify-center gap-2 active:scale-95 transition-all group font-mono">
              <span class="material-symbols-outlined text-[18px] group-hover:scale-110 transition-transform">cell_tower</span>
              <span>Send Magic Packet</span>
            </button>
          </div>
        `).join('');
      }
    }
  } catch(e) { console.debug('WoL load error:', e); }

  // 5. DMZ Host Status
  try {
    const res = await fetch('/nat/dmz');
    const statusLabel = document.getElementById('dmz-status-label');
    const ipInput = document.getElementById('dmz-ip-input');
    if (res.ok) {
      const data = await res.json();
      if (statusLabel) statusLabel.textContent = data.enable ? 'Status: Active DMZ' : 'Status: Disabled';
      if (ipInput && data.ipaddr) ipInput.value = data.ipaddr;
    }
  } catch(e) {}
}

async function unblock(mac) {
  if (!confirm('Unblock device ' + mac + '?')) return;
  try {
    await fetch('/access-control/unblock', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ macaddr: mac })
    });
    loadSecurityData();
  } catch(e) { alert('Error: ' + e.message); }
}

async function deleteDhcp(mac) {
  if (!confirm('Delete DHCP reservation for ' + mac + '?')) return;
  try {
    await fetch('/network/dhcp/reservations/' + mac, { method: 'DELETE' });
    loadSecurityData();
  } catch(e) { alert('Error: ' + e.message); }
}

async function wakeDevice(mac, name) {
  try {
    const res = await fetch('/wol/wake', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ macaddr: mac, name: name })
    });
    alert('Magic packet broadcast sent to ' + mac);
  } catch(e) { alert('WoL error: ' + e.message); }
}

async function broadcastManualWol() {
  const input = document.getElementById('manual-wol-input');
  if (!input || !input.value.trim()) return alert('Enter target MAC address');
  wakeDevice(input.value.trim(), 'Manual Target');
}

document.addEventListener('DOMContentLoaded', () => {
  loadSecurityData();
  setInterval(loadSecurityData, 10000);
});
</script>
'''
    html = html.replace('</body>', security_script + '\n</body>')

    with open('ui/stitch_security.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_security.html completely purged of mock data and wired.")


# ==============================================================================
# 3. PURGE & WIRE ui/stitch_wireless.html
# ==============================================================================
def clean_wireless():
    with open('ui/stitch_wireless.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. Replace hardcoded SSID and password values
    html = re.sub(
        r'<input class="w-full h-10 px-3 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary" type="text" value="Archer_AX12_2\.4G"/>',
        '<input id="wifi-ssid-2g" class="w-full h-10 px-3 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary font-mono" type="text" placeholder="Loading 2.4G SSID..." value=""/>',
        html
    )
    html = re.sub(
        r'<input class="w-full h-10 pl-3 pr-10 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary" type="password" value="SuperSecretPresharedPass123"/>',
        '<input id="wifi-pass-2g" class="w-full h-10 pl-3 pr-10 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary font-mono" type="password" placeholder="••••••••" value=""/>',
        html
    )
    html = re.sub(
        r'<input class="w-full h-10 px-3 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary" type="text" value="Archer_AX12_5G"/>',
        '<input id="wifi-ssid-5g" class="w-full h-10 px-3 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary font-mono" type="text" placeholder="Loading 5G SSID..." value=""/>',
        html
    )
    html = re.sub(
        r'<input class="w-full h-10 pl-3 pr-10 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary" type="password" value="SuperSecure5GHzAXPassphrase"/>',
        '<input id="wifi-pass-5g" class="w-full h-10 pl-3 pr-10 bg-surface border border-outline-variant rounded-lg text-code-md font-code-md text-on-surface focus:outline-none focus:border-primary font-mono" type="password" placeholder="••••••••" value=""/>',
        html
    )
    html = re.sub(
        r'<input class="w-full h-9 px-2 bg-surface-container border border-outline-variant rounded text-code-md font-code-md text-on-surface" type="text" value="Archer_Guest_2\.4G"/>',
        '<input id="wifi-guest-2g" class="w-full h-9 px-2 bg-surface-container border border-outline-variant rounded text-code-md font-code-md text-on-surface font-mono" type="text" placeholder="Loading Guest 2.4G..." value=""/>',
        html
    )
    html = re.sub(
        r'<input class="w-full h-9 px-2 bg-surface-container border border-outline-variant rounded text-code-md font-code-md text-on-surface" type="text" value="Archer_Guest_5G"/>',
        '<input id="wifi-guest-5g" class="w-full h-9 px-2 bg-surface-container border border-outline-variant rounded text-code-md font-code-md text-on-surface font-mono" type="text" placeholder="Loading Guest 5G..." value=""/>',
        html
    )

    # 2. Replace the static client association table body
    wifi_tbody_regex = r'<tbody class="divide-y divide-outline-variant text-body-md font-body-md">[\s\S]*?</tbody>'
    new_wifi_tbody = '''<tbody id="wifi-stats-tbody" class="divide-y divide-outline-variant font-code-sm text-code-sm">
<tr><td colspan="6" class="py-8 text-center text-outline font-mono">Loading active wireless associations from router...</td></tr>
</tbody>'''
    html = re.sub(wifi_tbody_regex, new_wifi_tbody, html, count=1)

    # 3. Clean up script block and wire live endpoints
    html = re.sub(r'<script>\s*async function loadWifiData[\s\S]*?</script>', '', html)

    wireless_script = '''
<script>
async function loadWifiData() {
  // 1. Wireless statistics and active associations
  try {
    const res = await fetch('/wifi/statistics');
    const tbody = document.getElementById('wifi-stats-tbody');
    if (res.ok && tbody) {
      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-outline font-mono">No wireless clients transmitting packets currently.</td></tr>';
      } else {
        tbody.innerHTML = data.map(s => `
          <tr class="hover:bg-surface-container/60 transition-colors">
            <td class="py-3 px-4 font-mono font-semibold text-primary">${s.macaddr}</td>
            <td class="py-3 px-4"><span class="px-2 py-0.5 rounded text-[10px] ${s.band.includes('5') ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-surface-container-highest text-tertiary border border-outline-variant'} font-mono">${s.band}</span></td>
            <td class="py-3 px-4 font-mono text-on-surface-variant">${s.encryption}</td>
            <td class="py-3 px-4 font-mono text-right text-on-surface">${s.rx_packets.toLocaleString()} pkts</td>
            <td class="py-3 px-4 font-mono text-right text-on-surface">${s.tx_packets.toLocaleString()} pkts</td>
            <td class="py-3 px-4 text-secondary font-mono">Active Link</td>
          </tr>
        `).join('');
      }
    }
  } catch(e) { console.debug('Wi-Fi stats error:', e); }

  // 2. Wi-Fi status and SSIDs
  try {
    const res = await fetch('/status');
    if (res.ok) {
      const data = await res.json();
      const ssid2g = document.getElementById('wifi-ssid-2g');
      if (ssid2g && data.wireless_2g && data.wireless_2g.ssid) ssid2g.value = data.wireless_2g.ssid;
      const ssid5g = document.getElementById('wifi-ssid-5g');
      if (ssid5g && data.wireless_5g && data.wireless_5g.ssid) ssid5g.value = data.wireless_5g.ssid;
    }
  } catch(e) { console.debug('Router status error:', e); }

  // 3. Guest network status
  try {
    const res = await fetch('/wifi/guest');
    if (res.ok) {
      const data = await res.json();
      const guest2g = document.getElementById('wifi-guest-2g');
      if (guest2g && data.ssid) guest2g.value = data.ssid;
      const guest5g = document.getElementById('wifi-guest-5g');
      if (guest5g && data.ssid_5g) guest5g.value = data.ssid_5g;
    }
  } catch(e) {}
}

document.addEventListener('DOMContentLoaded', () => {
  loadWifiData();
  setInterval(loadWifiData, 8000);
});
</script>
'''
    html = html.replace('</body>', wireless_script + '\n</body>')

    with open('ui/stitch_wireless.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("ui/stitch_wireless.html completely purged of mock data and wired.")

if __name__ == '__main__':
    clean_clients()
    clean_security()
    clean_wireless()

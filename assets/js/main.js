// ============================================================
//  NEURO-MESH — Master JavaScript v2.0
// ============================================================

/* ── Nav scroll state ──────────────────────────────────────── */
window.addEventListener('scroll', () => {
  const nav = document.getElementById('site-nav');
  if (nav) nav.classList.toggle('scrolled', window.scrollY > 20);
});

/* ── Mega Menu (App Launcher) ──────────────────────────────── */
const launcherBtn = document.getElementById('launcher-btn');
const megaMenu    = document.getElementById('mega-menu');
const menuClose   = document.getElementById('menu-close');

function openMenu() {
  megaMenu.classList.add('open');
  launcherBtn.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeMenu() {
  megaMenu.classList.remove('open');
  launcherBtn.classList.remove('open');
  document.body.style.overflow = '';
}

if (launcherBtn) launcherBtn.addEventListener('click', () => {
  megaMenu.classList.contains('open') ? closeMenu() : openMenu();
});
if (menuClose) menuClose.addEventListener('click', closeMenu);
if (megaMenu) megaMenu.addEventListener('click', e => {
  if (e.target === megaMenu) closeMenu();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });

/* ── Scroll-reveal (IntersectionObserver) ──────────────────── */
const revealEls = document.querySelectorAll('[data-reveal]');
const observer  = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('revealed');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -60px 0px' });
revealEls.forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(24px)';
  el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
  observer.observe(el);
});
document.addEventListener('animationend', () => {});
// Add class injector for observer
document.head.insertAdjacentHTML('beforeend', `
  <style>
    [data-reveal].revealed { opacity:1 !important; transform:translateY(0) !important; }
    [data-reveal][data-delay="1"] { transition-delay: 0.1s !important; }
    [data-reveal][data-delay="2"] { transition-delay: 0.2s !important; }
    [data-reveal][data-delay="3"] { transition-delay: 0.3s !important; }
    [data-reveal][data-delay="4"] { transition-delay: 0.4s !important; }
    [data-reveal][data-delay="5"] { transition-delay: 0.5s !important; }
  </style>
`);

/* ── App Overlay (Dashboard) ───────────────────────────────── */
const appOverlay = document.getElementById('app-overlay');
const tryBtns    = document.querySelectorAll('[data-launch-app]');
const overlayClose = document.getElementById('overlay-close');

function openApp() {
  if (!appOverlay) return;
  appOverlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeApp() {
  if (!appOverlay) return;
  appOverlay.classList.remove('open');
  document.body.style.overflow = '';
}

tryBtns.forEach(btn => btn.addEventListener('click', openApp));
if (overlayClose) overlayClose.addEventListener('click', closeApp);

/* ── Tab switching (Dashboard) ─────────────────────────────── */
function switchTab(tabId) {
  document.querySelectorAll('.glass-tab').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById('btn-' + tabId);
  if (activeBtn) activeBtn.classList.add('active');

  ['tab-dsa','tab-chat','tab-traffic'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (id === tabId) {
      el.classList.remove('opacity-0','pointer-events-none','z-0');
      el.classList.add('opacity-100','z-10');
    } else {
      el.classList.remove('opacity-100','z-10');
      el.classList.add('opacity-0','pointer-events-none','z-0');
    }
  });
}

/* ── Sliders ───────────────────────────────────────────────── */
function updateSliderTrack(slider) {
  if (!slider) return;
  const pct = (slider.value - slider.min) / (slider.max - slider.min) * 100;
  slider.style.background = `linear-gradient(to right,rgba(0,242,254,.6) ${pct}%,rgba(255,255,255,.1) ${pct}%)`;
}
function updateSlider(id, value, suffix) {
  const el = document.getElementById('val-' + id);
  if (el) el.innerText = value + suffix;
  updateSliderTrack(document.getElementById('slider-' + id));
}
['latency','error','traffic'].forEach(id => updateSliderTrack(document.getElementById('slider-' + id)));

/* ── Neuro Chat ────────────────────────────────────────────── */
let isTyping = false;
function predictFailure() {
  if (isTyping) return;
  const chatContainer = document.getElementById('chat-container');
  if (!chatContainer) return;
  const latency = document.getElementById('slider-latency')?.value || 45;
  const error   = document.getElementById('slider-error')?.value   || 2;
  const traffic = document.getElementById('slider-traffic')?.value || 65;

  chatContainer.insertAdjacentHTML('beforeend', `
    <div class="flex items-start gap-4 justify-end">
      <div class="bg-white/5 border border-white/10 rounded-2xl rounded-tr-none p-4 text-sm text-gray-300 max-w-[85%]">
        <p>Analyze — Latency <span style="color:#00f2fe">${latency}ms</span>, Error <span style="color:#a78bfa">${error}%</span>, Load <span style="color:#34d399">${traffic}%</span></p>
      </div>
      <div class="w-10 h-10 rounded-full bg-gray-800 flex items-center justify-center flex-shrink-0 border border-white/10">
        <i class="ph ph-user" style="color:#9ca3af"></i>
      </div>
    </div>`);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  isTyping = true;

  const tid = 'typing-' + Date.now();
  setTimeout(() => {
    chatContainer.insertAdjacentHTML('beforeend', `
      <div id="${tid}" class="flex items-start gap-4">
        <div class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0" style="background:#0f172a;border:1px solid rgba(124,58,237,.4)">
          <i class="ph ph-brain" style="color:#00f2fe;font-size:1.2rem"></i>
        </div>
        <div class="bg-white/5 border border-white/10 rounded-2xl rounded-tl-none p-4 flex gap-1.5" style="height:48px">
          <span style="width:6px;height:6px;background:#9ca3af;border-radius:50%;animation:bounce 1s infinite"></span>
          <span style="width:6px;height:6px;background:#9ca3af;border-radius:50%;animation:bounce 1s .2s infinite"></span>
          <span style="width:6px;height:6px;background:#9ca3af;border-radius:50%;animation:bounce 1s .4s infinite"></span>
        </div>
      </div>`);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }, 300);

  setTimeout(() => {
    document.getElementById(tid)?.remove();
    let text = '', cls = '#34d399';
    if (traffic > 85 || error > 10 || latency > 300) {
      text = 'CRITICAL: Trie Router collision probability HIGH. Worker_Offline detected. Initiating failover sequence.';
      cls = '#f87171';
    } else if (traffic > 65 || latency > 150) {
      text = 'WARNING: HashMap State Manager queue saturation approaching 80%. Recommend traffic redistribution.';
      cls = '#fbbf24';
    } else {
      text = 'NOMINAL: All mesh nodes synchronized. Trie routing at peak efficiency. Zero anomaly signatures detected.';
    }
    const mid = 'msg-' + Date.now();
    chatContainer.insertAdjacentHTML('beforeend', `
      <div class="flex items-start gap-4">
        <div class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0" style="background:#0f172a;border:1px solid rgba(124,58,237,.4)">
          <i class="ph ph-brain" style="color:#00f2fe;font-size:1.2rem"></i>
        </div>
        <div class="bg-white/5 border border-white/10 rounded-2xl rounded-tl-none p-4 text-sm max-w-[85%]">
          <p id="${mid}" style="color:${cls};font-weight:600;font-family:'JetBrains Mono',monospace;font-size:.8rem"></p>
        </div>
      </div>`);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    let i = 0;
    const el = document.getElementById(mid);
    const type = () => {
      if (!el) return;
      el.textContent += text[i++];
      chatContainer.scrollTop = chatContainer.scrollHeight;
      if (i < text.length) setTimeout(type, 18); else isTyping = false;
    };
    type();
  }, 1600);
}

/* ── Live Traffic Simulation ───────────────────────────────── */
const protocols = [
  { name:'HTTP',  cls:'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' },
  { name:'TCP',   cls:'bg-amber-500/10 text-amber-400 border border-amber-500/20' },
  { name:'UDP',   cls:'bg-gray-500/10 text-gray-400 border border-gray-500/30' },
  { name:'WSS',   cls:'bg-violet-500/10 text-violet-400 border border-violet-500/20' },
  { name:'gRPC',  cls:'bg-pink-500/10 text-pink-400 border border-pink-500/20' },
];
const getIP = () => Array.from({length:4},()=>Math.floor(Math.random()*255)).join('.');
setInterval(() => {
  const tbody = document.getElementById('traffic-table-body');
  const tabVisible = document.getElementById('tab-traffic')?.classList.contains('opacity-100');
  if (!tbody || !tabVisible) return;
  const d = new Date();
  const ts = [d.getHours(),d.getMinutes(),d.getSeconds()].map(v=>String(v).padStart(2,'0')).join(':') + '.' + String(d.getMilliseconds()).padStart(3,'0');
  const p = protocols[Math.floor(Math.random()*protocols.length)];
  const isErr = Math.random() > 0.87;
  const statHtml = isErr
    ? `<span style="color:#f87171">● Dropped</span>`
    : `<span style="color:#34d399">● ${p.name==='HTTP'?'200 OK':p.name==='WSS'?'Connected':'Active'}</span>`;
  const tr = document.createElement('tr');
  tr.style.cssText = 'animation:slideDown .3s ease forwards';
  tr.innerHTML = `
    <td style="padding:12px 16px;color:#6b7280;font-family:monospace;font-size:.8rem">${ts}</td>
    <td style="padding:12px 16px;font-size:.8rem;color:${isErr?'#f87171':'#e5e7eb'}">${getIP()}</td>
    <td style="padding:12px 16px;font-size:.8rem;color:#9ca3af">10.0.${Math.floor(Math.random()*5)}.${Math.floor(Math.random()*20)+1}</td>
    <td style="padding:12px 16px"><span class="${p.cls}" style="padding:3px 10px;border-radius:6px;font-size:.7rem;font-weight:600;font-family:monospace">${p.name}</span></td>
    <td style="padding:12px 16px;font-size:.8rem;font-family:monospace">${statHtml}</td>`;
  tbody.insertBefore(tr, tbody.firstChild);
  if (tbody.children.length > 14) tbody.removeChild(tbody.lastChild);
}, 1200);

/* ── DSA Node pulse randomizer ─────────────────────────────── */
setInterval(() => {
  const nodes = document.querySelectorAll('.dsa-node');
  nodes.forEach(node => {
    if (Math.random() > 0.7) node.classList.toggle('active-pulse');
  });
}, 2000);

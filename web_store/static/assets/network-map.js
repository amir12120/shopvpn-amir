(()=>{'use strict';
const root=document.getElementById('shopvpn-network-map');
if(!root)return;
const fa=document.documentElement.lang!=='en';
const T=fa?{title:'شبکه هوشمند ShopVPN',sub:'یک نمای شماتیک از مسیر امن اتصال شما؛ بدون نقشه واقعی و با انیمیشن زنده',online:'گره فعال',latency:'پینگ تقریبی',secure:'تونل رمزنگاری‌شده',fast:'مسیر بهینه'}:{title:'ShopVPN Smart Network',sub:'A schematic view of your secure route — no real map, just live motion',online:'Active nodes',latency:'Estimated ping',secure:'Encrypted tunnel',fast:'Optimal route'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function shell(){root.innerHTML=`
<section class="nm-schematic" aria-labelledby="network-map-title">
  <div class="nm-s-head"><div><span class="nm-eyebrow">${fa?'اتصال هوشمند':'SMART CONNECTION'}</span><h2 id="network-map-title">${T.title}</h2><p>${T.sub}</p></div><div class="nm-live"><i></i>${fa?'اتصال پایدار':'Connection stable'}</div></div>
  <div class="nm-s-grid">
    <div class="nm-visual">
      <div class="nm-orbit orbit-a"></div><div class="nm-orbit orbit-b"></div><div class="nm-orbit orbit-c"></div>
      <div class="nm-line l1"></div><div class="nm-line l2"></div><div class="nm-line l3"></div><div class="nm-line l4"></div><div class="nm-line l5"></div>
      <div class="nm-packet p1"></div><div class="nm-packet p2"></div><div class="nm-packet p3"></div><div class="nm-packet p4"></div>
      <div class="nm-device"><span class="nm-device-icon">⌁</span><b>${fa?'دستگاه شما':'Your device'}</b><small>${fa?'اتصال امن':'Secure client'}</small></div>
      <div class="nm-core"><div class="nm-core-ring"></div><span>SV</span><b>ShopVPN</b><small>${fa?'هاب امن':'Secure hub'}</small></div>
      <button class="nm-node n1" type="button"><i></i><span>🇩🇪 Frankfurt</span><small>52 ms</small></button>
      <button class="nm-node n2" type="button"><i></i><span>🇳🇱 Amsterdam</span><small>56 ms</small></button>
      <button class="nm-node n3" type="button"><i></i><span>🇬🇧 London</span><small>68 ms</small></button>
      <button class="nm-node n4" type="button"><i></i><span>🇦🇪 Dubai</span><small>48 ms</small></button>
      <button class="nm-node n5" type="button"><i></i><span>🇹🇷 Istanbul</span><small>34 ms</small></button>
      <div class="nm-chip c1">⚡ ${fa?'مسیر بهینه':'Optimal route'}</div><div class="nm-chip c2">🛡️ ${fa?'رمزنگاری فعال':'Encrypted'}</div>
    </div>
    <div class="nm-s-side">
      <div class="nm-stat"><span>${T.online}</span><b>5</b><em>●</em></div>
      <div class="nm-stat"><span>${T.latency}</span><b>48 <small>ms</small></b><em>↗</em></div>
      <div class="nm-stat"><span>${T.secure}</span><b>99.9<small>%</small></b><em>✓</em></div>
      <div class="nm-route-card"><div><span>${fa?'مسیر پیشنهادی':'Recommended route'}</span><b>🇮🇷 Tehran <strong>→</strong> 🇩🇪 Frankfurt</b></div><i>52 ms</i></div>
      <div class="nm-mini-bars"><span style="--h:42%"></span><span style="--h:68%"></span><span style="--h:55%"></span><span style="--h:82%"></span><span style="--h:63%"></span><span style="--h:92%"></span><span style="--h:72%"></span><span style="--h:86%"></span><span style="--h:58%"></span><span style="--h:76%"></span></div>
      <small class="nm-foot-note">${fa?'ترافیک به‌صورت نمایشی و غیرواقعی برای نمایش وضعیت شبکه':'Traffic is illustrative and not a real-time geographic map'}</small>
    </div>
  </div>
</section>`;
root.querySelectorAll('.nm-node').forEach(btn=>btn.addEventListener('click',()=>{root.querySelectorAll('.nm-node').forEach(x=>x.classList.remove('selected'));btn.classList.add('selected')}));
}
function sync(){const p=(location.hash||'#/').replace(/^#\//,'').split('/')[0];const show=p==='';root.hidden=!show;if(show&&!root.querySelector('.nm-schematic'))shell()}
sync();window.addEventListener('hashchange',sync);
})();

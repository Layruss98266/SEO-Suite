// ── Server health preflight ───────────────────────────────────────────────────
function withServerCheck(fn, logFn) {
  fetch('/health')
    .then(r => r.ok ? fn() : Promise.reject(new Error('Server returned ' + r.status)))
    .catch(() => logFn('Cannot reach the server — make sure main.py is running on port 8080.', true));
}

// ── Use Cases definition ──────────────────────────────────────────────────────
const UC_DEFS = {
  crawlability:  {label:'Crawl Access',  icon:'🕷️',color:'#6366F1',bg:'#EEF2FF',
    desc:'robots.txt · HTTP status · redirects · canonical · broken links · sitemaps · meta robots', requires:null,
    formats:['url','domain','sitemap','csv'], hint:'Checks robots.txt, redirects, canonical, noindex, broken links, sitemap'},
  on_page:       {label:'On-Page SEO',   icon:'📝',color:'#0EA5E9',bg:'#F0F9FF',
    desc:'Title · meta · headings · schema · OG tags · hreflang · readability · favicon', requires:null,
    formats:['url','csv'], hint:'Analyses title, meta, headings, schema, Open Graph, hreflang, readability'},
  site_health:   {label:'Site Health',   icon:'🛡️',color:'#14B8A6',bg:'#F0FDFA',
    desc:'SSL · HTTPS · mixed content · domain age · SPF · DMARC · MX · security headers', requires:null,
    formats:['url','domain'], hint:'SSL grade, HTTPS enforcement, DNS records, security headers, domain age'},
  performance:   {label:'Performance',   icon:'⚡', color:'#F59E0B',bg:'#FFFBEB',
    desc:'PageSpeed · LCP · CLS · FCP · INP · mobile vs desktop · GSC URL inspection', requires:'PageSpeed API key',
    formats:['url','csv'], hint:'Core Web Vitals, PageSpeed scores, mobile vs desktop gap'},
  search_console:{label:'Search Console',icon:'📊',color:'#10B981',bg:'#ECFDF5',
    desc:'Clicks · impressions · positions · top queries · CTR · coverage · manual actions', requires:'GSC API',
    formats:['url'], hint:'Clicks, impressions, positions, coverage errors, manual actions'},
  authority:     {label:'Authority',     icon:'🔗',color:'#8B5CF6',bg:'#F5F3FF',
    desc:'Backlinks · domain authority · page authority · domain rank · spam score · nofollow ratio', requires:null,
    formats:['url','domain'], hint:'Backlinks, DA/PA, referring domains, domain rank, spam score'},
  rankings:      {label:'Rankings',      icon:'🏆',color:'#EF4444',bg:'#FEF2F2',
    desc:'Keyword positions · SERP features · competitor analysis · rank change · traffic share', requires:'SerpAPI key',
    formats:['url'], hint:'Live keyword rankings, SERP features, rank changes, traffic share estimate'},
};

// Individual tasks per use case — IDs match backend tool names
const TASK_DEFS = {
  crawlability: [
    {id:'robots',         label:'robots.txt'},
    {id:'http_status',    label:'HTTP status'},
    {id:'redirect',       label:'Redirects'},
    {id:'broken_links',   label:'Broken links'},
    {id:'internal_links', label:'Internal links'},
    {id:'sitemap',        label:'Sitemap validation'},
    {id:'canonical',      label:'Canonical URL'},
    {id:'meta_robots',    label:'Meta robots / X-Robots-Tag'},
  ],
  on_page: [
    {id:'canonical',        label:'Canonical URL'},
    {id:'title',            label:'Title tag'},
    {id:'meta_description', label:'Meta description'},
    {id:'headings',         label:'Headings (H1–H3)'},
    {id:'image_alt',        label:'Image alt text'},
    {id:'word_count',       label:'Word count'},
    {id:'readability',      label:'Readability'},
    {id:'schema',           label:'Schema markup'},
    {id:'hreflang',         label:'Hreflang tags'},
    {id:'ttfb',             label:'TTFB (response time)'},
    {id:'og_tags',          label:'Open Graph / Twitter cards'},
    {id:'meta_robots',      label:'Meta robots / X-Robots-Tag'},
    {id:'favicon',          label:'Favicon'},
  ],
  site_health: [
    {id:'ssl',                label:'SSL / TLS grade'},
    {id:'domain_age',         label:'Domain age & expiry'},
    {id:'mixed_content',      label:'Mixed content (HTTP on HTTPS)'},
    {id:'https_enforcement',  label:'HTTPS enforcement'},
    {id:'security_headers',   label:'Security headers'},
    {id:'spf',                label:'SPF record'},
    {id:'dmarc',              label:'DMARC policy'},
    {id:'mx_records',         label:'MX records'},
  ],
  performance: [
    {id:'pagespeed_mobile',  label:'PageSpeed — Mobile'},
    {id:'pagespeed_desktop', label:'PageSpeed — Desktop'},
    {id:'mobile',            label:'Mobile vs Desktop gap'},
    {id:'crawlability',      label:'GSC URL inspection'},
    {id:'lcp',               label:'LCP — Largest Contentful Paint'},
    {id:'cls',               label:'CLS — Cumulative Layout Shift'},
    {id:'fcp',               label:'FCP — First Contentful Paint'},
    {id:'inp',               label:'INP — Interaction to Next Paint'},
  ],
  search_console: [
    {id:'clicks_impressions', label:'Clicks & impressions'},
    {id:'top_queries',        label:'Top queries'},
    {id:'position_tracker',   label:'Position tracker'},
    {id:'ctr_analyzer',       label:'CTR analyzer'},
    {id:'coverage_errors',    label:'Coverage errors'},
    {id:'sitemaps_status',    label:'Sitemaps status'},
    {id:'manual_actions',     label:'Manual actions'},
  ],
  authority: [
    {id:'backlinks',          label:'Backlinks'},
    {id:'domain_authority',   label:'Domain authority'},
    {id:'page_authority',     label:'Page authority'},
    {id:'referring_domains',  label:'Referring domains'},
    {id:'domain_rank',        label:'Domain rank'},
    {id:'broken_backlinks',   label:'Broken backlinks'},
    {id:'nofollow_ratio',     label:'Nofollow ratio'},
    {id:'spam_score',         label:'Spam score'},
  ],
  rankings: [
    {id:'rank_tracker',   label:'Keyword rankings'},
    {id:'serp_features',  label:'SERP features'},
    {id:'competitor',     label:'Competitor comparison'},
    {id:'rank_change',    label:'Rank change tracker'},
    {id:'traffic_share',  label:'Traffic share estimate'},
  ],
};

const PRESETS = {
  all:         Object.keys(UC_DEFS),
  technical:   ['crawlability','on_page','site_health'],
  performance: ['crawlability','performance'],
  visibility:  ['search_console','authority','rankings'],
  none:        [],
};

// Per-use-case info: checks list, when-to-use, example output, API setup
const UC_INFO = {
  crawlability: {
    desc: 'Checks every layer that controls whether Googlebot can reach and index your page — from robots.txt rules down to internal link health.',
    checks: ['robots.txt','HTTP status','Redirects','Broken links','Internal links','Sitemap validation','Canonical URL','Meta robots / X-Robots-Tag'],
    when: 'Use this when pages are missing from Google Search, after a site migration, or when taking over a new client site.',
    example:
`URL: https://example.com/blog/post
  robots.txt      PASS   Allowed for Googlebot
  HTTP status     PASS   200 OK
  Redirects       WARN   2 hops (→ /blog → /blog/post)
  Broken links    FAIL   3 broken internal links found
  Internal links  PASS   24 internal links found
  Sitemap         PASS   Listed in /sitemap.xml
  Canonical       PASS   Self-referencing canonical
  Meta robots     PASS   No noindex directive
  ─────────────────────────────────
  Score: 71 / 100`,
    tips: ['Run via Sitemap to check all URLs at once','Redirect chains > 2 hops waste crawl budget'],
    api: null,
  },
  on_page: {
    desc: 'Analyses every on-page signal Google uses to understand what your page is about and how to display it in search results.',
    checks: ['Canonical URL','Title tag','Meta description','Headings (H1–H3)','Image alt text','Word count','Readability','Schema markup','Hreflang tags','TTFB (response time)','Open Graph / Twitter cards','Meta robots / X-Robots-Tag','Favicon'],
    when: 'Run before publishing new content, after a rankings drop, or as part of a content refresh to find quick-win optimisation gaps.',
    example:
`URL: https://example.com/services
  Title           PASS   58 chars — "SEO Audit Tools | Example"
  Meta desc       WARN   Missing — write 120–160 chars
  H1              PASS   Exactly 1 H1 found
  Word count      PASS   1 240 words
  Alt text        FAIL   4 of 9 images missing alt text
  Schema          PASS   Organization schema detected
  Open Graph      WARN   og:image not set
  Readability     PASS   Flesch score 62  (Good)
  ─────────────────────────────────
  Score: 68 / 100`,
    tips: ['Upload a CSV to audit dozens of pages in one run','Alt text failures are fast wins — fix with a content pass'],
    api: null,
  },
  site_health: {
    desc: 'Checks the security, trust, and technical foundation of your domain — things Google factors into site-wide authority.',
    checks: ['SSL / TLS grade','Domain age & expiry','Mixed content (HTTP on HTTPS)','HTTPS enforcement','Security headers','SPF record','DMARC policy','MX records'],
    when: 'Use on new client takeovers, pre-launch checklists, or any time you need a quick trust & security snapshot without running a full audit.',
    example:
`Domain: example.com
  SSL grade         PASS   A+  (valid · 365 days remaining)
  Domain age        PASS   6 years 3 months
  Mixed content     PASS   None detected
  HTTPS enforcement PASS   HTTP → HTTPS redirect confirmed
  Security headers  WARN   Missing: CSP, X-Frame-Options
  SPF record        PASS   Present
  DMARC             WARN   p=none  (set p=reject to enforce)
  MX records        PASS   3 records found
  ─────────────────────────────────
  Score: 79 / 100`,
    tips: ['DMARC p=none is a common warning — easy fix in DNS','Use Domain input to check the whole site in one go'],
    api: null,
  },
  performance: {
    desc: 'Pulls live Core Web Vitals and PageSpeed scores for both mobile and desktop, pinpointing the exact metrics dragging your score down.',
    checks: ['PageSpeed — Mobile','PageSpeed — Desktop','Mobile vs Desktop gap','GSC URL inspection','LCP — Largest Contentful Paint','CLS — Cumulative Layout Shift','FCP — First Contentful Paint','INP — Interaction to Next Paint'],
    when: 'Run before a Google core update, when Core Web Vitals turn red in Search Console, or to find the slowest pages in a CSV of URLs.',
    example:
`URL: https://example.com/
  PageSpeed mobile  WARN   61 / 100
  PageSpeed desktop PASS   88 / 100
  Mobile gap        WARN   27-pt gap — optimise images & defer JS
  GSC inspection    PASS   URL indexed, no issues
  LCP               WARN   3.2 s   (target < 2.5 s)
  CLS               PASS   0.04    (target < 0.1)
  FCP               PASS   1.4 s   (target < 1.8 s)
  INP               PASS   78 ms   (target < 200 ms)
  ─────────────────────────────────
  Score: 63 / 100`,
    tips: ['Upload a CSV to rank pages by score — fix worst first','27-pt mobile gap usually means unoptimised images or render-blocking JS'],
    api: {
      title: 'PageSpeed Insights API key needed',
      steps: [
        'Go to <a href="https://console.cloud.google.com/" target="_blank">console.cloud.google.com</a> and sign in.',
        'APIs &amp; Services → Library → search <b>"PageSpeed Insights API"</b> → Enable.',
        'Credentials → <b>+ Create Credentials → API key</b> → copy the key.',
        'In SEO Suite: open <b>Settings</b> → paste into <code>PAGESPEED_API_KEY</code> → Save.',
      ],
    },
  },
  search_console: {
    desc: 'Pulls real click, impression, and position data straight from Google Search Console — no estimates, no third-party guesses.',
    checks: ['Clicks & impressions','Top queries','Position tracker','CTR analyzer','Coverage errors','Sitemaps status','Manual actions'],
    when: 'Use when you need to see which queries are driving traffic to a URL, diagnose a traffic drop, or confirm a page has no manual actions.',
    example:
`URL: https://example.com/blog/seo-guide
  Clicks (28d)     1 240
  Impressions     18 500
  CTR               6.7 %
  Avg. position    12.4

  Top queries:
    "seo audit tool"          pos 8   · 380 clicks
    "free seo checker"        pos 14  · 210 clicks
    "on page seo checklist"   pos 19  ·  90 clicks

  Coverage errors  PASS   None
  Manual actions   PASS   None
  ─────────────────────────────────
  Score: 82 / 100`,
    tips: ['The site URL in Settings must exactly match your GSC property','Pages with high impressions but low CTR are quick wins — improve the title'],
    api: {
      title: 'Google Search Console credentials needed',
      steps: [
        'Go to <a href="https://console.cloud.google.com/" target="_blank">console.cloud.google.com</a> → APIs &amp; Services → Library → enable <b>"Google Search Console API"</b>.',
        'IAM &amp; Admin → Service Accounts → Create → download the <b>JSON key</b>.',
        'Rename it <code>gsc_credentials.json</code> and place it in the SEO Suite root folder (next to <code>main.py</code>).',
        'In <a href="https://search.google.com/search-console" target="_blank">Search Console</a>: Settings → Users and permissions → Add user → paste the service account email → role <b>Full</b>.',
        'In SEO Suite: <b>Settings</b> → set <b>Site URL</b> to match your GSC property exactly → Save.',
      ],
    },
  },
  authority: {
    desc: "Measures your domain's backlink profile and authority score — the external signals that tell Google how much to trust your site.",
    checks: ['Backlinks','Domain authority','Page authority','Referring domains','Domain rank','Broken backlinks','Nofollow ratio','Spam score'],
    when: 'Use before or after a link-building campaign, when comparing your domain to a competitor, or to find broken backlinks worth reclaiming.',
    example:
`Domain: example.com
  Domain Authority    54   (Moz)
  Page Authority      38
  Backlinks        4 821
  Referring domains  312
  Broken backlinks    24  ← reclaim opportunities
  Domain rank         67  (DataForSEO)
  Dofollow           98 %
  Spam score          4 %  PASS
  ─────────────────────────────────
  Score: 74 / 100`,
    tips: ['Broken backlinks are free link equity — reach out and redirect','Works without an API key but data is limited — add Moz or DataForSEO for full backlink counts'],
    api: {
      title: 'Optional: add Moz or DataForSEO for full backlink data',
      steps: [
        '<b>Moz (free, 10 req/month):</b> <a href="https://moz.com/products/api" target="_blank">moz.com/products/api</a> → Get free access → copy <b>Access ID</b> &amp; <b>Secret Key</b> → Settings.',
        '<b>DataForSEO (pay-as-you-go ~$0.002/req):</b> <a href="https://dataforseo.com/" target="_blank">dataforseo.com</a> → sign up → copy login &amp; password → Settings.',
      ],
    },
  },
  rankings: {
    desc: 'Checks where your page ranks in live Google results for your target keywords, and shows who is outranking you.',
    checks: ['Keyword rankings','SERP features','Competitor comparison','Rank change tracker','Traffic share estimate'],
    when: 'Run weekly to track keyword movement, after publishing new content, or to see which competitors are outranking you and why.',
    example:
`URL: https://example.com/  ·  3 keywords
  Keyword rankings:
    "seo audit tool"        Rank  7  ▲2
    "on page seo checker"   Rank 14  ▼1
    "free website seo test" Rank 23  ▲5
  SERP features     PASS   Featured Snippet detected for kw #1
  Competitor:       moz.com · semrush.com · ahrefs.com
  Rank change       WARN   2 keywords dropped since last run
  Traffic share     PASS   ~4.2 % estimated organic share
  ─────────────────────────────────
  Avg. position: 14.7   Score: 55 / 100`,
    tips: ['Enter keywords comma-separated in the Keywords field','Free SerpAPI tier: 100 searches/month — enough for weekly tracking of ~15 keywords'],
    api: {
      title: 'SerpAPI key needed for live rank data',
      steps: [
        'Go to <a href="https://serpapi.com/" target="_blank">serpapi.com</a> → Register (free, no credit card).',
        'Dashboard → copy your <b>API Key</b>.',
        'In SEO Suite: <b>Settings</b> → paste into <code>SERPAPI_KEY</code> → Save.',
        'Enter target keywords (comma-separated) in the Keywords field above.',
      ],
    },
  },
};

let selectedUC = new Set(Object.keys(UC_DEFS));
// Per-use-case task selection (default = all tasks selected)
let selectedTasks = {};
Object.entries(TASK_DEFS).forEach(([uc,tasks])=>{
  selectedTasks[uc] = new Set(tasks.map(t=>t.id));
});
// Track which use-case cards have their task list expanded
let expandedUC = new Set();

// ── Navigation ────────────────────────────────────────────────────────────────
function nav(el){
  // Guard against navigating away from Settings with unsaved changes.
  if(typeof _settingsLeaveGuard==='function' && !_settingsLeaveGuard(el.dataset.panel)) return;
  document.querySelectorAll('.sb-item').forEach(i=>i.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  const panelId=el.dataset.panel;
  const panel=document.getElementById('panel-'+panelId);
  if(panel) panel.classList.add('active');
  // Update breadcrumb
  const sec=document.getElementById('tb-crumb-section');
  const pg=document.getElementById('tb-crumb-page');
  if(sec) sec.textContent=el.dataset.section||'Section';
  if(pg)  pg.textContent=el.dataset.name||'Page';
  // Sync navbar active state
  document.querySelectorAll('.navbar .nav-dd-item,.navbar .nav-link-direct').forEach(n=>n.classList.remove('active'));
  document.querySelectorAll('.navbar .nav-link').forEach(n=>n.classList.remove('active'));
  const navEl=document.querySelector(`.navbar [data-panel="${panelId}"]`);
  if(navEl){
    navEl.classList.add('active');
    const grp=navEl.closest('.nav-group');
    if(grp) grp.querySelector('.nav-link').classList.add('active');
  }
  // Refresh panel-specific data on navigate
  if(panelId==='home') { _stopRepAutoRefresh(); updateHomeStats(); }
  else if(panelId==='reports') loadReports();
  else { _stopRepAutoRefresh(); if(panelId==='trend') loadTrend(); }
}
function navTo(panelId){
  const item=document.querySelector('.sb-item[data-panel="'+panelId+'"]');
  if(item) nav(item);
}
// Called from navbar items — delegates to existing nav() via hidden sb-items
function navLink(panelId){
  navTo(panelId);
}

// ── Collapsible sidebar groups ────────────────────────────────────────────────
function sbToggle(id) {
  const group = document.getElementById(id);
  if (!group) return;
  const collapsed = group.classList.toggle('sb-group-collapsed');
  try {
    const state = JSON.parse(localStorage.getItem('sb-groups') || '{}');
    state[id] = collapsed;
    localStorage.setItem('sb-groups', JSON.stringify(state));
  } catch(e) {}
}

function sbRestoreGroups() {
  try {
    const state = JSON.parse(localStorage.getItem('sb-groups') || '{}');
    document.querySelectorAll('.sb-group').forEach(g => {
      if (g.id && state[g.id] !== undefined) {
        g.classList.toggle('sb-group-collapsed', state[g.id]);
      }
    });
  } catch(e) {}
}

// ── Sidebar toggle ────────────────────────────────────────────────────────────
function toggleSidebar(){
  const sb=document.getElementById('sidebar');
  const mask=document.getElementById('sb-mask');
  if(window.innerWidth<=720){
    const open=sb.classList.toggle('open');
    mask.classList.toggle('on',open);
  }else{
    const collapsed=sb.classList.toggle('collapsed');
    localStorage.setItem('seo-sb-collapsed', collapsed?'1':'0');
  }
}
if(localStorage.getItem('seo-sb-collapsed')==='1' && window.innerWidth>720){
  document.addEventListener('DOMContentLoaded',()=>{
    document.getElementById('sidebar')?.classList.add('collapsed');
  });
}

// ── Top-bar jump-to search (Ctrl+K) ───────────────────────────────────────────
let _tbResults=[], _tbResultIdx=-1;
function _allNavItems(){
  return [...document.querySelectorAll('.sb-item')].map(el=>({
    el, panel:el.dataset.panel,
    section:el.dataset.section||'',
    name:el.dataset.name||el.textContent.trim()
  }));
}
function tbSearch(q){
  const box=document.getElementById('tb-search-results');
  q=(q||'').trim().toLowerCase();
  if(!q){box.classList.remove('on');box.innerHTML='';_tbResults=[];return;}
  const items=_allNavItems().filter(x=>
    x.name.toLowerCase().includes(q)||x.section.toLowerCase().includes(q)
  ).slice(0,8);
  _tbResults=items; _tbResultIdx=-1;
  if(!items.length){
    box.innerHTML='<div class="tb-search-result" style="cursor:default;color:var(--text3)">No matches</div>';
    box.classList.add('on'); return;
  }
  box.innerHTML=items.map((x,i)=>`
    <div class="tb-search-result" data-i="${i}" onclick="tbJump(${i})">
      <span>${x.name}</span>
      <span class="tb-search-result-section">${x.section}</span>
    </div>`).join('');
  box.classList.add('on');
}
function tbJump(i){
  const r=_tbResults[i]; if(!r) return;
  nav(r.el); // nav() already calls loadReports/loadTrend/updateHomeStats
  if(r.panel==='compare') loadCompare();
  document.getElementById('tb-search-input').value='';
  tbSearch('');
}
function tbSearchKey(e){
  const box=document.getElementById('tb-search-results');
  if(e.key==='Escape'){e.target.value='';tbSearch('');e.target.blur();return;}
  if(!_tbResults.length) return;
  if(e.key==='ArrowDown'){e.preventDefault(); _tbResultIdx=Math.min(_tbResults.length-1,_tbResultIdx+1);_tbHighlight();}
  else if(e.key==='ArrowUp'){e.preventDefault(); _tbResultIdx=Math.max(0,_tbResultIdx-1);_tbHighlight();}
  else if(e.key==='Enter'){e.preventDefault(); tbJump(_tbResultIdx<0?0:_tbResultIdx);}
}
function _tbHighlight(){
  document.querySelectorAll('.tb-search-result').forEach((el,i)=>{
    el.classList.toggle('kb', i===_tbResultIdx);
    if(i===_tbResultIdx) el.scrollIntoView({block:'nearest'});
  });
}
// Keyboard shortcuts
document.addEventListener('keydown',e=>{
  // Ctrl+K / Cmd+K opens command palette
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){
    e.preventDefault();
    openCmdPalette();
    return;
  }
  // Enter inside the indexing/audit run forms triggers Start
  if(e.key==='Enter' && !e.shiftKey){
    const t=e.target;
    if(t && t.tagName==='INPUT' && t.type!=='checkbox' && t.type!=='radio'){
      const idxPanel=document.getElementById('panel-idx-run');
      const audPanel=document.getElementById('panel-aud-run');
      if(idxPanel && idxPanel.classList.contains('active') && idxPanel.contains(t)){
        e.preventDefault(); startIndex();
      } else if(audPanel && audPanel.classList.contains('active') && audPanel.contains(t)){
        e.preventDefault(); startAudit();
      }
    }
  }
});
// Click outside closes search results
document.addEventListener('click',e=>{
  const box=document.getElementById('tb-search-results');
  const wrap=document.querySelector('.tb-search');
  if(box&&wrap&&!wrap.contains(e.target)) box.classList.remove('on');
});

// ── Command Palette (Ctrl+K) ──────────────────────────────────────────────────
let _cmdResults=[], _cmdIdx=-1;

function openCmdPalette(){
  document.getElementById('cmd-mask').classList.add('open');
  const inp=document.getElementById('cmd-input');
  inp.value='';
  inp.focus();
  cmdSearch('');
}
function closeCmdPalette(){
  document.getElementById('cmd-mask').classList.remove('open');
  document.getElementById('cmd-input').value='';
  _cmdResults=[];_cmdIdx=-1;
}
function cmdSearch(q){
  const box=document.getElementById('cmd-results');
  q=(q||'').trim().toLowerCase();
  const all=_allNavItems();
  const filtered=q
    ? all.filter(x=>x.name.toLowerCase().includes(q)||x.section.toLowerCase().includes(q))
    : all;
  _cmdResults=filtered; _cmdIdx=-1;
  if(!filtered.length){
    box.innerHTML='<div class="cmd-empty">No results for "'+q+'"</div>';
    return;
  }
  // Group by section
  const groups={};
  filtered.forEach(x=>{
    const s=x.section||'Other';
    if(!groups[s]) groups[s]=[];
    groups[s].push(x);
  });
  let idx=0;
  box.innerHTML=Object.entries(groups).map(([section,items])=>`
    <div class="cmd-section-label">${section}</div>
    ${items.map(x=>`
      <div class="cmd-item" data-i="${idx++}" onclick="cmdJump(${idx-1})">
        <span>${x.name}</span>
        <span class="cmd-item-badge">${x.section}</span>
      </div>`).join('')}
  `).join('');
  // Re-map results flat order to match rendered order
  _cmdResults=filtered;
}
function cmdJump(i){
  const r=_cmdResults[i]; if(!r) return;
  nav(r.el);
  if(r.panel==='compare') loadCompare();
  closeCmdPalette();
}
function cmdKey(e){
  if(e.key==='Escape'){closeCmdPalette();return;}
  if(!_cmdResults.length) return;
  if(e.key==='ArrowDown'){e.preventDefault();_cmdIdx=Math.min(_cmdResults.length-1,_cmdIdx+1);_cmdHighlight();}
  else if(e.key==='ArrowUp'){e.preventDefault();_cmdIdx=Math.max(0,_cmdIdx-1);_cmdHighlight();}
  else if(e.key==='Enter'){e.preventDefault();cmdJump(_cmdIdx<0?0:_cmdIdx);}
}
function _cmdHighlight(){
  document.querySelectorAll('#cmd-results .cmd-item').forEach((el,i)=>{
    el.classList.toggle('kb',i===_cmdIdx);
    if(i===_cmdIdx) el.scrollIntoView({block:'nearest'});
  });
}

// ── Home: render use-case cards ───────────────────────────────────────────────
function renderHomeUC(){
  const g=document.getElementById('home-uc-grid');
  g.innerHTML=Object.entries(UC_DEFS).map(([id,uc])=>{
    const info=UC_INFO[id]||{};
    const checkCount=(info.checks||[]).length;
    const preview=(info.checks||[]).slice(0,3);
    const hasApi=!!info.api;
    return `
    <div class="home-uc" style="--uc-accent:${uc.color}" data-uc-id="${id}" onclick="runSingleUC(this.dataset.ucId)">
      <div class="home-uc-accent"></div>
      <div class="home-uc-top">
        <div class="home-uc-icon" style="background:${uc.bg};color:${uc.color}">${uc.icon}</div>
        <span class="home-uc-count">${checkCount} checks</span>
      </div>
      <div class="home-uc-name">${uc.label}</div>
      <div class="home-uc-desc">${uc.desc}</div>
      <div class="home-uc-pills">
        ${preview.map(c=>`<span class="home-uc-pill">${c}</span>`).join('')}
        ${checkCount>3?`<span class="home-uc-pill home-uc-pill-more">+${checkCount-3} more</span>`:''}
      </div>
      <div class="home-uc-foot">
        ${hasApi
          ?`<span class="home-uc-badge home-uc-badge-api">⚠ API key</span>`
          :`<span class="home-uc-badge home-uc-badge-free">✓ Free</span>`}
        <span class="home-uc-run">Run →</span>
      </div>
    </div>`;
  }).join('');
}
function runSingleUC(id){
  const uc=UC_DEFS[id];
  if(uc){
    const el=document.querySelector(`[data-panel="uc-runner"][data-name="${uc.label}"]`);
    if(el) nav(el);
    openUseCase(id);
  }
}
function openFullAudit(){ selectedUC=new Set(Object.keys(UC_DEFS)); renderUCSelector(); navTo('aud-run'); }

// ── Navbar: Use Cases dropdown — mirrors sidebar UC list ─────────────────────
function renderNavUC(){
  const list=document.getElementById('nav-uc-list');
  if(!list) return;
  list.innerHTML=Object.entries(UC_DEFS).map(([id,uc])=>`
    <a class="nav-dd-item" data-panel="uc-runner" data-section="Use Cases" data-name="${uc.label}"
       onclick="navLink('uc-runner');openUseCase('${id}')">
      <span style="font-size:15px">${uc.icon}</span>
      <span>${uc.label}</span>
    </a>`).join('');
}

// ── Sidebar: use-case list — driven from UC_DEFS so it stays in sync ──────────
function renderSidebarUC(){
  const list=document.getElementById('sb-uc-list');
  if(!list) return;
  list.innerHTML=Object.entries(UC_DEFS).map(([id,uc])=>{
    const info=UC_INFO[id]||{};
    const n=(info.checks||[]).length;
    return `<div class="sb-item" data-panel="uc-runner" data-section="Use Cases" data-name="${uc.label}"
        onclick="nav(this);openUseCase('${id}')">
      <span class="si sb-uc-emoji" style="color:${uc.color}">${uc.icon}</span>
      <span class="sb-text">${uc.label}</span>
      ${n?`<span class="sb-uc-badge">${n}</span>`:''}
    </div>`;
  }).join('');
}

// ── Audit: use-case selector ──────────────────────────────────────────────────
function renderUCSelector(){
  const g=document.getElementById('uc-selector');
  g.innerHTML=Object.entries(UC_DEFS).map(([id,uc])=>{
    const sel=selectedUC.has(id);
    const tasks=TASK_DEFS[id]||[];
    const selTaskCount=selectedTasks[id]?selectedTasks[id].size:0;
    const total=tasks.length;
    const isExpanded=expandedUC.has(id);
    const taskBadge = sel && total > 0
      ? `<span class="uc-task-badge">${selTaskCount}/${total}</span>` : '';
    const expandBtn = sel && total > 1
      ? `<button class="uc-expand-btn${isExpanded?' open':''}" onclick="event.stopPropagation();toggleExpandUC('${id}')" title="Choose specific tasks">
           <span class="uc-expand-label">${isExpanded?'Hide tasks':'Choose tasks'}</span>
           <span class="uc-expand-arrow">▾</span>
         </button>` : '';
    const taskList = sel && isExpanded
      ? `<div class="uc-tasks" onclick="event.stopPropagation()">
          <div class="uc-tasks-head">
            <span class="uc-tasks-title">Select checks to run</span>
            <button class="uc-tasks-toggle-all" onclick="toggleAllTasks('${id}')">
              ${selTaskCount===total?'Clear all':'Select all'}
            </button>
          </div>
          ${tasks.map(t=>{
            const on=selectedTasks[id].has(t.id);
            return `<label class="uc-task${on?' on':''}">
              <input type="checkbox" ${on?'checked':''} onchange="toggleTask('${id}','${t.id}')">
              <span class="uc-task-check"></span>
              <span class="uc-task-label">${t.label}</span>
            </label>`;
          }).join('')}
        </div>` : '';

    return `<div class="uc-card${sel?' selected':''}${isExpanded?' expanded':''}" id="uc-${id}"
        style="--uc-color:${uc.color};--uc-bg:${uc.bg}" onclick="toggleUC('${id}')">
      <div class="uc-check">✓</div>
      <div class="uc-icon">${uc.icon}</div>
      <div class="uc-card-head">
        <div class="uc-name">${uc.label}</div>
        ${taskBadge}
      </div>
      <div class="uc-desc">${uc.desc}</div>
      ${uc.requires?`<span class="uc-req">${uc.requires}</span>`:''}
      ${expandBtn}
      ${taskList}
    </div>`;
  }).join('');
  updateUCSummary();
  // Disable start button when nothing selected (skip if audit is already running)
  const btn=document.getElementById('aud-btn');
  if(btn && !btn.dataset.running){ btn.disabled=selectedUC.size===0; }
}
function toggleUC(id){
  if(selectedUC.has(id)){
    selectedUC.delete(id);
    expandedUC.delete(id);
  }else{
    selectedUC.add(id);
  }
  renderUCSelector();
  refreshInputForUseCases();
}

// Show/hide audit inputs based on which use cases are active
function refreshInputForUseCases(){
  const kwRow=document.getElementById('kw-row');
  if(kwRow) kwRow.style.display=selectedUC.has('rankings')?'block':'none';

  // Hint banner above URL source: show what each UC needs
  const banner=document.getElementById('aud-uc-hint');
  if(banner){
    const needs=[];
    if(selectedUC.has('rankings'))      needs.push('keywords');
    if(selectedUC.has('search_console'))needs.push('GSC API + site URL');
    if(selectedUC.has('performance'))   needs.push('PageSpeed API key');
    if(selectedUC.has('authority'))     needs.push('Moz/DataForSEO key (optional)');
    banner.style.display=needs.length?'flex':'none';
    banner.querySelector('.uc-hint-text').textContent=
      'Selected use cases need: ' + needs.join(' · ');
  }

  // Site-only use cases (no per-page checks) → recommend "Domain" input
  const onlySite = selectedUC.size>0 &&
    [...selectedUC].every(uc=>['authority','site_health'].includes(uc));
  const audType=document.querySelector('input[name=aud-type]:checked');
  if(onlySite && audType && audType.value==='sitemap'){
    // gentle nudge — switch label to suggest domain works
  }
}
function toggleExpandUC(id){
  if(expandedUC.has(id)) expandedUC.delete(id); else expandedUC.add(id);
  renderUCSelector();
}
function toggleTask(uc,tid){
  if(selectedTasks[uc].has(tid)) selectedTasks[uc].delete(tid);
  else selectedTasks[uc].add(tid);
  // If user unchecks all tasks, also deselect the use case
  if(selectedTasks[uc].size===0){
    selectedUC.delete(uc);
    expandedUC.delete(uc);
  }
  renderUCSelector();
}
function toggleAllTasks(uc){
  const tasks=TASK_DEFS[uc]||[];
  if(selectedTasks[uc].size===tasks.length){
    selectedTasks[uc].clear();
    selectedUC.delete(uc);
    expandedUC.delete(uc);
  }else{
    selectedTasks[uc]=new Set(tasks.map(t=>t.id));
  }
  renderUCSelector();
}
function updateUCSummary(){
  const n=selectedUC.size;
  let totalTasks=0,selTasks=0;
  selectedUC.forEach(uc=>{
    totalTasks+=(TASK_DEFS[uc]||[]).length;
    selTasks+=selectedTasks[uc].size;
  });
  const sub=totalTasks?` · ${selTasks}/${totalTasks} checks`:'';
  document.getElementById('uc-summary').textContent=
    n===0?'No use cases selected':
    n===Object.keys(UC_DEFS).length?`All ${n} use cases selected${sub}`:
    `${n} of ${Object.keys(UC_DEFS).length} use cases selected${sub}`;
}
function applyPreset(name){
  selectedUC=new Set(PRESETS[name]||[]);
  // Reset tasks to all-on for newly selected use cases
  selectedUC.forEach(uc=>{
    selectedTasks[uc]=new Set((TASK_DEFS[uc]||[]).map(t=>t.id));
  });
  expandedUC.clear();
  renderUCSelector();
  refreshInputForUseCases();
}
function renderUCRefTable(){
  const tb=document.getElementById('uc-ref-table');
  const reqLabel=r=>r
    ?`<span style="background:#FEF3C7;color:#92400E;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600">${r}</span>`
    :`<span style="background:#DCFCE7;color:#166534;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600">Free</span>`;
  tb.innerHTML=Object.entries(UC_DEFS).map(([,uc])=>`
    <tr>
      <td><span style="margin-right:6px">${uc.icon}</span><b>${uc.label}</b></td>
      <td style="color:#64748B">${uc.desc}</td>
      <td>${reqLabel(uc.requires)}</td>
    </tr>`).join('');
}

// ── Input toggles ─────────────────────────────────────────────────────────────
let _idxUploadedPath='', _audUploadedPath='';

function _setRow(id,show){const el=document.getElementById(id);if(el)el.style.display=show?'':'none';}

function idxToggle(){
  const t=document.querySelector('input[name=idx-type]:checked').value;
  _setRow('idx-src-row',  t==='sitemap'||t==='domain'||t==='multi');
  _setRow('idx-file-row', t==='csv');
  _setRow('idx-paste-row',t==='paste');
  if(t==='sitemap'||t==='domain'||t==='multi'){
    document.getElementById('idx-lbl').textContent=
      t==='sitemap'?'Sitemap URL':t==='domain'?'Domain':'Sitemap URLs (comma-separated)';
    document.getElementById('idx-src').placeholder=
      t==='sitemap'?'https://example.com/sitemap.xml':t==='domain'?'example.com':'url1, url2';
  }
}
function audToggle(){
  const t=document.querySelector('input[name=aud-type]:checked').value;
  _setRow('aud-src-row',  t==='sitemap'||t==='domain'||t==='crawl');
  _setRow('aud-file-row', t==='csv');
  _setRow('aud-paste-row',t==='paste');
  _setRow('aud-crawl-row',t==='crawl');
  if(t==='sitemap'||t==='domain'||t==='crawl'){
    document.getElementById('aud-lbl').textContent=
      t==='sitemap'?'Sitemap URL':t==='domain'?'Domain':'Start URL (crawl from here)';
    document.getElementById('aud-src').placeholder=
      t==='sitemap'?'https://example.com/sitemap.xml':
      t==='domain'?'example.com':'https://example.com/';
  }
}

// ── File upload ───────────────────────────────────────────────────────────────
function _uploadFile(file, target){
  if(!file) return;
  const fd=new FormData();
  fd.append('file', file);
  const dz=document.getElementById(target+'-dropzone');
  const titleEl=document.getElementById(target==='aud'?'dz-title':'idx-dz-title');
  const subEl=document.getElementById(target==='aud'?'dz-sub':'idx-dz-sub');
  titleEl.textContent='Uploading…';
  subEl.textContent=file.name;
  dz.classList.add('uploading');
  fetch('/api/upload',{method:'POST',body:fd})
    .then(async r=>{
      const ct=r.headers.get('content-type')||'';
      if(!ct.includes('application/json')){
        // Server returned HTML (likely route missing — needs restart)
        const txt=await r.text();
        throw new Error(r.status===404
          ? 'Upload route not found — restart the server (python main.py) to load new code'
          : 'Server returned non-JSON ('+r.status+'): '+txt.slice(0,80));
      }
      return r.json();
    }).then(d=>{
      dz.classList.remove('uploading');
      if(d.error){
        titleEl.textContent='Upload failed';
        subEl.textContent=d.error;
        dz.classList.add('err');
        return;
      }
      dz.classList.remove('err');
      dz.classList.add('done');
      titleEl.textContent='✓ '+d.filename;
      subEl.textContent=`${d.url_count} URL${d.url_count===1?'':'s'} detected — click to choose another`;
      if(target==='aud') _audUploadedPath=d.path;
      else _idxUploadedPath=d.path;
    })
    .catch(e=>{
      dz.classList.remove('uploading');
      dz.classList.add('err');
      titleEl.textContent='Upload failed';
      subEl.textContent=String(e.message||e);
    });
}
function audFileChange(e){_uploadFile(e.target.files[0],'aud');}
function audFileDrop(e){
  e.preventDefault();
  document.getElementById('aud-dropzone').classList.remove('drag');
  if(e.dataTransfer.files&&e.dataTransfer.files[0]) _uploadFile(e.dataTransfer.files[0],'aud');
}
function idxFileChange(e){_uploadFile(e.target.files[0],'idx');}
function idxFileDrop(e){
  e.preventDefault();
  document.getElementById('idx-dropzone').classList.remove('drag');
  if(e.dataTransfer.files&&e.dataTransfer.files[0]) _uploadFile(e.dataTransfer.files[0],'idx');
}

// Resolve final input string for current input mode
function _resolveAuditInput(){
  const t=document.querySelector('input[name=aud-type]:checked').value;
  if(t==='csv')   return _audUploadedPath;
  if(t==='paste'){
    const raw=(document.getElementById('aud-paste').value||'').trim();
    return raw.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean).join(',');
  }
  return document.getElementById('aud-src').value.trim();
}
function _resolveIdxInput(){
  const t=document.querySelector('input[name=idx-type]:checked').value;
  if(t==='csv')   return _idxUploadedPath;
  if(t==='paste'){
    const raw=(document.getElementById('idx-paste').value||'').trim();
    return raw.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean).join(',');
  }
  return document.getElementById('idx-src').value.trim();
}

// ── Shared timer helpers ──────────────────────────────────────────────────────
function fmtSecs(s){
  if(s<60) return s+'s';
  const m=Math.floor(s/60),sec=s%60;
  return m+'m '+(sec<10?'0':'')+sec+'s';
}
function nowTime(){
  const d=new Date();
  return [d.getHours(),d.getMinutes(),d.getSeconds()].map(n=>String(n).padStart(2,'0')).join(':');
}

// ══════════════════════════════════════════════════════════════════════════════
// INDEXING
// ══════════════════════════════════════════════════════════════════════════════
let iTotal=0,iDone=0,iIndexed=0,iNot=0,iErrors=0;
let _idxES=null, _idxTimer=null, _idxRunStart=0, _idxLogFilter='all';
let _idxLastReport='', _idxLastCsv='';
let _idxTimes=[];   // rolling completion timestamps for ETA + throughput

function startIndex(){
  iTotal=0;iDone=0;iIndexed=0;iNot=0;iErrors=0;_idxTimes=[];
  document.getElementById('idx-log').innerHTML='';
  resetStat(['is-checked','is-indexed','is-not','is-errors'],'0');
  document.getElementById('is-rate').textContent='0%';
  document.getElementById('idx-bar').style.width='0%';
  const idxPctEl=document.getElementById('idx-pct');
  if(idxPctEl){idxPctEl.textContent='0%';idxPctEl.classList.remove('done');}
  document.getElementById('idx-elapsed').textContent='';
  document.getElementById('idx-eta').textContent='';
  document.getElementById('idx-live-sub').textContent='Fetching URLs…';
  document.getElementById('idx-done-bar').classList.remove('visible');
  document.getElementById('idx-retry-btn').style.display='none';
  _idxLastReport=''; _idxLastCsv='';

  const idxType=document.querySelector('input[name=idx-type]:checked').value;
  const idxInput=_resolveIdxInput();
  if(!idxInput){
    idxSysLog('Please provide a sitemap URL, domain, file, or paste URLs first', true);
    const idxSrcVisible=document.getElementById('idx-src-row')?.style.display!=='none';
    if(idxSrcVisible) showFieldError('idx-src','This field is required');
    setBtn('idx-btn',false,'🔍 Start Indexing Check');
    return;
  }
  // Backend treats 'paste' as comma-separated URLs (input_type=multi works for that)
  const p={
    input_type: idxType==='paste'?'multi':idxType,
    input:      idxInput,
    pattern:    document.getElementById('idx-pattern').value,
    limit:      +document.getElementById('idx-limit').value||20,
    quiet:      document.getElementById('idx-quiet').checked,
    compare:    document.getElementById('idx-compare').checked,
    headless:   document.getElementById('idx-headless').checked,
  };
  setBtn('idx-btn',true,'Checking…');
  document.getElementById('idx-cancel-btn').style.display='inline-flex';
  document.getElementById('idx-pause-btn').style.display='inline-flex';
  document.getElementById('idx-resume-btn').style.display='none';
  document.getElementById('idx-partial-btn').style.display='none';
  const idxThrEl=document.getElementById('idx-throughput');if(idxThrEl)idxThrEl.style.display='none';
  setBadge('idx-badge','Indexing · Running',true);
  document.getElementById('pip-idx').classList.add('on');
  navTo('idx-live');
  startIdxTimer();

  withServerCheck(() => {
    fetch('/api/index/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
      .then(r=>r.json()).then(d=>{
        if(d.error){ idxSysLog(d.error,true); idxDone(false); return; }
        iTotal=d.total||20;
        streamIndex();
      })
      .catch(e=>{ idxSysLog('Error starting: '+e,true); idxDone(false); });
  }, idxSysLog);
}

function cancelIndex(){
  document.getElementById('idx-live-sub').textContent='Cancelling…';
  idxSysLog('Cancellation requested — saving partial report…',true);
  setBadge('idx-badge','Indexing · Cancelling',false);
  // Keep SSE open so the "cancelled" event (with report path) arrives
  fetch('/api/index/cancel',{method:'POST'}).catch(()=>{
    if(_idxES){_idxES.close();_idxES=null;}
    stopIdxTimer(); idxDone(false);
    setBadge('idx-badge','Indexing · Cancelled',false);
  });
}

function pauseIndex(){
  fetch('/api/index/pause',{method:'POST'}).catch(()=>{});
  document.getElementById('idx-pause-btn').style.display='none';
  document.getElementById('idx-resume-btn').style.display='inline-flex';
  setBadge('idx-badge','Indexing · Paused',false);
  document.getElementById('idx-live-sub').textContent='Paused — click Resume to continue';
  idxSysLog('Paused',true);
}

function resumeIndex(){
  fetch('/api/index/resume',{method:'POST'}).catch(()=>{});
  document.getElementById('idx-resume-btn').style.display='none';
  document.getElementById('idx-pause-btn').style.display='inline-flex';
  setBadge('idx-badge','Indexing · Running',true);
  document.getElementById('idx-live-sub').textContent='Running…';
  idxSysLog('Resumed');
}

function retryErrors(){
  const retryBtn=document.getElementById('idx-retry-btn');
  retryBtn.style.display='none';
  iTotal=0;iDone=0;iIndexed=0;iNot=0;iErrors=0;
  resetStat(['is-checked','is-indexed','is-not','is-errors'],'0');
  document.getElementById('is-rate').textContent='0%';
  document.getElementById('idx-bar').style.width='0%';
  document.getElementById('idx-elapsed').textContent='';
  document.getElementById('idx-eta').textContent='';
  document.getElementById('idx-done-bar').classList.remove('visible');
  document.getElementById('idx-live-sub').textContent='Retrying failed URLs…';
  idxSysLog('Retrying failed URLs…');

  const p={
    headless: document.getElementById('idx-headless').checked,
    quiet:    document.getElementById('idx-quiet').checked,
  };
  setBtn('idx-btn',true,'Retrying…');
  document.getElementById('idx-cancel-btn').style.display='inline-flex';
  document.getElementById('idx-pause-btn').style.display='inline-flex';
  document.getElementById('idx-resume-btn').style.display='none';
  setBadge('idx-badge','Indexing · Retrying',true);
  document.getElementById('pip-idx').classList.add('on');
  startIdxTimer();

  fetch('/api/index/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
    .then(r=>r.json()).then(d=>{
      if(d.error){idxSysLog(d.error,true);idxDone(false);retryBtn.style.display='inline-flex';return;}
      iTotal=d.total||1;
      streamIndex();
    })
    .catch(e=>{idxSysLog('Retry failed: '+e,true);idxDone(false);retryBtn.style.display='inline-flex';});
}

// ── Timer ─────────────────────────────────────────────────────────────────────
function startIdxTimer(){
  _idxRunStart=Date.now();
  clearInterval(_idxTimer);
  _idxTimer=setInterval(()=>{
    const el=Math.round((Date.now()-_idxRunStart)/1000);
    document.getElementById('idx-elapsed').textContent='Elapsed: '+fmtSecs(el);
    if(iDone<iTotal&&iTotal>0){
      const win=_idxTimes.slice(-10);
      if(win.length>=2){
        const rate=(win.length-1)/((win[win.length-1]-win[0])/1000);
        document.getElementById('idx-eta').textContent='ETA: ~'+fmtSecs(Math.round((iTotal-iDone)/rate));
      } else if(iDone>0){
        document.getElementById('idx-eta').textContent='ETA: ~'+fmtSecs(Math.round((el/iDone)*(iTotal-iDone)));
      }
    }
    // Throughput badge — last 60 s
    const win60=_idxTimes.filter(t=>t>Date.now()-60000);
    const thrEl=document.getElementById('idx-throughput');
    if(thrEl&&win60.length>=2){
      thrEl.style.display='inline-flex';
      thrEl.textContent=win60.length+'/min';
    }
  },1000);
}
function stopIdxTimer(){ clearInterval(_idxTimer);_idxTimer=null; }

// ── Log helpers ───────────────────────────────────────────────────────────────
function appendIdxRow(num,url,status,priority){
  const box=document.getElementById('idx-log');
  const st=status.toLowerCase().replace(' ','-');
  const dataStatus=st==='indexed'?'indexed':st==='not-indexed'?'not-indexed':'error';
  const badgeCls=st==='indexed'?'lr-b-indexed':st==='not-indexed'?'lr-b-not':'lr-b-error';
  const shortUrl=url.replace(/^https?:\/\//,'').replace(/\/$/,'');
  const priCls=priority==='High'?'lr-pri-high':priority==='Medium'?'lr-pri-med':'lr-pri-low';
  const priHtml=priority?`<span class="lr-pri ${priCls}">${priority}</span>`:'';

  const row=document.createElement('div');
  row.className='log-row';
  row.dataset.status=dataStatus;
  row.dataset.url=url;
  if(_idxLogFilter!=='all'&&_idxLogFilter!==dataStatus) row.classList.add('lr-hidden');
  row.innerHTML=`
    <span class="lr-num">${String(num).padStart(3,'0')}</span>
    <span class="lr-badge ${badgeCls}">${status}</span>
    ${priHtml}
    <span class="lr-url" title="${url}"><a href="${url}" target="_blank">${shortUrl}</a></span>
    <span class="lr-time">${nowTime()}</span>`;
  box.appendChild(row);
  // Update filter counts
  document.getElementById('idx-count-all').textContent=iDone;
  document.getElementById('idx-count-indexed').textContent=iIndexed;
  document.getElementById('idx-count-not').textContent=iNot;
  document.getElementById('idx-count-err').textContent=iErrors;
  if(document.getElementById('idx-autoscroll').checked) box.scrollTop=box.scrollHeight;
}

// Copy currently-visible URLs to clipboard
function copyIdxUrls(){
  const rows=document.querySelectorAll('#idx-log .log-row:not(.lr-hidden)');
  const urls=[...rows].map(r=>r.dataset.url).filter(Boolean);
  if(!urls.length){toast('No URLs in current view','warn');return;}
  navigator.clipboard.writeText(urls.join('\n'))
    .then(()=>toast(`Copied ${urls.length} URL${urls.length===1?'':'s'} to clipboard`,'success'))
    .catch(()=>toast('Copy failed','error'));
}
function expandIdxLog(btn){
  const box=document.getElementById('idx-log');
  const big=box.classList.toggle('log-big');
  btn.textContent=big?'⛶ Shrink':'⛶';
}

function idxSysLog(msg,warn=false){
  const box=document.getElementById('idx-log');
  const div=document.createElement('div');
  div.className='log-sys'+(warn?' sys-warn':'');
  div.textContent='── '+msg;
  box.appendChild(div);
  if(document.getElementById('idx-autoscroll').checked) box.scrollTop=box.scrollHeight;
}

function filterIdxLog(type,btn){
  _idxLogFilter=type;
  document.querySelectorAll('.log-filter .lf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#idx-log .log-row').forEach(row=>{
    const st=row.dataset.status;
    const show=type==='all'||(type==='indexed'&&st==='indexed')||
               (type==='not-indexed'&&st==='not-indexed')||(type==='error'&&st==='error');
    row.classList.toggle('lr-hidden',!show);
  });
}

function idxDone(ok){
  setBtn('idx-btn',false,'🔍 Start Indexing Check');
  document.getElementById('idx-cancel-btn').style.display='none';
  document.getElementById('idx-pause-btn').style.display='none';
  document.getElementById('idx-resume-btn').style.display='none';
  document.getElementById('idx-partial-btn').style.display='none';
  const idxThrEl=document.getElementById('idx-throughput');if(idxThrEl)idxThrEl.style.display='none';
  document.getElementById('pip-idx').classList.remove('on');
  stopIdxTimer();
  if(!ok) setBadge('idx-badge','Indexing · Error',false);
  else _fireIdxNotif('Indexing complete',`${iIndexed} indexed · ${iNot} not indexed`);
}

function openIdxReport(){ if(_idxLastReport) window.open('/api/open/'+_idxLastReport,'_blank'); }

// ── Stream ────────────────────────────────────────────────────────────────────
function streamIndex(){
  if(_idxES) _idxES.close();
  _idxES=new EventSource('/api/index/stream');
  _idxES.onmessage=e=>{
    const d=JSON.parse(e.data);
    if(d.type==='progress'){
      iDone++;iTotal=Math.max(iTotal,d.total||iDone);
      _idxTimes.push(Date.now());
      if(d.status==='Indexed') iIndexed++;
      else if(d.status==='Not Indexed') iNot++;
      else iErrors++;
      const pct=iDone?Math.round(iIndexed/iDone*100):0;
      document.getElementById('is-checked').textContent=iDone;
      document.getElementById('is-indexed').textContent=iIndexed;
      document.getElementById('is-not').textContent=iNot;
      document.getElementById('is-errors').textContent=iErrors;
      document.getElementById('is-rate').textContent=pct+'%';
      const _idxBarPct=iTotal?Math.round(iDone/iTotal*100):0;
      document.getElementById('idx-bar').style.width=_idxBarPct+'%';
      const _idxPctEl=document.getElementById('idx-pct');
      if(_idxPctEl) _idxPctEl.textContent=_idxBarPct+'%';
      document.getElementById('idx-live-sub').textContent=`Checked ${iDone} of ${iTotal}`;
      appendIdxRow(iDone,d.url,d.status,d.priority);
      // Show partial export after first result
      if(iDone===1){const pb=document.getElementById('idx-partial-btn');if(pb)pb.style.display='inline-flex';}

    } else if(d.type==='done'){
      document.getElementById('idx-bar').style.width='100%';
      const _idxDonePct=document.getElementById('idx-pct');
      if(_idxDonePct){_idxDonePct.textContent='100%';_idxDonePct.classList.add('done');}
      document.getElementById('idx-live-sub').textContent='Complete — '+iDone+' URLs checked';
      setBadge('idx-badge','Indexing · Done',false);
      idxDone(true);
      toast(`Indexing complete — ${iIndexed} indexed, ${iNot} not indexed`,'success',5000);

      // show done bar
      _idxLastReport=d.report?d.report.split(/[\\/]/).pop():'';
      const doneBar=document.getElementById('idx-done-bar');
      const elapsed=Math.round((Date.now()-_idxRunStart)/1000);
      document.getElementById('idx-done-text').textContent=
        `✓ Done in ${fmtSecs(elapsed)} · ${iIndexed} indexed · ${iNot} not indexed`+(iErrors?` · ${iErrors} errors`:'');
      doneBar.classList.add('visible');
      if(_idxLastReport){
        const openBtn=document.getElementById('idx-open-btn');
        openBtn.style.display='inline-flex';
        // derive csv name from html name
        const csv=_idxLastReport.replace(/\.html$/,'.csv');
        const dlBtn=document.getElementById('idx-dl-btn');
        dlBtn.href='/api/download/'+csv;
        dlBtn.style.display='inline-flex';
        _idxLastCsv=csv;
      }
      if(d.error_count>0){
        document.getElementById('idx-error-count').textContent=d.error_count;
        document.getElementById('idx-retry-btn').style.display='inline-flex';
        idxSysLog(`${d.error_count} URL(s) had errors — click Retry Errors to re-check`,true);
      }
      updateHomeStats();
      refreshReportsSilent();
      _idxES.close();_idxES=null;

    } else if(d.type==='cancelled'){
      idxDone(false);
      setBadge('idx-badge','Indexing · Cancelled',false);
      document.getElementById('idx-live-sub').textContent=`Cancelled — ${d.done||iDone} URLs processed`;
      const doneBar=document.getElementById('idx-done-bar');
      if(d.report){
        _idxLastReport=d.report;
        document.getElementById('idx-done-text').textContent=
          `⚠ Cancelled after ${iDone} URLs — partial report saved`;
        doneBar.classList.add('visible');
        document.getElementById('idx-open-btn').style.display='inline-flex';
        if(d.csv){
          const dlBtn=document.getElementById('idx-dl-btn');
          dlBtn.href='/api/download/'+d.csv; dlBtn.style.display='inline-flex';
        }
        idxSysLog(`Partial report saved — ${iDone} URLs processed`,true);
        toast(`Cancelled — partial indexing report saved (${iDone} URLs)`,'warn',6000);
      } else {
        idxSysLog('Cancelled — no results to save (run was still starting)',true);
        toast('Cancelled before any results were collected','warn',4000);
      }
      refreshReportsSilent();
      _idxES.close();_idxES=null;

    } else if(d.type==='paused'){
      idxSysLog('Paused',true);
    } else if(d.type==='resumed'){
      idxSysLog('Resumed');
    } else if(d.type==='error'){
      idxSysLog(d.message,true);
      document.getElementById('idx-live-sub').textContent='Error — see log';
      setBadge('idx-badge','Indexing · Error',false);
      idxDone(false);
      _idxES.close();_idxES=null;
    }
  };
  _idxES.onerror=()=>{if(_idxES){_idxES.close();_idxES=null;}};
}

// ══════════════════════════════════════════════════════════════════════════════
// SEO AUDIT
// ══════════════════════════════════════════════════════════════════════════════
let aDone=0,aTotal=0,aScores=[],aIssues=0,aWarns=0;
let aExcellent=0,aGood=0,aPoor=0;   // score distribution buckets
let _audES=null, _audTimer=null, _audRunStart=0, _audLogFilter='all';
let _audLastReport='', _audLastXlsx='';
let _audTimes=[];        // rolling completion timestamps
let _audWorkers=3;       // configured worker count (from server response)
let _audResultsMap=new Map();   // url -> slim results array for row drawers
let _audTopIssues=new Map();    // label -> count for top-issues panel

function startAudit(){
  if(selectedUC.size===0){toast('Select at least one use case before starting.','warn');return;}
  aDone=0;aTotal=0;aScores=[];aIssues=0;aWarns=0;
  aExcellent=0;aGood=0;aPoor=0;_audTimes=[];
  _audResultsMap.clear();_audTopIssues.clear();
  document.getElementById('aud-log').innerHTML='';
  resetStat(['as-done','as-issues','as-warns'],'0');
  document.getElementById('as-score').textContent='—';
  // Reset distribution strip
  ['sdb-high','sdb-mid','sdb-low'].forEach(id=>{const e=document.getElementById(id);if(e)e.style.width='0%';});
  ['sdc-high','sdc-mid','sdc-low'].forEach(id=>{const e=document.getElementById(id);if(e)e.textContent='0';});
  const sdbWrap=document.getElementById('sdb-wrap');if(sdbWrap)sdbWrap.style.display='none';
  const sdbLbls=document.getElementById('sdb-labels');if(sdbLbls)sdbLbls.style.display='none';
  const tiPanel=document.getElementById('aud-top-issues');if(tiPanel)tiPanel.style.display='none';
  document.getElementById('aud-top-issues-list').innerHTML='';
  document.getElementById('aud-bar').style.width='0%';
  const audPctReset=document.getElementById('aud-pct');
  if(audPctReset){audPctReset.textContent='0%';audPctReset.classList.remove('done');}
  document.getElementById('aud-elapsed').textContent='';
  document.getElementById('aud-eta').textContent='';
  document.getElementById('aud-live-sub').textContent='Fetching URLs…';
  document.getElementById('aud-done-bar').classList.remove('visible');
  const _nsReset=document.getElementById('aud-next-steps'); if(_nsReset) _nsReset.style.display='none';
  _audLastReport=''; _audLastXlsx='';

  const kw=document.getElementById('aud-kw').value;
  // Flatten selected tasks across selected use cases
  const flatTasks=[];
  selectedUC.forEach(uc=>{
    (selectedTasks[uc]||new Set()).forEach(t=>flatTasks.push(t));
  });
  const audType=document.querySelector('input[name=aud-type]:checked').value;
  const audInput=_resolveAuditInput();
  if(!audInput){
    audSysLog('Please provide a sitemap URL, domain, file, or paste URLs first', true);
    const audSrcVisible=document.getElementById('aud-src-row')?.style.display!=='none';
    if(audSrcVisible) showFieldError('aud-src','This field is required');
    setBtn('aud-btn', selectedUC.size===0, '🔬 Start Audit');
    return;
  }
  const p={
    input_type: audType,
    input:      audInput,
    pattern:    document.getElementById('aud-pattern').value,
    limit:      +document.getElementById('aud-limit').value||10,
    workers:    +(document.getElementById('aud-workers')||{value:3}).value||3,
    crawl_depth:+(document.getElementById('aud-crawl-depth')||{value:2}).value||2,
    use_cases:  [...selectedUC],
    tasks:      flatTasks,
    keywords:   kw?kw.split(',').map(k=>k.trim()):[],
  };
  setBtn('aud-btn',true,'Running…');
  document.getElementById('aud-btn').dataset.running='1';
  document.getElementById('aud-cancel-btn').style.display='inline-flex';
  document.getElementById('aud-pause-btn').style.display='inline-flex';
  document.getElementById('aud-resume-btn').style.display='none';
  document.getElementById('aud-partial-btn').style.display='none';
  const audThrEl=document.getElementById('aud-throughput');if(audThrEl)audThrEl.style.display='none';
  setBadge('aud-badge','Audit · Running',true);
  document.getElementById('pip-aud').classList.add('on');
  navTo('aud-live');
  startAudTimer();

  withServerCheck(() => {
    fetch('/api/audit/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
      .then(r=>r.json()).then(d=>{
        if(d.error){audSysLog(d.error,true);audDone(false);return;}
        aTotal=d.total||10;
        _audWorkers=d.workers||p.workers||3;
        const wuEl=document.getElementById('aud-worker-util');
        const wTotal=document.getElementById('aud-worker-total');
        if(wuEl)wuEl.style.display='flex';
        if(wTotal)wTotal.textContent=_audWorkers;
        audSysLog('URLs fetched — starting audit…');
        document.getElementById('aud-live-sub').textContent='Running…';
        streamAudit();
      })
      .catch(e=>{audSysLog('Error starting audit: '+e,true);audDone(false);});
  }, audSysLog);
}

function cancelAudit(){
  document.getElementById('aud-live-sub').textContent='Cancelling…';
  audSysLog('Cancellation requested — saving partial report…',true);
  setBadge('aud-badge','Audit · Cancelling',false);
  // Keep SSE open so the "cancelled" event (with report path) arrives
  fetch('/api/audit/cancel',{method:'POST'}).catch(()=>{
    if(_audES){_audES.close();_audES=null;}
    stopAudTimer(); audDone(false);
    setBadge('aud-badge','Audit · Cancelled',false);
  });
}

// ── Timer ─────────────────────────────────────────────────────────────────────
function startAudTimer(){
  _audRunStart=Date.now();
  clearInterval(_audTimer);
  _audTimer=setInterval(()=>{
    const el=Math.round((Date.now()-_audRunStart)/1000);
    document.getElementById('aud-elapsed').textContent='Elapsed: '+fmtSecs(el);
    if(aDone<aTotal&&aTotal>0){
      const win=_audTimes.slice(-10);
      if(win.length>=2){
        const rate=(win.length-1)/((win[win.length-1]-win[0])/1000);
        document.getElementById('aud-eta').textContent='ETA: ~'+fmtSecs(Math.round((aTotal-aDone)/rate));
      } else if(aDone>0){
        document.getElementById('aud-eta').textContent='ETA: ~'+fmtSecs(Math.round((el/aDone)*(aTotal-aDone)));
      }
    }
    // Throughput badge — last 60 s
    const win60=_audTimes.filter(t=>t>Date.now()-60000);
    const thrEl=document.getElementById('aud-throughput');
    if(thrEl&&win60.length>=2){
      thrEl.style.display='inline-flex';
      thrEl.textContent=win60.length+'/min';
    }
    // Worker utilisation — approximate active = min(remaining, workers)
    const remaining=aTotal-aDone;
    const active=Math.min(remaining,_audWorkers);
    const wActive=document.getElementById('aud-worker-active');
    if(wActive&&aDone<aTotal) wActive.textContent=active;
    const wuDot=document.getElementById('aud-wu-dot');
    if(wuDot) wuDot.style.background=active>0?'var(--success)':'var(--text3)';
  },1000);
}
function stopAudTimer(){ clearInterval(_audTimer);_audTimer=null; }

// ── Log helpers ───────────────────────────────────────────────────────────────
function appendAudRow(num,url,score,issues,warns){
  const box=document.getElementById('aud-log');
  const sc=score||0;
  const scoreCls=sc>=80?'lr-s-high':sc>=50?'lr-s-mid':'lr-s-low';
  const dataIssues=issues||0;
  const shortUrl=url.replace(/^https?:\/\//,'').replace(/\/$/,'');
  const detail=dataIssues>0?(issues+' issue'+(issues!==1?'s':''))+(warns>0?` · ${warns} warn`:''):'OK';

  const row=document.createElement('div');
  row.className='log-row';
  row.dataset.issues=dataIssues;
  row.dataset.score=sc;
  row.dataset.url=url;
  if(_audLogFilter==='issues'&&dataIssues===0) row.classList.add('lr-hidden');
  if(_audLogFilter==='low'&&sc>=50) row.classList.add('lr-hidden');
  row.innerHTML=`
    <span class="lr-num">${String(num).padStart(3,'0')}</span>
    <span class="lr-score ${scoreCls}">${sc}</span>
    <span class="lr-url" title="${url}"><a href="${url}" target="_blank">${shortUrl}</a></span>
    <span class="lr-detail">${detail}</span>
    <span class="lr-time">${nowTime()}</span>`;
  box.appendChild(row);
  // Update counts
  const all=aDone, iss=document.querySelectorAll('#aud-log .log-row[data-issues]:not([data-issues="0"])').length;
  const low=[...document.querySelectorAll('#aud-log .log-row')].filter(r=>+r.dataset.score<50&&+r.dataset.score>0).length;
  const cAll=document.getElementById('aud-count-all'); if(cAll) cAll.textContent=all;
  const cIss=document.getElementById('aud-count-iss'); if(cIss) cIss.textContent=iss;
  const cLow=document.getElementById('aud-count-low'); if(cLow) cLow.textContent=low;
  if(document.getElementById('aud-autoscroll').checked) box.scrollTop=box.scrollHeight;
}

function copyAudUrls(){
  const rows=document.querySelectorAll('#aud-log .log-row:not(.lr-hidden)');
  const urls=[...rows].map(r=>r.dataset.url).filter(Boolean);
  if(!urls.length){toast('No URLs in current view','warn');return;}
  navigator.clipboard.writeText(urls.join('\n'))
    .then(()=>toast(`Copied ${urls.length} URL${urls.length===1?'':'s'}`,'success'))
    .catch(()=>toast('Copy failed','error'));
}
function expandAudLog(btn){
  const box=document.getElementById('aud-log');
  const big=box.classList.toggle('log-big');
  btn.textContent=big?'⛶ Shrink':'⛶';
}

function audSysLog(msg,warn=false){
  const box=document.getElementById('aud-log');
  const div=document.createElement('div');
  div.className='log-sys'+(warn?' sys-warn':'');
  div.textContent='── '+msg;
  box.appendChild(div);
  if(document.getElementById('aud-autoscroll').checked) box.scrollTop=box.scrollHeight;
}

function filterAudLog(type,btn){
  _audLogFilter=type;
  document.querySelectorAll('#panel-aud-live .log-filter .lf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#aud-log .log-row').forEach(row=>{
    const show=type==='all'||
      (type==='issues'&&+row.dataset.issues>0)||
      (type==='low'&&+row.dataset.score<50);
    row.classList.toggle('lr-hidden',!show);
  });
}

function audDone(ok){
  const audBtn=document.getElementById('aud-btn');
  delete audBtn.dataset.running;
  audBtn.disabled=selectedUC.size===0;
  setBtn('aud-btn',audBtn.disabled,'🔬 Start Audit');
  document.getElementById('aud-cancel-btn').style.display='none';
  document.getElementById('aud-pause-btn').style.display='none';
  document.getElementById('aud-resume-btn').style.display='none';
  document.getElementById('aud-partial-btn').style.display='none';
  const audThrEl=document.getElementById('aud-throughput');if(audThrEl)audThrEl.style.display='none';
  const wuEl=document.getElementById('aud-worker-util');if(wuEl)wuEl.style.display='none';
  document.getElementById('pip-aud').classList.remove('on');
  stopAudTimer();
  if(!ok) setBadge('aud-badge','Audit · Error',false);
  else {
    const avg=aScores.length?Math.round(aScores.reduce((a,b)=>a+b,0)/aScores.length):0;
    _fireAudNotif('Audit complete',`${aDone} URLs · avg score ${avg} · ${aIssues} issues`);
  }
}

function openAudReport(){ if(_audLastReport) window.open('/api/open/'+_audLastReport,'_blank'); }

// ── Stream ────────────────────────────────────────────────────────────────────
function streamAudit(){
  if(_audES) _audES.close();
  _audES=new EventSource('/api/audit/stream');
  _audES.onmessage=e=>{
    const d=JSON.parse(e.data);
    if(d.type==='progress'){
      aDone++;aTotal=Math.max(aTotal,d.total||aDone);
      aScores.push(d.score||0);aIssues+=d.issues||0;aWarns+=d.warnings||0;
      const avg=aScores.length?Math.round(aScores.reduce((a,b)=>a+b,0)/aScores.length):0;
      document.getElementById('as-done').textContent=aDone;
      document.getElementById('as-score').textContent=avg;
      document.getElementById('as-issues').textContent=aIssues;
      document.getElementById('as-warns').textContent=aWarns;
      document.getElementById('aud-bar').style.width=(aTotal?Math.round(aDone/aTotal*100):0)+'%';
      document.getElementById('aud-live-sub').textContent=`Audited ${aDone} of ${aTotal}`;
      appendAudRow(aDone,d.url,d.score,d.issues,d.warnings);

    } else if(d.type==='done'){
      document.getElementById('aud-bar').style.width='100%';
      const avg=aScores.length?Math.round(aScores.reduce((a,b)=>a+b,0)/aScores.length):0;
      document.getElementById('aud-live-sub').textContent='Complete — '+aDone+' URLs audited';
      setBadge('aud-badge','Audit · Done',false);
      audDone(true);

      _audLastReport=d.report?d.report.split(/[\\/]/).pop():'';
      _audLastXlsx  =d.xlsx  ?d.xlsx.split(/[\\/]/).pop()  :'';
      const elapsed=Math.round((Date.now()-_audRunStart)/1000);
      document.getElementById('aud-done-text').textContent=
        `✓ Done in ${fmtSecs(elapsed)} · avg score ${avg} · ${aIssues} issues · ${aWarns} warnings`;
      const doneBar=document.getElementById('aud-done-bar');
      doneBar.classList.add('visible');
      const _ns1=document.getElementById('aud-next-steps'); if(_ns1) _ns1.style.display='block';
      if(_audLastReport){
        document.getElementById('aud-open-btn').style.display='inline-flex';
        const pdfBtn=document.getElementById('aud-pdf-btn');
        pdfBtn.href='/api/reports/pdf/'+_audLastReport;
        pdfBtn.style.display='inline-flex';
      }
      if(_audLastXlsx){
        const dlBtn=document.getElementById('aud-dl-btn');
        dlBtn.href='/api/download/'+_audLastXlsx;
        dlBtn.style.display='inline-flex';
      }
      updateHomeStats();
      refreshReportsSilent();
      _audES.close();_audES=null;

    } else if(d.type==='error'){
      audSysLog(d.message,true);
      document.getElementById('aud-live-sub').textContent='Error — see log';
      setBadge('aud-badge','Audit · Error',false);
      audDone(false);
      _audES.close();_audES=null;
    }
  };
  _audES.onerror=()=>{if(_audES){_audES.close();_audES=null;}};
}

// ══════════════════════════════════════════════════════════════════════════════
// REPORTS
// ══════════════════════════════════════════════════════════════════════════════
let _allReports=[], _reportFilter='all';
let _repRefreshTimer=null;

function loadReports(){
  const wrap=document.getElementById('rep-cards-wrap');
  if(wrap) wrap.innerHTML='<div class="rep-empty"><div class="rep-empty-icon" style="animation:spin 1s linear infinite">⟳</div><div class="rep-empty-sub">Loading…</div></div>';
  fetch('/api/reports').then(r=>r.json()).then(d=>{
    _allReports=d;
    updateRepStats();
    renderReports();
    _startRepAutoRefresh();
  });
}

/* Refresh report data silently (no spinner) — called after a run completes
   and on a periodic timer when the Reports panel is visible.              */
function refreshReportsSilent(){
  fetch('/api/reports').then(r=>r.json()).then(d=>{
    const prevLen=_allReports.length;
    _allReports=d;
    updateRepStats();
    // Only re-render the card list if the Reports panel is currently visible
    // or the count changed (so nav badge stays accurate)
    const repPanel=document.getElementById('panel-reports');
    if(repPanel&&!repPanel.classList.contains('hidden')) renderReports();
  }).catch(()=>{});
}

function _startRepAutoRefresh(){
  _stopRepAutoRefresh();
  _repRefreshTimer=setInterval(()=>{
    const repPanel=document.getElementById('panel-reports');
    if(repPanel&&!repPanel.classList.contains('hidden')) refreshReportsSilent();
    else _stopRepAutoRefresh();
  }, 10000); // re-check every 10 s while panel is open
}
function _stopRepAutoRefresh(){
  if(_repRefreshTimer){clearInterval(_repRefreshTimer);_repRefreshTimer=null;}
}

function updateRepStats(){
  const idx=_allReports.filter(r=>r.kind==='indexing').length;
  const aud=_allReports.filter(r=>r.kind==='audit').length;
  document.getElementById('rep-total').textContent=_allReports.length;
  document.getElementById('rep-idx-count').textContent=idx;
  document.getElementById('rep-aud-count').textContent=aud;
}

function filterReports(kind,btn){
  _reportFilter=kind;
  document.querySelectorAll('.rep-toolbar .tab-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderReports();
}

function renderReports(){
  const q=(document.getElementById('rep-search')||{value:''}).value.toLowerCase();
  const clearBtn=document.getElementById('rep-search-clear');
  if(clearBtn) clearBtn.style.display=q?'':'none';
  const sortVal=(document.getElementById('rep-sort')||{value:'newest'}).value;
  let list=_reportFilter==='all'?_allReports:_allReports.filter(r=>r.kind===_reportFilter);
  if(q) list=list.filter(r=>r.name.toLowerCase().includes(q));
  list=[...list];
  if(sortVal==='oldest')       list.sort((a,b)=>a.name.localeCompare(b.name));
  else if(sortVal==='newest')  list.sort((a,b)=>b.name.localeCompare(a.name));
  else if(sortVal==='score-desc') list.sort((a,b)=>(b.score||0)-(a.score||0));
  else if(sortVal==='score-asc')  list.sort((a,b)=>(a.score||0)-(b.score||0));

  const wrap=document.getElementById('rep-cards-wrap');
  if(!list.length){
    wrap.innerHTML=`<div class="rep-empty">
      <div class="rep-empty-icon">📭</div>
      <div class="rep-empty-title">${q?'No reports match your search':'No reports yet'}</div>
      <div class="rep-empty-sub">${q?'Try a different search term':'Run an indexing check or SEO audit to generate reports'}</div>
    </div>`;
    return;
  }

  // Check for visible-list select-all state
  const allSelected=list.every(r=>_selectedReports.has(r.name));
  const someSelected=list.some(r=>_selectedReports.has(r.name));

  const bulkBar = `
    <div class="rep-bulk-bar ${_selectedReports.size?'active':''}">
      <label class="rep-bulk-checkall">
        <input type="checkbox" id="rep-checkall"
               ${allSelected?'checked':''}
               ${someSelected&&!allSelected?'data-indeterminate="true"':''}
               onchange="toggleSelectAllReports(this.checked)">
        <span class="rep-bulk-cb-box"></span>
        <span class="rep-bulk-checkall-text">
          ${_selectedReports.size?`<b>${_selectedReports.size} selected</b>`:`Select all (${list.length})`}
        </span>
      </label>
      <div class="rep-bulk-actions" style="${_selectedReports.size?'':'display:none'}">
        <button class="btn btn-ghost btn-sm" onclick="clearReportSelection()">Clear</button>
        <button class="btn btn-danger btn-sm" onclick="bulkDeleteReports()">🗑 Delete ${_selectedReports.size}</button>
      </div>
      <button class="btn btn-ghost btn-sm rep-bulk-deleteall"
              style="margin-left:auto" onclick="deleteAllReports()" title="Delete every report">
        ⚠ Delete all reports
      </button>
    </div>`;

  wrap.innerHTML=bulkBar+`<div class="rep-cards">${list.map(r=>{
    const isIdx=r.kind==='indexing';
    const icon=isIdx?'📊':'🔬';
    const iconCls=isIdx?'rep-icon-indexing':'rep-icon-audit';
    const kindCls=isIdx?'indexing':'audit';
    const kindLabel=isIdx?'Indexing':'SEO Audit';
    const displayName=_repDisplayName(r.name);
    const sel=_selectedReports.has(r.name);

    const dlBtn=isIdx
      ?`<a href="/api/download/${r.name}" class="btn-rep" style="text-decoration:none">⬇ CSV</a>`
      :(r.xlsx_name?`<a href="/api/download/${r.xlsx_name}" class="btn-rep" style="text-decoration:none">⬇ XLSX</a>`:'');
    const pdfBtn=!isIdx?`<a href="/api/reports/pdf/${r.html_name}" class="btn-rep" style="text-decoration:none">⬇ PDF</a>`:'';

    return `<div class="rep-card${sel?' selected':''}" id="rc-${r.name.replace(/\./g,'-')}">
      <label class="rep-card-cb" onclick="event.stopPropagation()">
        <input type="checkbox" ${sel?'checked':''} onchange="toggleReportSelection('${r.name}',this.checked)">
        <span class="rep-bulk-cb-box"></span>
      </label>
      <div class="rep-card-top">
        <div class="rep-card-icon ${iconCls}">${icon}</div>
        <div class="rep-card-body">
          <div class="rep-card-name">${displayName}</div>
          <div class="rep-card-meta">
            <span class="rep-kind ${kindCls}">${kindLabel}</span>
            <span>${r.date}</span>
            <span>${r.size}</span>
          </div>
        </div>
      </div>
      <div class="rep-card-actions">
        <button class="btn-rep rp" onclick="openRep('${r.html_name||r.name}')">↗ Open HTML</button>
        ${dlBtn}
        ${pdfBtn}
        <button class="btn-rep del" onclick="deleteReport('${r.name}',this)" title="Delete report">🗑 Delete</button>
      </div>
    </div>`;
  }).join('')}</div>`;
  // Set indeterminate state on the master checkbox
  const ca=document.getElementById('rep-checkall');
  if(ca) ca.indeterminate=someSelected&&!allSelected;
}

function openRep(name){ window.open('/api/open/'+name,'_blank'); }

function _repDisplayName(name){
  const m=name.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/);
  if(!m) return name;
  const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const h=+m[4], ap=h>=12?'PM':'AM', hr=h%12||12;
  return `${months[+m[2]-1]} ${+m[3]}, ${m[1]}  ${hr}:${m[5]} ${ap}`;
}


// ── Mobile bottom nav ─────────────────────────────────────────────────────────
function mnavActive(id){
  document.querySelectorAll('.mobile-nav-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id)?.classList.add('active');
}

// ── Bulk delete ───────────────────────────────────────────────────────────────
let _selectedReports=new Set();

function toggleReportSelection(name, checked){
  if(checked) _selectedReports.add(name);
  else _selectedReports.delete(name);
  renderReports();
}
function toggleSelectAllReports(checked){
  // Operate on the currently-visible filtered list only
  const q=(document.getElementById('rep-search')||{value:''}).value.toLowerCase();
  let list=_reportFilter==='all'?_allReports:_allReports.filter(r=>r.kind===_reportFilter);
  if(q) list=list.filter(r=>r.name.toLowerCase().includes(q));
  if(checked) list.forEach(r=>_selectedReports.add(r.name));
  else        list.forEach(r=>_selectedReports.delete(r.name));
  renderReports();
}
function clearReportSelection(){
  _selectedReports.clear();
  renderReports();
}
// Robust JSON fetch — surfaces "route missing → restart server" instead of cryptic JSON parse error
function _jsonFetch(url, opts){
  return fetch(url, opts).then(async r=>{
    const ct=r.headers.get('content-type')||'';
    if(!ct.includes('application/json')){
      const txt=await r.text();
      const hint=r.status===404||r.status===405
        ? `${url} not found — restart the server (python main.py) to pick up new routes`
        : `Server returned non-JSON (${r.status})`;
      throw new Error(hint+(txt?' · '+txt.slice(0,80):''));
    }
    return r.json();
  });
}

function bulkDeleteReports(){
  const names=[..._selectedReports];
  if(!names.length) return;
  if(!confirm(`Delete ${names.length} report${names.length===1?'':'s'}? This cannot be undone.`)) return;
  _jsonFetch('/api/reports/delete_bulk',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({names})
  })
    .then(d=>{
      if(d.error){toast('Bulk delete failed: '+d.error,'error',6000);return;}
      _allReports=_allReports.filter(r=>!d.deleted.includes(r.name));
      _selectedReports.clear();
      updateRepStats();
      renderReports();
      refreshReportCount&&refreshReportCount();
      const msg=`Deleted ${d.deleted_count} report${d.deleted_count===1?'':'s'}`+
                (d.failed_count?` · ${d.failed_count} failed`:'');
      toast(msg, d.failed_count?'warn':'success');
    })
    .catch(e=>toast('Bulk delete failed: '+(e.message||e),'error',6000));
}
function deleteAllReports(){
  const total=_allReports.length;
  if(!total){toast('No reports to delete','info');return;}
  const phrase=prompt(`This will permanently delete ALL ${total} reports. Type DELETE to confirm:`);
  if(phrase!=='DELETE'){toast('Cancelled','info');return;}
  _jsonFetch('/api/reports/delete_all',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({confirm:'YES'})
  })
    .then(d=>{
      if(d.error){toast('Delete-all failed: '+d.error,'error',6000);return;}
      _allReports=[];
      _selectedReports.clear();
      updateRepStats();
      renderReports();
      refreshReportCount&&refreshReportCount();
      toast(`Deleted ${d.deleted_count} files`, 'success');
    })
    .catch(e=>toast('Delete-all failed: '+(e.message||e),'error',6000));
}

function deleteReport(name,btn){
  if(!confirm(`Delete report "${name}" and all associated files?`)) return;
  btn.disabled=true; btn.textContent='Deleting…';
  fetch('/api/reports/delete/'+name,{method:'DELETE'})
    .then(r=>r.json()).then(d=>{
      if(d.error){toast('Delete failed: '+d.error,'error');btn.disabled=false;btn.textContent='🗑 Delete';return;}
      _allReports=_allReports.filter(r=>r.name!==name);
      _selectedReports.delete(name);
      updateRepStats();
      renderReports();
      refreshReportCount&&refreshReportCount();
      toast(`Deleted "${name}"`,'success');
    })
    .catch(()=>{toast('Delete failed','error');btn.disabled=false;btn.textContent='🗑 Delete';});
}

// ── Trend ─────────────────────────────────────────────────────────────────────
let tChart=null;
function loadTrend(){
  const tbody=document.getElementById('trend-tbody');
  if(tbody) tbody.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:18px">Loading…</td></tr>';
  fetch('/api/history').then(r=>r.json()).then(d=>{
    const empty=document.getElementById('trend-empty');
    const tbl=document.getElementById('trend-table');
    if(!d.length){empty.style.display='block';if(tbl)tbl.style.display='none';
      const kpiRow=document.getElementById('trend-kpi-row');if(kpiRow)kpiRow.style.display='none';return;}
    empty.style.display='none';
    // Populate KPI cards
    const kpiRow=document.getElementById('trend-kpi-row');
    if(kpiRow){
      kpiRow.style.display='';
      const withR=d.map(h=>{const t=h.total||((h.indexed||0)+(h.not_indexed||0));return{...h,_r:t?Math.round((h.indexed||0)/t*100):0,_t:t};});
      const best=Math.max(...withR.map(h=>h._r));
      const latest=withR[withR.length-1];
      const prev=withR.length>1?withR[withR.length-2]:null;
      const delta=prev?latest._r-prev._r:null;
      const deltaStr=delta!==null?(delta>=0?`▲ ${delta}% vs prev`:`▼ ${Math.abs(delta)}% vs prev`):'First run';
      document.getElementById('trend-kpi-runs').textContent=d.length;
      document.getElementById('trend-kpi-runs-sub').textContent=`${d[0]?.date?.slice(0,10)||''} → ${d[d.length-1]?.date?.slice(0,10)||''}`;
      document.getElementById('trend-kpi-best').textContent=best+'%';
      const bestRun=withR.find(h=>h._r===best);
      document.getElementById('trend-kpi-best-sub').textContent=bestRun?`on ${bestRun.date?.slice(0,10)||''}`:'' ;
      document.getElementById('trend-kpi-latest').textContent=latest._r+'%';
      document.getElementById('trend-kpi-latest-sub').textContent=deltaStr;
    }
    if(tChart) tChart.destroy();
    const dark=document.body.classList.contains('dark');
    const gridColor=dark?'rgba(255,255,255,.06)':'#F1F5F9';
    tChart=new Chart(document.getElementById('trend-chart'),{
      type:'line',
      data:{
        labels:d.map(h=>h.date.slice(0,10)),
        datasets:[
          {label:'Indexed',data:d.map(h=>h.indexed),borderColor:'#10B981',
           backgroundColor:'rgba(16,185,129,.08)',tension:.4,fill:true,pointRadius:4,pointHoverRadius:6},
          {label:'Not Indexed',data:d.map(h=>h.not_indexed),borderColor:'#EF4444',
           backgroundColor:'rgba(239,68,68,.08)',tension:.4,fill:true,pointRadius:4,pointHoverRadius:6},
        ]
      },
      options:{responsive:true,interaction:{mode:'index',intersect:false},
        plugins:{legend:{position:'bottom'},tooltip:{callbacks:{footer:items=>{
          const idx=items[0]?.parsed.y||0;
          const tot=(items[0]?.parsed.y||0)+(items[1]?.parsed.y||0);
          return tot?`Index rate: ${Math.round(idx/tot*100)}%`:'';
        }}}},
        scales:{y:{beginAtZero:true,grid:{color:gridColor}},x:{grid:{color:gridColor}}}}
    });
    // History table
    if(tbl){
      tbl.style.display='';
      // Parse YYYYMMDD_HHMMSS → "YYYY-MM-DD HH:MM:SS"
      const fmtDate=s=>{
        if(!s) return s;
        const m=s.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/);
        if(m) return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}`;
        // fallback: ISO or other
        return s.slice(0,16).replace('T',' ');
      };
      // Compute rate for each run using h.total as denominator when available
      const withRate=d.map(h=>{
        const tot=h.total||((h.indexed||0)+(h.not_indexed||0));
        const rate=tot?Math.round((h.indexed||0)/tot*100):0;
        return {...h,_tot:tot,_rate:rate};
      });
      const maxRate=Math.max(...withRate.map(h=>h._rate));
      const minRate=Math.min(...withRate.map(h=>h._rate));
      const hasVariation=maxRate!==minRate;
      const tbody=withRate.slice().reverse().map(h=>{
        const isBest=hasVariation&&h._rate===maxRate;
        const isWorst=hasVariation&&h._rate===minRate;
        return `<tr>
          <td>${fmtDate(h.date)}</td>
          <td>${h._tot}</td>
          <td style="color:var(--success);font-weight:600">${h.indexed||0}</td>
          <td style="color:var(--danger)">${h.not_indexed||0}</td>
          <td>
            <div class="trend-rate-bar" title="${h._rate}%">
              <div style="width:${h._rate}%;background:var(--success);height:6px;border-radius:4px"></div>
            </div>
            <span style="font-size:11px;color:var(--text2)">${h._rate}%</span>
          </td>
          <td>${isBest?'<span style="background:#DCFCE7;color:#166534;padding:2px 7px;border-radius:10px;font-size:11px">Best</span>':isWorst?'<span style="background:#FEE2E2;color:#991B1B;padding:2px 7px;border-radius:10px;font-size:11px">Worst</span>':''}</td>
        </tr>`;
      }).join('');
      document.getElementById('trend-tbody').innerHTML=tbody;
    }
  });
}

// ── Settings ──────────────────────────────────────────────────────────────────
function setBadge(id, isSet){
  const el=document.getElementById(id);
  if(!el) return;
  el.className='cfg-badge '+(isSet?'is-set':'is-unset');
  el.textContent=isSet?'✓ Configured':'Not set';
}

function updateSettingBadges(){
  setBadge('badge-gsc',       document.getElementById('cfg-gsc')?.checked);
  setBadge('badge-pagespeed', !!document.getElementById('cfg-pagespeed')?.value.trim());
  setBadge('badge-serpapi',   !!document.getElementById('cfg-serpapi')?.value.trim());
  setBadge('badge-moz',       !!document.getElementById('cfg-moz-id')?.value.trim());
  setBadge('badge-dfs',       !!document.getElementById('cfg-dfs-login')?.value.trim());
  setBadge('badge-email',     document.getElementById('cfg-email')?.checked);
  setBadge('badge-slack',     document.getElementById('cfg-slack')?.checked);
  setBadge('badge-teams',     document.getElementById('cfg-teams')?.checked);
  setBadge('badge-groq',      !!document.getElementById('cfg-groq')?.value.trim());
  setBadge('badge-bing',      !!document.getElementById('cfg-bing')?.value.trim());
  setBadge('badge-indexnow',  !!document.getElementById('cfg-indexnow-key')?.value.trim());
  setBadge('badge-schedule',  document.getElementById('cfg-schedule')?.checked);
  renderCfgHealth();
  _renderAuthStatus();
}

function renderCfgHealth(){
  const grid=document.getElementById('cfg-health-grid');
  if(!grid) return;
  const items=[
    {label:'Google Search Console', ok:document.getElementById('cfg-gsc')?.checked,    sub:'Indexing API'},
    {label:'PageSpeed Insights',     ok:!!document.getElementById('cfg-pagespeed')?.value.trim(), sub:'Performance + Perf Opportunities'},
    {label:'SerpAPI',                ok:!!document.getElementById('cfg-serpapi')?.value.trim(),   sub:'Rankings phase'},
    {label:'Moz API',                ok:!!document.getElementById('cfg-moz-id')?.value.trim(),    sub:'Domain authority'},
    {label:'DataForSEO',             ok:!!document.getElementById('cfg-dfs-login')?.value.trim(), sub:'Backlinks & SERP'},
    {label:'Groq AI',                ok:!!document.getElementById('cfg-groq')?.value.trim(),      sub:'AI explanations & meta drafting'},
    {label:'Bing Webmaster',         ok:!!document.getElementById('cfg-bing')?.value.trim(),      sub:'Bing visibility panel'},
    {label:'IndexNow',               ok:!!document.getElementById('cfg-indexnow-key')?.value.trim()&&!!document.getElementById('cfg-indexnow-host')?.value.trim(), sub:'URL submission to Bing/Yandex'},
    {label:'Slack',                  ok:document.getElementById('cfg-slack')?.checked&&!!document.getElementById('cfg-slack-webhook')?.value.trim(), sub:'Notifications'},
    {label:'Teams',                  ok:document.getElementById('cfg-teams')?.checked&&!!document.getElementById('cfg-teams-webhook')?.value.trim(), sub:'Notifications'},
    {label:'Email Notifications',    ok:document.getElementById('cfg-email-toggle')?.checked&&!!document.getElementById('cfg-smtp-host')?.value.trim(), sub:'SMTP reports'},
    {label:'Scheduled Runs',         ok:document.getElementById('cfg-schedule')?.checked, sub:'Automatic recurring indexing'},
    {label:'Proxies',                ok:!!(document.getElementById('cfg-proxies')?.value.trim()), sub:'Proxy rotation for indexing'},
  ];
  grid.innerHTML=items.map(it=>`
    <div class="cfg-health-item">
      <div class="cfg-health-dot ${it.ok?'ok':'miss'}"></div>
      <div class="cfg-health-info">
        <div class="cfg-health-label">${it.label}</div>
        <div class="cfg-health-status">${it.ok?'✓ Configured':'Not set'} · ${it.sub}</div>
      </div>
    </div>`).join('');
}

function _renderAuthStatus(){
  // Show whether password auth is active (based on whether /api/settings returns authEnabled)
  const desc = document.getElementById('auth-status-desc');
  const badge = document.getElementById('badge-auth');
  if(!desc) return;
  fetch('/api/auth_status').then(r=>r.json()).then(d=>{
    if(d.auth_enabled){
      desc.textContent = `Auth active — logged in as ${d.username||'admin'}`;
      if(badge) { badge.textContent='✓ Active'; badge.style.background='var(--c-green)'; badge.style.color='#fff'; badge.style.padding='2px 8px'; badge.style.borderRadius='99px'; }
    } else {
      desc.textContent = 'Auth disabled — set SEO_SUITE_PASSWORD_HASH env var to require login';
      if(badge) { badge.textContent='Off'; badge.style.background='var(--c-border)'; badge.style.color='var(--c-muted)'; badge.style.padding='2px 8px'; badge.style.borderRadius='99px'; }
    }
    const secretBadge = document.getElementById('auth-secret-badge');
    if(secretBadge){
      secretBadge.textContent = d.secret_set ? '✓ Secret configured' : '⚠ Ephemeral (sessions lost on restart)';
      secretBadge.style.color = d.secret_set ? 'var(--c-green)' : 'var(--c-yellow)';
    }
  }).catch(()=>{});
}

// ── Topbar user badge ─────────────────────────────────────────────────────────
function initUserBadge(){
  fetch('/api/auth_status').then(r=>r.json()).then(d=>{
    const wrap = document.getElementById('tb-user');
    const nameEl = document.getElementById('tb-user-name');
    if(!wrap) return;
    if(d.auth_enabled){
      wrap.style.display='flex';
      // Show only the first letter of username as avatar initial — don't expose full email in topbar
      const initial = (d.username || 'A')[0].toUpperCase();
      const avatarEl = document.getElementById('tb-user-avatar');
      if(avatarEl) avatarEl.textContent = initial;
      if(nameEl)   nameEl.style.display = 'none'; // hide full username/email
    } else {
      wrap.style.display='none';
    }
  }).catch(()=>{});
}

async function doLogout(){
  try {
    await fetch('/logout', {method:'POST'});
  } catch(e){ /* ignore */ }
  window.location.href = '/login';
}

function toggleNotifExpand(key, open){
  const el=document.getElementById('notif-expand-'+key);
  if(el) el.classList.toggle('open', open);
}

function setThemePref(pref){
  ['light','dark','system'].forEach(p=>{
    const el=document.getElementById('theme-opt-'+p);
    if(el) el.classList.toggle('active', p===pref);
  });
  localStorage.setItem('themePref', pref);
  if(pref==='system'){
    const prefersDark=window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.body.classList.toggle('dark', prefersDark);
  } else {
    document.body.classList.toggle('dark', pref==='dark');
  }
}

function _initThemePref(){
  const pref=localStorage.getItem('themePref')||'system';
  setThemePref(pref);
}

function saveSettings(){
  const parallelRaw = parseInt(document.getElementById('cfg-parallel-tabs')?.value)||1;
  const cfg={
    parallel_tabs:       Math.min(8, Math.max(1, parallelRaw)),
    // API keys — all now correctly included in _SETTINGS_ALLOWED_KEYS server-side
    pagespeed_api_key:   document.getElementById('cfg-pagespeed')?.value||'',
    serpapi_key:         document.getElementById('cfg-serpapi')?.value||'',
    dataforseo_login:    document.getElementById('cfg-dfs-login')?.value||'',
    dataforseo_password: document.getElementById('cfg-dfs-pass')?.value||'',
    moz_access_id:       document.getElementById('cfg-moz-id')?.value||'',
    moz_secret_key:      document.getElementById('cfg-moz-secret')?.value||'',
    // Stage 3 keys
    groq_api_key:        document.getElementById('cfg-groq')?.value||'',
    bing_api_key:        document.getElementById('cfg-bing')?.value||'',
    // IndexNow (Stage 2-B)
    indexnow_key:        document.getElementById('cfg-indexnow-key')?.value||'',
    indexnow_host:       document.getElementById('cfg-indexnow-host')?.value||'',
    // Public signup toggle (default on)
    allow_signup:        document.getElementById('cfg-allow-signup') ? document.getElementById('cfg-allow-signup').checked : true,
    email:  {
      enabled:     document.getElementById('cfg-email-toggle')?.checked||false,
      smtp_host:   document.getElementById('cfg-smtp-host')?.value||'',
      smtp_port:   parseInt(document.getElementById('cfg-smtp-port')?.value)||587,
      smtp_from:   document.getElementById('cfg-smtp-from')?.value||'',
      smtp_user:   document.getElementById('cfg-smtp-user')?.value||'',
      smtp_pass:   document.getElementById('cfg-smtp-pass')?.value||'',
      to:          document.getElementById('cfg-smtp-to')?.value||'',
    },
    slack:  {enabled:document.getElementById('cfg-slack')?.checked||false, webhook_url:document.getElementById('cfg-slack-webhook')?.value||''},
    teams:  {enabled:document.getElementById('cfg-teams')?.checked||false, webhook_url:document.getElementById('cfg-teams-webhook')?.value||''},
    gsc:    {
      enabled:          document.getElementById('cfg-gsc')?.checked||false,
      credentials_file: document.getElementById('cfg-gsc-creds')?.value.trim()||'gsc_credentials.json',
    },
    proxies: (document.getElementById('cfg-proxies')?.value||'')
               .split('\n').map(p=>p.trim()).filter(Boolean),
    schedule: {
      enabled:     document.getElementById('cfg-schedule')?.checked||false,
      interval:    document.getElementById('cfg-schedule-interval')?.value||'daily',
      time:        document.getElementById('cfg-schedule-time')?.value||'08:00',
      sitemap_url: document.getElementById('cfg-schedule-sitemap')?.value||'',
      limit:       parseInt(document.getElementById('cfg-schedule-limit')?.value||'100')||100,
    },
  };
  // Client-side validation before the round-trip.
  const vErr = _validateSettingsClient(cfg);
  if(vErr){ toast(vErr,'error'); return; }
  fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})
    .then(r=>r.json().then(d=>({ok:r.ok,d})))
    .then(({ok,d})=>{
      if(!ok){ toast(d.error||'Save rejected','error'); return; }
      toast(d.message||'Settings saved!','success');
      _clearSettingsDirty();
      updateSettingBadges();
    })
    .catch(()=>toast('Save failed — is the server running?','error'));
}

// ── Settings: client-side validation ──────────────────────────────────────────
function _validateSettingsClient(cfg){
  if(cfg.email){
    const p = cfg.email.smtp_port;
    if(p!==undefined && p!=='' && (!(Number.isInteger(p)) || p<1 || p>65535))
      return 'SMTP port must be a whole number between 1 and 65535';
    const _email = v => !v || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v);
    if(!_email(cfg.email.smtp_from)) return 'From Address is not a valid email';
    if(!_email(cfg.email.to))        return 'Report To is not a valid email';
  }
  if(cfg.indexnow_host && !/^[A-Za-z0-9.-]+$/.test(cfg.indexnow_host))
    return 'IndexNow host must be a bare hostname (no http:// or path), e.g. example.com';
  const _https = v => !v || v==='••••••••' || v.startsWith('https://');
  if(cfg.slack && !_https(cfg.slack.webhook_url)) return 'Slack webhook URL must start with https://';
  if(cfg.teams && !_https(cfg.teams.webhook_url)) return 'Teams webhook URL must start with https://';
  return null;
}

function toggleKeyVis(btn){
  const input=btn.previousElementSibling;
  if(!input) return;
  const hidden=input.type==='password'||input.dataset.hidden==='1';
  if(hidden){
    input.dataset._type=input.type;
    input.type='text';
    input.dataset.hidden='0';
    btn.style.opacity='1';
  }else{
    input.type=input.dataset._type||'password';
    input.dataset.hidden='1';
    btn.style.opacity='.5';
  }
}

async function generateAndFillIndexNowKey(){
  try {
    const d = await _api('/api/tools/indexnow_generate_key', {});
    if(d.ok && d.key){
      const el = document.getElementById('cfg-indexnow-key');
      if(el){ el.value=d.key; el.type='text'; }
      showToast('Key generated — save settings and host the key file');
    }
  } catch(e) { showToast('Generate failed: '+e.message,'error'); }
}

async function changeAuthCredentials(){
  const user  = (document.getElementById('cfg-auth-user')?.value||'').trim();
  const pass  = (document.getElementById('cfg-auth-pass')?.value||'');
  const pass2 = (document.getElementById('cfg-auth-pass2')?.value||'');
  const errEl = document.getElementById('auth-change-error');
  const _err  = msg => { if(errEl){ errEl.textContent=msg; errEl.style.display=''; } };
  const _ok   = ()  => { if(errEl){ errEl.style.display='none'; } };
  _ok();
  if(!user)             { _err('Username required'); return; }
  if(pass.length < 12)  { _err('Password must be at least 12 characters'); return; }
  if(pass !== pass2)    { _err('Passwords do not match'); return; }
  // Generate hash client-side is impossible without bcrypt in the browser;
  // route this through the server which has werkzeug available.
  try {
    const d = await _api('/api/auth/change_credentials', {username: user, password: pass});
    if(d.ok){
      _ok();
      showToast('Hash generated — see env snippet below','success');
      document.getElementById('cfg-auth-pass').value='';
      document.getElementById('cfg-auth-pass2').value='';
      if(d.env_snippet && errEl){
        errEl.style.display='';
        errEl.style.color='var(--c-green)';
        errEl.style.fontFamily='monospace';
        errEl.style.fontSize='11px';
        errEl.style.whiteSpace='pre';
        errEl.textContent = 'Add to .env and restart:\n\n' + d.env_snippet;
      }
    } else {
      _err(d.error || 'Update failed');
    }
  } catch(e) { _err(e.message); }
}

function loadSettings(){
  fetch('/api/settings').then(r=>r.json()).then(c=>{
    // Helper: set input value only if truthy (avoids overwriting with empty strings)
    const _set = (id, val) => { const el=document.getElementById(id); if(el && val) el.value=val; };
    const _chk = (id, val) => { const el=document.getElementById(id); if(el) el.checked=!!val; };

    _set('cfg-pagespeed',      c.pagespeed_api_key);
    _set('cfg-serpapi',        c.serpapi_key);
    _set('cfg-dfs-login',      c.dataforseo_login);
    _set('cfg-dfs-pass',       c.dataforseo_password);   // was missing
    _set('cfg-moz-id',         c.moz_access_id);
    _set('cfg-moz-secret',     c.moz_secret_key);        // was missing
    _set('cfg-parallel-tabs',  c.parallel_tabs);
    // Stage 3 + IndexNow
    _set('cfg-groq',           c.groq_api_key);
    _set('cfg-bing',           c.bing_api_key);
    _set('cfg-indexnow-key',   c.indexnow_key);
    _set('cfg-indexnow-host',  c.indexnow_host);
    // GSC
    _set('cfg-gsc-creds', c.gsc?.credentials_file);
    _chk('cfg-gsc',       c.gsc?.enabled);
    // Email
    if(c.email?.enabled){ _chk('cfg-email-toggle', true); toggleNotifExpand('email', true); }
    _set('cfg-smtp-host', c.email?.smtp_host);
    _set('cfg-smtp-port', c.email?.smtp_port);
    _set('cfg-smtp-from', c.email?.smtp_from);
    _set('cfg-smtp-user', c.email?.smtp_user);
    _set('cfg-smtp-pass', c.email?.smtp_pass);           // was missing
    _set('cfg-smtp-to',   c.email?.to);
    // Slack
    if(c.slack?.enabled){ _chk('cfg-slack', true); toggleNotifExpand('slack', true); }
    _set('cfg-slack-webhook', c.slack?.webhook_url);
    // Teams
    if(c.teams?.enabled){ _chk('cfg-teams', true); toggleNotifExpand('teams', true); }
    _set('cfg-teams-webhook', c.teams?.webhook_url);
    // Proxies
    if(Array.isArray(c.proxies) && c.proxies.length) {
      const el = document.getElementById('cfg-proxies');
      if(el) el.value = c.proxies.join('\n');
    }
    // Schedule
    if(c.schedule?.enabled){ _chk('cfg-schedule', true); toggleScheduleExpand(true); }
    if(c.schedule?.interval){ const el=document.getElementById('cfg-schedule-interval'); if(el) el.value=c.schedule.interval; }
    _set('cfg-schedule-time',    c.schedule?.time);
    _set('cfg-schedule-sitemap', c.schedule?.sitemap_url);
    _set('cfg-schedule-limit',   c.schedule?.limit);

    _chk('cfg-allow-signup', c.allow_signup !== false);  // default on
    updateSettingBadges();
    _initThemePref();
    _initSettingsEnhancements();
    loadUsers();
    _clearSettingsDirty();   // freshly-loaded form is clean
  }).catch(()=>{});
}

// ── Settings: user management (admin only) ────────────────────────────────────
function loadUsers(){
  const panel = document.getElementById('users-admin');
  fetch('/api/users').then(r=>{
    if(r.status===403 || r.status===401){ if(panel) panel.style.display='none'; return null; }
    return r.json();
  }).then(d=>{
    if(!d || !d.ok){ return; }
    if(panel) panel.style.display='';   // current user is an admin
    const list = document.getElementById('users-list');
    if(!list) return;
    if(!d.users.length){ list.innerHTML='<div style="color:var(--text3);font-size:12px">No users yet</div>'; return; }
    list.innerHTML='';
    d.users.forEach(u=>{
      const row=document.createElement('div');
      row.style.cssText='display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 10px;border:1px solid var(--c-border);border-radius:8px';
      const tags=[];
      if(u.is_admin) tags.push('<span style="font-size:10px;background:rgba(139,92,246,.15);color:#8B5CF6;padding:1px 7px;border-radius:10px">admin</span>');
      if(u.source==='env') tags.push('<span style="font-size:10px;color:var(--text3)">env</span>');
      if(u.username===d.me) tags.push('<span style="font-size:10px;color:var(--text3)">you</span>');
      const left=document.createElement('div');
      left.style.cssText='display:flex;align-items:center;gap:8px;font-size:13px';
      left.innerHTML=`<b>${_esc(u.username)}</b> ${tags.join(' ')}`;
      row.appendChild(left);
      // Env admin and your own account can't be deleted here.
      if(u.source!=='env' && u.username!==d.me){
        const del=document.createElement('button');
        del.className='btn btn-ghost btn-sm';
        del.textContent='Delete';
        del.onclick=()=>deleteUser(u.username);
        row.appendChild(del);
      }
      list.appendChild(row);
    });
  }).catch(()=>{ if(panel) panel.style.display='none'; });
}

function _esc(s){ const d=document.createElement('div'); d.textContent=String(s==null?'':s); return d.innerHTML; }

async function createUser(){
  const name=(document.getElementById('new-user-name')?.value||'').trim();
  const pass=document.getElementById('new-user-pass')?.value||'';
  const isAdmin=document.getElementById('new-user-admin')?.checked||false;
  const errEl=document.getElementById('new-user-error');
  const _err=m=>{ if(errEl){ errEl.textContent=m; errEl.style.display=''; } };
  if(errEl) errEl.style.display='none';
  if(!name){ _err('Username required'); return; }
  if(pass.length<12){ _err('Password must be at least 12 characters'); return; }
  try{
    const r=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:name,password:pass,is_admin:isAdmin})});
    const d=await r.json();
    if(!r.ok || !d.ok){ _err(d.error||'Create failed'); return; }
    document.getElementById('new-user-name').value='';
    document.getElementById('new-user-pass').value='';
    document.getElementById('new-user-admin').checked=false;
    toast('User created','success');
    loadUsers();
  }catch(e){ _err('Request failed'); }
}

async function deleteUser(username){
  if(!confirm('Delete user "'+username+'"? This cannot be undone.')) return;
  try{
    const r=await fetch('/api/users/'+encodeURIComponent(username),{method:'DELETE'});
    const d=await r.json();
    if(!r.ok || !d.ok){ toast(d.error||'Delete failed','error'); return; }
    toast('User deleted','success');
    loadUsers();
  }catch(e){ toast('Request failed','error'); }
}

// ── Settings: Test-connection buttons, dirty guard, search filter ─────────────
let _settingsDirty = false;
let _settingsWired = false;

// inputId → {provider, label}. Each gets a "Test" button + result chip.
const _SETTINGS_TESTS = [
  {id:'cfg-pagespeed', provider:'pagespeed'},
  {id:'cfg-groq',      provider:'groq'},
  {id:'cfg-bing',      provider:'bing'},
  {id:'cfg-serpapi',   provider:'serpapi'},
  {id:'cfg-moz-id',    provider:'moz'},
  {id:'cfg-dfs-login', provider:'dataforseo'},
  {id:'cfg-gsc-creds', provider:'gsc'},
];

function _initSettingsEnhancements(){
  if(_settingsWired) return;
  _settingsWired = true;
  _wireTestButtons();
  // Dirty tracking on every settings input/toggle.
  const panel = document.getElementById('panel-settings');
  if(panel){
    panel.addEventListener('input',  _markSettingsDirty);
    panel.addEventListener('change', _markSettingsDirty);
  }
  // Warn on tab close / refresh with unsaved changes.
  window.addEventListener('beforeunload', e => {
    if(_settingsDirty){ e.preventDefault(); e.returnValue=''; }
  });
}

function _wireTestButtons(){
  _SETTINGS_TESTS.forEach(({id,provider})=>{
    const input = document.getElementById(id);
    if(!input) return;
    const row = input.closest('.settings-row');
    if(!row || row.querySelector('.cfg-test-btn')) return;
    const wrap = document.createElement('div');
    wrap.style.cssText='display:flex;align-items:center;gap:8px;margin-top:6px;justify-content:flex-end';
    const chip = document.createElement('span');
    chip.className='cfg-test-chip';
    chip.style.cssText='font-size:11px;color:var(--text3)';
    const btn = document.createElement('button');
    btn.type='button';
    btn.className='btn btn-ghost btn-sm cfg-test-btn';
    btn.textContent='Test';
    btn.onclick=()=>testConnection(provider, btn, chip);
    wrap.appendChild(chip); wrap.appendChild(btn);
    row.appendChild(wrap);
  });
}

// Collect the credential fields each provider needs from the live inputs.
function _gatherTestCreds(provider){
  const g = id => document.getElementById(id)?.value || '';
  switch(provider){
    case 'pagespeed':  return {pagespeed_api_key:g('cfg-pagespeed')};
    case 'groq':       return {groq_api_key:g('cfg-groq')};
    case 'bing':       return {bing_api_key:g('cfg-bing')};
    case 'serpapi':    return {serpapi_key:g('cfg-serpapi')};
    case 'moz':        return {moz_access_id:g('cfg-moz-id'), moz_secret_key:g('cfg-moz-secret')};
    case 'dataforseo': return {dataforseo_login:g('cfg-dfs-login'), dataforseo_password:g('cfg-dfs-pass')};
    case 'gsc':        return {};   // server uses the configured credentials file
    default:           return {};
  }
}

async function testConnection(provider, btn, chip){
  btn.disabled=true; const orig=btn.textContent; btn.textContent='Testing…';
  chip.textContent=''; chip.style.color='var(--text3)';
  try{
    const r = await fetch('/api/settings/test/'+encodeURIComponent(provider),
      {method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify(_gatherTestCreds(provider))});
    const d = await r.json();
    chip.textContent = (d.ok?'✓ ':'✗ ') + (d.message||'');
    chip.style.color = d.ok ? 'var(--c-green,#1a7f37)' : 'var(--c-red,#cf222e)';
  }catch(e){
    chip.textContent='✗ Request failed';
    chip.style.color='var(--c-red,#cf222e)';
  }finally{
    btn.disabled=false; btn.textContent=orig;
  }
}

function _markSettingsDirty(){
  if(_settingsDirty) return;
  _settingsDirty=true;
  const btn=document.querySelector('#panel-settings .settings-header .btn-primary');
  if(btn) btn.textContent='💾 Save Settings ●';
}
function _clearSettingsDirty(){
  _settingsDirty=false;
  const btn=document.querySelector('#panel-settings .settings-header .btn-primary');
  if(btn) btn.textContent='💾 Save Settings';
}
function _settingsLeaveGuard(targetPanel){
  const onSettings = document.getElementById('panel-settings')?.classList.contains('active');
  if(onSettings && targetPanel!=='settings' && _settingsDirty){
    if(!confirm('You have unsaved settings changes. Leave without saving?')) return false;
    _clearSettingsDirty();
  }
  return true;
}

function filterSettings(q){
  q=(q||'').trim().toLowerCase();
  document.querySelectorAll('#panel-settings .settings-grid > .card').forEach(card=>{
    let anyVisible=false;
    card.querySelectorAll('.settings-row').forEach(row=>{
      const hit = !q || row.textContent.toLowerCase().includes(q);
      row.style.display = hit ? '' : 'none';
      if(hit) anyVisible=true;
    });
    // Card with a matching title stays fully visible.
    const title=(card.querySelector('.section-title')?.textContent||'').toLowerCase();
    if(q && title.includes(q)){ card.style.display=''; card.querySelectorAll('.settings-row').forEach(r=>r.style.display=''); return; }
    card.style.display = (!q || anyVisible) ? '' : 'none';
  });
}

// ── Home stats / greeting / recent ────────────────────────────────────────────
function updateHomeStats(){
  // Pull most-recent indexing run + most-recent audit + history
  Promise.all([
    fetch('/api/history').then(r=>r.json()).catch(()=>[]),
    fetch('/api/reports').then(r=>r.json()).catch(()=>[]),
  ]).then(([hist, reports])=>{
    // Last indexing run from history
    const lastIdx=hist&&hist.length?hist[hist.length-1]:null;
    const prevIdx=hist&&hist.length>1?hist[hist.length-2]:null;
    if(lastIdx){
      const checked=(lastIdx.indexed||0)+(lastIdx.not_indexed||0);
      _setHomeStat('h-checked', checked);
      _setHomeStat('h-indexed', lastIdx.indexed||0);
      if(prevIdx){
        const prevChecked=(prevIdx.indexed||0)+(prevIdx.not_indexed||0);
        _setHomeTrend('h-trend-checked', checked-prevChecked);
        _setHomeTrend('h-trend-indexed', (lastIdx.indexed||0)-(prevIdx.indexed||0));
      }
    } else if(iDone){
      _setHomeStat('h-checked', iDone);
      _setHomeStat('h-indexed', iIndexed);
    }
    // Latest audit avg + issues — prefer .json sidecar, fall back to .xlsx
    const audits=(reports||[]).filter(r=>r.kind==='audit');
    const summaryFile=audits.length?(audits[0].json_name||audits[0].xlsx_name):null;
    if(summaryFile){
      fetch('/api/reports/summary?file='+encodeURIComponent(summaryFile))
        .then(r=>r.ok?r.json():null).then(s=>{
          if(s){
            _setHomeStat('h-avgscore', s.avg_score);
            _setHomeStat('h-issues', s.total_issues);
          }
        }).catch(()=>{});
    }
    // Greeting subtitle
    const sub=document.getElementById('h-greet-sub');
    if(sub){
      const parts=[];
      if(lastIdx) parts.push(`Last indexing: ${_relTime(lastIdx.date)}`);
      if(audits.length) parts.push(`${audits.length} audit${audits.length===1?'':'s'} on file`);
      sub.textContent=parts.length?parts.join(' · ')
        :'Pick a use case to run, or start a full audit';
    }
  });
  // Greeting based on hour
  const g=document.getElementById('h-greeting');
  if(g){
    const h=new Date().getHours();
    const tod=h<5?'Working late':h<12?'Good morning':h<17?'Good afternoon':h<22?'Good evening':'Working late';
    g.textContent=`${tod} · SEO Suite`;
  }
  // Update fa-sub with check count
  const fa=document.getElementById('fa-sub');
  if(fa && typeof UC_DEFS==='object'){
    const totalChecks=Object.values(UC_INFO).reduce((s,v)=>s+(v.checks||[]).length,0);
    fa.textContent=`All 7 use cases · ${totalChecks}+ checks per URL · scored 0–100 · HTML + XLSX report`;
  }
  loadRecentReports();
}
function _setHomeStat(id,v){
  const el=document.getElementById(id);
  if(!el) return;
  if(v===undefined||v===null) return;
  el.textContent=typeof v==='number'?v.toLocaleString():v;
}
function _setHomeTrend(id, delta){
  const el=document.getElementById(id);
  if(!el||!delta) return;
  const arrow=delta>0?'▲':'▼';
  const cls=delta>0?'trend-up':'trend-down';
  el.innerHTML=`<span class="${cls}">${arrow} ${Math.abs(delta).toLocaleString()}</span> vs previous`;
}
function _relTime(iso){
  if(!iso) return '';
  const t=new Date(iso); if(isNaN(t)) return '';
  const s=Math.round((Date.now()-t)/1000);
  if(s<60) return 'just now';
  if(s<3600) return Math.floor(s/60)+'m ago';
  if(s<86400) return Math.floor(s/3600)+'h ago';
  if(s<604800) return Math.floor(s/86400)+'d ago';
  return t.toLocaleDateString();
}
function loadRecentReports(){
  const wrap=document.getElementById('h-recent-reports');
  if(!wrap) return;
  fetch('/api/reports').then(r=>r.json()).then(d=>{
    if(!d||!d.length){
      wrap.innerHTML=`<div class="empty-state">
  <div class="empty-state-icon">📋</div>
  <div class="empty-state-title">No reports yet</div>
  <div class="empty-state-sub">Run an indexing check or SEO audit to generate your first report</div>
  <div class="empty-state-action"><button class="btn btn-primary btn-sm" onclick="navTo('idx-run')">Start a check →</button></div>
</div>`;
      return;
    }
    wrap.innerHTML=d.slice(0,5).map(r=>{
      const isIdx=r.kind==='indexing';
      const cls=isIdx?'rep-icon-indexing':'rep-icon-audit';
      const icon=isIdx?'📊':'🔬';
      return `<div class="home-recent-row" onclick="openRep('${r.html_name||r.name}')" title="${r.name}">
        <div class="home-recent-icon ${cls}">${icon}</div>
        <div class="home-recent-body">
          <div class="home-recent-name">${r.name}</div>
          <div class="home-recent-meta">${r.date} · ${r.size}</div>
        </div>
        <span class="home-recent-arrow">↗</span>
      </div>`;
    }).join('');
  }).catch(()=>{
    wrap.innerHTML='<div class="empty" style="padding:18px 8px;color:var(--danger)">Failed to load</div>';
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setBtn(id,disabled,text){
  const b=document.getElementById(id);b.disabled=disabled;b.textContent=text;
}
function setBadge(id,text,running){
  const el=document.getElementById(id);
  if(!el) return;
  el.textContent=text;
  el.classList.toggle('running',running);
  // Show only when not idle. "Ready" / "Idle" → hide. Anything else → show.
  const isIdle=/\b(Ready|Idle)$/.test(text);
  el.classList.toggle('tb-hidden', isIdle);
  // Auto-hide finished state after 8 seconds
  clearTimeout(el._badgeTimer);
  if(/\b(Done|Cancelled|Error)\b/.test(text)){
    el._badgeTimer=setTimeout(()=>{
      el.classList.add('tb-hidden');
    }, 8000);
  }
}
// Initial state — both badges hidden until something runs
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('idx-badge')?.classList.add('tb-hidden');
  document.getElementById('aud-badge')?.classList.add('tb-hidden');
  sbRestoreGroups();
});
function resetStat(ids,val){ ids.forEach(id=>{const e=document.getElementById(id);if(e)e.textContent=val;}); }

// ── Dark mode ─────────────────────────────────────────────────────────────────
function toggleDark(){
  const dark=document.body.classList.toggle('dark');
  localStorage.setItem('seo-dark', dark?'1':'0');
  document.getElementById('dark-toggle').textContent=dark?'☀️':'🌙';
}
if(localStorage.getItem('seo-dark')==='1'){
  document.body.classList.add('dark');
  document.addEventListener('DOMContentLoaded',()=>{
    const btn=document.getElementById('dark-toggle');
    if(btn) btn.textContent='☀️';
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
_initThemePref();
renderHomeUC();
renderSidebarUC();
renderNavUC();
renderUCSelector();
renderUCRefTable();
loadSettings();
refreshInputForUseCases();
updateHomeStats();
initUserBadge();

// Populate version pills + server status
function refreshHealth(){
  fetch('/health').then(r=>r.json()).then(d=>{
    const v='v'+(d.version||'?');
    const sbV=document.getElementById('sb-version');
    const lgV=document.getElementById('logo-ver');
    if(sbV) sbV.textContent=v;
    if(lgV) lgV.textContent=v;
    const dot=document.querySelector('.sb-foot-dot');
    const txt=document.getElementById('sb-server-status');
    if(dot) dot.classList.remove('off');
    if(txt) txt.textContent='Server online';
  }).catch(()=>{
    const dot=document.querySelector('.sb-foot-dot');
    const txt=document.getElementById('sb-server-status');
    if(dot) dot.classList.add('off');
    if(txt) txt.textContent='Server offline';
  });
}
refreshHealth();
setInterval(refreshHealth, 30000); // every 30s

// Populate Reports count in sidebar
function refreshReportCount(){
  fetch('/api/reports').then(r=>r.json()).then(d=>{
    const el=document.getElementById('sb-rep-count');
    if(el && Array.isArray(d)){
      el.textContent=d.length;
      el.style.display=d.length?'inline-block':'none';
    }
  }).catch(()=>{});
}
refreshReportCount();

// ══════════════════════════════════════════════════════════════════════════════
// HELP MODAL
// ══════════════════════════════════════════════════════════════════════════════
const HELP_CONTENT = {
  overview: `
    <h3>What is SEO Suite?</h3>
    <p>A self-hosted toolkit for indexing checks and full SEO audits. Two main flows:</p>
    <ul>
      <li><b>🔍 Indexing Checker</b> — verifies which URLs Google has indexed via Playwright + Google's <code>site:</code> search.</li>
      <li><b>🔬 SEO Audit</b> — runs up to <b>35+ checks per URL</b> across 7 use cases, scored 0-100.</li>
    </ul>
    <h3>Workflow</h3>
    <ol>
      <li>Pick an input source — sitemap, domain, crawl, file upload, or pasted URLs</li>
      <li>(Audit) Pick use cases · drill into any to choose individual tasks</li>
      <li>Set parallel workers (1–8) and limits</li>
      <li>Hit Start — watch live in the streaming log, click any URL row for the detail drawer</li>
      <li>Open the HTML/PDF report or download CSV/XLSX from <b>Reports</b></li>
      <li>Use <b>Compare</b> to diff two audit runs · <b>Trend</b> to see indexing over time</li>
    </ol>
    <h3>Saved profiles</h3>
    <p>On the Audit page, save your current use-case + task selection as a named profile. Reload it anytime from the dropdown.</p>
  `,
  usecases: `
    <h3>The 7 use cases</h3>
    <p style="font-size:12.5px;color:var(--text2);margin-bottom:14px">Each use case targets a specific SEO dimension. Run them individually for a quick spot-check, combine presets for a focused audit, or run all 7 at once for a complete picture. Scores are 0–100 per URL.</p>

    <div class="help-uc-grid">

      <div class="help-uc-card">
        <div class="help-uc-hd">
          <span class="help-uc-icon">🕷️</span>
          <div>
            <div class="help-uc-name">Crawl Access</div>
            <div class="help-uc-sub">Can search engines find and crawl your pages?</div>
            <div class="help-uc-meta"><span class="help-tag free">No API needed</span><span class="help-uc-formats">Input: URL · Domain · Sitemap · CSV</span></div>
          </div>
        </div>
        <div class="help-uc-checks">
          <span class="help-uc-check">robots.txt rules</span>
          <span class="help-uc-check">HTTP status codes</span>
          <span class="help-uc-check">redirect chains</span>
          <span class="help-uc-check">broken internal links</span>
          <span class="help-uc-check">internal link count</span>
          <span class="help-uc-check">sitemap presence</span>
          <span class="help-uc-check">canonical tag</span>
          <span class="help-uc-check">meta robots / X-Robots-Tag</span>
        </div>
        <div class="help-uc-tip">Best for: diagnosing pages that aren&#39;t appearing in Google — catches blocks at the crawl layer before content analysis.</div>
        <div class="help-uc-out-lbl">Sample output</div>
        <div class="help-pre">URL: https://example.com/blog/post
  robots.txt      PASS   Allowed for Googlebot
  HTTP status     PASS   200 OK
  Redirects       WARN   2 hops (→ /blog → /blog/post)
  Broken links    FAIL   3 broken internal links found
  Internal links  PASS   24 internal links found
  Sitemap         PASS   Listed in /sitemap.xml
  Canonical       PASS   Self-referencing canonical
  Meta robots     PASS   No noindex directive
  Score: 71/100</div>
      </div>

      <div class="help-uc-card">
        <div class="help-uc-hd">
          <span class="help-uc-icon">📝</span>
          <div>
            <div class="help-uc-name">On-Page SEO</div>
            <div class="help-uc-sub">Is the page optimised for search visibility and click-through?</div>
            <div class="help-uc-meta"><span class="help-tag free">No API needed</span><span class="help-uc-formats">Input: URL · CSV</span></div>
          </div>
        </div>
        <div class="help-uc-checks">
          <span class="help-uc-check">canonical URL</span>
          <span class="help-uc-check">title tag length &amp; keywords</span>
          <span class="help-uc-check">meta description</span>
          <span class="help-uc-check">H1 / H2 / H3 structure</span>
          <span class="help-uc-check">image alt text</span>
          <span class="help-uc-check">word count</span>
          <span class="help-uc-check">readability score</span>
          <span class="help-uc-check">structured data / schema</span>
          <span class="help-uc-check">hreflang tags</span>
          <span class="help-uc-check">TTFB (response time)</span>
          <span class="help-uc-check">Open Graph / Twitter cards</span>
          <span class="help-uc-check">meta robots / X-Robots-Tag</span>
          <span class="help-uc-check">favicon</span>
        </div>
        <div class="help-uc-tip">Best for: content and SEO teams auditing landing pages, blog posts, or product pages before publishing or after a rankings drop.</div>
        <div class="help-uc-out-lbl">Sample output</div>
        <div class="help-pre">URL: https://example.com/services
  Title           PASS   58 chars — "SEO Audit Tools | Example"
  Meta desc       WARN   Missing meta description
  H1              PASS   Exactly 1 H1 found
  Word count      PASS   1 240 words
  Alt text        FAIL   4 of 9 images missing alt text
  Schema          PASS   Organization schema detected
  Open Graph      WARN   og:image not set
  Readability     PASS   Flesch score 62 (Good)
  Score: 68/100</div>
      </div>

      <div class="help-uc-card">
        <div class="help-uc-hd">
          <span class="help-uc-icon">🛡️</span>
          <div>
            <div class="help-uc-name">Site Health</div>
            <div class="help-uc-sub">Is the site secure, trustworthy, and technically sound?</div>
            <div class="help-uc-meta"><span class="help-tag free">No API needed</span><span class="help-uc-formats">Input: URL · Domain</span></div>
          </div>
        </div>
        <div class="help-uc-checks">
          <span class="help-uc-check">SSL certificate &amp; grade</span>
          <span class="help-uc-check">domain age &amp; expiry</span>
          <span class="help-uc-check">mixed content (HTTP on HTTPS)</span>
          <span class="help-uc-check">HTTPS enforcement</span>
          <span class="help-uc-check">security headers (CSP, HSTS…)</span>
          <span class="help-uc-check">SPF record</span>
          <span class="help-uc-check">DMARC policy</span>
          <span class="help-uc-check">MX records</span>
        </div>
        <div class="help-uc-tip">Best for: pre-launch checklists, client site takeovers, or any time you need a quick trust &amp; security snapshot without a full audit.</div>
        <div class="help-uc-out-lbl">Sample output</div>
        <div class="help-pre">Domain: example.com
  SSL grade         PASS   A+ (valid · 365 days remaining)
  Domain age        PASS   6 years, 3 months
  Mixed content     PASS   None detected
  HTTPS enforcement PASS   HTTP → HTTPS redirect confirmed
  Security headers  WARN   Missing: CSP, X-Frame-Options
  SPF record        PASS   Present
  DMARC             WARN   p=none (set p=reject to enforce)
  MX records        PASS   3 records found
  Score: 79/100</div>
      </div>

      <div class="help-uc-card">
        <div class="help-uc-hd">
          <span class="help-uc-icon">⚡</span>
          <div>
            <div class="help-uc-name">Performance</div>
            <div class="help-uc-sub">How fast does the page load for real users?</div>
            <div class="help-uc-meta"><span class="help-tag paid">Needs PageSpeed API key</span><span class="help-uc-formats">Input: URL · CSV</span></div>
          </div>
        </div>
        <div class="help-uc-checks">
          <span class="help-uc-check">PageSpeed score — mobile</span>
          <span class="help-uc-check">PageSpeed score — desktop</span>
          <span class="help-uc-check">mobile vs desktop gap</span>
          <span class="help-uc-check">GSC URL inspection</span>
          <span class="help-uc-check">LCP — Largest Contentful Paint</span>
          <span class="help-uc-check">CLS — Cumulative Layout Shift</span>
          <span class="help-uc-check">FCP — First Contentful Paint</span>
          <span class="help-uc-check">INP — Interaction to Next Paint</span>
        </div>
        <div class="help-uc-tip">Best for: Core Web Vitals checks before a Google algorithm update, or finding the slowest pages in a CSV of URLs to prioritise dev work. See <b>API Keys</b> tab to set up the free PageSpeed key.</div>
        <div class="help-uc-out-lbl">Sample output</div>
        <div class="help-pre">URL: https://example.com/
  PageSpeed mobile  WARN   61 / 100
  PageSpeed desktop PASS   88 / 100
  Mobile gap        WARN   27-point gap — optimise images &amp; defer JS
  GSC inspection    PASS   URL indexed, no issues
  LCP               WARN   3.2 s  (target &lt; 2.5 s)
  CLS               PASS   0.04   (target &lt; 0.1)
  FCP               PASS   1.4 s  (target &lt; 1.8 s)
  INP               PASS   78 ms  (target &lt; 200 ms)
  Score: 63/100</div>
      </div>

      <div class="help-uc-card">
        <div class="help-uc-hd">
          <span class="help-uc-icon">📊</span>
          <div>
            <div class="help-uc-name">Search Console</div>
            <div class="help-uc-sub">How is Google actually seeing and ranking your pages?</div>
            <div class="help-uc-meta"><span class="help-tag paid">Needs GSC API credentials</span><span class="help-uc-formats">Input: URL (must be in your verified property)</span></div>
          </div>
        </div>
        <div class="help-uc-checks">
          <span class="help-uc-check">clicks (last 28 days)</span>
          <span class="help-uc-check">impressions</span>
          <span class="help-uc-check">average CTR</span>
          <span class="help-uc-check">average position</span>
          <span class="help-uc-check">top queries</span>
          <span class="help-uc-check">coverage errors</span>
          <span class="help-uc-check">manual actions</span>
        </div>
        <div class="help-uc-tip">Best for: understanding real search traffic and query data from Google — no third-party estimates. Requires a service-account JSON and the site added to your Search Console property. See <b>API Keys</b> tab for the full setup guide.</div>
        <div class="help-uc-out-lbl">Sample output</div>
        <div class="help-pre">URL: https://example.com/blog/seo-guide
  Clicks (28d)    1 240
  Impressions     18 500
  CTR             6.7 %
  Avg. position   12.4
  Top queries:
    "seo audit tool"         → pos 8,  clicks 380
    "free seo checker"       → pos 14, clicks 210
    "on page seo checklist"  → pos 19, clicks 90
  Coverage errors  PASS  No errors
  Manual actions   PASS  None
  Score: 82/100</div>
      </div>

      <div class="help-uc-card">
        <div class="help-uc-hd">
          <span class="help-uc-icon">🔗</span>
          <div>
            <div class="help-uc-name">Authority</div>
            <div class="help-uc-sub">How trusted and well-linked is your domain?</div>
            <div class="help-uc-meta"><span class="help-tag free">Works without API (limited)</span><span class="help-uc-formats">Input: URL · Domain</span></div>
          </div>
        </div>
        <div class="help-uc-checks">
          <span class="help-uc-check">total backlinks</span>
          <span class="help-uc-check">domain authority (Moz)</span>
          <span class="help-uc-check">page authority (Moz)</span>
          <span class="help-uc-check">referring domains</span>
          <span class="help-uc-check">domain rank (DataForSEO)</span>
          <span class="help-uc-check">broken backlinks</span>
          <span class="help-uc-check">nofollow / dofollow ratio</span>
          <span class="help-uc-check">spam score</span>
        </div>
        <div class="help-uc-tip">Works free (basic checks only). Add a Moz or DataForSEO key to unlock full backlink data. Useful before a link-building campaign or when comparing your domain against a competitor&#39;s. See <b>API Keys</b> tab.</div>
        <div class="help-uc-out-lbl">Sample output</div>
        <div class="help-pre">Domain: example.com
  Backlinks         4 821
  Domain Authority  54  (Moz)
  Page Authority    38
  Referring domains 312
  Domain rank        67  (DataForSEO)
  Broken backlinks   24  ← review &amp; reclaim
  Nofollow ratio      2 %  (98 % dofollow)
  Spam score          4 %  PASS
  Score: 74/100</div>
      </div>

      <div class="help-uc-card">
        <div class="help-uc-hd">
          <span class="help-uc-icon">🏆</span>
          <div>
            <div class="help-uc-name">Rankings</div>
            <div class="help-uc-sub">Where does your page rank for target keywords?</div>
            <div class="help-uc-meta"><span class="help-tag paid">Needs SerpAPI key</span><span class="help-uc-formats">Input: URL + keywords (comma-separated)</span></div>
          </div>
        </div>
        <div class="help-uc-checks">
          <span class="help-uc-check">keyword position</span>
          <span class="help-uc-check">SERP features (snippets, PAA)</span>
          <span class="help-uc-check">top 10 competitor URLs</span>
          <span class="help-uc-check">rank change vs last run</span>
          <span class="help-uc-check">estimated traffic share</span>
        </div>
        <div class="help-uc-tip">Enter keywords in the field that appears when you select this use case. Run regularly to track rank movement. The free SerpAPI tier gives 100 searches/month — enough for weekly tracking of ~15 keywords. See <b>API Keys</b> tab for setup.</div>
        <div class="help-uc-out-lbl">Sample output</div>
        <div class="help-pre">URL: https://example.com/ · 3 keywords
  Keyword rankings:
    "seo audit tool"        Rank  7  ▲2
    "on page seo checker"   Rank 14  ▼1
    "free website seo test" Rank 23  ▲5
  SERP features   PASS   Featured Snippet for kw #1
  Competitor      moz.com · semrush.com · ahrefs.com
  Rank change     WARN   2 keywords dropped since last run
  Traffic share   PASS   ~4.2 % estimated organic share
  Score: 55/100  (avg. position 14.7)</div>
      </div>

    </div>

    <h3>Score weighting</h3>
    <p style="font-size:12.5px;color:var(--text2)">Each individual check carries a weight of 1–15 points based on SEO importance. The use-case score is <code>earned_points / total_points × 100</code>. <b>Pass</b> = full weight · <b>Warning</b> = half weight · <b>Fail / Error</b> = 0 points. The full-audit score averages all selected use cases.</p>
  `,
  keys: `
    <p style="font-size:12.5px;color:var(--text2);margin-bottom:14px">Three use cases work completely free. Four others unlock richer data when you add an API key. All keys are stored server-side in <code>data/config.json</code> — never exposed to the browser.</p>

    <div class="help-api-list">

      <div class="help-api-card">
        <div class="help-api-hd">⚡ PageSpeed Insights API <span class="help-tag free">Free</span></div>
        <p style="font-size:12px;color:var(--text2);margin:0 0 10px">Required for the <b>Performance</b> use case — Core Web Vitals, LCP, CLS, mobile score.</p>
        <ol class="help-steps">
          <li>Go to <a href="https://console.cloud.google.com/" target="_blank">console.cloud.google.com</a> and sign in with your Google account.</li>
          <li>Create a new project (or select an existing one) from the top dropdown.</li>
          <li>In the left menu go to <b>APIs &amp; Services → Library</b>.</li>
          <li>Search for <b>"PageSpeed Insights API"</b> → click it → click <b>Enable</b>.</li>
          <li>Go to <b>APIs &amp; Services → Credentials → + Create Credentials → API key</b>.</li>
          <li>Copy the generated key.</li>
          <li>In SEO Suite: open <b>Settings</b> from the sidebar → paste the key into <code>PAGESPEED_API_KEY</code> → Save.</li>
        </ol>
        <div class="help-out-lbl">What you unlock</div>
        <div class="help-pre">{
  "mobile_score":  61,
  "desktop_score": 88,
  "lcp":  3.2,       // Largest Contentful Paint (s)
  "inp":  78,        // Interaction to Next Paint (ms)
  "cls":  0.04,      // Cumulative Layout Shift
  "ttfb": 320,       // Time to First Byte (ms)
  "fcp":  1.1        // First Contentful Paint (s)
}</div>
        <div class="help-note">Quota: <b>25 000 free requests/day</b> — more than enough for any audit. No billing required unless you exceed this.</div>
      </div>

      <div class="help-api-card">
        <div class="help-api-hd">📊 Google Search Console API <span class="help-tag paid">Service account (free)</span></div>
        <p style="font-size:12px;color:var(--text2);margin:0 0 10px">Required for the <b>Search Console</b> use case — real clicks, impressions, positions, and top queries from Google.</p>
        <ol class="help-steps">
          <li>Go to <a href="https://console.cloud.google.com/" target="_blank">console.cloud.google.com</a> → your project → <b>APIs &amp; Services → Library</b>.</li>
          <li>Search <b>"Google Search Console API"</b> → Enable it.</li>
          <li>Go to <b>IAM &amp; Admin → Service Accounts → + Create Service Account</b>.</li>
          <li>Give it a name (e.g. <code>seo-suite-gsc</code>) → Continue → Done.</li>
          <li>Click the new service account → <b>Keys</b> tab → <b>Add Key → Create new key → JSON</b> → Download.</li>
          <li>Rename the downloaded file to <code>gsc_credentials.json</code> and place it in the <b>SEO Suite root folder</b> (same folder as <code>main.py</code>).</li>
          <li>Open <a href="https://search.google.com/search-console" target="_blank">search.google.com/search-console</a> → select your property → <b>Settings → Users and permissions → Add user</b>.</li>
          <li>Paste the service account email (found in the JSON under <code>"client_email"</code>) → set role to <b>Full</b> → Add.</li>
          <li>In SEO Suite: open <b>Settings</b> → enter your <b>Site URL</b> (must exactly match the GSC property, e.g. <code>https://example.com/</code>) → Save.</li>
        </ol>
        <div class="help-out-lbl">What you unlock</div>
        <div class="help-pre">{
  "url":         "https://example.com/blog/seo-guide",
  "clicks":      1240,
  "impressions": 18500,
  "ctr":         0.067,       // 6.7 %
  "position":    12.4,
  "top_queries": [
    { "query": "seo audit tool",       "position": 8,  "clicks": 380 },
    { "query": "free seo checker",     "position": 14, "clicks": 210 },
    { "query": "on page seo checklist","position": 19, "clicks": 90  }
  ],
  "coverage_errors": 0,
  "manual_actions":  0
}</div>
        <div class="help-note"><b>Tip:</b> the site URL in Settings must match the verified GSC property exactly — including the trailing slash and http/https scheme. A mismatch causes a "Permission denied" error.</div>
      </div>

      <div class="help-api-card">
        <div class="help-api-hd">🏆 SerpAPI <span class="help-tag free">100 free searches / month</span></div>
        <p style="font-size:12px;color:var(--text2);margin:0 0 10px">Required for the <b>Rankings</b> use case — live Google keyword positions, SERP features, and competitor URLs.</p>
        <ol class="help-steps">
          <li>Go to <a href="https://serpapi.com/" target="_blank">serpapi.com</a> → <b>Register</b> (no credit card needed for free tier).</li>
          <li>Verify your email and log in.</li>
          <li>Dashboard → <b>API Key</b> (shown on the home screen) → Copy.</li>
          <li>In SEO Suite: open <b>Settings</b> → paste the key into <code>SERPAPI_KEY</code> → Save.</li>
          <li>When running the Rankings use case, enter your <b>target keywords</b> comma-separated in the keywords field (e.g. <code>seo audit tool, on page seo checker</code>).</li>
        </ol>
        <div class="help-out-lbl">What you unlock</div>
        <div class="help-pre">{
  "url":     "https://example.com/",
  "keyword": "seo audit tool",
  "rank":    7,
  "change":  +2,           // vs previous run
  "serp_features": ["Featured Snippet", "People Also Ask"],
  "top_results": [
    { "position": 1, "url": "moz.com/free-seo-checker" },
    { "position": 2, "url": "semrush.com/seo-audit" },
    { "position": 3, "url": "ahrefs.com/seo-checker" }
  ]
}</div>
        <div class="help-note">Free tier: <b>100 searches/month</b>. Each keyword × URL pair = 1 search. Paid plans start at $50/mo for 5 000 searches — sufficient for weekly rank tracking of 100+ keywords.</div>
      </div>

      <div class="help-api-card">
        <div class="help-api-hd">🔗 Moz API <span class="help-tag free">10 free requests / month</span></div>
        <p style="font-size:12px;color:var(--text2);margin:0 0 10px">Optional for the <b>Authority</b> use case — Domain Authority, Page Authority, and spam score.</p>
        <ol class="help-steps">
          <li>Go to <a href="https://moz.com/products/api" target="_blank">moz.com/products/api</a> → <b>Get free API access</b>.</li>
          <li>Create a Moz account (free).</li>
          <li>Dashboard → <b>API Credentials</b> → copy <b>Access ID</b> and <b>Secret Key</b>.</li>
          <li>In SEO Suite: open <b>Settings</b> → paste into <code>MOZ_ACCESS_ID</code> and <code>MOZ_SECRET_KEY</code> → Save.</li>
        </ol>
        <div class="help-out-lbl">What you unlock</div>
        <div class="help-pre">{
  "domain":           "example.com",
  "domain_authority": 54,
  "page_authority":   38,
  "spam_score":        4,   // percent — lower is better
  "linking_domains":  312,
  "total_links":     4821
}</div>
        <div class="help-note">Free tier is limited to <b>10 requests/month</b>. If you need more, use <b>DataForSEO</b> (below) as a higher-volume alternative for backlink data.</div>
      </div>

      <div class="help-api-card">
        <div class="help-api-hd">🔗 DataForSEO <span class="help-tag paid">Pay-as-you-go · ~$0.002 / request</span></div>
        <p style="font-size:12px;color:var(--text2);margin:0 0 10px">Optional for <b>Authority</b> and <b>Rankings</b> — full backlink profiles, domain rank, and broken backlink detection at scale.</p>
        <ol class="help-steps">
          <li>Go to <a href="https://dataforseo.com/" target="_blank">dataforseo.com</a> → <b>Sign Up</b>.</li>
          <li>Verify your email. You start with a small free credit balance for testing.</li>
          <li>Dashboard → <b>API Access</b> → note your <b>Login</b> (email) and <b>Password</b>.</li>
          <li>In SEO Suite: open <b>Settings</b> → paste into <code>DATAFORSEO_LOGIN</code> and <code>DATAFORSEO_PASSWORD</code> → Save.</li>
        </ol>
        <div class="help-out-lbl">What you unlock</div>
        <div class="help-pre">{
  "domain":             "example.com",
  "domain_rank":        67,
  "backlinks":        4821,
  "referring_domains":  312,
  "broken_backlinks":    24,   // reclaim opportunities
  "nofollow_backlinks":  89,
  "dofollow_backlinks": 4732,
  "referring_ips":      198
}</div>
        <div class="help-note">Costs roughly <b>$0.002–$0.01 per domain lookup</b>. A typical audit of 50 domains costs under $0.50. Add funds via the DataForSEO dashboard — no monthly commitment.</div>
      </div>

    </div>

    <h3>Where to enter keys</h3>
    <p style="font-size:12.5px;color:var(--text2)">Open <b>Settings</b> from the sidebar → paste keys into the matching fields → click <b>Save</b>. Keys are stored in <code>data/config.json</code> on the server — they are never sent to the browser. You can also set them as environment variables in <code>.env</code> (environment variables always override the UI values).</p>
  `,
  shortcuts: `
    <h3>Keyboard shortcuts</h3>
    <table class="help-table">
      <thead><tr><th>Key</th><th>Action</th></tr></thead>
      <tbody>
        <tr><td><kbd>Ctrl</kbd> + <kbd>K</kbd></td><td>Open jump-to search in the topbar</td></tr>
        <tr><td><kbd>↑</kbd> / <kbd>↓</kbd></td><td>Navigate search results</td></tr>
        <tr><td><kbd>Enter</kbd></td><td>Confirm search jump · or start the active form (Indexing/Audit)</td></tr>
        <tr><td><kbd>Esc</kbd></td><td>Close drawer · close search · close help</td></tr>
      </tbody>
    </table>
    <h3>UI tips</h3>
    <ul>
      <li>Click any URL row in the live audit log to open the <b>detail drawer</b> with all checks</li>
      <li>Click status badges in the topbar to jump straight to Live Progress</li>
      <li>Hamburger collapses the sidebar to icon-only on desktop · slides as drawer on mobile</li>
      <li>Drag and drop a CSV/Excel file directly onto the upload zone</li>
      <li>Use the 📋 Copy URLs button on log filters to extract URLs for action</li>
    </ul>
  `,
  troubleshoot: `
    <h3>Common issues</h3>
    <div class="help-troubleshoot">
      <div class="ht-item">
        <div class="ht-q">"Unexpected token '&lt;'" or 404 errors after deploy</div>
        <div class="ht-a">The running server is on old code. <b>Restart <code>python main.py</code></b> to pick up new routes.</div>
      </div>
      <div class="ht-item">
        <div class="ht-q">Indexing check fails immediately / browser crash</div>
        <div class="ht-a">First time on this machine? Run <code>python -m playwright install chromium</code> once. If you keep getting CAPTCHAs, lower the URL limit and try the headless toggle.</div>
      </div>
      <div class="ht-item">
        <div class="ht-q">PageSpeed checks all return errors</div>
        <div class="ht-a">Add a PageSpeed Insights API key in <b>Settings</b>. Without one, performance checks are skipped.</div>
      </div>
      <div class="ht-item">
        <div class="ht-q">PDF export fails with "gobject-2.0-0" error</div>
        <div class="ht-a">That's the old WeasyPrint path — already replaced with Playwright PDF. Restart the server.</div>
      </div>
      <div class="ht-item">
        <div class="ht-q">Search Console returns "Permission denied"</div>
        <div class="ht-a">Add your service-account email as a user in the GSC property's Settings → Users and permissions. Verify <code>site_url</code> in Settings exactly matches the verified property.</div>
      </div>
      <div class="ht-item">
        <div class="ht-q">Audit takes forever</div>
        <div class="ht-a">Increase <b>Parallel workers</b> on the Audit page (default 3, max 8). Use task selection to skip checks you don't need.</div>
      </div>
    </div>
  `,
  about: `
    <h3>SEO Suite</h3>
    <p>Version: <code id="help-version">…</code> · Self-hosted Flask app + Playwright browser automation</p>
    <h3>Project layout</h3>
    <pre class="help-pre">SEO Suite/
├─ main.py              # entry point
├─ app/
│  ├─ server.py         # Flask app + all routes
│  ├─ templates/        # dashboard.html
│  └─ static/           # css, js
├─ core/
│  ├─ checker.py        # indexing checker (Playwright)
│  ├─ seo_audit.py      # audit orchestrator + report generation
│  └─ version.py
├─ tools/
│  ├─ phase1.py         # 24+ free on-page / technical checks
│  ├─ phase2.py         # PageSpeed + GSC URL inspection
│  ├─ phase3.py         # Search Console
│  └─ phase4.py         # Backlinks, DA, rankings
└─ data/                # reports · history · profiles · uploads</pre>
    <h3>Data location</h3>
    <ul>
      <li><code>data/reports/</code> — HTML/CSV/XLSX exports</li>
      <li><code>data/history.json</code> — indexing run log</li>
      <li><code>data/profiles.json</code> — saved audit profiles</li>
      <li><code>data/uploads/</code> — uploaded CSV/XLSX files</li>
      <li><code>data/app.log</code> — server logs</li>
    </ul>
  `,
};

function openHelp(){
  document.getElementById('help-mask').classList.add('on');
  document.getElementById('help-modal').classList.add('open');
  helpTab('overview', document.querySelector('.modal-tab'));
}
function closeHelp(){
  document.getElementById('help-mask').classList.remove('on');
  document.getElementById('help-modal').classList.remove('open');
}
function helpTab(name, btn){
  document.querySelectorAll('.modal-tab').forEach(t=>t.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const body=document.getElementById('help-body');
  body.innerHTML=HELP_CONTENT[name]||'<p>—</p>';
  body.scrollTop=0;
  // Inject version on About tab
  const v=document.getElementById('help-version');
  if(v){
    fetch('/health').then(r=>r.json()).then(d=>{
      v.textContent=(d.version||'?');
    }).catch(()=>{ v.textContent='offline'; });
  }
}
// ? key opens help; Space pauses/resumes audit when on live panel (not typing)
document.addEventListener('keydown',e=>{
  const t=e.target;
  const typing=t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.isContentEditable);
  if(e.key==='?' && !e.ctrlKey && !e.metaKey){
    if(typing) return;
    e.preventDefault();
    openHelp();
  } else if(e.key==='Escape'){
    closeHelp();
  } else if(e.key===' ' && !typing){
    // Space = pause/resume audit if it is running
    const audBtn=document.getElementById('aud-btn');
    if(audBtn&&audBtn.dataset.running){
      e.preventDefault();
      const resumeBtn=document.getElementById('aud-resume-btn');
      if(resumeBtn&&resumeBtn.style.display!=='none') resumeAudit();
      else pauseAudit();
    }
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// TOASTS (replace alert)
// ══════════════════════════════════════════════════════════════════════════════
function showFieldError(inputId, msg){
  const el=document.getElementById(inputId);
  if(!el) return;
  el.classList.add('input-error');
  const existing=el.parentNode.querySelector('.field-error');
  if(existing) existing.remove();
  const err=document.createElement('div');
  err.className='field-error';
  err.textContent=msg;
  el.parentNode.appendChild(err);
  el.addEventListener('input',()=>{
    el.classList.remove('input-error');
    err.remove();
  },{once:true});
}

function toast(msg, type='info', timeout=3500){
  const stack=document.getElementById('toast-stack');
  if(!stack) return alert(msg);
  const t=document.createElement('div');
  t.className='toast t-'+type;
  const icon={info:'ℹ️',success:'✓',warn:'⚠',error:'✕'}[type]||'•';
  t.innerHTML=`<span class="toast-icon">${icon}</span><span class="toast-msg">${msg}</span><button class="toast-close" onclick="this.parentNode.remove()">×</button>`;
  stack.appendChild(t);
  setTimeout(()=>{t.classList.add('out'); setTimeout(()=>t.remove(),300);}, timeout);
}

// ══════════════════════════════════════════════════════════════════════════════
// URL DETAIL DRAWER
// ══════════════════════════════════════════════════════════════════════════════
const _audUrlData={}; // url -> {score, issues, warnings, results, counts}

function openDrawer(url){
  const d=_audUrlData[url];
  if(!d){toast('No details available — wait for the audit to finish this URL','warn');return;}
  document.getElementById('drawer-title').textContent=url.replace(/^https?:\/\//,'').replace(/\/$/,'');
  const sc=d.score||0;
  const scClass=sc>=80?'lr-s-high':sc>=50?'lr-s-mid':'lr-s-low';
  document.getElementById('drawer-sub').innerHTML=
    `<a href="${url}" target="_blank" style="color:var(--primary)">${url}</a> · <span class="lr-score ${scClass}">${sc}</span> · ${d.issues||0} issues · ${d.warnings||0} warnings`;

  const body=document.getElementById('drawer-body');
  if(!d.results||!d.results.length){
    body.innerHTML='<div class="empty">No checks ran for this URL.</div>';
  }else{
    const groups={pass:[],warning:[],fail:[],error:[]};
    d.results.forEach(r=>(groups[r.status]||groups.error).push(r));
    const order=['fail','error','warning','pass'];
    body.innerHTML=order.filter(k=>groups[k].length).map(k=>{
      const label={pass:'Passed',warning:'Warnings',fail:'Issues',error:'Errors'}[k];
      const cls={pass:'check-ok',warning:'check-warn',fail:'check-fail',error:'check-err'}[k];
      return `<div class="check-group">
        <div class="check-group-title">${label} (${groups[k].length})</div>
        ${groups[k].map(r=>`
          <div class="check-row ${cls}">
            <div class="check-tool">${(r.tool||'').replace(/_/g,' ')}</div>
            <div class="check-msg">${r.message||'—'}</div>
          </div>`).join('')}
      </div>`;
    }).join('');
  }
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-mask').classList.add('on');
}
function closeDrawer(){
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-mask').classList.remove('on');
}
document.addEventListener('keydown',e=>{if(e.key==='Escape') closeDrawer();});

// Hook audit progress to capture per-URL data + make rows clickable
const _origAppendAudRow=typeof appendAudRow==='function'?appendAudRow:null;
if(_origAppendAudRow){
  appendAudRow=function(num,url,score,issues,warns){
    _origAppendAudRow(num,url,score,issues,warns);
    const rows=document.querySelectorAll('#aud-log .log-row');
    const row=rows[rows.length-1];
    if(row){
      row.style.cursor='pointer';
      row.title='Click to view full check results';
      row.addEventListener('click',ev=>{
        if(ev.target.tagName==='A') return;
        openDrawer(url);
      });
    }
  };
}
// Full-featured streamAudit: score distribution, throughput, top issues, pause/resume, partial export, row drawers
streamAudit=function(){
  if(_audES) _audES.close();
  _audES=new EventSource('/api/audit/stream');
  _audES.onmessage=e=>{
    const d=JSON.parse(e.data);
    if(d.type==='progress'){
      _audUrlData[d.url]={score:d.score,issues:d.issues,warnings:d.warnings,
                          results:d.results||[], counts:d.counts||{}};
      _audResultsMap.set(d.url,d.results||[]);
      _audTimes.push(Date.now());
      aDone++;aTotal=Math.max(aTotal,d.total||aDone);
      const sc=d.score||0;
      aScores.push(sc);aIssues+=d.issues||0;aWarns+=d.warnings||0;
      if(sc>=80) aExcellent++; else if(sc>=50) aGood++; else aPoor++;
      const avg=Math.round(aScores.reduce((a,b)=>a+b,0)/aScores.length);
      document.getElementById('as-done').textContent=aDone;
      document.getElementById('as-score').textContent=avg;
      document.getElementById('as-issues').textContent=aIssues;
      document.getElementById('as-warns').textContent=aWarns;
      const _audBarPct=aTotal?Math.round(aDone/aTotal*100):0;
      document.getElementById('aud-bar').style.width=_audBarPct+'%';
      const _audPctEl=document.getElementById('aud-pct');
      if(_audPctEl) _audPctEl.textContent=_audBarPct+'%';
      document.getElementById('aud-live-sub').textContent=`Audited ${aDone} of ${aTotal}`;
      appendAudRow(aDone,d.url,d.score,d.issues,d.warnings);
      // Score distribution strip
      _updateScoreDist();
      // Top failing checks
      (d.results||[]).forEach(r=>{
        if(r.status==='fail'||r.status==='error'){
          const lbl=(r.tool||'').replace(/_/g,' ');
          _audTopIssues.set(lbl,(_audTopIssues.get(lbl)||0)+1);
        }
      });
      _renderTopIssues();
      // Show partial export button after first result
      if(aDone===1){const pb=document.getElementById('aud-partial-btn');if(pb)pb.style.display='inline-flex';}

    } else if(d.type==='paused'){
      audSysLog('Paused — click Resume to continue');
      document.getElementById('aud-pause-btn').style.display='none';
      document.getElementById('aud-resume-btn').style.display='inline-flex';

    } else if(d.type==='resumed'){
      audSysLog('Resumed');
      document.getElementById('aud-pause-btn').style.display='inline-flex';
      document.getElementById('aud-resume-btn').style.display='none';

    } else if(d.type==='done'){
      document.getElementById('aud-bar').style.width='100%';
      const _audDonePct=document.getElementById('aud-pct');
      if(_audDonePct){_audDonePct.textContent='100%';_audDonePct.classList.add('done');}
      const avg=aScores.length?Math.round(aScores.reduce((a,b)=>a+b,0)/aScores.length):0;
      document.getElementById('aud-live-sub').textContent='Complete — '+aDone+' URLs audited';
      setBadge('aud-badge','Audit · Done',false);
      audDone(true);
      toast(`Audit complete — avg score ${avg}, ${aIssues} issues found`,'success',5000);
      _audLastReport=d.report?d.report.split(/[\\/]/).pop():'';
      _audLastXlsx  =d.xlsx  ?d.xlsx.split(/[\\/]/).pop()  :'';
      const elapsed=Math.round((Date.now()-_audRunStart)/1000);
      document.getElementById('aud-done-text').textContent=
        `✓ Done in ${fmtSecs(elapsed)} · avg score ${avg} · ${aIssues} issues · ${aWarns} warnings`;
      document.getElementById('aud-done-bar').classList.add('visible');
      const _ns2=document.getElementById('aud-next-steps'); if(_ns2) _ns2.style.display='block';
      if(_audLastReport){
        document.getElementById('aud-open-btn').style.display='inline-flex';
        const pdfBtn=document.getElementById('aud-pdf-btn');
        pdfBtn.href='/api/reports/pdf/'+_audLastReport;
        pdfBtn.style.display='inline-flex';
      }
      if(_audLastXlsx){
        const dlBtn=document.getElementById('aud-dl-btn');
        dlBtn.href='/api/download/'+_audLastXlsx;
        dlBtn.style.display='inline-flex';
      }
      updateHomeStats();
      refreshReportsSilent();
      _audES.close();_audES=null;

    } else if(d.type==='cancelled'){
      audDone(false);
      setBadge('aud-badge','Audit · Cancelled',false);
      document.getElementById('aud-live-sub').textContent=`Cancelled — ${d.done||aDone} URLs audited`;
      const doneBar=document.getElementById('aud-done-bar');
      if(d.report){
        _audLastReport=d.report;
        _audLastXlsx  =d.xlsx||'';
        const avg=aScores.length?Math.round(aScores.reduce((a,b)=>a+b,0)/aScores.length):0;
        document.getElementById('aud-done-text').textContent=
          `⚠ Cancelled after ${aDone} URLs — partial report saved · avg score ${avg}`;
        doneBar.classList.add('visible');
        document.getElementById('aud-open-btn').style.display='inline-flex';
        const pdfBtn=document.getElementById('aud-pdf-btn');
        pdfBtn.href='/api/reports/pdf/'+_audLastReport; pdfBtn.style.display='inline-flex';
        if(_audLastXlsx){
          const dlBtn=document.getElementById('aud-dl-btn');
          dlBtn.href='/api/download/'+_audLastXlsx; dlBtn.style.display='inline-flex';
        }
        audSysLog(`Partial report saved — ${aDone} of ${aTotal} URLs audited`,true);
        toast(`Cancelled — partial audit report saved (${aDone} URLs)`,'warn',6000);
      } else {
        audSysLog('Cancelled — no results to save (run was still starting)',true);
        toast('Cancelled before any URLs were audited','warn',4000);
      }
      updateHomeStats();
      refreshReportsSilent();
      _audES.close();_audES=null;

    } else if(d.type==='error'){
      audSysLog(d.message,true);
      document.getElementById('aud-live-sub').textContent='Error — see log';
      setBadge('aud-badge','Audit · Error',false);
      audDone(false);
      toast(d.message,'error',6000);
      _audES.close();_audES=null;
    }
  };
  _audES.onerror=()=>{if(_audES){_audES.close();_audES=null;}};
};

// ── Score distribution strip ───────────────────────────────────────────────────
function _updateScoreDist(){
  const total=aDone||1;
  const pHigh=Math.round(aExcellent/total*100);
  const pMid =Math.round(aGood/total*100);
  const pLow =100-pHigh-pMid;
  const sdbWrap=document.getElementById('sdb-wrap');
  const sdbLbls=document.getElementById('sdb-labels');
  if(sdbWrap) sdbWrap.style.display='flex';
  if(sdbLbls) sdbLbls.style.display='flex';
  const hi=document.getElementById('sdb-high');if(hi) hi.style.width=pHigh+'%';
  const mi=document.getElementById('sdb-mid'); if(mi) mi.style.width=pMid+'%';
  const lo=document.getElementById('sdb-low'); if(lo) lo.style.width=Math.max(0,pLow)+'%';
  const chi=document.getElementById('sdc-high');if(chi) chi.textContent=aExcellent;
  const cmi=document.getElementById('sdc-mid'); if(cmi) cmi.textContent=aGood;
  const clo=document.getElementById('sdc-low'); if(clo) clo.textContent=aPoor;
}

// ── Top failing checks panel ───────────────────────────────────────────────────
function _renderTopIssues(){
  const list=document.getElementById('aud-top-issues-list');
  const panel=document.getElementById('aud-top-issues');
  if(!list||!panel||_audTopIssues.size===0) return;
  panel.style.display='block';
  const sorted=[..._audTopIssues.entries()].sort((a,b)=>b[1]-a[1]).slice(0,5);
  const maxCnt=sorted[0][1]||1;
  list.innerHTML=sorted.map(([lbl,cnt])=>{
    const pct=Math.round(cnt/maxCnt*100);
    return `<div class="tir">
      <span class="tir-label">${lbl}</span>
      <div class="tir-bar-wrap"><div class="tir-bar" style="width:${pct}%"></div></div>
      <span class="tir-count">${cnt}</span>
    </div>`;
  }).join('');
}

// ── Pause / Resume audit ───────────────────────────────────────────────────────
function pauseAudit(){
  fetch('/api/audit/pause',{method:'POST'}).catch(()=>{});
  audSysLog('Pause requested…');
}
function resumeAudit(){
  fetch('/api/audit/resume',{method:'POST'}).catch(()=>{});
  audSysLog('Resume requested…');
  document.getElementById('aud-pause-btn').style.display='inline-flex';
  document.getElementById('aud-resume-btn').style.display='none';
}

// ── Browser notifications ──────────────────────────────────────────────────────
let _audNotifOn=false, _idxNotifOn=false;

function toggleAudNotif(btn){
  if(!('Notification' in window)){toast('Browser notifications not supported','warn');return;}
  if(Notification.permission==='denied'){toast('Notifications blocked — enable in browser settings','warn');return;}
  if(Notification.permission==='default'){
    Notification.requestPermission().then(p=>{if(p==='granted'){_audNotifOn=true;_syncNotifBtn(btn,true);}});
    return;
  }
  _audNotifOn=!_audNotifOn;
  _syncNotifBtn(btn,_audNotifOn);
  toast(_audNotifOn?'Audit notifications on':'Audit notifications off','info',2000);
}
function toggleIdxNotif(btn){
  if(!('Notification' in window)){toast('Browser notifications not supported','warn');return;}
  if(Notification.permission==='denied'){toast('Notifications blocked — enable in browser settings','warn');return;}
  if(Notification.permission==='default'){
    Notification.requestPermission().then(p=>{if(p==='granted'){_idxNotifOn=true;_syncNotifBtn(btn,true);}});
    return;
  }
  _idxNotifOn=!_idxNotifOn;
  _syncNotifBtn(btn,_idxNotifOn);
  toast(_idxNotifOn?'Indexing notifications on':'Indexing notifications off','info',2000);
}
function _syncNotifBtn(btn,on){
  if(!btn) return;
  btn.classList.toggle('notif-on',on);
  btn.title=on?'Notifications on — click to disable':'Enable browser notifications';
}
function _fireAudNotif(title,body){
  if(!_audNotifOn||Notification.permission!=='granted') return;
  try{ new Notification(title,{body,icon:'/static/img/logo.png'}); }catch(e){}
}
function _fireIdxNotif(title,body){
  if(!_idxNotifOn||Notification.permission!=='granted') return;
  try{ new Notification(title,{body,icon:'/static/img/logo.png'}); }catch(e){}
}

// ── Notification toggle dispatcher (HTML calls toggleNotif('aud'/'idx')) ───────
function toggleNotif(type){
  const btn=document.getElementById(type+'-notif-btn');
  if(type==='aud') toggleAudNotif(btn);
  else toggleIdxNotif(btn);
}

// ── Partial export ────────────────────────────────────────────────────────────
function exportPartialAudit(){
  window.open('/api/audit/partial','_blank');
}
function exportPartialIndex(){
  window.open('/api/index/partial','_blank');
}

// ══════════════════════════════════════════════════════════════════════════════
// SAVED PROFILES
// ══════════════════════════════════════════════════════════════════════════════
function loadProfilesList(){
  fetch('/api/profiles').then(r=>r.json()).then(profiles=>{
    const sel=document.getElementById('aud-profile');
    if(!sel) return;
    const cur=sel.value;
    sel.innerHTML='<option value="">— Select a profile —</option>'+
      Object.keys(profiles).sort().map(n=>`<option value="${n}">${n}</option>`).join('');
    if(cur && profiles[cur]) sel.value=cur;
  }).catch(()=>{});
}
function saveProfile(){
  const name=prompt('Profile name?');
  if(!name||!name.trim()) return;
  const flatTasks=[];
  selectedUC.forEach(uc=>{(selectedTasks[uc]||new Set()).forEach(t=>flatTasks.push(t));});
  const data={
    name: name.trim(),
    use_cases: [...selectedUC],
    tasks: flatTasks,
    keywords: document.getElementById('aud-kw').value,
    limit: +document.getElementById('aud-limit').value||10,
  };
  fetch('/api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
    .then(r=>r.json()).then(d=>{
      if(d.error){toast(d.error,'error');return;}
      toast(`Profile "${data.name}" saved`,'success');
      loadProfilesList();
    }).catch(e=>toast('Save failed: '+e,'error'));
}
function loadProfile(name){
  if(!name) return;
  fetch('/api/profiles').then(r=>r.json()).then(profiles=>{
    const p=profiles[name]; if(!p) return;
    selectedUC=new Set(p.use_cases||[]);
    Object.keys(TASK_DEFS).forEach(uc=>{
      selectedTasks[uc]=new Set((TASK_DEFS[uc]||[]).map(t=>t.id));
    });
    if(p.tasks && p.tasks.length){
      // Rebuild per-UC selection from flat task list
      Object.keys(TASK_DEFS).forEach(uc=>{
        const ucTasks=new Set((TASK_DEFS[uc]||[]).map(t=>t.id));
        const sel=new Set(p.tasks.filter(t=>ucTasks.has(t)));
        if(selectedUC.has(uc)) selectedTasks[uc]=sel.size?sel:ucTasks;
      });
    }
    if(p.keywords) document.getElementById('aud-kw').value=p.keywords;
    if(p.limit) document.getElementById('aud-limit').value=p.limit;
    renderUCSelector();
    document.getElementById('kw-row').style.display=selectedUC.has('rankings')?'block':'none';
    toast(`Loaded profile "${name}"`,'info');
  });
}
function deleteProfile(){
  const sel=document.getElementById('aud-profile');
  const name=sel.value;
  if(!name){toast('Pick a profile first','warn');return;}
  if(!confirm(`Delete profile "${name}"?`)) return;
  fetch('/api/profiles?name='+encodeURIComponent(name),{method:'DELETE'})
    .then(r=>r.json()).then(()=>{
      toast(`Deleted "${name}"`,'success');
      loadProfilesList();
    });
}

// ══════════════════════════════════════════════════════════════════════════════
// COMPARE
// ══════════════════════════════════════════════════════════════════════════════
function loadCompare(){
  fetch('/api/reports').then(r=>r.json()).then(reports=>{
    const audits=reports.filter(r=>r.kind==='audit'&&r.xlsx_name);
    const opts='<option value="">— Pick a report —</option>'+
      audits.map(r=>`<option value="${r.xlsx_name}">${r.name} · ${r.date}</option>`).join('');
    document.getElementById('cmp-a').innerHTML=opts;
    document.getElementById('cmp-b').innerHTML=opts;
  });
}
function runCompare(){
  const a=document.getElementById('cmp-a').value;
  const b=document.getElementById('cmp-b').value;
  if(!a||!b){toast('Pick two reports','warn');return;}
  if(a===b){toast('Pick two different reports','warn');return;}
  document.getElementById('cmp-result').innerHTML='<div class="card"><div class="empty">Comparing…</div></div>';
  fetch(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`)
    .then(r=>r.json()).then(d=>{
      if(d.error){
        document.getElementById('cmp-result').innerHTML=`<div class="card"><div class="empty" style="color:var(--danger)">${d.error}</div></div>`;
        return;
      }
      const rows=d.rows.sort((x,y)=>{
        if(x.delta===null) return 1;
        if(y.delta===null) return -1;
        return Math.abs(y.delta)-Math.abs(x.delta);
      });
      const tbody=rows.map(r=>{
        const sa=r.a_score==null?'—':r.a_score;
        const sb=r.b_score==null?'—':r.b_score;
        let dCell='—', cls='';
        if(r.added){dCell='<span class="cmp-tag cmp-new">NEW</span>'; cls='cmp-new-row';}
        else if(r.removed){dCell='<span class="cmp-tag cmp-removed">REMOVED</span>'; cls='cmp-removed-row';}
        else if(r.delta>0){dCell=`<span class="cmp-tag cmp-up">▲ +${r.delta}</span>`; cls='cmp-up-row';}
        else if(r.delta<0){dCell=`<span class="cmp-tag cmp-down">▼ ${r.delta}</span>`; cls='cmp-down-row';}
        else{dCell='<span class="cmp-tag cmp-flat">=</span>';}
        const short=r.url.replace(/^https?:\/\//,'').replace(/\/$/,'');
        return `<tr class="${cls}"><td title="${r.url}">${short}</td><td>${sa}</td><td>${sb}</td><td>${dCell}</td></tr>`;
      }).join('');
      const unchanged=rows.filter(r=>r.delta===0).length;
      document.getElementById('cmp-result').innerHTML=`
        <div class="rep-stats">
          <div class="rep-stat"><div class="rep-stat-n c-green">▲ ${d.improved}</div><div class="rep-stat-l">Improved</div></div>
          <div class="rep-stat"><div class="rep-stat-n c-red">▼ ${d.declined}</div><div class="rep-stat-l">Declined</div></div>
          <div class="rep-stat"><div class="rep-stat-n" style="color:#64748B">= ${unchanged}</div><div class="rep-stat-l">Unchanged</div></div>
          <div class="rep-stat"><div class="rep-stat-n c-blue">+ ${d.added}</div><div class="rep-stat-l">New URLs</div></div>
          <div class="rep-stat"><div class="rep-stat-n" style="color:#F59E0B">− ${d.removed||0}</div><div class="rep-stat-l">Removed</div></div>
        </div>
        <div class="card"><table>
          <thead><tr><th>URL</th><th>A</th><th>B</th><th>Δ</th></tr></thead>
          <tbody>${tbody}</tbody>
        </table></div>`;
    });
}

loadProfilesList();

// ════════════════════════════════════════════════════════════════════════════
// QUICK TOOLS — Phase A
// ════════════════════════════════════════════════════════════════════════════

// ── Tool 1: SERP Snippet Preview ─────────────────────────────────────────────
async function runSerpPreview() {
  const url = document.getElementById('serp-url').value.trim();
  if (!url) { toast('Enter a URL first', 'warn'); return; }
  const btn = document.getElementById('serp-btn');
  btn.textContent = 'Fetching…'; btn.disabled = true;
  document.getElementById('serp-result').style.display = 'none';
  document.getElementById('serp-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/serp_preview', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');
    renderSerpPreview(d);
  } catch(e) {
    document.getElementById('serp-error').style.display = '';
    document.getElementById('serp-error').textContent = '✖ ' + e.message;
  } finally {
    btn.textContent = 'Fetch Preview'; btn.disabled = false;
  }
}

function renderSerpPreview(d) {
  const parsed = new URL(d.url);
  document.getElementById('serp-favicon').src     = d.favicon_url;
  document.getElementById('serp-site-name').textContent  = parsed.hostname;
  document.getElementById('serp-breadcrumb').textContent = d.display_url;
  document.getElementById('serp-title-text').textContent = d.title || '(no title)';
  document.getElementById('serp-desc-text').textContent  = d.description || '(no description)';

  const titleColor = d.title_len > 60 ? 'var(--danger)' : d.title_len < 30 ? 'var(--warn)' : 'var(--success)';
  const descColor  = d.desc_len  > 160? 'var(--danger)' : d.desc_len  < 70 ? 'var(--warn)' : 'var(--success)';
  document.getElementById('serp-meta-grid').innerHTML = `
    <div class="serp-meta-item">
      <div class="serp-meta-label">Title length</div>
      <div class="serp-meta-val" style="color:${titleColor}">${d.title_len}</div>
      <div class="serp-meta-sub">chars · ideal 30–60</div>
    </div>
    <div class="serp-meta-item">
      <div class="serp-meta-label">Description length</div>
      <div class="serp-meta-val" style="color:${descColor}">${d.desc_len}</div>
      <div class="serp-meta-sub">chars · ideal 70–160</div>
    </div>`;

  const wDiv = document.getElementById('serp-warnings');
  if (d.warnings.length === 0) {
    wDiv.innerHTML = '<div class="serp-warn-item ok">✓ Title and description look good</div>';
  } else {
    wDiv.innerHTML = d.warnings.map(w => `<div class="serp-warn-item warn">⚠ ${escTool(w)}</div>`).join('');
  }

  const og = d.og, tw = d.twitter;
  document.getElementById('og-site').textContent  = parsed.hostname.toUpperCase();
  document.getElementById('og-title').textContent = og.title || d.title || '(no og:title)';
  document.getElementById('og-desc').textContent  = og.description || d.description || '(no og:description)';
  const ogImg = document.getElementById('og-img');
  if (og.image) { ogImg.src = og.image; ogImg.style.display = ''; } else { ogImg.style.display = 'none'; }

  document.getElementById('tw-site').textContent  = parsed.hostname.toUpperCase();
  document.getElementById('tw-title').textContent = tw.title || d.title || '(no twitter:title)';
  document.getElementById('tw-desc').textContent  = tw.description || d.description || '(no twitter:description)';
  const twImg = document.getElementById('tw-img');
  if (tw.image) { twImg.src = tw.image; twImg.style.display = ''; } else { twImg.style.display = 'none'; }

  document.getElementById('serp-result').style.display = '';
}

function serpSocialTab(tab, btn) {
  document.querySelectorAll('#panel-tool-serp .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('serp-og-panel').style.display = tab === 'og' ? '' : 'none';
  document.getElementById('serp-tw-panel').style.display = tab === 'tw' ? '' : 'none';
}


// ── Tool 2: Redirect Chain Checker ────────────────────────────────────────────
async function runRedirectChain() {
  const url = document.getElementById('redir-url').value.trim();
  if (!url) { toast('Enter a URL first', 'warn'); return; }
  document.getElementById('redir-result').style.display = 'none';
  document.getElementById('redir-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/redirect_chain', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');

    document.getElementById('redir-summary').innerHTML = `
      <div class="redir-stat-box"><div class="redir-stat-n">${d.total_hops}</div><div class="redir-stat-l">Hops</div></div>
      <div class="redir-stat-box"><div class="redir-stat-n">${d.hops.reduce((s,h)=>s+(h.latency_ms||0),0)} ms</div><div class="redir-stat-l">Total latency</div></div>
      <div class="redir-stat-box"><div class="redir-stat-n">${d.hops[d.hops.length-1]?.status || '?'}</div><div class="redir-stat-l">Final status</div></div>`;

    document.getElementById('redir-issues').innerHTML = d.issues.map(i =>
      `<div class="redir-issue warn">⚠ ${escTool(i)}</div>`
    ).join('');

    document.getElementById('redir-chain').innerHTML = d.hops.map((h,i) => {
      const isFinal = i === d.hops.length - 1;
      const cls  = isFinal ? 'final' : (h.status >= 400 ? 'error' : '');
      const sCls = h.status === 301 ? 's301' : h.status === 302 ? 's302' : h.status === 200 ? 's200' : 'serr';
      return `
        <div class="redir-hop">
          <div class="redir-hop-num ${cls}">${i + 1}</div>
          <div class="redir-hop-body">
            <div class="redir-hop-url">${escTool(h.url)}</div>
            <div class="redir-hop-meta">
              <span class="redir-badge ${sCls}">${h.status || '?'}</span>
              ${h.type ? `<span style="color:var(--text3);font-size:12px">${escTool(h.type)}</span>` : ''}
              ${h.latency_ms != null ? `<span style="color:var(--text3);font-size:12px">${h.latency_ms} ms</span>` : ''}
            </div>
            ${h.redirect_to ? `<div style="font-size:12px;color:var(--text3);margin-top:4px">→ ${escTool(h.redirect_to)}</div>` : ''}
          </div>
        </div>`;
    }).join('');

    document.getElementById('redir-result').style.display = '';
  } catch(e) {
    document.getElementById('redir-error').style.display = '';
    document.getElementById('redir-error').textContent = '✖ ' + e.message;
  }
}


// ── Tool 3: HTTP Headers Viewer ────────────────────────────────────────────────
async function runHttpHeaders() {
  const url     = document.getElementById('hdrs-url').value.trim();
  const seoOnly = document.getElementById('hdrs-seo-only').checked;
  if (!url) { toast('Enter a URL first', 'warn'); return; }
  document.getElementById('hdrs-result').style.display = 'none';
  document.getElementById('hdrs-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/http_headers', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');

    document.getElementById('hdrs-highlights').innerHTML = d.highlights.map(h =>
      `<div class="hdrs-hl ${h.level}">${h.level==='error'?'✖':h.level==='warn'?'⚠':'ℹ'} ${escTool(h.msg)}</div>`
    ).join('');

    const rows = seoOnly ? d.headers.filter(h => h.seo_relevant) : d.headers;
    document.getElementById('hdrs-tbody').innerHTML = rows.map(h => `
      <tr class="${h.seo_relevant ? 'hdrs-seo-row' : ''}">
        <td style="font-family:monospace;font-size:12px;white-space:nowrap">${escTool(h.name)}</td>
        <td style="font-size:12px;word-break:break-all">${escTool(h.value)}</td>
        <td style="font-size:12px;color:var(--text3)">${escTool(h.note)}</td>
      </tr>`
    ).join('');

    // Missing SEO-critical headers summary
    const presentNames = new Set(d.headers.map(h => h.name.toLowerCase()));
    const recommended = [
      { name:'x-content-type-options', why:'Prevents MIME-type sniffing; improves security signals' },
      { name:'x-frame-options',        why:'Protects against clickjacking; minor trust signal' },
      { name:'referrer-policy',        why:'Controls referrer data leakage to third parties' },
      { name:'permissions-policy',     why:'Declares which browser features are allowed' },
      { name:'cache-control',          why:'Controls caching; affects crawl efficiency and speed' },
      { name:'content-security-policy',why:'Restricts resource origins; strong security header' },
      { name:'strict-transport-security', why:'Forces HTTPS; prevents redirect hops from HTTP' },
    ];
    const missing = recommended.filter(r => !presentNames.has(r.name));
    const missWrap = document.getElementById('hdrs-missing');
    if (missWrap) {
      if (missing.length) {
        missWrap.style.display = '';
        missWrap.innerHTML = `<div class="section-title" style="margin-bottom:8px;font-size:12px">Missing recommended headers (${missing.length})</div>`
          + missing.map(m => `<div class="hdrs-missing-row"><code class="hdrs-missing-name">${m.name}</code><span class="hdrs-missing-why">${m.why}</span></div>`).join('');
      } else {
        missWrap.style.display = '';
        missWrap.innerHTML = `<div style="font-size:13px;color:var(--success-d);font-weight:600">✓ All recommended security &amp; SEO headers are present</div>`;
      }
    }

    document.getElementById('hdrs-result').style.display = '';
  } catch(e) {
    document.getElementById('hdrs-error').style.display = '';
    document.getElementById('hdrs-error').textContent = '✖ ' + e.message;
  }
}

document.getElementById('hdrs-seo-only').addEventListener('change', () => {
  if (document.getElementById('hdrs-result').style.display !== 'none') runHttpHeaders();
});


// ── Tool 4: Keyword Density Checker ──────────────────────────────────────────
async function runKeywordDensity() {
  const url  = document.getElementById('kw-url').value.trim();
  const topN = parseInt(document.getElementById('kw-top').value) || 20;
  if (!url) { toast('Enter a URL first', 'warn'); return; }
  document.getElementById('kw-result').style.display = 'none';
  document.getElementById('kw-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/keyword_density', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url, top_n:topN})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');

    document.getElementById('kw-summary').innerHTML = `
      <div class="kw-stat"><div class="kw-stat-n">${d.total_words.toLocaleString()}</div><div class="kw-stat-l">Total words</div></div>
      <div class="kw-stat"><div class="kw-stat-n">${d.unique_words.toLocaleString()}</div><div class="kw-stat-l">Unique words</div></div>
      <div class="kw-stat"><div class="kw-stat-n">${d.top_keywords.length}</div><div class="kw-stat-l">Showing</div></div>`;

    const maxDensity = Math.max(...d.top_keywords.map(k => parseFloat(k.density)), 0.01);
    document.getElementById('kw-tbody').innerHTML = d.top_keywords.map((k, i) => {
      const pct = Math.round(parseFloat(k.density) / maxDensity * 100);
      const hi  = parseFloat(k.density) >= 5;
      return `<tr>
        <td>${i + 1}</td>
        <td style="font-weight:500">${escTool(k.keyword)}</td>
        <td>${k.count}</td>
        <td>
          <div class="kw-bar-wrap">
            <div class="kw-bar-track"><div class="kw-bar-fill${hi?' kw-hi':''}" style="width:${pct}%"></div></div>
            <span class="kw-bar-pct${hi?' kw-hi':''}">${k.density}%</span>
          </div>
        </td>
        <td class="${k.in_title ? 'kw-in' : 'kw-out'}">${k.in_title ? '✓' : '—'}</td>
        <td class="${k.in_h1 ? 'kw-in' : 'kw-out'}">${k.in_h1 ? '✓' : '—'}</td>
      </tr>`;
    }).join('');

    document.getElementById('kw-result').style.display = '';
  } catch(e) {
    document.getElementById('kw-error').style.display = '';
    document.getElementById('kw-error').textContent = '✖ ' + e.message;
  }
}


// ── Tool 5: Code-to-Text Ratio ────────────────────────────────────────────────
async function runCodeTextRatio() {
  const url = document.getElementById('ratio-url').value.trim();
  if (!url) { toast('Enter a URL first', 'warn'); return; }
  document.getElementById('ratio-result').style.display = 'none';
  document.getElementById('ratio-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/code_text_ratio', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');

    const codeBytes = d.html_bytes - d.text_bytes;
    const codePct   = Math.round(100 - d.ratio_pct);

    const pctEl = document.getElementById('ratio-pct');
    pctEl.textContent = d.ratio_pct + '%';
    pctEl.style.color = d.rating==='good' ? 'var(--success)' : d.rating==='average' ? 'var(--warn)' : 'var(--danger)';

    document.getElementById('ratio-bars').innerHTML = `
      <div class="ratio-bar-wrap">
        <div class="ratio-bar-label"><span>Text (${(d.text_bytes/1024).toFixed(1)} KB)</span><span>${d.ratio_pct}%</span></div>
        <div class="ratio-bar-track"><div class="ratio-bar-fill text" style="width:${d.ratio_pct}%"></div></div>
      </div>
      <div class="ratio-bar-wrap">
        <div class="ratio-bar-label"><span>HTML/Code (${(codeBytes/1024).toFixed(1)} KB)</span><span>${codePct}%</span></div>
        <div class="ratio-bar-track"><div class="ratio-bar-fill code" style="width:${codePct}%"></div></div>
      </div>`;

    document.getElementById('ratio-advice').innerHTML =
      `<div class="ratio-advice-box ${d.rating}">${d.rating==='good'?'✓':'⚠'} ${escTool(d.advice)}</div>`;

    document.getElementById('ratio-result').style.display = '';
  } catch(e) {
    document.getElementById('ratio-error').style.display = '';
    document.getElementById('ratio-error').textContent = '✖ ' + e.message;
  }
}


// ── Tool 6: GZIP & Cache Headers ──────────────────────────────────────────────
async function runCompression() {
  const url = document.getElementById('comp-url').value.trim();
  if (!url) { toast('Enter a URL first', 'warn'); return; }
  document.getElementById('comp-result').style.display = 'none';
  document.getElementById('comp-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/compression', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');

    const rating = d.score >= 80 ? 'good' : d.score >= 50 ? 'average' : 'poor';
    document.getElementById('comp-score-row').innerHTML = `
      <div class="comp-score-circle ${rating}">${d.score}</div>
      <div class="comp-score-text">${d.passed} of ${d.total} checks passed</div>`;

    document.getElementById('comp-checks').innerHTML = d.checks.map(c => `
      <div class="comp-check">
        <div class="comp-check-icon ${c.pass ? 'pass' : 'fail'}">${c.pass ? '✓' : '✖'}</div>
        <div class="comp-check-body">
          <div class="comp-check-name">${escTool(c.name)}</div>
          <div class="comp-check-val">${escTool(c.value)}</div>
          ${!c.pass ? `<div class="comp-check-advice">${escTool(c.advice)}</div>` : ''}
        </div>
      </div>`
    ).join('');

    document.getElementById('comp-result').style.display = '';
  } catch(e) {
    document.getElementById('comp-error').style.display = '';
    document.getElementById('comp-error').textContent = '✖ ' + e.message;
  }
}

function escTool(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
/** Allow only http/https URLs in href attributes — blocks javascript: URIs. */
function safeHref(u) {
  return /^https?:\/\//i.test(String(u||'')) ? escTool(u) : '#';
}

// ════════════════════════════════════════════════════════════════════════════
// USE CASE RUNNER
// ════════════════════════════════════════════════════════════════════════════

// UC_META and UC_CONFIG are aliases — UC_DEFS is the single source of truth
const UC_META   = UC_DEFS;
const UC_CONFIG = UC_DEFS;

let _activeUseCase = null;
let _activeUcFormat = 'url';

// (formats / hint / requires are now on UC_DEFS directly — keeping UC_CONFIG alias above
// so existing UC_CONFIG[uc].formats / UC_CONFIG[uc].hint calls keep working unchanged)

function setUcFormat(fmt, btn) {
  _activeUcFormat = fmt;
  document.querySelectorAll('.uc-fmt-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _applyUcFormat();
}

function _applyUcFormat() {
  const textRow   = document.getElementById('uc-text-row');
  const fileRow   = document.getElementById('uc-file-row');
  const inputLbl  = document.getElementById('uc-input-label');
  const urlInput  = document.getElementById('uc-url');

  if (_activeUcFormat === 'csv') {
    textRow.style.display = 'none';
    fileRow.style.display = '';
  } else {
    textRow.style.display = '';
    fileRow.style.display = 'none';
    if (_activeUcFormat === 'url') {
      inputLbl.textContent = 'Page URL';
      urlInput.placeholder = 'https://example.com/page';
    } else if (_activeUcFormat === 'domain') {
      inputLbl.textContent = 'Domain';
      urlInput.placeholder = 'https://example.com';
    } else if (_activeUcFormat === 'sitemap') {
      inputLbl.textContent = 'Sitemap URL';
      urlInput.placeholder = 'https://example.com/sitemap.xml';
    }
  }
}

function _updateUcFormatTabs(uc) {
  const _raw = UC_CONFIG[uc] || {};
  const cfg = {
    formats:  _raw.formats  || ['url'],
    hint:     _raw.hint     || '',
    requires: Array.isArray(_raw.requires) ? _raw.requires
              : (_raw.requires ? [_raw.requires] : []),
  };
  const tabs = document.getElementById('uc-fmt-tabs');
  if (!tabs) return;
  tabs.querySelectorAll('.uc-fmt-tab').forEach(btn => {
    const fmt = btn.dataset.fmt;
    const allowed = cfg.formats.includes(fmt);
    btn.style.display = allowed ? '' : 'none';
    if (!allowed && btn.classList.contains('active')) {
      // switch to first allowed
      _activeUcFormat = cfg.formats[0];
      tabs.querySelector(`[data-fmt="${cfg.formats[0]}"]`)?.classList.add('active');
      btn.classList.remove('active');
    }
  });
  // Ensure active tab is valid
  if (!cfg.formats.includes(_activeUcFormat)) {
    _activeUcFormat = cfg.formats[0];
    tabs.querySelectorAll('.uc-fmt-tab').forEach(b => b.classList.remove('active'));
    tabs.querySelector(`[data-fmt="${_activeUcFormat}"]`)?.classList.add('active');
  }
  // Hint
  const hint = document.getElementById('uc-fmt-hint');
  if (hint) hint.textContent = cfg.hint || '';
  // Requirement badges
  const badges = document.getElementById('uc-req-badges');
  if (badges) {
    badges.innerHTML = cfg.requires.length
      ? cfg.requires.map(r => `<span class="uc-req-badge required">⚠ ${r}</span>`).join('')
      : '<span class="uc-req-badge optional">No API keys needed</span>';
  }
  _applyUcFormat();
}

// _UC_INFO_STUB removed — UC_INFO at top of file is the single source

function _renderUcInfoPanel(uc) {
  const info = UC_INFO[uc] || {};
  const panel = document.getElementById('uc-info-panel');
  if (!panel) return;

  // Guide section
  document.getElementById('uc-info-icon').textContent = (UC_META[uc] || {}).icon || '🔍';
  document.getElementById('uc-info-title').textContent = `What ${(UC_META[uc] || {}).label || uc} checks`;
  document.getElementById('uc-info-desc').textContent  = info.desc || '';

  // Check pills
  const checksEl = document.getElementById('uc-info-checks');
  checksEl.innerHTML = (info.checks || []).map(c =>
    `<span class="tool-guide-tip">${c}</span>`
  ).join('');

  // "When to use" tip
  const whenEl = document.getElementById('uc-info-when');
  if (info.when) {
    whenEl.innerHTML = `<div style="margin-top:10px;font-size:12px;color:var(--text2);border-left:3px solid var(--primary);padding-left:8px;line-height:1.55"><b>When to use:</b> ${info.when}</div>`;
  } else {
    whenEl.innerHTML = '';
  }

  // Example output
  document.getElementById('uc-info-example').textContent = info.example || '';

  // Pro tips
  const tipsEl = document.getElementById('uc-info-tips');
  tipsEl.innerHTML = (info.tips || []).map(t =>
    `<span class="tool-guide-tip">💡 ${t}</span>`
  ).join('');

  // API notice
  const apiNotice = document.getElementById('uc-api-notice');
  if (info.api) {
    document.getElementById('uc-api-notice-title').textContent = info.api.title;
    document.getElementById('uc-api-notice-steps').innerHTML = (info.api.steps || [])
      .map(s => `<li>${s}</li>`).join('');
    apiNotice.style.display = '';
  } else {
    apiNotice.style.display = 'none';
  }

  // Related use cases
  const UC_RELATED_MAP = {
    crawlability:   ['on_page','site_health'],
    on_page:        ['crawlability','site_health','performance'],
    site_health:    ['crawlability','on_page'],
    performance:    ['on_page','site_health'],
    search_console: ['rankings','authority'],
    authority:      ['search_console','rankings'],
    rankings:       ['search_console','authority','on_page'],
  };
  const related = UC_RELATED_MAP[uc] || [];
  const relSection = document.getElementById('uc-related-section');
  const relGrid    = document.getElementById('uc-related-grid');
  if (relSection && relGrid && related.length) {
    relGrid.innerHTML = related.map(r => {
      const m = UC_META[r] || {};
      return `<div class="uc-related-item" onclick="openUseCase('${r}')">
        <span class="uc-related-icon">${m.icon||'🔍'}</span>${m.label||r}
      </div>`;
    }).join('');
    relSection.style.display = '';
  } else if (relSection) {
    relSection.style.display = 'none';
  }

  panel.style.display = '';
}

function openUseCase(uc) {
  _activeUseCase = uc;
  const meta = UC_META[uc] || {};
  document.getElementById('uc-icon').textContent    = meta.icon  || '🔍';
  document.getElementById('uc-title').textContent   = meta.label || uc;
  document.getElementById('uc-desc').textContent    = meta.desc  || '';
  document.getElementById('uc-run-btn').textContent = `Run ${meta.label || 'Check'}`;

  // Show keywords row only for rankings
  document.getElementById('uc-keywords-row').style.display = uc === 'rankings' ? '' : 'none';

  // Reset result area, show info panel
  document.getElementById('uc-results').style.display    = 'none';
  document.getElementById('uc-error').style.display      = 'none';
  document.getElementById('uc-spinner').style.display    = 'none';
  _renderUcInfoPanel(uc);

  // Update format tabs & hints for this use case
  _updateUcFormatTabs(uc);

  // Update active sidebar item highlight
  document.querySelectorAll('[data-panel="uc-runner"]').forEach(el => {
    el.classList.toggle('active', el.dataset.name === meta.label);
  });
}

function copyUcResults() {
  const title  = document.getElementById('uc-title')?.textContent || 'Use Case';
  const checks = document.getElementById('uc-checks-list');
  if (!checks) return;
  const lines = [`${title} — Results`, ''];
  checks.querySelectorAll('[class*="uc-check"]').forEach(row => {
    const label  = row.querySelector('[class*="label"],[class*="name"],[class*="title"]');
    const status = row.querySelector('[class*="status"],[class*="badge"],[class*="icon"]');
    if (label) lines.push(`${status?.textContent?.trim() || ''} ${label.textContent.trim()}`);
  });
  // fallback: just grab all text content
  if (lines.length <= 2) lines.push(checks.innerText.trim());
  navigator.clipboard.writeText(lines.join('\n'))
    .then(() => toast('Results copied to clipboard', 'success', 2500))
    .catch(() => toast('Copy failed — try manually selecting the text', 'warn'));
}

async function runUseCase() {
  if (!_activeUseCase) { toast('Select a use case from the sidebar', 'warn'); return; }

  const btn = document.getElementById('uc-run-btn');
  btn.disabled = true;
  document.getElementById('uc-results').style.display = 'none';
  document.getElementById('uc-error').style.display   = 'none';
  document.getElementById('uc-spinner').style.display = '';

  try {
    let fetchOpts, url;

    if (_activeUcFormat === 'csv') {
      const fileInput = document.getElementById('uc-file');
      if (!fileInput.files.length) { toast('Select a CSV or XLSX file', 'warn'); return; }
      const fd = new FormData();
      fd.append('file', fileInput.files[0]);
      fd.append('use_case', _activeUseCase);
      if (_activeUseCase === 'rankings') {
        const kw = document.getElementById('uc-keywords').value.trim();
        if (kw) fd.append('keywords', kw);
      }
      url = '/api/usecase/run_bulk';
      fetchOpts = { method: 'POST', body: fd };
    } else {
      const inputUrl = document.getElementById('uc-url').value.trim();
      if (!inputUrl) { toast('Enter a ' + (_activeUcFormat === 'sitemap' ? 'sitemap URL' : _activeUcFormat === 'domain' ? 'domain' : 'URL') + ' first', 'warn'); return; }
      const body = { url: inputUrl, use_case: _activeUseCase, input_format: _activeUcFormat };
      if (_activeUseCase === 'rankings') {
        const kw = document.getElementById('uc-keywords').value.trim();
        if (kw) body.keywords = kw;
      }
      url = '/api/usecase/run';
      fetchOpts = { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) };
    }

    const r = await fetch(url, fetchOpts);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');
    renderUCResults(d);
  } catch(e) {
    document.getElementById('uc-error').style.display = '';
    document.getElementById('uc-error').textContent   = '✖ ' + e.message;
  } finally {
    document.getElementById('uc-spinner').style.display = 'none';
    btn.disabled = false;
  }
}

function renderUCResults(d) {
  // Hide info panel now that real results are showing
  const infoPnl = document.getElementById('uc-info-panel');
  if (infoPnl) infoPnl.style.display = 'none';

  const meta       = UC_META[d.use_case] || {};
  const scoreColor = d.score >= 80 ? 'var(--success-d)' : d.score >= 50 ? 'var(--warn-d)' : 'var(--danger-d)';

  document.getElementById('uc-score-row').innerHTML = `
    <div class="uc-score-box">
      <div class="uc-score-num" style="color:${scoreColor}">${d.score}</div>
      <div class="uc-score-lbl">Score</div>
    </div>
    <div class="uc-score-box">
      <div class="uc-score-num" style="color:var(--success-d)">${d.passes}</div>
      <div class="uc-score-lbl">Passed</div>
    </div>
    <div class="uc-score-box">
      <div class="uc-score-num" style="color:var(--warn-d)">${d.warnings}</div>
      <div class="uc-score-lbl">Warnings</div>
    </div>
    <div class="uc-score-box">
      <div class="uc-score-num" style="color:var(--danger-d)">${d.fails}</div>
      <div class="uc-score-lbl">Failed</div>
    </div>`;

  const STATUS_ICON  = { pass: '✓', warning: '!', fail: '✗', error: '?' };
  const STATUS_LABEL = { pass: 'Pass', warning: 'Warning', fail: 'Fail', error: 'Error' };

  // Pretty-print tool IDs → readable labels
  const TOOL_LABELS = {
    // On-page
    canonical:'Canonical URL', title:'Title Tag', meta_description:'Meta Description',
    headings:'Headings (H1–H3)', image_alt:'Image Alt Text', word_count:'Word Count',
    readability:'Readability', schema:'Schema Markup', hreflang:'Hreflang Tags',
    ttfb:'TTFB (Response Time)', og_tags:'Open Graph / Twitter', meta_robots:'Meta Robots',
    favicon:'Favicon',
    // Crawlability
    robots:'robots.txt', http_status:'HTTP Status', redirect:'Redirects',
    broken_links:'Broken Links', internal_links:'Internal Links', sitemap:'Sitemap',
    // Site health
    ssl:'SSL / TLS', domain_age:'Domain Age', dns_health:'DNS Health',
    mixed_content:'Mixed Content', https_enforcement:'HTTPS Enforcement',
    security_headers:'Security Headers', spf:'SPF Record', dmarc:'DMARC Policy',
    mx_records:'MX Records',
    // Performance
    pagespeed_mobile:'PageSpeed Mobile', pagespeed_desktop:'PageSpeed Desktop',
    mobile:'Mobile vs Desktop', crawlability:'GSC Inspection',
    lcp:'LCP — Largest Contentful Paint', cls:'CLS — Cumulative Layout Shift',
    fcp:'FCP — First Contentful Paint', inp:'INP — Interaction to Next Paint',
    // Search Console
    clicks_impressions:'Clicks & Impressions', top_queries:'Top Queries',
    position_tracker:'Position Tracker', ctr_analyzer:'CTR Analyzer',
    coverage_errors:'Coverage Errors', sitemaps_status:'Sitemaps Status',
    manual_actions:'Manual Actions',
    // Authority
    backlinks:'Backlinks', domain_authority:'Domain Authority',
    page_authority:'Page Authority', referring_domains:'Referring Domains',
    domain_rank:'Domain Rank', broken_backlinks:'Broken Backlinks',
    nofollow_ratio:'Nofollow Ratio', spam_score:'Spam Score',
    // Rankings
    rank_tracker:'Keyword Rankings', serp_features:'SERP Features',
    competitor:'Competitor Comparison', rank_change:'Rank Change Tracker',
    traffic_share:'Traffic Share Estimate',
  };

  document.getElementById('uc-checks-list').innerHTML = (d.results || []).map(r => {
    const st    = r.status || 'error';
    const label = TOOL_LABELS[r.tool] || r.label || r.tool || '';
    const msg   = r.message || r.detail || '';
    return `
      <div class="uc-check-row">
        <div class="uc-check-icon ${st}" title="${STATUS_LABEL[st] || st}">${STATUS_ICON[st] || '?'}</div>
        <div class="uc-check-body">
          <div class="uc-check-title">${escTool(label)}</div>
          ${msg ? `<div class="uc-check-detail">${escTool(msg)}</div>` : ''}
        </div>
      </div>`;
  }).join('');

  document.getElementById('uc-results').style.display = '';
}

// ════════════════════════════════════════════════════════════════════════════
// GENERATORS — Phase B
// ════════════════════════════════════════════════════════════════════════════

function copyOutput(id) {
  const el = document.getElementById(id);
  if (!el || !el.value) { toast('Nothing to copy', 'warn'); return; }
  navigator.clipboard.writeText(el.value).then(() => toast('Copied to clipboard ✓', 'success'));
}

// ── Clear helpers ─────────────────────────────────────────────────────────────
function _hide(...ids){ ids.forEach(id=>{const el=document.getElementById(id);if(el)el.style.display='none';}); }
function _show(id){ const el=document.getElementById(id);if(el)el.style.display=''; }
function _hideAll(...ids){ _hide(...ids); }
function _showErr(id, msg){ const el=document.getElementById(id); if(el){el.textContent=msg||'Error';el.style.display='';} }
async function _api(path, body={}){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return r.json();
}
function _clearVal(...ids){ ids.forEach(id=>{const el=document.getElementById(id);if(el)el.value='';}); }

// Tools
function clearSerp(){
  _clearVal('serp-url');
  _hide('serp-result');
  const err=document.getElementById('serp-error'); if(err)err.style.display='none';
}
function clearRedirect(){
  _clearVal('redir-url');
  _hide('redir-result');
  const err=document.getElementById('redir-error'); if(err)err.style.display='none';
}
function clearHeaders(){
  _clearVal('hdrs-url');
  _hide('hdrs-result');
  const err=document.getElementById('hdrs-error'); if(err)err.style.display='none';
}
function clearKeywords(){
  _clearVal('kw-url','kw-keyword');
  _hide('kw-result');
  const err=document.getElementById('kw-error'); if(err)err.style.display='none';
}
function clearRatio(){
  _clearVal('ratio-url');
  _hide('ratio-result');
  const err=document.getElementById('ratio-error'); if(err)err.style.display='none';
}
function clearCompression(){
  _clearVal('comp-url');
  _hide('comp-result');
  const err=document.getElementById('comp-error'); if(err)err.style.display='none';
}

// ════════════════════════════════════════════════════════════════════════════
// SCHEMA VALIDATION (Stage 2-A)
// ════════════════════════════════════════════════════════════════════════════

async function runSchemaValidation() {
  const url = document.getElementById('schema-url').value.trim();
  if (!url) { toast('Enter a URL first', 'warn'); return; }
  document.getElementById('schema-result').style.display = 'none';
  document.getElementById('schema-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/schema_validate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url}),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Validation failed');
    renderSchemaValidation(d);
  } catch(e) {
    document.getElementById('schema-error').style.display = '';
    document.getElementById('schema-error').textContent = '✖ ' + e.message;
  }
}

function renderSchemaValidation(d) {
  // ── Summary bar ─────────────────────────────────────────────────────────
  const errCls  = d.summary.errors   > 0 ? 'color:#ef4444' : 'color:#10b981';
  const warnCls = d.summary.warnings > 0 ? 'color:#f59e0b' : 'color:#94a3b8';
  const typesHtml = d.types_found.length
    ? d.types_found.map(t => `<span style="background:#e0e7ff;color:#4338ca;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600">${escTool(t)}</span>`).join(' ')
    : '<span style="color:#94a3b8;font-size:13px">None found</span>';

  document.getElementById('schema-summary-card').innerHTML = `
    <div style="display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap">
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Blocks</div>
        <div style="font-size:28px;font-weight:700">${d.block_count}</div>
      </div>
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Errors</div>
        <div style="font-size:28px;font-weight:700;${errCls}">${d.summary.errors}</div>
      </div>
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Warnings</div>
        <div style="font-size:28px;font-weight:700;${warnCls}">${d.summary.warnings}</div>
      </div>
      <div style="flex:1;min-width:160px">
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Types found</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${typesHtml}</div>
      </div>
    </div>`;

  // ── Recommendations ──────────────────────────────────────────────────────
  const recsCard = document.getElementById('schema-recs-card');
  if (d.recommendations && d.recommendations.length) {
    document.getElementById('schema-recs').innerHTML = d.recommendations
      .map(t => `<span style="display:inline-block;margin:3px;background:#fef3c7;color:#92400e;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600">${escTool(t)}</span>`)
      .join('');
    recsCard.style.display = '';
  } else {
    recsCard.style.display = 'none';
  }

  // ── Per-block breakdown ──────────────────────────────────────────────────
  const blocksEl = document.getElementById('schema-blocks');
  if (!d.blocks || !d.blocks.length) {
    blocksEl.innerHTML = '<div class="empty" style="padding:24px">No JSON-LD blocks found on this page.</div>';
  } else {
    blocksEl.innerHTML = d.blocks.map((b, i) => {
      const blockErrors   = b.issues.filter(x => x.level === 'error').length;
      const blockWarnings = b.issues.filter(x => x.level === 'warning').length;
      const statusIcon    = !b.valid_json ? '✖' : blockErrors ? '✖' : blockWarnings ? '⚠' : '✓';
      const statusColor   = !b.valid_json ? '#ef4444' : blockErrors ? '#ef4444' : blockWarnings ? '#f59e0b' : '#10b981';
      const typeLabel     = b.types.length ? b.types.join(', ') : 'Unknown type';

      const issuesHtml = b.issues.length ? b.issues.map(iss => {
        const lvlColor = iss.level === 'error' ? '#ef4444' : iss.level === 'warning' ? '#f59e0b' : '#6366f1';
        const lvlIcon  = iss.level === 'error' ? '✖' : iss.level === 'warning' ? '⚠' : 'ℹ';
        return `<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid #f1f5f9">
          <span style="color:${lvlColor};font-weight:700;flex-shrink:0">${lvlIcon}</span>
          <div>
            <span style="font-size:11px;font-weight:600;color:${lvlColor};text-transform:uppercase">${iss.level}</span>
            <span style="font-size:11px;color:#64748b;margin-left:6px">${escTool(iss.path)}</span>
            <div style="font-size:13px;color:#1e293b;margin-top:2px">${escTool(iss.message)}</div>
          </div>
        </div>`;
      }).join('') : '<div style="color:#10b981;padding:8px 0;font-size:13px">✓ No issues found</div>';

      // Collapsible raw JSON
      const jsonId = `schema-json-${i}`;
      const rawJson = b.valid_json && b.parsed
        ? JSON.stringify(b.parsed, null, 2)
        : escTool(b.raw || '');

      return `<div class="card" style="margin-bottom:12px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
          <span style="font-size:20px;color:${statusColor};font-weight:700">${statusIcon}</span>
          <div>
            <div style="font-weight:700;font-size:15px">${escTool(typeLabel)}</div>
            <div style="font-size:12px;color:#94a3b8">Block ${i+1} · ${b.issues.length} issue${b.issues.length!==1?'s':''}</div>
          </div>
        </div>
        <div style="margin-bottom:14px">${issuesHtml}</div>
        <details>
          <summary style="font-size:12px;color:#6366f1;cursor:pointer;user-select:none">View raw JSON-LD</summary>
          <pre id="${jsonId}" style="margin-top:8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;font-size:11px;overflow-x:auto;white-space:pre-wrap;word-break:break-all">${b.valid_json && b.parsed ? escTool(JSON.stringify(b.parsed,null,2)) : escTool(b.raw||'')}</pre>
        </details>
      </div>`;
    }).join('');
  }

  document.getElementById('schema-result').style.display = '';
}

function clearSchemaValidation() {
  _clearVal('schema-url');
  document.getElementById('schema-result').style.display = 'none';
  document.getElementById('schema-error').style.display  = 'none';
}

// ════════════════════════════════════════════════════════════════════════════
// INDEXNOW SUBMISSION (Stage 2-B)
// ════════════════════════════════════════════════════════════════════════════

async function indexnowGenerateKey() {
  try {
    const r = await fetch('/api/tools/indexnow_generate_key', {method:'POST'});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Failed');
    document.getElementById('inow-key').value = d.key;
    const host = (document.getElementById('inow-host').value || '').trim() || 'yourdomain.com';
    const hint = document.getElementById('inow-key-hint');
    hint.style.display = '';
    hint.innerHTML = `
      <strong>Key generated:</strong> <code style="background:#e0f2fe;padding:1px 5px;border-radius:4px">${escTool(d.key)}</code><br>
      <strong>Next step:</strong> Create a text file at <code style="background:#e0f2fe;padding:1px 5px;border-radius:4px">https://${escTool(host)}/${escTool(d.key)}.txt</code>
      containing only the key string, then save this key in Settings.`;
    toast('Key generated — see setup instructions below', 'info');
  } catch(e) {
    toast('Key generation failed: ' + e.message, 'error');
  }
}

async function runIndexNow() {
  const key   = (document.getElementById('inow-key').value  || '').trim();
  const host  = (document.getElementById('inow-host').value || '').trim();
  const raw   = (document.getElementById('inow-urls').value || '').trim();
  if (!key)  { toast('Enter your IndexNow API key', 'warn'); return; }
  if (!host) { toast('Enter your hostname', 'warn'); return; }
  if (!raw)  { toast('Enter at least one URL', 'warn'); return; }

  const urls = raw.split(/[\n,]+/).map(u => u.trim()).filter(Boolean);

  document.getElementById('inow-result').style.display = 'none';
  document.getElementById('inow-error').style.display  = 'none';

  try {
    const r = await fetch('/api/tools/indexnow_submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({urls, key, host}),
    });
    const d = await r.json();

    const body = document.getElementById('inow-result-body');
    if (d.ok) {
      const submitted = d.submitted ?? 1;
      const skipped   = d.skipped   ? d.skipped.length : 0;
      body.innerHTML = `
        <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:14px">
          <div>
            <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Status</div>
            <div style="font-size:22px;font-weight:700;color:#10b981">✓ Accepted</div>
          </div>
          <div>
            <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Submitted</div>
            <div style="font-size:22px;font-weight:700">${submitted}</div>
          </div>
          ${skipped ? `<div>
            <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Skipped</div>
            <div style="font-size:22px;font-weight:700;color:#f59e0b">${skipped}</div>
          </div>` : ''}
        </div>
        ${skipped ? `<div style="font-size:12px;color:#ef4444;margin-top:8px">${d.skipped.map(s=>`<div>✖ ${escTool(s.url)} — ${escTool(s.reason)}</div>`).join('')}</div>` : ''}
        <div style="font-size:13px;color:#64748b;margin-top:8px">HTTP ${d.status} — URLs queued for crawling by Bing and IndexNow partners.</div>`;
    } else {
      body.innerHTML = `
        <div style="color:#ef4444;font-weight:700;margin-bottom:8px">✖ Submission failed</div>
        <div style="font-size:13px;color:#64748b">${escTool(d.error || 'Unknown error')}</div>
        ${d.skipped && d.skipped.length ? `<div style="margin-top:8px;font-size:12px;color:#f59e0b">${d.skipped.length} URL(s) skipped</div>` : ''}`;
    }
    document.getElementById('inow-result').style.display = '';
  } catch(e) {
    document.getElementById('inow-error').style.display = '';
    document.getElementById('inow-error').textContent = '✖ ' + e.message;
  }
}

function clearIndexNow() {
  document.getElementById('inow-urls').value = '';
  document.getElementById('inow-result').style.display = 'none';
  document.getElementById('inow-error').style.display  = 'none';
  document.getElementById('inow-key-hint').style.display = 'none';
}

// ════════════════════════════════════════════════════════════════════════════
// SITEMAP AUDIT (Stage 2-C)
// ════════════════════════════════════════════════════════════════════════════

async function runSitemapAudit() {
  const url = document.getElementById('smap-url').value.trim();
  if (!url) { toast('Enter a sitemap URL first', 'warn'); return; }
  document.getElementById('smap-result').style.display = 'none';
  document.getElementById('smap-error').style.display  = 'none';
  try {
    const r = await fetch('/api/tools/sitemap_audit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url}),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Audit failed');
    renderSitemapAudit(d);
  } catch(e) {
    document.getElementById('smap-error').style.display = '';
    document.getElementById('smap-error').textContent = '✖ ' + e.message;
  }
}

function renderSitemapAudit(d) {
  const s = d.summary;
  const scoreColor = d.score >= 80 ? '#10b981' : d.score >= 50 ? '#f59e0b' : '#ef4444';

  // ── Summary card ─────────────────────────────────────────────────────────
  document.getElementById('smap-summary').innerHTML = `
    <div style="display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap;margin-bottom:20px">
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Score</div>
        <div style="font-size:32px;font-weight:700;color:${scoreColor}">${d.score}</div>
      </div>
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Total URLs</div>
        <div style="font-size:32px;font-weight:700">${d.total_urls.toLocaleString()}</div>
      </div>
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">File Size</div>
        <div style="font-size:32px;font-weight:700">${d.size_mb} <span style="font-size:14px;font-weight:400">MB</span></div>
      </div>
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Errors</div>
        <div style="font-size:32px;font-weight:700;color:${s.errors>0?'#ef4444':'#10b981'}">${s.errors}</div>
      </div>
      <div>
        <div style="font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Warnings</div>
        <div style="font-size:32px;font-weight:700;color:${s.warnings>0?'#f59e0b':'#94a3b8'}">${s.warnings}</div>
      </div>
    </div>
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      ${_smapBadge('lastmod', s.has_lastmod)}
      ${_smapBadge('changefreq', s.has_changefreq)}
      ${_smapBadge('priority', s.has_priority)}
      ${s.http_in_https ? `<span style="background:#fef2f2;color:#dc2626;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:600">${s.http_in_https} HTTP-in-HTTPS</span>` : ''}
      ${s.duplicates ? `<span style="background:#fffbeb;color:#92400e;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:600">${s.duplicates} duplicate(s)</span>` : ''}
      ${s.non_indexable ? `<span style="background:#fff7ed;color:#c2410c;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:600">${s.non_indexable} non-indexable</span>` : ''}
    </div>`;

  // ── Issues list ───────────────────────────────────────────────────────────
  const issuesEl = document.getElementById('smap-issues');
  if (!d.issues || !d.issues.length) {
    issuesEl.innerHTML = '<div class="empty" style="padding:24px">✓ No issues found — sitemap looks healthy!</div>';
  } else {
    issuesEl.innerHTML = d.issues.map(iss => {
      const lvlColor = iss.level === 'error' ? '#ef4444' : iss.level === 'warning' ? '#f59e0b' : '#6366f1';
      const lvlIcon  = iss.level === 'error' ? '✖' : iss.level === 'warning' ? '⚠' : 'ℹ';
      const urlsHtml = iss.urls && iss.urls.length
        ? `<div style="margin-top:8px;max-height:120px;overflow-y:auto;background:#f8fafc;border-radius:6px;padding:8px;font-size:11px;font-family:monospace">${iss.urls.map(u=>`<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escTool(u)}</div>`).join('')}</div>`
        : '';
      return `<div class="card" style="margin-bottom:10px;display:flex;gap:12px;align-items:flex-start">
        <span style="font-size:20px;color:${lvlColor};margin-top:2px">${lvlIcon}</span>
        <div style="flex:1">
          <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:${lvlColor}">${iss.level}</span>
          <div style="font-size:14px;color:#1e293b;margin-top:4px">${escTool(iss.message)}</div>
          ${urlsHtml}
        </div>
      </div>`;
    }).join('');
  }

  document.getElementById('smap-result').style.display = '';
}

function _smapBadge(field, present) {
  const col = present ? '#10b981' : '#94a3b8';
  const bg  = present ? '#d1fae5' : '#f1f5f9';
  return `<span style="background:${bg};color:${col};padding:4px 10px;border-radius:12px;font-size:12px;font-weight:600">${present?'✓':'–'} &lt;${field}&gt;</span>`;
}

function clearSitemapAudit() {
  _clearVal('smap-url');
  document.getElementById('smap-result').style.display = 'none';
  document.getElementById('smap-error').style.display  = 'none';
}

// ═══════════════════════════════════════════════════════════════════════════
// Stage 3-A: Bing Visibility
// ═══════════════════════════════════════════════════════════════════════════
async function runBingOverview() {
  const site_url = (document.getElementById('bing-site-url').value || '').trim();
  const period   = parseInt(document.getElementById('bing-period').value) || 2;
  if (!site_url) { _showErr('bing-error','Site URL required'); return; }
  _hideAll('bing-error','bing-result'); _show('bing-spinner');
  try {
    const d = await _api('/api/tools/bing/overview', {site_url, period});
    _hide('bing-spinner');
    if (!d.ok) { _showErr('bing-error', d.error || 'Bing API error'); return; }
    _renderBingOverview(d);
    _show('bing-result');
  } catch(e) { _hide('bing-spinner'); _showErr('bing-error', e.message); }
}

function _renderBingOverview(d) {
  // Traffic stats
  const tr = d.traffic?.data || {};
  const row = document.getElementById('bing-traffic-row');
  row.innerHTML = [
    ['Clicks',       tr.clicks       ?? '—', 'c-green'],
    ['Impressions',  tr.impressions  ?? '—', 'c-blue'],
    ['Avg CTR',      tr.avg_ctr != null ? tr.avg_ctr + '%' : '—', 'c-purple'],
    ['Avg Position', tr.avg_position ?? '—', 'c-yellow'],
  ].map(([l,v,c]) =>
    `<div class="stat" style="min-width:120px"><div class="stat-n ${c}">${v}</div><div class="stat-l">${l}</div></div>`
  ).join('');

  // Crawl issues
  const ci = document.getElementById('bing-crawl-issues');
  const issues = d.crawl?.issues || [];
  ci.innerHTML = issues.length
    ? `<div class="issues-list">${issues.map(i=>`<div class="issue-item issue-warn">⚠ ${i}</div>`).join('')}</div>`
    : '<div class="tool-success-note">✓ No crawl issues detected</div>';

  // Sitemaps table
  const sm = d.sitemaps?.data || [];
  const smDiv = document.getElementById('bing-sitemaps');
  if (!sm.length) { smDiv.innerHTML='<div style="color:var(--c-muted);font-size:13px">No sitemaps submitted</div>'; return; }
  smDiv.innerHTML = `<div class="card-title" style="font-size:13px;margin-bottom:8px">Sitemaps</div>
    <div class="table-wrap"><table class="result-table">
    <thead><tr><th>Sitemap</th><th>URLs</th><th>Indexed</th><th>Rate</th><th>Errors</th></tr></thead>
    <tbody>${sm.map(s=>`<tr>
      <td style="font-size:11px;word-break:break-all">${s.url||'—'}</td>
      <td>${s.url_count??'—'}</td>
      <td>${s.indexed??'—'}</td>
      <td>${s.index_rate??'—'}%</td>
      <td class="${s.errors>0?'c-red':''}">${s.errors||0}</td>
    </tr>`).join('')}</tbody>
    </table></div>`;
}

async function runBingInspect() {
  const url      = (document.getElementById('bing-inspect-url').value || '').trim();
  const site_url = (document.getElementById('bing-site-url').value || '').trim();
  if (!url) { _showErr('bing-error','Page URL required'); return; }
  if (!site_url) { _showErr('bing-error','Enter Site URL in the Overview card first'); return; }
  const d = await _api('/api/tools/bing/inspect', {url, site_url});
  const el = document.getElementById('bing-inspect-result');
  if (!d.ok) { el.innerHTML=`<div class="error-box" style="display:block">${d.error}</div>`; _show('bing-inspect-result'); return; }
  const dd = d.data || {};
  const badge = dd.is_indexed ? '<span class="status-pass">Indexed</span>' : '<span class="status-warn">Not indexed</span>';
  el.innerHTML = `<div style="font-size:13px;line-height:1.8">
    <b>Status:</b> ${badge} &nbsp;
    <b>Crawl state:</b> ${dd.crawl_state||'—'} &nbsp;
    <b>Index state:</b> ${dd.index_state||'—'}<br>
    <b>Last crawled:</b> ${dd.last_crawled||'—'} &nbsp;
    <b>Canonical:</b> <span style="word-break:break-all">${dd.canonical||'—'}</span>
  </div>`;
  _show('bing-inspect-result');
}

async function runBingSubmit() {
  const url      = (document.getElementById('bing-inspect-url').value || '').trim();
  const site_url = (document.getElementById('bing-site-url').value || '').trim();
  if (!url || !site_url) { _showErr('bing-error','Enter URL and site URL first'); return; }
  const d = await _api('/api/tools/bing/submit', {url, site_url});
  const el = document.getElementById('bing-inspect-result');
  el.innerHTML = d.ok
    ? `<div class="tool-success-note">✓ ${d.message}</div>`
    : `<div class="error-box" style="display:block">${d.error}</div>`;
  _show('bing-inspect-result');
}

function clearBing() {
  _clearVal('bing-site-url','bing-inspect-url');
  _hideAll('bing-error','bing-result','bing-inspect-result');
}

// ═══════════════════════════════════════════════════════════════════════════
// Stage 3-B: GSC Opportunities
// ═══════════════════════════════════════════════════════════════════════════
async function runGscOpps() {
  const site_url = (document.getElementById('gsc-opps-site').value || '').trim();
  if (!site_url) { _showErr('gsc-opps-error','Site URL required'); return; }
  _hideAll('gsc-opps-error','gsc-opps-result'); _show('gsc-opps-spinner');
  try {
    const d = await _api('/api/tools/gsc_opportunities', {site_url});
    _hide('gsc-opps-spinner');
    if (!d.ok) { _showErr('gsc-opps-error', d.error || 'GSC error'); return; }
    _renderGscOpps(d);
    _show('gsc-opps-result');
  } catch(e) { _hide('gsc-opps-spinner'); _showErr('gsc-opps-error', e.message); }
}

function _renderGscOpps(d) {
  // Opportunity pages
  const opp = d.opportunity_pages || {};
  const oppRows = (opp.value || []);
  document.getElementById('gsc-opps-opp-summary').textContent =
    opp.message || `${oppRows.length} opportunity pages`;
  const oppTb = document.querySelector('#gsc-opps-opp-table tbody');
  oppTb.innerHTML = oppRows.slice(0,50).map(r => `<tr>
    <td style="font-size:11px;word-break:break-all">${r.url}</td>
    <td>${r.impressions.toLocaleString()}</td>
    <td>${r.ctr}%</td>
    <td>${r.position}</td>
    <td class="c-green"><b>+${r.est_extra_clicks.toLocaleString()}</b></td>
    <td style="font-size:11px">${r.action}</td>
  </tr>`).join('') || '<tr><td colspan="6" style="color:var(--c-muted)">No opportunities found</td></tr>';

  // Position decay
  const dec = d.position_decay || {};
  const decRows = (dec.value || []);
  document.getElementById('gsc-opps-decay-summary').textContent = dec.message || '';
  const decTb = document.querySelector('#gsc-opps-decay-table tbody');
  const sevClass = s => s==='high'?'c-red':s==='medium'?'c-yellow':'c-muted';
  decTb.innerHTML = decRows.slice(0,50).map(r => `<tr>
    <td style="font-size:11px;word-break:break-all">${r.url}</td>
    <td>${r.pos_start}</td>
    <td>${r.pos_end}</td>
    <td class="c-red"><b>▼${r.delta}</b></td>
    <td>${(r.total_clicks||0).toLocaleString()}</td>
    <td class="${sevClass(r.severity)}">${r.severity}</td>
  </tr>`).join('') || '<tr><td colspan="6" style="color:var(--c-muted)">No decay detected</td></tr>';

  // Cannibalization
  const can = d.keyword_cannibalization || {};
  const canRows = (can.value || []);
  document.getElementById('gsc-opps-cannibal-summary').textContent = can.message || '';
  const canTb = document.querySelector('#gsc-opps-cannibal-table tbody');
  canTb.innerHTML = canRows.slice(0,50).map(r => `<tr>
    <td><b>${r.query}</b></td>
    <td class="c-yellow">${r.competing_pages}</td>
    <td>${(r.total_impressions||0).toLocaleString()}</td>
    <td style="font-size:11px;word-break:break-all">${r.winner||'—'}</td>
    <td style="font-size:11px">${r.recommendation||''}</td>
  </tr>`).join('') || '<tr><td colspan="5" style="color:var(--c-muted)">No cannibalization detected</td></tr>';
}

function clearGscOpps() {
  _clearVal('gsc-opps-site');
  _hideAll('gsc-opps-error','gsc-opps-result');
}

// ═══════════════════════════════════════════════════════════════════════════
// GSC Position Tracker
// ═══════════════════════════════════════════════════════════════════════════
async function runGscPosition() {
  const url      = (document.getElementById('gsc-pos-url')?.value  || '').trim();
  const site_url = (document.getElementById('gsc-pos-site')?.value || '').trim();
  if (!url || !site_url) { _showErr('gsc-pos-error','Page URL and Site URL required'); return; }
  _hideAll('gsc-pos-error','gsc-pos-result'); _show('gsc-pos-spinner');
  try {
    const d = await _api('/api/tools/gsc_position_tracker', {url, site_url});
    _hide('gsc-pos-spinner');
    if (!d.ok && d.error) { _showErr('gsc-pos-error', d.error); return; }
    const trend = d.value || [];
    const sumEl = document.getElementById('gsc-pos-summary');
    if (sumEl) sumEl.textContent = d.message || '';
    const tb = document.querySelector('#gsc-pos-table tbody');
    const posClass = p => p <= 3 ? 'c-green' : p <= 10 ? 'c-yellow' : 'c-red';
    tb.innerHTML = trend.length
      ? trend.map(r => `<tr>
          <td>${r.date}</td>
          <td class="${posClass(r.position)}"><b>${r.position}</b></td>
          <td>${(r.clicks||0).toLocaleString()}</td>
        </tr>`).join('')
      : '<tr><td colspan="3" style="color:var(--c-muted)">No position data found</td></tr>';
    _show('gsc-pos-result');
  } catch(e) { _hide('gsc-pos-spinner'); _showErr('gsc-pos-error', e.message); }
}
function clearGscPosition() {
  _clearVal('gsc-pos-url','gsc-pos-site');
  _hideAll('gsc-pos-error','gsc-pos-result');
}

// ═══════════════════════════════════════════════════════════════════════════
// GSC CTR Analyzer
// ═══════════════════════════════════════════════════════════════════════════
async function runGscCtr() {
  const site_url       = (document.getElementById('gsc-ctr-site')?.value || '').trim();
  const min_impressions = parseInt(document.getElementById('gsc-ctr-min')?.value || '100') || 100;
  if (!site_url) { _showErr('gsc-ctr-error','Site URL required'); return; }
  _hideAll('gsc-ctr-error','gsc-ctr-result'); _show('gsc-ctr-spinner');
  try {
    const d = await _api('/api/tools/gsc_ctr_analyzer', {site_url, min_impressions});
    _hide('gsc-ctr-spinner');
    if (!d.ok && d.error) { _showErr('gsc-ctr-error', d.error); return; }
    const rows = d.value || [];
    document.getElementById('gsc-ctr-summary').textContent = d.message || `${rows.length} low-CTR pages found`;
    const tb = document.querySelector('#gsc-ctr-table tbody');
    tb.innerHTML = rows.length
      ? rows.map(r => `<tr>
          <td style="font-size:11px;word-break:break-all">${r.url}</td>
          <td>${(r.impressions||0).toLocaleString()}</td>
          <td>${(r.clicks||0).toLocaleString()}</td>
          <td class="c-yellow"><b>${r.ctr}%</b></td>
          <td>${r.position}</td>
          <td style="font-size:11px">${r.opportunity||''}</td>
        </tr>`).join('')
      : '<tr><td colspan="6" style="color:var(--c-muted)">No low-CTR pages found</td></tr>';
    _show('gsc-ctr-result');
  } catch(e) { _hide('gsc-ctr-spinner'); _showErr('gsc-ctr-error', e.message); }
}
function clearGscCtr() {
  _clearVal('gsc-ctr-site');
  _hideAll('gsc-ctr-error','gsc-ctr-result');
}

// ═══════════════════════════════════════════════════════════════════════════
// GSC Coverage Errors
// ═══════════════════════════════════════════════════════════════════════════
async function runGscCoverage() {
  const site_url = (document.getElementById('gsc-cov-site')?.value || '').trim();
  if (!site_url) { _showErr('gsc-cov-error','Site URL required'); return; }
  _hideAll('gsc-cov-error','gsc-cov-result'); _show('gsc-cov-spinner');
  try {
    const d = await _api('/api/tools/gsc_coverage_errors', {site_url});
    _hide('gsc-cov-spinner');
    if (!d.ok && d.error) { _showErr('gsc-cov-error', d.error); return; }
    const warnings = (d.value || {}).warnings || [];
    document.getElementById('gsc-cov-summary').textContent = d.message || '';
    const tb = document.querySelector('#gsc-cov-table tbody');
    const rateClass = r => r >= 90 ? 'c-green' : r >= 50 ? 'c-yellow' : 'c-red';
    tb.innerHTML = warnings.length
      ? warnings.map(w => {
          const rate = w.submitted ? Math.round((w.indexed / w.submitted) * 100) : 0;
          return `<tr>
            <td style="font-size:11px;word-break:break-all">${w.sitemap||'—'}</td>
            <td>${(w.submitted||0).toLocaleString()}</td>
            <td>${(w.indexed||0).toLocaleString()}</td>
            <td class="c-red"><b>${(w.not_indexed||0).toLocaleString()}</b></td>
            <td class="${rateClass(rate)}">${rate}%</td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="5" style="color:var(--c-muted)">No coverage gaps found</td></tr>';
    _show('gsc-cov-result');
  } catch(e) { _hide('gsc-cov-spinner'); _showErr('gsc-cov-error', e.message); }
}
function clearGscCoverage() {
  _clearVal('gsc-cov-site');
  _hideAll('gsc-cov-error','gsc-cov-result');
}

// ═══════════════════════════════════════════════════════════════════════════
// GSC Sitemaps Status
// ═══════════════════════════════════════════════════════════════════════════
async function runGscSitemaps() {
  const site_url = (document.getElementById('gsc-sm-site')?.value || '').trim();
  if (!site_url) { _showErr('gsc-sm-error','Site URL required'); return; }
  _hideAll('gsc-sm-error','gsc-sm-result'); _show('gsc-sm-spinner');
  try {
    const d = await _api('/api/tools/gsc_sitemaps_status', {site_url});
    _hide('gsc-sm-spinner');
    if (!d.ok && d.error) { _showErr('gsc-sm-error', d.error); return; }
    const sitemaps = d.value || [];
    document.getElementById('gsc-sm-summary').textContent = d.message || `${sitemaps.length} sitemaps found`;
    const tb = document.querySelector('#gsc-sm-table tbody');
    const rateClass = r => r >= 90 ? 'c-green' : r >= 50 ? 'c-yellow' : 'c-red';
    tb.innerHTML = sitemaps.length
      ? sitemaps.map(s => {
          const rate = s.submitted ? Math.round((s.indexed / s.submitted) * 100) : 0;
          const errBadge = s.errors ? `<span style="color:var(--c-red)">${s.errors} err</span>` : '—';
          return `<tr>
            <td style="font-size:11px;word-break:break-all">${s.path||s.sitemap||'—'}</td>
            <td>${(s.submitted||0).toLocaleString()}</td>
            <td>${(s.indexed||0).toLocaleString()}</td>
            <td class="${rateClass(rate)}">${rate}%</td>
            <td>${errBadge}</td>
            <td style="font-size:11px">${s.last_submitted||'—'}</td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="6" style="color:var(--c-muted)">No sitemaps found in GSC</td></tr>';
    _show('gsc-sm-result');
  } catch(e) { _hide('gsc-sm-spinner'); _showErr('gsc-sm-error', e.message); }
}
function clearGscSitemaps() {
  _clearVal('gsc-sm-site');
  _hideAll('gsc-sm-error','gsc-sm-result');
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase Runner
// ═══════════════════════════════════════════════════════════════════════════
async function runPhaseRunner() {
  const url   = (document.getElementById('phase-run-url')?.value || '').trim();
  const phase = parseInt(document.getElementById('phase-run-num')?.value || '1');
  if (!url) { _showErr('phase-run-error','URL required'); return; }
  _hideAll('phase-run-error','phase-run-result'); _show('phase-run-spinner');
  try {
    const d = await _api(`/api/audit/phase/${phase}`, {url});
    _hide('phase-run-spinner');
    if (!d.ok) { _showErr('phase-run-error', d.error || 'Phase run failed'); return; }
    const sumEl = document.getElementById('phase-run-summary');
    if (sumEl) {
      const sc = d.score || 0;
      const scCol = sc >= 80 ? 'c-green' : sc >= 50 ? 'c-yellow' : 'c-red';
      const {pass=0, warning=0, fail=0} = d.counts || {};
      sumEl.innerHTML = `
        <span class="${scCol}" style="font-size:22px;font-weight:700">${sc}</span>
        <span style="font-size:12px;color:var(--c-muted)">score</span>
        <span style="margin-left:12px;font-size:12px"><span style="color:var(--c-green)">✓ ${pass}</span> &nbsp;
        <span style="color:var(--c-yellow)">⚠ ${warning}</span> &nbsp;
        <span style="color:var(--c-red)">✗ ${fail}</span></span>`;
    }
    const tb = document.querySelector('#phase-run-table tbody');
    const statusIcon = s => s==='pass'?'<span class="c-green">✓</span>':s==='warning'?'<span class="c-yellow">⚠</span>':s==='error'?'<span class="c-muted">—</span>':'<span class="c-red">✗</span>';
    tb.innerHTML = (d.results || []).map(r => `<tr>
      <td style="font-size:12px">${(r.tool||'').replace(/_/g,' ')}</td>
      <td>${statusIcon(r.status)}</td>
      <td style="font-size:12px">${r.message||''}</td>
      <td style="font-size:11px;color:var(--c-muted)">${r.details ? JSON.stringify(r.details).slice(0,80) : ''}</td>
    </tr>`).join('') || '<tr><td colspan="4" style="color:var(--c-muted)">No results</td></tr>';
    _show('phase-run-result');
  } catch(e) { _hide('phase-run-spinner'); _showErr('phase-run-error', e.message); }
}
function clearPhaseRunner() {
  _clearVal('phase-run-url');
  _hideAll('phase-run-error','phase-run-result');
}

// ═══════════════════════════════════════════════════════════════════════════
// Notification test
// ═══════════════════════════════════════════════════════════════════════════
async function testNotify(channel) {
  const msgEl = document.getElementById('notif-test-msg');
  if (msgEl) { msgEl.textContent = `Sending ${channel} test…`; msgEl.style.color = 'var(--c-muted)'; }
  try {
    const d = await _api('/api/tools/notify_test', {channel});
    if (msgEl) {
      msgEl.textContent = d.ok ? `✓ ${d.message}` : `✗ ${d.error}`;
      msgEl.style.color = d.ok ? 'var(--c-green)' : 'var(--c-red)';
    }
  } catch(e) {
    if (msgEl) { msgEl.textContent = `✗ ${e.message}`; msgEl.style.color = 'var(--c-red)'; }
  }
}

function toggleScheduleExpand(show) {
  const el = document.getElementById('notif-expand-schedule');
  if (el) el.style.display = show ? '' : 'none';
}

// ═══════════════════════════════════════════════════════════════════════════
// Stage 3-C: Performance Opportunities
// ═══════════════════════════════════════════════════════════════════════════
async function runPerfOpps() {
  const url = (document.getElementById('perf-opps-url').value || '').trim();
  if (!url) { _showErr('perf-opps-error','URL required'); return; }
  _hideAll('perf-opps-error','perf-opps-result'); _show('perf-opps-spinner');
  try {
    const d = await _api('/api/tools/perf_opportunities', {url});
    _hide('perf-opps-spinner');
    if (!d.ok) { _showErr('perf-opps-error', d.error || 'Error'); return; }
    _renderPerfOpps(d);
    _show('perf-opps-result');
  } catch(e) { _hide('perf-opps-spinner'); _showErr('perf-opps-error', e.message); }
}

function _perfGradeClass(g) {
  return g==='good'?'c-green':g==='needs_improvement'?'c-yellow':'c-red';
}

function _renderPerfOpps(d) {
  // Score cards
  const sc = d.scores || {};
  const row = document.getElementById('perf-opps-scores');
  row.innerHTML = [
    ['Mobile',  sc.mobile  ?? '—', 'c-purple'],
    ['Desktop', sc.desktop ?? '—', 'c-blue'],
    ['Gap',     sc.gap     != null ? (sc.gap > 0 ? `Desktop +${sc.gap}` : sc.gap) : '—', sc.gap > 20 ? 'c-red' : 'c-muted'],
  ].map(([l,v,c]) =>
    `<div class="stat" style="min-width:120px"><div class="stat-n ${c}">${v}</div><div class="stat-l">${l}</div></div>`
  ).join('');

  function _fillBucket(bucketId, tableId, rows) {
    const el = document.getElementById(bucketId);
    const tb = document.querySelector(`#${tableId} tbody`);
    if (!rows || !rows.length) { el.style.display='none'; return; }
    el.style.display='';
    tb.innerHTML = rows.map(m => `<tr>
      <td><b>${m.label}</b></td>
      <td class="${_perfGradeClass(m.mobile?.grade)}">${m.mobile?.value||'—'}</td>
      <td class="${_perfGradeClass(m.desktop?.grade)}">${m.desktop?.value||'—'}</td>
      <td style="font-size:11px">${m.fix||''}</td>
    </tr>`).join('');
  }

  const b = d.buckets || {};
  _fillBucket('perf-opps-critical', 'perf-critical-table', b.critical);
  _fillBucket('perf-opps-quick',    'perf-quick-table',    b.quick_wins);
  _fillBucket('perf-opps-nice',     'perf-nice-table',     b.nice_to_have);
}

function clearPerfOpps() {
  _clearVal('perf-opps-url');
  _hideAll('perf-opps-error','perf-opps-result');
  ['perf-opps-critical','perf-opps-quick','perf-opps-nice'].forEach(id=>{
    const el=document.getElementById(id); if(el) el.style.display='none';
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// Stage 3-D: AI Assistant
// ═══════════════════════════════════════════════════════════════════════════
async function runAiExplain() {
  const raw = (document.getElementById('ai-audit-json').value || '').trim();
  const url = (document.getElementById('ai-audit-url').value || '').trim();
  if (!raw) { _showErr('ai-explain-error','Paste audit results JSON first'); return; }
  let results;
  try { results = JSON.parse(raw); }
  catch { _showErr('ai-explain-error','Invalid JSON — paste the raw audit results array'); return; }
  _hideAll('ai-explain-error','ai-explain-result'); _show('ai-explain-spinner');
  try {
    const d = await _api('/api/tools/ai_explain', {results, url});
    _hide('ai-explain-spinner');
    if (!d.ok) { _showErr('ai-explain-error', d.error || 'AI error'); return; }
    document.getElementById('ai-explain-summary').textContent = d.explanation || '—';
    const ol = document.getElementById('ai-explain-actions');
    ol.innerHTML = (d.top_actions||[]).map(a=>`<li>${a}</li>`).join('');
    const model = document.getElementById('ai-explain-model');
    model.textContent = `Model: ${d.model||'—'} · Fails: ${d.stats?.fails||0} · Warnings: ${d.stats?.warnings||0}`;
    _show('ai-explain-result');
  } catch(e) { _hide('ai-explain-spinner'); _showErr('ai-explain-error', e.message); }
}

function clearAiExplain() {
  _clearVal('ai-audit-json','ai-audit-url');
  _hideAll('ai-explain-error','ai-explain-result');
}

async function runAiDraftMeta() {
  const url   = (document.getElementById('ai-meta-url').value   || '').trim();
  const title = (document.getElementById('ai-meta-title').value || '').trim();
  const desc  = (document.getElementById('ai-meta-desc').value  || '').trim();
  const qraw  = (document.getElementById('ai-meta-queries').value || '');
  const top_queries = qraw.split(',').map(s=>s.trim()).filter(Boolean);
  if (!url) { _showErr('ai-meta-error','URL required'); return; }
  _hideAll('ai-meta-error','ai-meta-result'); _show('ai-meta-spinner');
  try {
    const d = await _api('/api/tools/ai_draft_meta', {url, title, description: desc, top_queries});
    _hide('ai-meta-spinner');
    if (!d.ok) { _showErr('ai-meta-error', d.error || 'AI error'); return; }
    const variants = d.variants || [];
    document.getElementById('ai-meta-result').innerHTML = variants.map((v,i) => `
      <div class="card" style="margin-bottom:12px;background:var(--c-surface2);border:1px solid var(--c-border2)">
        <div class="card-title" style="font-size:12px;color:var(--c-muted)">Variant ${i+1}</div>
        <div style="font-size:14px;font-weight:600;color:var(--c-text);margin:4px 0">
          ${v.title}
          <span style="font-size:11px;color:${v.title.length>60?'var(--c-red)':'var(--c-muted)'};margin-left:8px">${v.title.length} chars</span>
        </div>
        <div style="font-size:13px;color:var(--c-muted2);margin:4px 0">
          ${v.description}
          <span style="font-size:11px;color:${v.description.length>155?'var(--c-red)':v.description.length<140?'var(--c-yellow)':'var(--c-green)'};margin-left:8px">${v.description.length} chars</span>
        </div>
        ${v.rationale ? `<div style="font-size:11px;color:var(--c-muted);margin-top:6px;font-style:italic">💡 ${v.rationale}</div>` : ''}
        <button class="btn btn-ghost btn-sm" style="margin-top:8px"
          onclick="navigator.clipboard.writeText(${JSON.stringify(v.title)});showToast('Title copied')">Copy title</button>
        <button class="btn btn-ghost btn-sm" style="margin-top:8px;margin-left:6px"
          onclick="navigator.clipboard.writeText(${JSON.stringify(v.description)});showToast('Description copied')">Copy desc</button>
      </div>`).join('') || '<div style="color:var(--c-muted)">No variants returned</div>';
    _show('ai-meta-result');
  } catch(e) { _hide('ai-meta-spinner'); _showErr('ai-meta-error', e.message); }
}

function clearAiDraftMeta() {
  _clearVal('ai-meta-url','ai-meta-title','ai-meta-desc','ai-meta-queries');
  _hideAll('ai-meta-error','ai-meta-result');
}

// ── Keyword Research ─────────────────────────────────────────────────────────
async function runKwResearch() {
  const seeds = document.getElementById('kw-seed')?.value.trim();
  if(!seeds){ _showErr('kw-error','Enter at least one seed keyword'); return; }
  const mode     = document.getElementById('kw-mode')?.value || 'auto';
  const location = parseInt(document.getElementById('kw-location')?.value || '2840');
  _hideAll('kw-error','kw-result');
  _show('kw-spinner');
  try {
    const r = await fetch('/api/tools/keyword_research', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ keywords: seeds, mode, location_code: location, limit: 50 }),
    });
    const d = await r.json();
    _hide('kw-spinner');
    if(!d.ok){ _showErr('kw-error', d.error||'Keyword research failed'); return; }

    const rows = d.rows || [];
    const tb = document.querySelector('#kw-table tbody');
    if(tb) tb.innerHTML = rows.map(row => {
      const vol  = row.searchVolume != null ? row.searchVolume.toLocaleString() : '—';
      const kd   = row.keywordDifficulty != null ? row.keywordDifficulty : '—';
      const cpc  = row.cpc != null ? '$'+row.cpc.toFixed(2) : '—';
      const comp = row.competition != null ? (row.competition*100).toFixed(0)+'%' : '—';
      const intent = row.intent || '—';
      const kdColor = kd==='—'?'':(kd>=70?'color:var(--c-red)':kd>=40?'color:var(--c-yellow)':'color:var(--c-green)');
      return `<tr>
        <td style="font-weight:500">${row.keyword||''}</td>
        <td>${vol}</td>
        <td style="${kdColor};font-weight:600">${kd}</td>
        <td>${cpc}</td>
        <td>${comp}</td>
        <td><span class="uc-req" style="font-size:10px;padding:1px 6px">${intent}</span></td>
      </tr>`;
    }).join('') || '<tr><td colspan="6" style="color:var(--c-muted);text-align:center">No keywords found</td></tr>';

    const summary = document.getElementById('kw-summary');
    if(summary) summary.textContent = `${rows.length} keywords for "${d.seedKeyword||seeds}" · source: ${d.source||'—'}${d.usedFallback?' (fallback used)':''}`;

    _show('kw-result');
  } catch(e) { _hide('kw-spinner'); _showErr('kw-error', e.message); }
}

function clearKwResearch() {
  _clearVal('kw-seed');
  _hideAll('kw-error','kw-result');
}

// Indexing run form
function clearIdxForm(){
  _clearVal('idx-src','idx-pattern');
  const lim=document.getElementById('idx-limit'); if(lim) lim.value=50;
  // reset to first radio (sitemap)
  const radio=document.querySelector('input[name="idx-type"][value="sitemap"]');
  if(radio){radio.checked=true; idxToggle();}
  const fileRow=document.getElementById('idx-file-row'); if(fileRow) fileRow.style.display='none';
}

// Compare
function clearCompare(){
  const a=document.getElementById('cmp-a'); if(a) a.selectedIndex=0;
  const b=document.getElementById('cmp-b'); if(b) b.selectedIndex=0;
  const res=document.getElementById('cmp-result'); if(res) res.innerHTML='';
}

// UC runner
function clearUcRunner(){
  _clearVal('uc-url','uc-keywords');
  _hide('uc-results','uc-error','uc-spinner');
  // re-show info panel for the current use case
  if(typeof _activeUseCase !== 'undefined' && _activeUseCase){
    _renderUcInfoPanel(_activeUseCase);
  }
}

// Reports search
function clearRepSearch(){
  const s=document.getElementById('rep-search'); if(s) s.value='';
  renderReports();
}

// Generators
function clearSchemaForm(){
  document.querySelectorAll('#schema-form-fields input,#schema-form-fields textarea,#schema-form-fields select').forEach(el=>el.value='');
  document.querySelectorAll('#sf-faq-items .gen-repeater,#sf-bc-items .gen-repeater').forEach(el=>el.remove());
  _clearVal('schema-output');
  _hide('schema-error','schema-test-link');
  const card=document.getElementById('schema-output-card'); if(card) card.style.display='none';
  // re-init the current type's default items
  if(typeof _schemaCurrentType!=='undefined'){
    if(_schemaCurrentType==='faq'){_faqCount=0; addFaqItem(); addFaqItem();}
    else if(_schemaCurrentType==='breadcrumb'){_bcCount=0; addBcItem(); addBcItem(); addBcItem();}
  }
}
function clearRobotsForm(){
  document.getElementById('robots-rules').innerHTML='';
  _clearVal('robots-sitemap','robots-output');
  _hide('robots-disallow-warn');
  _robotsRuleCount=0;
  addRobotsRule();
}
function clearSitemapForm(){
  _clearVal('sitemap-urls','sitemap-output');
  const cnt=document.getElementById('sitemap-url-count'); if(cnt) cnt.textContent='';
}
function clearHreflangForm(){
  document.getElementById('hreflang-rows').innerHTML='';
  _clearVal('hreflang-xdefault-url','hreflang-output','hreflang-http-output');
  const cb=document.getElementById('hreflang-xdefault'); if(cb){cb.checked=false; toggleXDefault(false);}
  _hreflangCount=0;
  addHreflangRow(); addHreflangRow();
}
function clearMetaTagsForm(){
  const fields=['meta-title','meta-desc','meta-keywords','meta-canonical','meta-og-image','meta-og-sitename','meta-tw-site'];
  _clearVal(...fields,'metatags-output');
  document.getElementById('meta-robots').selectedIndex=0;
  document.getElementById('meta-og-type').selectedIndex=0;
  _hide('metatags-serp-preview');
  const warn=document.getElementById('metatags-warnings'); if(warn) warn.innerHTML='';
  const tl=document.getElementById('meta-title-len'); if(tl) tl.textContent='';
  const dl=document.getElementById('meta-desc-len'); if(dl) dl.textContent='';
}

function downloadOutput(id, basename, ext) {
  const el = document.getElementById(id);
  if (!el || !el.value) { toast('Nothing to download', 'warn'); return; }
  const mimeMap = { json:'application/json', xml:'application/xml', txt:'text/plain', html:'text/html' };
  const blob = new Blob([el.value], { type: mimeMap[ext]||'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${basename}.${ext}`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast(`Downloaded ${basename}.${ext} ✓`, 'success');
}

// ── Tool 7: Schema Markup Generator ──────────────────────────────────────────
const SCHEMA_LOCALE_LABELS = {
  article: 'Article', faq: 'FAQ Page', product: 'Product',
  breadcrumb: 'Breadcrumb', localbusiness: 'Local Business',
  video: 'Video Object', event: 'Event', howto: 'HowTo',
  person: 'Person', organization: 'Organization',
};

// Client-side field definitions for new schema types
const SCHEMA_CLIENT_FIELDS = {
  video: [
    {id:'name',label:'Video Name',type:'text',required:true},
    {id:'description',label:'Description',type:'textarea',required:true},
    {id:'thumbnailUrl',label:'Thumbnail URL',type:'text'},
    {id:'uploadDate',label:'Upload Date',type:'date',required:true},
    {id:'contentUrl',label:'Content URL (direct video link)',type:'text'},
    {id:'embedUrl',label:'Embed URL (iframe src)',type:'text'},
    {id:'duration',label:'Duration (ISO 8601, e.g. PT5M30S)',type:'text'},
  ],
  event: [
    {id:'name',label:'Event Name',type:'text',required:true},
    {id:'startDate',label:'Start Date & Time',type:'text',required:true},
    {id:'endDate',label:'End Date & Time',type:'text'},
    {id:'description',label:'Description',type:'textarea'},
    {id:'location',label:'Location Name',type:'text',required:true},
    {id:'locationAddress',label:'Location Address',type:'text'},
    {id:'url',label:'Event URL',type:'text'},
    {id:'image',label:'Event Image URL',type:'text'},
    {id:'eventStatus',label:'Status',type:'select',options:['EventScheduled','EventCancelled','EventPostponed','EventRescheduled']},
    {id:'eventAttendanceMode',label:'Attendance Mode',type:'select',options:['OfflineEventAttendanceMode','OnlineEventAttendanceMode','MixedEventAttendanceMode']},
  ],
  howto: [
    {id:'name',label:'Title (HowTo name)',type:'text',required:true},
    {id:'description',label:'Description',type:'textarea',required:true},
    {id:'totalTime',label:'Total Time (ISO 8601, e.g. PT30M)',type:'text'},
    {id:'estimatedCost',label:'Estimated Cost (e.g. $10)',type:'text'},
    {id:'tool',label:'Tools Needed (comma-separated)',type:'text'},
    {id:'supply',label:'Supplies Needed (comma-separated)',type:'text'},
    {id:'steps',label:'Steps (one per line)',type:'textarea',required:true},
  ],
  person: [
    {id:'name',label:'Full Name',type:'text',required:true},
    {id:'jobTitle',label:'Job Title',type:'text'},
    {id:'url',label:'Profile URL',type:'text'},
    {id:'email',label:'Email',type:'text'},
    {id:'telephone',label:'Telephone',type:'text'},
    {id:'image',label:'Profile Image URL',type:'text'},
    {id:'sameAs',label:'Social Profiles (comma-separated URLs)',type:'text'},
    {id:'description',label:'Bio / Description',type:'textarea'},
  ],
  organization: [
    {id:'name',label:'Organization Name',type:'text',required:true},
    {id:'url',label:'Website URL',type:'text',required:true},
    {id:'logo',label:'Logo URL',type:'text'},
    {id:'description',label:'Description',type:'textarea'},
    {id:'telephone',label:'Telephone',type:'text'},
    {id:'email',label:'Email',type:'text'},
    {id:'streetAddress',label:'Street Address',type:'text'},
    {id:'addressLocality',label:'City',type:'text'},
    {id:'addressCountry',label:'Country (2-letter code)',type:'text'},
    {id:'sameAs',label:'Social / Wiki URLs (comma-separated)',type:'text'},
  ],
};

let _schemaCurrentType = 'article';

async function loadSchemaForm(type) {
  _schemaCurrentType = type;
  // New types handled client-side
  if (SCHEMA_CLIENT_FIELDS[type]) {
    renderSchemaForm(SCHEMA_CLIENT_FIELDS[type]);
    return;
  }
  try {
    const r = await fetch(`/api/tools/schema_fields/${type}`);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    renderSchemaForm(d.fields);
  } catch(e) {
    document.getElementById('schema-form-fields').innerHTML = `<div class="empty">${e.message}</div>`;
  }
}

function renderSchemaForm(fields) {
  const container = document.getElementById('schema-form-fields');
  container.innerHTML = '';

  fields.forEach(f => {
    const div = document.createElement('div');
    div.className = 'gen-field';
    div.innerHTML = `<div class="gen-field-label">${f.label}${f.required ? ' <span style="color:var(--danger)">*</span>' : ''}</div>`;

    if (f.type === 'text') {
      div.innerHTML += `<input class="input" id="sf-${f.id}" placeholder="${f.label}">`;
    } else if (f.type === 'date') {
      div.innerHTML += `<input class="input" type="date" id="sf-${f.id}">`;
    } else if (f.type === 'textarea') {
      div.innerHTML += `<textarea class="input" id="sf-${f.id}" rows="3" placeholder="${f.label}"></textarea>`;
    } else if (f.type === 'select') {
      const opts = (f.options || []).map(o => `<option value="${o}">${o}</option>`).join('');
      div.innerHTML += `<select class="input" id="sf-${f.id}">${opts}</select>`;
    } else if (f.type === 'faq_repeater') {
      div.innerHTML += `
        <div id="sf-faq-items"></div>
        <button class="btn btn-ghost btn-sm" style="margin-top:8px" onclick="addFaqItem()">+ Add Question</button>`;
      container.appendChild(div);
      addFaqItem(); addFaqItem();
      return;
    } else if (f.type === 'breadcrumb_repeater') {
      div.innerHTML += `
        <div id="sf-bc-items"></div>
        <button class="btn btn-ghost btn-sm" style="margin-top:8px" onclick="addBcItem()">+ Add Item</button>`;
      container.appendChild(div);
      addBcItem(); addBcItem(); addBcItem();
      return;
    }
    container.appendChild(div);
  });
}

let _faqCount = 0;
function addFaqItem() {
  _faqCount++;
  const div = document.createElement('div');
  div.className = 'gen-repeater';
  div.id = `faq-item-${_faqCount}`;
  div.innerHTML = `
    <div class="gen-repeater-head">Q${_faqCount} <button class="btn btn-ghost btn-sm" onclick="this.closest('.gen-repeater').remove()">✕</button></div>
    <div class="gen-field"><div class="gen-field-label">Question</div><input class="input faq-q" placeholder="Question text"></div>
    <div class="gen-field"><div class="gen-field-label">Answer</div><textarea class="input faq-a" rows="2" placeholder="Answer text"></textarea></div>`;
  document.getElementById('sf-faq-items').appendChild(div);
}

let _bcCount = 0;
function addBcItem() {
  _bcCount++;
  const div = document.createElement('div');
  div.className = 'gen-repeater';
  div.id = `bc-item-${_bcCount}`;
  div.innerHTML = `
    <div class="gen-repeater-head">Item ${_bcCount} <button class="btn btn-ghost btn-sm" onclick="this.closest('.gen-repeater').remove()">✕</button></div>
    <div style="display:grid;grid-template-columns:1fr 2fr;gap:8px">
      <div><div class="gen-field-label">Name</div><input class="input bc-name" placeholder="Home"></div>
      <div><div class="gen-field-label">URL</div><input class="input bc-url" placeholder="https://example.com"></div>
    </div>`;
  document.getElementById('sf-bc-items').appendChild(div);
}

async function generateSchema() {
  const type = _schemaCurrentType;
  let formData = {};

  // Client-side generation for new schema types
  if (SCHEMA_CLIENT_FIELDS[type]) {
    document.querySelectorAll('#schema-form-fields [id^="sf-"]').forEach(el => {
      formData[el.id.replace('sf-', '')] = el.value;
    });
    const schema = _buildClientSchema(type, formData);
    const markup = `<script type="application/ld+json">\n${JSON.stringify(schema, null, 2)}\n<\/script>`;
    document.getElementById('schema-output').value = markup;
    document.getElementById('schema-error').style.display = 'none';
    document.getElementById('schema-output-card').style.display = '';
    document.getElementById('schema-test-link').style.display = '';
    return;
  }

  if (type === 'faq') {
    const items = [];
    document.querySelectorAll('#sf-faq-items .gen-repeater').forEach(el => {
      items.push({ question: el.querySelector('.faq-q').value, answer: el.querySelector('.faq-a').value });
    });
    formData.faq_items = items;
  } else if (type === 'breadcrumb') {
    const items = [];
    document.querySelectorAll('#sf-bc-items .gen-repeater').forEach(el => {
      items.push({ name: el.querySelector('.bc-name').value, url: el.querySelector('.bc-url').value });
    });
    formData.items = items;
  } else {
    document.querySelectorAll('#schema-form-fields [id^="sf-"]').forEach(el => {
      formData[el.id.replace('sf-', '')] = el.value;
    });
  }

  try {
    const r = await fetch('/api/tools/schema_generate', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ schema_type: type, data: formData })
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    document.getElementById('schema-output').value = d.markup;
    document.getElementById('schema-error').style.display = 'none';
    document.getElementById('schema-output-card').style.display = '';
    document.getElementById('schema-test-link').style.display = '';
  } catch(e) {
    document.getElementById('schema-error').textContent = '✖ ' + e.message;
    document.getElementById('schema-error').style.display = '';
  }
}

function _buildClientSchema(type, d) {
  const ctx = 'https://schema.org';
  const split = s => s ? s.split(',').map(x=>x.trim()).filter(Boolean) : undefined;
  if (type === 'video') return {'@context':ctx,'@type':'VideoObject',name:d.name,description:d.description,thumbnailUrl:d.thumbnailUrl||undefined,uploadDate:d.uploadDate||undefined,contentUrl:d.contentUrl||undefined,embedUrl:d.embedUrl||undefined,duration:d.duration||undefined};
  if (type === 'event') return {'@context':ctx,'@type':'Event',name:d.name,startDate:d.startDate,endDate:d.endDate||undefined,description:d.description||undefined,eventStatus:`https://schema.org/${d.eventStatus||'EventScheduled'}`,eventAttendanceMode:`https://schema.org/${d.eventAttendanceMode||'OfflineEventAttendanceMode'}`,location:{...( d.locationAddress?{address:d.locationAddress}:{}), '@type':'Place',name:d.location},url:d.url||undefined,image:d.image||undefined};
  if (type === 'howto') {
    const steps = (d.steps||'').split('\n').filter(Boolean).map((s,i)=>({'@type':'HowToStep',name:`Step ${i+1}`,text:s.trim()}));
    return {'@context':ctx,'@type':'HowTo',name:d.name,description:d.description,totalTime:d.totalTime||undefined,estimatedCost:d.estimatedCost?{'@type':'MonetaryAmount',value:d.estimatedCost}:undefined,tool:split(d.tool),supply:split(d.supply),step:steps};
  }
  if (type === 'person') return {'@context':ctx,'@type':'Person',name:d.name,jobTitle:d.jobTitle||undefined,url:d.url||undefined,email:d.email||undefined,telephone:d.telephone||undefined,image:d.image||undefined,description:d.description||undefined,sameAs:split(d.sameAs)};
  if (type === 'organization') return {'@context':ctx,'@type':'Organization',name:d.name,url:d.url,logo:d.logo?{'@type':'ImageObject',url:d.logo}:undefined,description:d.description||undefined,telephone:d.telephone||undefined,email:d.email||undefined,address:d.streetAddress?{'@type':'PostalAddress',streetAddress:d.streetAddress,addressLocality:d.addressLocality||undefined,addressCountry:d.addressCountry||undefined}:undefined,sameAs:split(d.sameAs)};
  return {'@context':ctx,'@type':'Thing',...d};
}

// Initialise with Article form on load
document.addEventListener('DOMContentLoaded', () => loadSchemaForm('article'));


// ── Tool 8: robots.txt Generator ──────────────────────────────────────────────
let _robotsRuleCount = 0;

function addRobotsRule() {
  _robotsRuleCount++;
  const div = document.createElement('div');
  div.className = 'robots-rule';
  div.id = `robots-rule-${_robotsRuleCount}`;
  div.innerHTML = `
    <div class="robots-rule-head">
      Rule ${_robotsRuleCount}
      <button class="btn btn-ghost btn-sm" onclick="this.closest('.robots-rule').remove()">✕ Remove</button>
    </div>
    <div class="form-grid">
      <div class="fg-full"><span class="label">User-agent</span>
        <input class="input rr-ua" value="*" placeholder="* or Googlebot">
      </div>
      <div class="fg-full"><span class="label">Disallow paths <span style="font-weight:400;color:var(--text3)">(one per line)</span></span>
        <textarea class="input rr-disallow" rows="3" placeholder="/admin/&#10;/private/"></textarea>
      </div>
      <div class="fg-full"><span class="label">Allow paths <span style="font-weight:400;color:var(--text3)">(optional)</span></span>
        <textarea class="input rr-allow" rows="2" placeholder="/public/"></textarea>
      </div>
      <div><span class="label">Crawl-delay <span style="font-weight:400;color:var(--text3)">(seconds)</span></span>
        <input class="input rr-delay" type="number" placeholder="10" min="0">
      </div>
    </div>`;
  document.getElementById('robots-rules').appendChild(div);
}

async function generateRobots() {
  const rules = [];
  document.querySelectorAll('.robots-rule').forEach(el => {
    rules.push({
      user_agent:  el.querySelector('.rr-ua').value || '*',
      disallow:    el.querySelector('.rr-disallow').value.split('\n').map(s=>s.trim()).filter(Boolean),
      allow:       el.querySelector('.rr-allow').value.split('\n').map(s=>s.trim()).filter(Boolean),
      crawl_delay: el.querySelector('.rr-delay').value || '',
    });
  });
  const sitemap = document.getElementById('robots-sitemap').value.trim();
  try {
    const r = await fetch('/api/tools/robots_txt', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ rules, sitemap })
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    const content = d.content;
    document.getElementById('robots-output').value = content;
    // Warn if Disallow: / is present (blocks entire site)
    const disallowAll = rules.some(r => r.disallow.includes('/'));
    const warn = document.getElementById('robots-disallow-warn');
    if (warn) warn.style.display = disallowAll ? '' : 'none';
  } catch(e) {
    document.getElementById('robots-output').value = 'Error: ' + e.message;
  }
}

// init one rule
document.addEventListener('DOMContentLoaded', () => addRobotsRule());


// ── Tool 9: XML Sitemap Generator ─────────────────────────────────────────────
async function generateSitemap() {
  const rawUrls    = document.getElementById('sitemap-urls').value.trim();
  const changefreq = document.getElementById('sitemap-changefreq').value;
  const priority   = document.getElementById('sitemap-priority').value;
  const lastmod    = document.getElementById('sitemap-lastmod').value;
  if (!rawUrls) { toast('Enter at least one URL', 'warn'); return; }

  const urls = rawUrls.split('\n').map(u => u.trim()).filter(Boolean).map(url => ({
    url, changefreq, priority, lastmod
  }));

  try {
    const r = await fetch('/api/tools/sitemap_generate', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({urls})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    document.getElementById('sitemap-output').value = d.content;
    document.getElementById('sitemap-url-count').textContent = `(${d.url_count} URLs)`;
  } catch(e) {
    document.getElementById('sitemap-output').value = 'Error: ' + e.message;
  }
}


// ── Tool 10: Hreflang Tag Generator ───────────────────────────────────────────
const COMMON_LOCALES = [
  'en','en-US','en-GB','en-AU','en-CA',
  'fr','fr-FR','fr-CA','de','de-DE','de-AT','de-CH',
  'es','es-ES','es-MX','it','it-IT','pt','pt-BR','pt-PT',
  'nl','sv','da','no','fi','pl','cs','sk','hu','ro',
  'ru','uk','ar','zh','zh-CN','zh-TW','ja','ko','hi',
  'tr','vi','th','id','ms',
];

let _hreflangCount = 0;

function addHreflangRow() {
  _hreflangCount++;
  const div = document.createElement('div');
  div.className = 'hreflang-row';
  const opts = COMMON_LOCALES.map(l => `<option value="${l}">${l}</option>`).join('');
  div.innerHTML = `
    <select class="input hl-locale"><option value="">— pick —</option>${opts}</select>
    <input class="input hl-url" placeholder="https://example.com/page/">
    <button class="btn btn-ghost btn-sm" onclick="this.closest('.hreflang-row').remove()">✕</button>`;
  document.getElementById('hreflang-rows').appendChild(div);
}

function toggleXDefault(checked) {
  document.getElementById('hreflang-xdefault-url').style.display = checked ? '' : 'none';
}

let _hreflangData = null;

async function generateHreflang() {
  const items = [];
  document.querySelectorAll('.hreflang-row').forEach(el => {
    const locale = el.querySelector('.hl-locale').value;
    const url    = el.querySelector('.hl-url').value.trim();
    if (locale && url) items.push({locale, url});
  });
  if (!items.length) { toast('Add at least one locale/URL pair', 'warn'); return; }

  const include_xdefault = document.getElementById('hreflang-xdefault').checked;
  const xdefault_url     = document.getElementById('hreflang-xdefault-url').value.trim();

  try {
    const r = await fetch('/api/tools/hreflang_generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({items, include_xdefault, xdefault_url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    _hreflangData = d;
    document.getElementById('hreflang-output').value      = d.html_tags;
    document.getElementById('hreflang-http-output').value = d.http_header;
  } catch(e) {
    document.getElementById('hreflang-output').value = 'Error: ' + e.message;
  }
}

function hreflangTab(tab, btn) {
  document.querySelectorAll('#panel-gen-hreflang .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('hreflang-output').style.display      = tab === 'html' ? '' : 'none';
  document.getElementById('hreflang-http-output').style.display = tab === 'http' ? '' : 'none';
  if (tab === 'http') {
    document.getElementById('hreflang-http-output').value = _hreflangData?.http_header || '';
    copyOutput('hreflang-http-output');
  }
}

// init some rows
document.addEventListener('DOMContentLoaded', () => { addHreflangRow(); addHreflangRow(); });


// ── Tool 11: Meta Tags Generator ──────────────────────────────────────────────
function metaLenUpdate() {
  const t = document.getElementById('meta-title').value.length;
  const d = document.getElementById('meta-desc').value.length;
  const tEl = document.getElementById('meta-title-len');
  const dEl = document.getElementById('meta-desc-len');
  tEl.textContent = `(${t}/60)`;
  tEl.className   = t > 60 ? 'meta-len-err' : t < 30 ? 'meta-len-warn' : 'meta-len-ok';
  dEl.textContent = `(${d}/160)`;
  dEl.className   = d > 160 ? 'meta-len-err' : d < 70 ? 'meta-len-warn' : 'meta-len-ok';
  updateMetaSerpPreview();
}

function updateMetaSerpPreview() {
  const title    = document.getElementById('meta-title').value.trim();
  const desc     = document.getElementById('meta-desc').value.trim();
  const canonical= document.getElementById('meta-canonical').value.trim();
  const siteName = document.getElementById('meta-og-sitename').value.trim();
  if (!title && !desc) { document.getElementById('metatags-serp-preview').style.display='none'; return; }
  document.getElementById('metatags-serp-preview').style.display = '';
  document.getElementById('mt-serp-title').textContent = title || '(no title)';
  document.getElementById('mt-serp-desc').textContent  = desc  || '(no description)';
  const host = canonical ? (() => { try { return new URL(canonical).hostname; } catch{ return canonical; } })() : (siteName || 'example.com');
  document.getElementById('mt-serp-site').textContent = siteName || host;
  document.getElementById('mt-serp-url').textContent  = canonical || '';
  const tLen = title.length, dLen = desc.length;
  document.getElementById('mt-title-len-hint').textContent = tLen ? `Title: ${tLen} chars${tLen>60?' (too long)':tLen<30?' (too short)':' ✓'}` : '';
  document.getElementById('mt-desc-len-hint').textContent  = dLen ? `Description: ${dLen} chars${dLen>160?' (too long)':dLen<70?' (too short)':' ✓'}` : '';
}

async function generateMetaTags() {
  const data = {
    title:         document.getElementById('meta-title').value,
    description:   document.getElementById('meta-desc').value,
    keywords:      document.getElementById('meta-keywords').value,
    canonical:     document.getElementById('meta-canonical').value,
    robots:        document.getElementById('meta-robots').value,
    og_type:       document.getElementById('meta-og-type').value,
    og_image:      document.getElementById('meta-og-image').value,
    og_site_name:  document.getElementById('meta-og-sitename').value,
    tw_site:       document.getElementById('meta-tw-site').value,
  };
  try {
    const r = await fetch('/api/tools/meta_tags_generate', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    document.getElementById('metatags-output').value = d.content;
    document.getElementById('metatags-warnings').innerHTML = d.warnings.map(w =>
      `<div class="gen-warn-item">⚠ ${escTool(w)}</div>`
    ).join('');
  } catch(e) {
    document.getElementById('metatags-output').value = 'Error: ' + e.message;
  }
}

// ════════════════════════════════════════════════════════════════════════════
// ROBOTS.TXT TESTER
// ════════════════════════════════════════════════════════════════════════════

async function runRobotsTester() {
  const url = (document.getElementById('robots-test-url').value || '').trim();
  if (!url) { _showErr('robots-test-error', 'Enter a URL'); return; }

  _show('robots-test-spinner');
  _hide('robots-test-error', 'robots-test-result');

  try {
    const r = await fetch('/api/tools/robots_tester', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Unknown error');

    // ── Verdict card ──────────────────────────────────────────────────────
    const starOk   = d.verdicts?.star_allowed;
    const gbOk     = d.verdicts?.googlebot_allowed;
    const verdictHtml = `
      <div class="card-title" style="margin-bottom:12px">Crawl Verdict for <code style="font-size:12px">${escTool(d.target_url)}</code></div>
      <div style="display:flex;gap:16px;flex-wrap:wrap">
        <div class="kpi-card" style="flex:1;min-width:140px;text-align:center;padding:14px;background:${starOk?'var(--success-l)':'var(--danger-l)'};border-radius:10px">
          <div style="font-size:22px">${starOk ? '✅' : '❌'}</div>
          <div style="font-weight:700;margin-top:4px">All bots (*)</div>
          <div style="font-size:12px;color:var(--c-muted)">${starOk ? 'Allowed' : 'Blocked'}</div>
        </div>
        <div class="kpi-card" style="flex:1;min-width:140px;text-align:center;padding:14px;background:${gbOk?'var(--success-l)':'var(--danger-l)'};border-radius:10px">
          <div style="font-size:22px">${gbOk ? '✅' : '❌'}</div>
          <div style="font-weight:700;margin-top:4px">Googlebot</div>
          <div style="font-size:12px;color:var(--c-muted)">${gbOk ? 'Allowed' : 'Blocked'}</div>
        </div>
        <div class="kpi-card" style="flex:1;min-width:140px;text-align:center;padding:14px;background:var(--surface2);border-radius:10px">
          <div style="font-size:22px">${d.summary?.has_sitemap ? '📋' : '⚠️'}</div>
          <div style="font-weight:700;margin-top:4px">Sitemap</div>
          <div style="font-size:12px;color:var(--c-muted)">${d.summary?.has_sitemap ? d.sitemaps.length + ' declared' : 'Not declared'}</div>
        </div>
        <div class="kpi-card" style="flex:1;min-width:140px;text-align:center;padding:14px;background:var(--surface2);border-radius:10px">
          <div style="font-size:22px">🤖</div>
          <div style="font-weight:700;margin-top:4px">User-agents</div>
          <div style="font-size:12px;color:var(--c-muted)">${d.summary?.total_agents} defined</div>
        </div>
      </div>
      ${d.sitemaps?.length ? `<div style="margin-top:10px;font-size:12px;color:var(--c-muted)">Sitemap(s): ${d.sitemaps.map(s=>`<a href="${safeHref(s)}" target="_blank" rel="noopener noreferrer" style="color:var(--primary)">${escTool(s)}</a>`).join(', ')}</div>` : ''}
    `;
    document.getElementById('robots-verdict-card').innerHTML = verdictHtml;

    // ── Issues card ───────────────────────────────────────────────────────
    const issueHtml = d.issues?.length ? `
      <div class="card-title" style="margin-bottom:10px">Issues &amp; Recommendations</div>
      ${d.issues.map(i => {
        const icon  = i.level==='error' ? '❌' : i.level==='warning' ? '⚠️' : 'ℹ️';
        const color = i.level==='error' ? 'var(--danger)' : i.level==='warning' ? 'var(--warn)' : 'var(--c-muted)';
        return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--border);font-size:12.5px">
          <span style="flex-shrink:0">${icon}</span>
          <span style="color:${color}">${escTool(i.message)}</span>
        </div>`;
      }).join('')}
    ` : '<div style="color:var(--c-muted);font-size:13px">No issues detected.</div>';
    document.getElementById('robots-issues-card').innerHTML = issueHtml;

    // ── Agent blocks ──────────────────────────────────────────────────────
    const agentRows = (d.agents || []).map(ag => {
      const disallowPills = (ag.disallows||[]).map(p => p
        ? `<span style="display:inline-block;margin:2px;padding:1px 7px;background:var(--danger-l);border-radius:10px;font-size:11px;font-family:monospace;color:var(--danger)">${escTool(p)}</span>`
        : `<span style="display:inline-block;margin:2px;padding:1px 7px;background:var(--success-l);border-radius:10px;font-size:11px;font-family:monospace;color:var(--success)">(allow all)</span>`
      ).join('') || '<span style="color:var(--c-muted);font-size:11px">none</span>';
      const allowPills = (ag.allows||[]).map(p =>
        `<span style="display:inline-block;margin:2px;padding:1px 7px;background:var(--success-l);border-radius:10px;font-size:11px;font-family:monospace;color:var(--success)">${escTool(p)}</span>`
      ).join('') || '<span style="color:var(--c-muted);font-size:11px">none</span>';
      return `<tr>
        <td style="font-weight:700;font-family:monospace;font-size:12px;white-space:nowrap;padding:8px 10px">${escTool(ag.user_agent)}</td>
        <td style="padding:8px 10px">${disallowPills}</td>
        <td style="padding:8px 10px">${allowPills}</td>
        <td style="padding:8px 10px;font-size:11px;color:var(--c-muted)">${ag.crawl_delay || '—'}</td>
      </tr>`;
    }).join('');

    document.getElementById('robots-agents-card').innerHTML = agentRows ? `
      <div class="card-title" style="margin-bottom:10px">User-agent Blocks</div>
      <div class="table-wrap"><table class="result-table">
        <thead><tr><th>User-agent</th><th>Disallow</th><th>Allow</th><th>Crawl-delay</th></tr></thead>
        <tbody>${agentRows}</tbody>
      </table></div>
    ` : '<div style="color:var(--c-muted);font-size:13px">No user-agent blocks found.</div>';

    // ── Raw content ────────────────────────────────────────────────────────
    if (d.content) {
      document.getElementById('robots-raw-content').value = d.content;
      showEl('robots-raw-card');
    }

    _show('robots-test-result');
  } catch(e) {
    _showErr('robots-test-error', e.message);
  } finally {
    _hide('robots-test-spinner');
  }
}

function clearRobotsTester() {
  _clearVal('robots-test-url');
  _hide('robots-test-result', 'robots-test-error');
}

// ════════════════════════════════════════════════════════════════════════════
// HREFLANG VALIDATOR
// ════════════════════════════════════════════════════════════════════════════

async function runHreflangValidator() {
  const url = (document.getElementById('hreflang-val-url').value || '').trim();
  if (!url) { _showErr('hreflang-val-error', 'Enter a URL'); return; }

  _show('hreflang-val-spinner');
  _hide('hreflang-val-error', 'hreflang-val-result');

  try {
    const r = await fetch('/api/tools/hreflang_validate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Unknown error');

    const sm = d.summary || {};
    const entries = d.entries || [];

    // ── Summary card ──────────────────────────────────────────────────────
    const summaryHtml = `
      <div class="card-title" style="margin-bottom:12px">hreflang Summary</div>
      <div style="display:flex;gap:14px;flex-wrap:wrap">
        <div style="flex:1;min-width:120px;text-align:center;padding:12px;background:var(--surface2);border-radius:10px">
          <div style="font-size:22px;font-weight:800">${sm.total || 0}</div>
          <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">Tags found</div>
        </div>
        <div style="flex:1;min-width:120px;text-align:center;padding:12px;background:${sm.has_x_default?'var(--success-l)':'var(--danger-l)'};border-radius:10px">
          <div style="font-size:22px">${sm.has_x_default ? '✅' : '❌'}</div>
          <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">x-default</div>
        </div>
        <div style="flex:1;min-width:120px;text-align:center;padding:12px;background:${sm.unreachable_count?'var(--danger-l)':'var(--success-l)'};border-radius:10px">
          <div style="font-size:22px;font-weight:800">${sm.unreachable_count || 0}</div>
          <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">Unreachable</div>
        </div>
        <div style="flex:1;min-width:120px;text-align:center;padding:12px;background:${(sm.duplicate_langs||[]).length?'var(--danger-l)':'var(--surface2)'};border-radius:10px">
          <div style="font-size:22px;font-weight:800">${(sm.duplicate_langs||[]).length}</div>
          <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">Duplicate langs</div>
        </div>
      </div>
    `;
    document.getElementById('hreflang-summary-card').innerHTML = summaryHtml;

    // ── Issues card ───────────────────────────────────────────────────────
    const issues = d.issues || [];
    const issueHtml = issues.map(i => {
      const icon  = i.level==='error' ? '❌' : i.level==='warning' ? '⚠️' : 'ℹ️';
      const color = i.level==='error' ? 'var(--danger)' : i.level==='warning' ? 'var(--warn)' : 'var(--c-muted)';
      return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--border);font-size:12.5px">
        <span style="flex-shrink:0">${icon}</span>
        <span style="color:${color}">${escTool(i.message)}</span>
      </div>`;
    }).join('');
    document.getElementById('hreflang-issues-card').innerHTML = issues.length
      ? `<div class="card-title" style="margin-bottom:10px">Issues &amp; Recommendations</div>${issueHtml}`
      : '<div style="color:var(--c-muted);font-size:13px">No issues detected.</div>';

    // ── Entries table ─────────────────────────────────────────────────────
    if (entries.length) {
      const rows = entries.map(e => {
        const reachBadge = e.reachable === true
          ? `<span style="color:var(--success);font-weight:700">${e.status}</span>`
          : e.reachable === false
            ? `<span style="color:var(--danger);font-weight:700">${e.status || 'Error'}</span>`
            : `<span style="color:var(--c-muted)">—</span>`;
        const redirect = e.redirect_to
          ? `<div style="font-size:10px;color:var(--warn);margin-top:2px">↪ ${escTool(e.redirect_to.slice(0,60))}</div>`
          : '';
        return `<tr>
          <td style="font-family:monospace;font-weight:700;font-size:12px;white-space:nowrap;padding:7px 10px">
            ${e.lang === 'x-default' ? '⭐ ' : ''}${escTool(e.lang)}
          </td>
          <td style="padding:7px 10px;font-size:12px;word-break:break-all">
            <a href="${safeHref(e.url)}" target="_blank" rel="noopener noreferrer" style="color:var(--primary)">${escTool(e.url)}</a>
            ${redirect}
          </td>
          <td style="padding:7px 10px;text-align:center">${reachBadge}</td>
          <td style="padding:7px 10px;font-size:11px;color:var(--c-muted)">${escTool(e.source||'html')}</td>
        </tr>`;
      }).join('');
      document.getElementById('hreflang-entries-card').innerHTML = `
        <div class="card-title" style="margin-bottom:10px">Alternate URLs (${entries.length})</div>
        <div class="table-wrap"><table class="result-table">
          <thead><tr><th>Lang</th><th>URL</th><th>Status</th><th>Source</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      `;
    } else {
      document.getElementById('hreflang-entries-card').innerHTML =
        '<div style="color:var(--c-muted);font-size:13px">No hreflang entries found on this page.</div>';
    }

    _show('hreflang-val-result');
  } catch(e) {
    _showErr('hreflang-val-error', e.message);
  } finally {
    _hide('hreflang-val-spinner');
  }
}

function clearHreflangValidator() {
  _clearVal('hreflang-val-url');
  _hide('hreflang-val-result', 'hreflang-val-error');
}

// ═══════════════════════════════════════════════════════════════════════════
// Link Health — broken outbound link checker
// ═══════════════════════════════════════════════════════════════════════════
let _lhRun = 0;
async function runLinkHealth() {
  const url = (document.getElementById('lh-url')?.value || '').trim();
  if (!url) { _showErr('lh-error', 'URL required'); return; }
  const tok = ++_lhRun;
  _hide('lh-error', 'lh-result'); _show('lh-spinner');
  try {
    const d = await _api('/api/tools/link_health', {url});
    if (tok !== _lhRun) return; // stale response — user already cleared or re-ran
    _hide('lh-spinner');
    if (!d.ok) { _showErr('lh-error', d.error || 'Error'); return; }
    _renderLinkHealth(d);
    _show('lh-result');
  } catch(e) { if (tok !== _lhRun) return; _hide('lh-spinner'); _showErr('lh-error', e.message); }
}

function _renderLinkHealth(d) {
  const sm = d.summary || {};
  const hasBroken = sm.broken > 0 || sm.errors > 0;
  // Summary KPIs
  document.getElementById('lh-summary-card').innerHTML = `
    <div class="card-title">Scan Results${d.capped ? ' <span style="font-size:11px;font-weight:400;color:var(--c-muted)">(first 60 links)</span>' : ''}${d.timed_out ? ' <span style="font-size:11px;font-weight:400;color:var(--warn)">⚠ 30s limit hit — some links skipped</span>' : ''}</div>
    <div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:12px">
      <div style="flex:1;min-width:100px;text-align:center;padding:12px;background:${hasBroken?'var(--danger-l)':'var(--success-l)'};border-radius:10px">
        <div style="font-size:28px;font-weight:800;color:${hasBroken?'var(--danger)':'var(--success)'}">${sm.broken+sm.errors}</div>
        <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">Broken</div>
      </div>
      <div style="flex:1;min-width:100px;text-align:center;padding:12px;background:${sm.redirect?'var(--warn-l)':'var(--surface2)'};border-radius:10px">
        <div style="font-size:28px;font-weight:800;color:${sm.redirect?'var(--warn)':'var(--text2)'}">${sm.redirect}</div>
        <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">Redirects</div>
      </div>
      <div style="flex:1;min-width:100px;text-align:center;padding:12px;background:var(--success-l);border-radius:10px">
        <div style="font-size:28px;font-weight:800;color:var(--success)">${sm.ok}</div>
        <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">OK</div>
      </div>
      <div style="flex:1;min-width:100px;text-align:center;padding:12px;background:var(--surface2);border-radius:10px">
        <div style="font-size:28px;font-weight:800">${sm.total}</div>
        <div style="font-size:11px;color:var(--c-muted);text-transform:uppercase;letter-spacing:.5px">Total</div>
      </div>
    </div>
  `;
  // Links table
  const links = d.links || [];
  const visible = links.filter(l => l.type !== 'skip');
  const rows = visible.map(l => {
    const status = l.status
      ? `<span style="font-weight:700;color:${l.status>=400?'var(--danger)':l.status>=300?'var(--warn)':'var(--success)'}">${l.status}</span>`
      : `<span style="color:var(--danger)">Error</span>`;
    const typeBadge = l.type === 'internal'
      ? `<span style="background:var(--primary-l);color:var(--primary);border-radius:4px;padding:1px 5px;font-size:10px">int</span>`
      : `<span style="background:var(--surface3);color:var(--text2);border-radius:4px;padding:1px 5px;font-size:10px">ext</span>`;
    const redirect = l.redirect_to
      ? `<div style="font-size:10px;color:var(--warn);margin-top:2px">↪ ${escTool(l.redirect_to.slice(0,70))}</div>`
      : '';
    const errMsg = l.error
      ? `<div style="font-size:10px;color:var(--danger)">${escTool(l.error)}</div>`
      : '';
    return `<tr>
      <td style="padding:6px 10px">${status}</td>
      <td style="padding:6px 10px">${typeBadge}</td>
      <td style="padding:6px 10px;font-size:11px;word-break:break-all">
        <a href="${safeHref(l.url)}" target="_blank" rel="noopener noreferrer" style="color:var(--primary)">${escTool(l.url)}</a>
        ${redirect}${errMsg}
      </td>
    </tr>`;
  }).join('');
  document.getElementById('lh-links-card').innerHTML = visible.length
    ? `<div class="card-title" style="margin-bottom:10px">Links (${visible.length})</div>
       <div class="table-wrap"><table class="result-table">
         <thead><tr><th>Status</th><th>Type</th><th>URL</th></tr></thead>
         <tbody>${rows}</tbody>
       </table></div>`
    : '<div style="color:var(--c-muted);font-size:13px">No links found on this page.</div>';
}

function clearLinkHealth() {
  _clearVal('lh-url');
  _hide('lh-result', 'lh-error');
}

// ═══════════════════════════════════════════════════════════════════════════
// Crawl Intelligence — robots.txt + sitemap audit in one view
// ═══════════════════════════════════════════════════════════════════════════
let _ciRun = 0;
async function runCrawlIntel() {
  const url = (document.getElementById('ci-url')?.value || '').trim();
  if (!url) { _showErr('ci-error', 'Site URL required'); return; }
  const tok = ++_ciRun;
  _hide('ci-error', 'ci-result'); _show('ci-spinner');
  try {
    // Run robots tester and sitemap audit in parallel
    const [robots, sitemap] = await Promise.all([
      _api('/api/tools/robots_tester', {url}),
      _api('/api/tools/sitemap_audit', {url}),
    ]);
    if (tok !== _ciRun) return; // stale — user cleared or re-ran
    _hide('ci-spinner');
    if (!robots.ok && !sitemap.ok) {
      _showErr('ci-error', robots.error || sitemap.error || 'Both checks failed');
      return;
    }
    _renderCrawlIntel(robots, sitemap, url);
    _show('ci-result');
  } catch(e) { if (tok !== _ciRun) return; _hide('ci-spinner'); _showErr('ci-error', e.message); }
}

function _renderCrawlIntel(robots, sitemap, url) {
  // ── Robots card ──────────────────────────────────────────────────────────
  const rm = robots.summary || {};
  const robotsHtml = robots.ok ? `
    <div class="card-title" style="margin-bottom:10px">🤖 robots.txt</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px">
      <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:${rm.all_blocked?'var(--danger-l)':rm.googlebot_blocked?'var(--warn-l)':'var(--success-l)'};border-radius:8px">
        <div style="font-size:16px">${rm.all_blocked?'❌':rm.googlebot_blocked?'⚠️':'✅'}</div>
        <div style="font-size:10px;color:var(--c-muted);margin-top:2px">Googlebot</div>
      </div>
      <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:${rm.has_sitemap?'var(--success-l)':'var(--warn-l)'};border-radius:8px">
        <div style="font-size:16px">${rm.has_sitemap?'✅':'❌'}</div>
        <div style="font-size:10px;color:var(--c-muted);margin-top:2px">Sitemap</div>
      </div>
      <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:${rm.issue_count?'var(--warn-l)':'var(--surface2)'};border-radius:8px">
        <div style="font-size:20px;font-weight:700">${rm.issue_count||0}</div>
        <div style="font-size:10px;color:var(--c-muted);margin-top:2px">Issues</div>
      </div>
    </div>
    ${(robots.issues||[]).slice(0,6).map(i=>`<div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border)">
      ${i.level==='error'?'❌':i.level==='warning'?'⚠️':'ℹ️'} ${escTool(i.message)}</div>`).join('')}
  ` : `<div class="card-title">🤖 robots.txt</div><div class="error-box" style="margin-top:8px">${escTool(robots.error||'Failed')}</div>`;
  document.getElementById('ci-robots-card').innerHTML = robotsHtml;

  // ── Sitemap card ─────────────────────────────────────────────────────────
  const ss = sitemap.summary || {};
  const sitemapHtml = sitemap.ok ? `
    <div class="card-title" style="margin-bottom:10px">🗺️ Sitemap</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px">
      <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:var(--surface2);border-radius:8px">
        <div style="font-size:20px;font-weight:700">${ss.total_urls||0}</div>
        <div style="font-size:10px;color:var(--c-muted);margin-top:2px">URLs</div>
      </div>
      <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:${ss.broken_count?'var(--danger-l)':'var(--success-l)'};border-radius:8px">
        <div style="font-size:20px;font-weight:700;color:${ss.broken_count?'var(--danger)':'var(--success)'}">${ss.broken_count||0}</div>
        <div style="font-size:10px;color:var(--c-muted);margin-top:2px">Broken</div>
      </div>
      <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:${ss.duplicate_count?'var(--warn-l)':'var(--surface2)'};border-radius:8px">
        <div style="font-size:20px;font-weight:700">${ss.duplicate_count||0}</div>
        <div style="font-size:10px;color:var(--c-muted);margin-top:2px">Dupes</div>
      </div>
    </div>
    ${(sitemap.issues||[]).slice(0,6).map(i=>`<div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border)">
      ${i.level==='error'?'❌':i.level==='warning'?'⚠️':'ℹ️'} ${escTool(i.message)}</div>`).join('')}
  ` : `<div class="card-title">🗺️ Sitemap</div><div class="error-box" style="margin-top:8px">${escTool(sitemap.error||'Failed')}</div>`;
  document.getElementById('ci-sitemap-card').innerHTML = sitemapHtml;

  // ── Combined issues / verdict card ───────────────────────────────────────
  const allIssues = [
    // Synthetic errors for failed checks — prevent false "healthy" verdict
    ...(!robots.ok  ? [{level:'error', message: `robots.txt check failed: ${escTool(robots.error||'unknown error')}`,  src:'robots.txt'}] : []),
    ...(!sitemap.ok ? [{level:'error', message: `Sitemap check failed: ${escTool(sitemap.error||'unknown error')}`, src:'sitemap'}]      : []),
    ...(robots.issues||[]).filter(i=>i.level!=='info').map(i=>({...i, src:'robots.txt'})),
    ...(sitemap.issues||[]).filter(i=>i.level!=='info').map(i=>({...i, src:'sitemap'})),
  ];
  const errCount  = allIssues.filter(i=>i.level==='error').length;
  const warnCount = allIssues.filter(i=>i.level==='warning').length;
  const verdict   = errCount ? '🔴 Critical crawl issues — fix before next crawl'
                  : warnCount ? '🟡 Crawl warnings — review and improve'
                  : '🟢 Crawl access looks healthy';
  const issueRows = allIssues.slice(0,20).map(i => `
    <div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12.5px">
      <span style="flex-shrink:0">${i.level==='error'?'❌':'⚠️'}</span>
      <span style="flex:1">${escTool(i.message)}</span>
      <span style="font-size:10px;color:var(--c-muted);white-space:nowrap">${i.src}</span>
    </div>`).join('');
  document.getElementById('ci-issues-card').innerHTML = `
    <div style="font-size:14px;font-weight:700;margin-bottom:12px">${verdict}</div>
    ${allIssues.length
      ? issueRows
      : '<div style="color:var(--c-muted);font-size:13px">No issues detected across robots.txt and sitemap.</div>'}
  `;

  // Make grid single-column on narrow screens (already handled by CSS grid auto-fit,
  // but we remove the grid wrapper on mobile < 640px via inline style)
  const grid = document.getElementById('ci-grid');
  if (grid && window.innerWidth < 640) grid.style.gridTemplateColumns = '1fr';
}

function clearCrawlIntel() {
  _clearVal('ci-url');
  _hide('ci-result', 'ci-error');
}

// ═══════════════════════════════════════════════════════════════════════════
// Content + SERP Optimizer — snippet quality + keyword fit in one view
// ═══════════════════════════════════════════════════════════════════════════
let _csRun = 0;
async function runContentSerp() {
  const url = (document.getElementById('cs-url')?.value || '').trim();
  const kw  = (document.getElementById('cs-kw')?.value  || '').trim();
  if (!url) { _showErr('cs-error', 'URL required'); return; }
  if (!kw)  { _showErr('cs-error', 'Target keyword required'); return; }
  const tok = ++_csRun;
  _hide('cs-error', 'cs-result'); _show('cs-spinner');
  try {
    const [snippet, density] = await Promise.all([
      _api('/api/tools/serp_preview', {url}),
      _api('/api/tools/keyword_density', {url, top_n: 30}),
    ]);
    if (tok !== _csRun) return; // stale — user cleared or re-ran
    _hide('cs-spinner');
    if (!snippet.ok && !density.ok) {
      _showErr('cs-error', snippet.error || density.error || 'Both checks failed');
      return;
    }
    _renderContentSerp(snippet, density, kw);
    _show('cs-result');
  } catch(e) { if (tok !== _csRun) return; _hide('cs-spinner'); _showErr('cs-error', e.message); }
}

function _renderContentSerp(snippet, density, kw) {
  const kwLow = kw.toLowerCase();

  // ── SERP Snippet card ────────────────────────────────────────────────────
  if (snippet.ok) {
    const title = snippet.title || '';
    const desc  = snippet.description || '';
    const titleHasKw  = title.toLowerCase().includes(kwLow);
    const descHasKw   = desc.toLowerCase().includes(kwLow);
    const titleWarn   = snippet.title_warnings?.length ? snippet.title_warnings.join('; ') : null;
    const descWarn    = snippet.desc_warnings?.length  ? snippet.desc_warnings.join('; ')  : null;

    document.getElementById('cs-snippet-card').innerHTML = `
      <div class="card-title" style="margin-bottom:12px">🔍 SERP Snippet</div>
      <!-- Google-style preview -->
      <div style="background:var(--surface2);border-radius:8px;padding:14px 16px;margin-bottom:14px;max-width:600px">
        <div style="font-size:12px;color:var(--c-muted);margin-bottom:2px">${escTool(snippet.display_url||'')}</div>
        <div style="font-size:18px;color:#1a0dab;font-weight:500;line-height:1.3">${escTool(title||'(No title)')}</div>
        <div style="font-size:13.5px;color:#4d5156;margin-top:4px;line-height:1.5">${escTool(desc||'(No description)')}</div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px">
        <span style="padding:3px 10px;border-radius:20px;font-size:12px;background:${titleHasKw?'var(--success-l)':'var(--danger-l)'};color:${titleHasKw?'var(--success)':'var(--danger)'}">
          ${titleHasKw?'✅':'❌'} Keyword in title
        </span>
        <span style="padding:3px 10px;border-radius:20px;font-size:12px;background:${descHasKw?'var(--success-l)':'var(--warn-l)'};color:${descHasKw?'var(--success)':'var(--warn)'}">
          ${descHasKw?'✅':'⚠️'} Keyword in description
        </span>
        <span style="padding:3px 10px;border-radius:20px;font-size:12px;background:var(--surface3)">
          Title: ${snippet.title_len||0} chars
        </span>
        <span style="padding:3px 10px;border-radius:20px;font-size:12px;background:var(--surface3)">
          Desc: ${snippet.desc_len||0} chars
        </span>
      </div>
      ${titleWarn ? `<div style="font-size:12px;color:var(--warn);margin-top:4px">⚠️ ${escTool(titleWarn)}</div>` : ''}
      ${descWarn  ? `<div style="font-size:12px;color:var(--warn);margin-top:4px">⚠️ ${escTool(descWarn)}</div>`  : ''}
    `;
  } else {
    document.getElementById('cs-snippet-card').innerHTML =
      `<div class="card-title">🔍 SERP Snippet</div><div class="error-box" style="margin-top:8px">${escTool(snippet.error||'Failed')}</div>`;
  }

  // ── Keyword Density card ─────────────────────────────────────────────────
  // Backend returns top_keywords:[{keyword, count, density}] — not "words"/"word"
  if (density.ok) {
    const words   = density.top_keywords || [];
    const kwEntry = words.find(w => w.keyword?.toLowerCase() === kwLow); // exact match only — no substring
    const kwCount = kwEntry?.count || 0;
    const kwDens  = kwEntry?.density || 0;
    const densOk  = kwDens >= 0.5 && kwDens <= 3.5;
    const topWords = words.slice(0, 15);
    const rows = topWords.map((w, i) => {
      const isKw = w.keyword?.toLowerCase() === kwLow; // exact match only
      return `<tr style="${isKw?'background:var(--primary-l)':''}">
        <td style="padding:5px 10px;color:var(--c-muted)">${i+1}</td>
        <td style="padding:5px 10px;font-weight:${isKw?700:400}">${escTool(w.keyword)}</td>
        <td style="padding:5px 10px">${w.count}</td>
        <td style="padding:5px 10px">${w.density}%</td>
      </tr>`;
    }).join('');
    document.getElementById('cs-kw-card').innerHTML = `
      <div class="card-title" style="margin-bottom:12px">📊 Keyword Density</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px">
        <div style="flex:1;min-width:120px;text-align:center;padding:10px;background:${kwCount?'var(--primary-l)':'var(--danger-l)'};border-radius:8px">
          <div style="font-size:24px;font-weight:800">${kwCount}</div>
          <div style="font-size:11px;color:var(--c-muted)">Occurrences of "${escTool(kw)}"</div>
        </div>
        <div style="flex:1;min-width:120px;text-align:center;padding:10px;background:${densOk?'var(--success-l)':kwDens>3.5?'var(--warn-l)':'var(--danger-l)'};border-radius:8px">
          <div style="font-size:24px;font-weight:800">${kwDens}%</div>
          <div style="font-size:11px;color:var(--c-muted)">Keyword density</div>
        </div>
        <div style="flex:1;min-width:120px;text-align:center;padding:10px;background:var(--surface2);border-radius:8px">
          <div style="font-size:24px;font-weight:800">${density.total_words||0}</div>
          <div style="font-size:11px;color:var(--c-muted)">Total words</div>
        </div>
      </div>
      <div class="table-wrap"><table class="result-table">
        <thead><tr><th>#</th><th>Word</th><th>Count</th><th>Density</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    `;
  } else {
    document.getElementById('cs-kw-card').innerHTML =
      `<div class="card-title">📊 Keyword Density</div><div class="error-box" style="margin-top:8px">${escTool(density.error||'Failed')}</div>`;
  }

  // ── Combined Score / Recommendations card ─────────────────────────────────
  const recs = [];
  if (snippet.ok) {
    const title = snippet.title || '';
    const desc  = snippet.description || '';
    if (!title.toLowerCase().includes(kwLow))
      recs.push({level:'error', msg:`Add "${kw}" to your title tag for better keyword targeting`});
    if (!desc.toLowerCase().includes(kwLow))
      recs.push({level:'warn', msg:`Consider including "${kw}" in the meta description`});
    if ((snippet.title_len||0) < 30)
      recs.push({level:'warn', msg:`Title is too short (${snippet.title_len} chars) — aim for 50-60 characters`});
    if ((snippet.title_len||0) > 65)
      recs.push({level:'warn', msg:`Title may be truncated in SERPs (${snippet.title_len} chars) — keep under 65`});
    if ((snippet.desc_len||0) < 70)
      recs.push({level:'warn', msg:`Description is too short (${snippet.desc_len} chars) — aim for 130-160 characters`});
    if ((snippet.desc_len||0) > 165)
      recs.push({level:'warn', msg:`Description may be truncated (${snippet.desc_len} chars) — keep under 165`});
  }
  if (density.ok) {
    // Use correct backend field name: top_keywords[].keyword (not words[].word)
    const kwDens = (density.top_keywords||[]).find(w=>w.keyword?.toLowerCase()===kwLow)?.density || 0;
    if (kwDens === 0)
      recs.push({level:'error', msg:`Keyword "${kw}" not found in page content — add it to headings and body text`});
    else if (kwDens < 0.5)
      recs.push({level:'warn', msg:`Keyword density is very low (${kwDens}%) — try to use "${kw}" more naturally in the content`});
    else if (kwDens > 3.5)
      recs.push({level:'warn', msg:`Keyword density is high (${kwDens}%) — keyword stuffing can hurt rankings; aim for 1-3%`});
    else
      recs.push({level:'ok', msg:`Keyword density is healthy (${kwDens}%) — good balance of keyword usage`});
  }
  // Guard: if both APIs failed, no recs were generated — show failure state, not a perfect score
  if (!snippet.ok && !density.ok) {
    document.getElementById('cs-score-card').innerHTML =
      '<div class="error-box">Both checks failed — cannot compute optimisation score.</div>';
    return;
  }
  if (!recs.length) recs.push({level:'ok', msg:'No obvious optimisation issues found'});

  const recHtml = recs.map(r => `
    <div style="display:flex;gap:8px;align-items:flex-start;padding:7px 0;border-bottom:1px solid var(--border);font-size:12.5px">
      <span style="flex-shrink:0">${r.level==='error'?'❌':r.level==='warn'?'⚠️':'✅'}</span>
      <span>${escTool(r.msg)}</span>
    </div>`).join('');
  const score = Math.max(0, 100 - recs.filter(r=>r.level==='error').length*25 - recs.filter(r=>r.level==='warn').length*10);
  document.getElementById('cs-score-card').innerHTML = `
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
      <div style="width:56px;height:56px;border-radius:50%;background:conic-gradient(${score>=70?'var(--success)':score>=40?'var(--warn)':'var(--danger)'} ${score*3.6}deg,var(--surface3) 0);display:flex;align-items:center;justify-content:center">
        <div style="width:44px;height:44px;border-radius:50%;background:var(--surface);display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800">${score}</div>
      </div>
      <div>
        <div style="font-size:16px;font-weight:700">Optimisation Score</div>
        <div style="font-size:12px;color:var(--c-muted)">${score>=70?'Well optimised':score>=40?'Needs improvement':'Needs work'} for "${escTool(kw)}"</div>
      </div>
    </div>
    <div class="card-title" style="margin-bottom:8px">Recommendations</div>
    ${recHtml}
  `;
}

function clearContentSerp() {
  _clearVal('cs-url', 'cs-kw');
  _hide('cs-result', 'cs-error');
}

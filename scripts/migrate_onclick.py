"""
Convert inline onclick="..." in dashboard.html / base.html to data-action="..."
event delegation. Also appends delegation handler to dashboard.js.

Run from project root:  python scripts/migrate_onclick.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ─── Explicit mapping for multi-expression / complex patterns
# key = exact onclick VALUE (no surrounding quotes), value = (action, arg, arg2)
EXPLICIT_MAP = {
    # multi-expression nav
    "navTo('uc-runner');mnavActive('mnav-uc')":         ("navToUcRunner", None, None),
    "navTo('aud-run');openFullAudit()":                  ("navToAudRun", None, None),
    "navTo('home');mnavActive('mnav-home')":              ("navToHome", None, None),
    "navTo('home');return false":                         ("navToHome", None, None),
    "navTo('reports');loadReports()":                     ("navToReports", None, None),
    "navTo('reports');mnavActive('mnav-rep')":            ("navToReportsMnav", None, None),
    "navTo('settings');mnavActive('mnav-settings')":      ("navToSettings", None, None),
    # navLink combos
    "navLink('compare');loadCompare()":                   ("navLinkCompare", None, None),
    "navLink('home');return false":                       ("navLinkHome", None, None),
    "navLink('reports');loadReports()":                   ("navLinkReports", None, None),
    "navLink('settings');return false":                   ("navLinkSettings", None, None),
    "navLink('trend');loadTrend()":                       ("navLinkTrend", None, None),
    # nav(this) + load combos
    "nav(this);loadCompare()":                            ("navAndLoadCompare", None, None),
    "nav(this);loadReports()":                            ("navAndLoadReports", None, None),
    "nav(this);loadTrend()":                              ("navAndLoadTrend", None, None),
    # help
    "openHelp();helpTab('keys',document.querySelector('[data-tab=\\'keys\\']'))":
                                                          ("openHelpKeys", None, None),
    # backdrop close
    "if(event.target===this)closeCmdPalette()":           ("closeCmdPaletteIfSelf", None, None),
    # stop propagation inside cmd-palette (prevents backdrop close)
    "event.stopPropagation()":                            ("stopPropagation", None, None),
    # base.html mobile nav toggle
    "document.getElementById('nav').classList.toggle('open')": ("navMobileToggle", None, None),
    # JS DOM expressions
    "document.getElementById('aud-file').click()":        ("clickAudFile", None, None),
    "document.getElementById('idx-file').click()":        ("clickIdxFile", None, None),
    # serpSocialTab(tab, this)
    "serpSocialTab('og',this)":  ("serpSocialTab", "og", None),
    "serpSocialTab('tw',this)":  ("serpSocialTab", "tw", None),
    # copyOutput — already handled by regex but listed for safety
    "copyOutput('hreflang-output')": ("copyOutput", "hreflang-output", None),
    "copyOutput('metatags-output')": ("copyOutput", "metatags-output", None),
    "copyOutput('robots-output')":   ("copyOutput", "robots-output", None),
    "copyOutput('schema-output')":   ("copyOutput", "schema-output", None),
    "copyOutput('sitemap-output')":  ("copyOutput", "sitemap-output", None),
    # downloadOutput('id','name','ext')
    "downloadOutput('hreflang-output','hreflang','html')": ("downloadOutput", "hreflang-output", "hreflang|html"),
    "downloadOutput('metatags-output','metatags','html')": ("downloadOutput", "metatags-output", "metatags|html"),
    "downloadOutput('robots-output','robots','txt')":      ("downloadOutput", "robots-output", "robots|txt"),
    "downloadOutput('schema-output','schema','json')":     ("downloadOutput", "schema-output", "schema|json"),
    "downloadOutput('sitemap-output','sitemap','xml')":    ("downloadOutput", "sitemap-output", "sitemap|xml"),
    # filterAudLog / filterIdxLog / filterReports with (tab, this)
    "filterAudLog('all',this)":         ("filterAudLog", "all", None),
    "filterAudLog('issues',this)":      ("filterAudLog", "issues", None),
    "filterAudLog('low',this)":         ("filterAudLog", "low", None),
    "filterIdxLog('all',this)":         ("filterIdxLog", "all", None),
    "filterIdxLog('error',this)":       ("filterIdxLog", "error", None),
    "filterIdxLog('indexed',this)":     ("filterIdxLog", "indexed", None),
    "filterIdxLog('not-indexed',this)": ("filterIdxLog", "not-indexed", None),
    "filterReports('all',this)":        ("filterReports", "all", None),
    "filterReports('audit',this)":      ("filterReports", "audit", None),
    "filterReports('indexing',this)":   ("filterReports", "indexing", None),
    # helpTab(tab, this)
    "helpTab('about',this)":        ("helpTab", "about", None),
    "helpTab('keys',this)":         ("helpTab", "keys", None),
    "helpTab('overview',this)":     ("helpTab", "overview", None),
    "helpTab('shortcuts',this)":    ("helpTab", "shortcuts", None),
    "helpTab('troubleshoot',this)": ("helpTab", "troubleshoot", None),
    "helpTab('usecases',this)":     ("helpTab", "usecases", None),
    # hreflangTab(tab, this)
    "hreflangTab('html',this)": ("hreflangTab", "html", None),
    "hreflangTab('http',this)": ("hreflangTab", "http", None),
    # setUcFormat(fmt, this)
    "setUcFormat('csv',this)":    ("setUcFormat", "csv", None),
    "setUcFormat('domain',this)": ("setUcFormat", "domain", None),
    "setUcFormat('sitemap',this)":("setUcFormat", "sitemap", None),
    "setUcFormat('url',this)":    ("setUcFormat", "url", None),
}

def parse_onclick(val: str):
    """Return (action, arg, arg2) or None."""
    val = val.strip()
    if val in EXPLICIT_MAP:
        return EXPLICIT_MAP[val]
    # func(this) or func()
    m = re.fullmatch(r"([a-zA-Z_$][\w$]*)\((?:this)?\)", val)
    if m:
        return (m.group(1), None, None)
    # func('arg') or func("arg")
    m = re.fullmatch(r"([a-zA-Z_$][\w$]*)\(['\"]([^'\"]+)['\"]\)", val)
    if m:
        return (m.group(1), m.group(2), None)
    return None


def onclick_to_attrs(val: str):
    parsed = parse_onclick(val)
    if parsed is None:
        return None
    action, arg, arg2 = parsed
    attrs = f'data-action="{action}"'
    if arg is not None:
        attrs += f' data-arg="{arg}"'
    if arg2 is not None:
        attrs += f' data-arg2="{arg2}"'
    return attrs


def transform_html(text: str):
    failed = []
    def replace(m):
        val = m.group(1)
        replacement = onclick_to_attrs(val)
        if replacement is None:
            failed.append(val)
            return m.group(0)
        return replacement
    result = re.sub(r'onclick="([^"]*)"', replace, text)
    return result, failed


DELEGATION_JS = """
// --- S-NEW: Centralised click delegation (replaces inline onclick) -----------
document.addEventListener('click', function _delegatedClick(e) {
  var el = e.target.closest('[data-action]');
  if (!el) return;
  var action = el.dataset.action;
  var arg    = el.dataset.arg  || null;
  var arg2   = el.dataset.arg2 || null;

  function _call(fn) {
    var args = Array.prototype.slice.call(arguments, 1);
    if (typeof window[fn] === 'function') window[fn].apply(null, args);
    else if (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
      console.warn('[delegation] unknown fn:', fn);
  }

  switch (action) {
    // Navigation
    case 'nav':               if(typeof nav==='function') nav(el); break;
    case 'navTo':             _call('navTo', arg); break;
    case 'navLink':           _call('navLink', arg); break;
    case 'navToUcRunner':     _call('navTo','uc-runner'); _call('mnavActive','mnav-uc'); break;
    case 'navToAudRun':       _call('navTo','aud-run'); _call('openFullAudit'); break;
    case 'navToHome':         _call('navTo','home'); break;
    case 'navToReports':      _call('navTo','reports'); _call('loadReports'); break;
    case 'navToReportsMnav':  _call('navTo','reports'); _call('mnavActive','mnav-rep'); break;
    case 'navToSettings':     _call('navTo','settings'); _call('mnavActive','mnav-settings'); break;
    case 'navLinkCompare':    _call('navLink','compare'); _call('loadCompare'); break;
    case 'navLinkHome':       _call('navLink','home'); break;
    case 'navLinkReports':    _call('navLink','reports'); _call('loadReports'); break;
    case 'navLinkSettings':   _call('navLink','settings'); break;
    case 'navLinkTrend':      _call('navLink','trend'); _call('loadTrend'); break;
    case 'navAndLoadCompare': if(typeof nav==='function') nav(el); _call('loadCompare'); break;
    case 'navAndLoadReports': if(typeof nav==='function') nav(el); _call('loadReports'); break;
    case 'navAndLoadTrend':   if(typeof nav==='function') nav(el); _call('loadTrend'); break;
    // Sidebar / UI
    case 'toggleSidebar':     _call('toggleSidebar'); break;
    case 'toggleKeyVis':      if(typeof toggleKeyVis==='function') toggleKeyVis(el); break;
    case 'sbToggle':          _call('sbToggle', arg); break;
    case 'toggleDark':        _call('toggleDark'); break;
    case 'openCmdPalette':    _call('openCmdPalette'); break;
    case 'closeCmdPaletteIfSelf': if(e.target===el) _call('closeCmdPalette'); break;
    case 'stopPropagation':   e.stopPropagation(); break;
    case 'navMobileToggle': { var n=document.getElementById('nav'); if(n) n.classList.toggle('open'); break; }
    case 'openHelp':          _call('openHelp'); break;
    case 'openHelpKeys': {
      _call('openHelp');
      var t=document.querySelector('[data-tab="keys"]');
      if(typeof helpTab==='function') helpTab('keys',t);
      break;
    }
    case 'closeHelp':         _call('closeHelp'); break;
    case 'closeDrawer':       _call('closeDrawer'); break;
    case 'closeAiOptModal':   _call('closeAiOptModal'); break;
    case 'closeCannibalModal':_call('closeCannibalModal'); break;
    case 'renderCfgHealth':   _call('renderCfgHealth'); break;
    case 'helpTab':           if(typeof helpTab==='function') helpTab(arg, el); break;
    case 'hreflangTab':       if(typeof hreflangTab==='function') hreflangTab(arg, el); break;
    // Theme
    case 'setThemePref':      _call('setThemePref', arg); break;
    // Audit
    case 'startAudit':        _call('startAudit'); break;
    case 'cancelAudit':       _call('cancelAudit'); break;
    case 'pauseAudit':        _call('pauseAudit'); break;
    case 'resumeAudit':       _call('resumeAudit'); break;
    case 'openAudReport':     _call('openAudReport'); break;
    case 'openFullAudit':     _call('openFullAudit'); break;
    case 'copyAudUrls':       _call('copyAudUrls'); break;
    case 'runAiExplain':      _call('runAiExplain'); break;
    case 'clearAiExplain':    _call('clearAiExplain'); break;
    case 'runAiDraftMeta':    _call('runAiDraftMeta'); break;
    case 'clearAiDraftMeta':  _call('clearAiDraftMeta'); break;
    case 'applyPreset':       _call('applyPreset', arg); break;
    case 'retryErrors':       _call('retryErrors'); break;
    case 'filterAudLog':      if(typeof filterAudLog==='function') filterAudLog(arg, el); break;
    case 'clickAudFile': { var f=document.getElementById('aud-file'); if(f) f.click(); } break;
    case 'clickIdxFile': { var f=document.getElementById('idx-file'); if(f) f.click(); } break;
    // Use-case / phase runner
    case 'runUseCase':        _call('runUseCase'); break;
    case 'copyUcResults':     _call('copyUcResults'); break;
    case 'setUcFormat':       if(typeof setUcFormat==='function') setUcFormat(arg, el); break;
    case 'clearUcRunner':     _call('clearUcRunner'); break;
    case 'clearPhaseRunner':  _call('clearPhaseRunner'); break;
    case 'runPhaseRunner':    _call('runPhaseRunner'); break;
    // Indexing
    case 'startIndex':        _call('startIndex'); break;
    case 'cancelIndex':       _call('cancelIndex'); break;
    case 'pauseIndex':        _call('pauseIndex'); break;
    case 'resumeIndex':       _call('resumeIndex'); break;
    case 'openIdxReport':     _call('openIdxReport'); break;
    case 'copyIdxUrls':       _call('copyIdxUrls'); break;
    case 'clearIdxForm':      _call('clearIdxForm'); break;
    case 'filterIdxLog':      if(typeof filterIdxLog==='function') filterIdxLog(arg, el); break;
    // Reports
    case 'clearRepSearch':    _call('clearRepSearch'); break;
    case 'runCompare':        _call('runCompare'); break;
    case 'clearCompare':      _call('clearCompare'); break;
    case 'filterReports':     if(typeof filterReports==='function') filterReports(arg, el); break;
    // Quick tools
    case 'runSerpPreview':    _call('runSerpPreview'); break;
    case 'clearSerp':         _call('clearSerp'); break;
    case 'serpSocialTab':     if(typeof serpSocialTab==='function') serpSocialTab(arg, el); break;
    case 'runRedirectChain':  _call('runRedirectChain'); break;
    case 'clearRedirect':     _call('clearRedirect'); break;
    case 'runHttpHeaders':    _call('runHttpHeaders'); break;
    case 'clearHeaders':      _call('clearHeaders'); break;
    case 'runKeywordDensity': _call('runKeywordDensity'); break;
    case 'clearKeywords':     _call('clearKeywords'); break;
    case 'runCodeTextRatio':  _call('runCodeTextRatio'); break;
    case 'clearRatio':        _call('clearRatio'); break;
    case 'runCompression':    _call('runCompression'); break;
    case 'clearCompression':  _call('clearCompression'); break;
    case 'runPageType':       _call('runPageType'); break;
    case 'runBlogAudit':      _call('runBlogAudit'); break;
    case 'runCourseAudit':    _call('runCourseAudit'); break;
    case 'runDuplicateScan':  _call('runDuplicateScan'); break;
    case 'clearContentSerp':  _call('clearContentSerp'); break;
    case 'runContentSerp':    _call('runContentSerp'); break;
    // Sitemap / Schema
    case 'runSitemapAudit':   _call('runSitemapAudit'); break;
    case 'clearSitemapAudit': _call('clearSitemapAudit'); break;
    case 'runSchemaValidation':_call('runSchemaValidation'); break;
    case 'clearSchemaValidation':_call('clearSchemaValidation'); break;
    // Keyword research
    case 'runKwResearch':     _call('runKwResearch'); break;
    case 'clearKwResearch':   _call('clearKwResearch'); break;
    // Bing
    case 'runBingOverview':   _call('runBingOverview'); break;
    case 'runBingInspect':    _call('runBingInspect'); break;
    case 'runBingSubmit':     _call('runBingSubmit'); break;
    case 'clearBing':         _call('clearBing'); break;
    // GSC
    case 'runGscOpps':        _call('runGscOpps'); break;
    case 'clearGscOpps':      _call('clearGscOpps'); break;
    case 'runGscPosition':    _call('runGscPosition'); break;
    case 'clearGscPosition':  _call('clearGscPosition'); break;
    case 'runGscCtr':         _call('runGscCtr'); break;
    case 'clearGscCtr':       _call('clearGscCtr'); break;
    case 'runGscCoverage':    _call('runGscCoverage'); break;
    case 'clearGscCoverage':  _call('clearGscCoverage'); break;
    case 'runGscSitemaps':    _call('runGscSitemaps'); break;
    case 'clearGscSitemaps':  _call('clearGscSitemaps'); break;
    // Performance
    case 'runPerfOpps':       _call('runPerfOpps'); break;
    case 'clearPerfOpps':     _call('clearPerfOpps'); break;
    // Diagnostics
    case 'runRobotsTester':   _call('runRobotsTester'); break;
    case 'clearRobotsTester': _call('clearRobotsTester'); break;
    case 'runHreflangValidator':_call('runHreflangValidator'); break;
    case 'clearHreflangValidator':_call('clearHreflangValidator'); break;
    case 'runLinkHealth':     _call('runLinkHealth'); break;
    case 'clearLinkHealth':   _call('clearLinkHealth'); break;
    case 'runCrawlIntel':     _call('runCrawlIntel'); break;
    case 'clearCrawlIntel':   _call('clearCrawlIntel'); break;
    // Generators
    case 'clearSchemaForm':   _call('clearSchemaForm'); break;
    case 'clearRobotsForm':   _call('clearRobotsForm'); break;
    case 'clearSitemapForm':  _call('clearSitemapForm'); break;
    case 'clearHreflangForm': _call('clearHreflangForm'); break;
    case 'clearMetaTagsForm': _call('clearMetaTagsForm'); break;
    case 'addHreflangRow':    _call('addHreflangRow'); break;
    case 'addRobotsRule':     _call('addRobotsRule'); break;
    case 'copyOutput':        _call('copyOutput', arg); break;
    case 'downloadOutput': {
      var parts = (arg2||'').split('|');
      _call('downloadOutput', arg, parts[0]||'', parts[1]||'');
      break;
    }
    // Settings / auth
    case 'saveSettings':      _call('saveSettings'); break;
    case 'saveProfile':       _call('saveProfile'); break;
    case 'deleteProfile':     _call('deleteProfile'); break;
    case 'changeAuthCredentials':_call('changeAuthCredentials'); break;
    case 'createUser':        _call('createUser'); break;
    case 'doLogout':          _call('doLogout'); break;
    case 'testNotify':        _call('testNotify', arg); break;
    case 'toggleNotif':       _call('toggleNotif', arg); break;
    // Cannibalisation
    case 'switchCannibalTab': _call('switchCannibalTab', arg); break;
    // IndexNow
    case 'runIndexNow':       _call('runIndexNow'); break;
    case 'clearIndexNow':     _call('clearIndexNow'); break;
    default:
      if (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
        console.warn('[delegation] unknown data-action:', action, el);
  }
});
"""


def main():
    html_path = ROOT / "app/templates/dashboard.html"
    js_path   = ROOT / "app/static/js/dashboard.js"
    base_path = ROOT / "app/templates/site/base.html"

    # Remove delegation handler if already appended (idempotent re-run)
    marker = "// --- S-NEW: Centralised click delegation"
    for path in (js_path,):
        txt = path.read_text(encoding="utf-8")
        if marker in txt:
            path.write_text(txt[:txt.index(marker)].rstrip() + "\n", encoding="utf-8")

    # Transform dashboard.html
    html_text = html_path.read_text(encoding="utf-8")
    # Restore any previously migrated onclick that we need to re-process
    # (run is idempotent: nothing to undo since data-action != onclick)
    new_html, failed_html = transform_html(html_text)
    if failed_html:
        sys.stderr.write("WARN: unparseable onclick values (left unchanged):\n")
        for v in sorted(set(failed_html)):
            sys.stderr.write(f"  {v!r}\n")
    html_path.write_text(new_html, encoding="utf-8")
    before = len(re.findall(r'onclick=', html_text))
    after  = len(re.findall(r'onclick=', new_html))
    print(f"dashboard.html: {before} onclick -> {after} remaining")

    # Transform base.html
    base_text = base_path.read_text(encoding="utf-8")
    new_base, failed_base = transform_html(base_text)
    base_path.write_text(new_base, encoding="utf-8")
    before_b = len(re.findall(r'onclick=', base_text))
    after_b  = len(re.findall(r'onclick=', new_base))
    print(f"base.html: {before_b} onclick -> {after_b} remaining")

    # Append delegation handler to dashboard.js
    js_text = js_path.read_text(encoding="utf-8")
    js_path.write_text(js_text + "\n" + DELEGATION_JS, encoding="utf-8")
    print("dashboard.js: delegation handler appended")
    print("Done.")


if __name__ == "__main__":
    main()

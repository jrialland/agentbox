export const STYLES = `
:root{
  --ink:#121812;--muted:#5a6658;--canvas:#f3f6f0;--surface:#ffffff;--raised:#e9eee5;
  --border:#c8d2c4;--phosphor:#087a43;--grid:rgba(8,122,67,.07);
  --crit:#b42318;--high:#a31c8c;--med:#9a5a00;--low:#007a99;--info:#5a6658;--unknown:#8e9c8e;
}
*{box-sizing:border-box}
@page{size:A4;margin:16mm}
html{background:#fff}
body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.55 "Inter",system-ui,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
h1,h2,h3{font-family:"Silkscreen",monospace;font-weight:400;letter-spacing:.02em;margin:0}
h1{font-size:30px;line-height:1.2}
h2{font-size:20px;margin-bottom:8px}
h3{font-size:15px;margin-bottom:6px}
p{margin:0 0 10px}
a{color:var(--phosphor);text-decoration:none}
.mono{font-family:"JetBrains Mono",ui-monospace,monospace}
.muted{color:var(--muted)}
.page{background:var(--surface);border:1px solid var(--border);padding:24px;margin:0 0 18px}
.page-break{break-before:page}
.cover{min-height:240mm;display:flex;flex-direction:column;justify-content:space-between;background-image:linear-gradient(to right,var(--grid) 1px,transparent 1px),linear-gradient(to bottom,var(--grid) 1px,transparent 1px);background-size:24px 24px}
.wordmark{font-family:"Silkscreen",monospace;font-size:22px;color:var(--phosphor)}
.classification{float:right;font-family:"JetBrains Mono",monospace;font-size:11px;letter-spacing:.12em;text-transform:uppercase;border:1px solid var(--border);padding:4px 8px}
.cover-title{margin-top:64px}
.cover-subtitle{font-size:18px;color:var(--muted);margin-top:8px}
.cover-meta{display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;font-size:12px;margin-top:24px}
.cover-meta div{border-top:1px solid var(--border);padding-top:6px}
.status{display:inline-block;margin-top:28px;padding:8px 14px;border:1px solid var(--phosphor);color:var(--phosphor);font-family:"JetBrains Mono",monospace;font-size:13px}
.status.clean{background:rgba(8,122,67,.08)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--border)}
th{font-family:"JetBrains Mono",monospace;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
thead{display:table-header-group}
tr{break-inside:avoid}
.kv{width:100%;font-size:12px}
.kv th{width:28%}
.badge{display:inline-block;padding:1px 6px;border-radius:2px;color:#fff;font-family:"JetBrains Mono",monospace;font-size:10px;text-transform:uppercase}
.badge-critical{background:var(--crit)}.badge-high{background:var(--high)}.badge-medium{background:var(--med)}.badge-low{background:var(--low)}.badge-info{background:var(--info)}.badge-unknown{background:var(--unknown)}
.card{border:1px solid var(--border);background:var(--surface);padding:16px}
.card h3{margin-bottom:12px}
.summary{display:grid;grid-template-columns:180px 1fr;gap:16px;align-items:center}
.donut{width:180px;height:180px}
.donut-total{font-family:"Silkscreen",monospace;font-size:24px;fill:var(--ink)}
.donut-label{font-family:"Inter",sans-serif;font-size:10px;fill:var(--muted)}
.legend{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.legend li{display:grid;grid-template-columns:10px 1fr 40px 44px;gap:8px;align-items:center;font-size:12px}
.legend-dot{width:10px;height:10px;border-radius:50%}
.legend-count,.legend-pct{font-family:"JetBrains Mono",monospace;text-align:right}
.banner{border:1px solid var(--med);background:rgba(154,90,0,.08);padding:10px 12px;margin:0 0 14px;font-size:12px}
.tool-block{border-top:2px solid var(--phosphor);padding-top:12px;margin-top:18px}
.strip{display:flex;height:8px;border:1px solid var(--border);margin:8px 0 10px;overflow:hidden;background:var(--raised)}
.strip-seg{display:block;height:100%}
.strip-empty{display:block;height:100%;width:100%;background:var(--phosphor);opacity:.35}
.tool-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:10px}
.stats{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:12px;margin-bottom:10px}
.stats b{font-family:"JetBrains Mono",monospace}
.detail{color:var(--muted);font-size:11px}
.footer{margin-top:18px;padding-top:8px;border-top:1px solid var(--border);font-family:"JetBrains Mono",monospace;font-size:10px;color:var(--muted);display:flex;justify-content:space-between;gap:12px}
.toc{columns:2;column-gap:24px;font-size:13px}
.toc a{display:block;padding:3px 0}
.clean{color:var(--phosphor)}
`;

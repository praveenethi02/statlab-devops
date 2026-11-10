'use strict';

const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
const paths = {
  home:'M3 10l9-7 9 7v10H3z M9 20v-7h6v7',
  data:'M4 4h16v16H4z M4 9h16 M9 4v16 M4 14h16',
  history:'M3 11a9 9 0 1 1 3 7 M3 4v7h7 M12 7v5l3 2',
  compare:'M5 20V10 M12 20V4 M19 20V7 M2 20h20',
  settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z',
  plus:'M12 5v14 M5 12h14', search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6',
  arrow:'M5 12h14 M14 7l5 5-5 5', file:'M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6',
  copy:'M9 9h12v12H9z M15 9V3H3v12h6', edit:'M4 16l12-12 4 4L8 20H4z M14 6l4 4',
  trash:'M3 6h18 M8 6V3h8v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7',
  logout:'M10 4H4v16h6 M10 12h11 M17 8l4 4-4 4', moon:'M20 15a9 9 0 1 1-11-11 7 7 0 0 0 11 11',
  upload:'M4 15v6h16v-6 M12 16V3 M7 8l5-5 5 5', download:'M4 15v6h16v-6 M12 3v13 M7 11l5 5 5-5',
  check:'M5 12l4 4L19 6', lock:'M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4',
  calculator:'M5 3h14v18H5z M8 6h8 M8 11h1 M15 11h1 M8 16h1 M15 16h1',
  clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l4 2', close:'M6 6l12 12 M6 18L18 6',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`;
const state = {user:null, csrf:'', datasets:[], analyses:[], metrics:{}, dataset:null, editor:null, calculation:null, saved:null, revision:null, settings:{}, precision:4, route:'', search:'', sort:'updated', renderId:0};
let toastTimer, previewTimer, previewSequence = 0;
try { document.documentElement.dataset.theme = localStorage.getItem('statlab-theme') || 'light'; } catch { /* Storage is optional. */ }

function toast(message, error = false) {
  const el = $('#toast'); el.textContent = message; el.classList.toggle('error', error); el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, 6500);
}

async function api(path, options = {}) {
  const method = options.method || 'GET';
  const headers = {};
  let body;
  if (method !== 'GET') headers['X-CSRF-Token'] = state.csrf;
  if (options.form) body = options.form;
  else if (options.data !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(options.data); }
  let response;
  try { response = await fetch(`/api/${path}`, {method, headers, body, credentials:'same-origin'}); }
  catch { throw new Error('Unable to connect to the server. Check your connection and try again.'); }
  const result = await response.json();
  if (result.csrf_token) state.csrf = result.csrf_token;
  if (!response.ok) {
    if (response.status === 401 && !['login','profile/password'].includes(path)) { state.user = null; location.hash = '#login'; }
    if (response.status === 403 && result.error?.includes('CSRF')) {
      const refreshed = await fetch('/api/me', {credentials:'same-origin'}).then(r => r.json());
      state.csrf = refreshed.csrf_token;
    }
    throw new Error(result.error || 'The request could not be completed.');
  }
  return result;
}

async function busy(button, work) {
  const original = button?.innerHTML;
  if (button) { button.disabled = true; button.innerHTML = 'Please wait…'; }
  try { await work(); }
  catch (error) {
    if ($('#modal').open) {
      const el = $('#modal .modal-error'); if (el) { el.textContent = error.message; el.hidden = false; } else toast(error.message, true);
    } else toast(error.message, true);
  }
  finally { if (button?.isConnected) { button.disabled = false; button.innerHTML = original; } }
}

const date = value => new Date(value).toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'});
const datetime = value => new Date(value).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'});
const fmt = value => {
  if (value === null || value === undefined) return 'Undefined';
  if (typeof value === 'number') {
    if (Number.isInteger(value) && Math.abs(value) < 1e10) return value.toLocaleString();
    if (Math.abs(value) >= 1e10 || (Math.abs(value) > 0 && Math.abs(value) < 10**(-state.precision))) return value.toExponential(state.precision);
    return value.toLocaleString(undefined, {maximumFractionDigits:state.precision});
  }
  if (Array.isArray(value)) return value.length ? value.map(fmt).join(', ') : 'None detected';
  if (typeof value === 'object') return Object.entries(value).map(([key,v]) => `${key}: ${fmt(v)}`).join(' · ');
  return String(value);
};

function shell(title, active, content) {
  const nav = [['dashboard','home','Overview'], ['datasets','data','My datasets'], ['analyses','history','Saved analyses'], ['compare','compare','Compare datasets'], ['profile','settings','Settings']];
  $('#app').innerHTML = `<aside class="sidebar"><a class="brand" href="#dashboard"><img src="/static/mark.svg" alt="">Stat<span>Lab<em>.</em></span></a>
    <div class="side-caption">YOUR WORKSPACE</div><nav class="nav-links" aria-label="Main navigation">${nav.map(([route, symbol, label]) => `<a href="#${route}" title="${label}" class="${active===route?'active':''}" ${active===route?'aria-current="page"':''}>${icon(symbol)}${label}${route==='datasets'?`<span class="count">${state.datasets.length}</span>`:''}</a>`).join('')}</nav>
    <div class="side-note">${icon('lock')}<p><strong>Your research, saved.</strong><br>Your datasets and analyses stay private in your account.</p></div>
    <div class="side-account"><div class="avatar">${escapeHTML(state.user.username.slice(0,2).toUpperCase())}</div><div><div class="account-name">${escapeHTML(state.user.username)}</div><small>Personal workspace</small></div><button data-action="logout" aria-label="Sign out" title="Sign out">${icon('logout')}</button></div></aside>
    <div class="workspace"><header class="topbar"><div class="breadcrumb">Workspace <span>/</span><strong>${escapeHTML(title)}</strong></div><div class="top-actions"><span><i class="dot"></i> Account storage connected</span><button class="icon-btn" data-action="theme" aria-label="Toggle light or dark theme" title="Toggle theme">${icon('moon')}</button><a href="#profile" class="avatar" aria-label="Profile">${escapeHTML(state.user.username.slice(0,2).toUpperCase())}</a><button class="icon-btn mobile-logout" data-action="logout" aria-label="Sign out" title="Sign out">${icon('logout')}</button></div></header>
    <main id="content" tabindex="-1">${content}<footer class="app-footer"><span>StatLab · A little clarity in every number.</span><span>Private datasets. Reproducible results.</span></footer></main></div>`;
  document.title = `${title} · StatLab`;
}

function pageHead(eyebrow, title, subtitle, buttons='') {
  return `<div class="page-head"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${buttons}</div></div>`;
}

function auth(signup = false) {
  const title = signup ? 'Create your workspace.' : 'Welcome back.';
  $('#app').innerHTML = `<main class="auth-screen" id="content"><section class="auth-art"><a class="brand" href="#login"><img src="/static/mark.svg" alt="">StatLab<em>.</em></a><div class="auth-intro"><p class="eyebrow">FROM DATA TO UNDERSTANDING</p><h1>Every number<br>has a <em>story.</em></h1><p>Find the patterns. Understand the uncertainty. Keep your research together in one thoughtful workspace.</p><div class="auth-chart" aria-hidden="true">${'<i></i>'.repeat(9)}</div><p>Explore your data. Save your insights.<br>Pick up exactly where you left off.</p></div><footer>BUILT FOR CURIOUS MINDS · STUDENTS, ENGINEERS & RESEARCHERS</footer></section>
    <section class="auth-form-side"><div class="auth-card"><p class="eyebrow">YOUR PERSONAL DATA LAB</p><h1>${title}</h1><p>${signup?'Start collecting data and discovering insights.':'Sign in to your statistical workspace.'}</p>
    <form id="${signup?'signup':'login'}Form">${signup?`<div class="field"><label for="username">Username</label><input id="username" name="username" autocomplete="username" pattern="[A-Za-z0-9_]{3,32}" minlength="3" maxlength="32" placeholder="Choose a username" required><small>3–32 letters, numbers, or underscores.</small></div><div class="field"><label for="email">Email address</label><input id="email" name="email" autocomplete="email" type="email" maxlength="254" placeholder="you@example.com" required></div>`:`<div class="field"><label for="identifier">Username or email</label><input id="identifier" name="identifier" autocomplete="username" maxlength="254" placeholder="Enter your username or email" required></div>`}
    <div class="field"><label for="password">Password</label><div class="password-row"><input id="password" name="password" type="password" autocomplete="${signup?'new':'current'}-password" ${signup?'minlength="8"':''} maxlength="128" placeholder="${signup?'At least 8 characters':'Enter your password'}" required><button type="button" data-action="show-password" aria-pressed="false">Show</button></div></div>
    ${signup?'<div class="field"><label for="confirmation">Confirm password</label><input id="confirmation" name="confirmation" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></div>':'<div class="options"><label class="check"><input name="remember" type="checkbox"> Remember me for 30 days</label></div>'}
    <button class="btn primary" type="submit">${signup?'Create account':'Sign in'} ${icon('arrow')}</button></form><p class="switch">${signup?'Already have an account? <a href="#login">Sign in</a>':'New to StatLab? <a href="#signup">Create an account</a>'}</p><p class="auth-note">${icon('lock')} Your data stays private in your account.</p></div></section></main>`;
  document.title = `${title} · StatLab`;
}

async function refreshLists() {
  const [datasets, analyses] = await Promise.all([api('datasets'), api('analyses')]);
  state.datasets = datasets.datasets; state.analyses = analyses.analyses;
}

function datasetCard(dataset) {
  return `<article class="dataset-card"><div class="card-top"><span class="file-icon">${icon('file')}</span><span class="badge">${dataset.kind==='interval'?'Grouped estimates':dataset.kind==='frequency'?'Frequency':'Numerical data'}</span></div><h3><a href="#dataset/${dataset.id}">${escapeHTML(dataset.name)}</a></h3><p class="description">${escapeHTML(dataset.description || 'Ready for your next insight.')}</p><div class="card-meta"><span>${dataset.observation_count.toLocaleString()} observations</span><span>${dataset.analysis_count} saved ${dataset.analysis_count===1?'analysis':'analyses'}</span></div><p class="date-created">Created ${date(dataset.created_at)} · Updated ${date(dataset.updated_at)}</p><div class="card-bottom"><a href="#analyze/${dataset.id}">Analyze dataset ${icon('arrow')}</a><div class="card-menu"><button class="icon-btn" data-action="rename-dataset" data-id="${dataset.id}" aria-label="Rename ${escapeHTML(dataset.name)}" title="Rename">${icon('edit')}</button><button class="icon-btn" data-action="duplicate-dataset" data-id="${dataset.id}" aria-label="Duplicate ${escapeHTML(dataset.name)}" title="Duplicate">${icon('copy')}</button><button class="icon-btn" data-action="delete-dataset" data-id="${dataset.id}" aria-label="Delete ${escapeHTML(dataset.name)}" title="Delete">${icon('trash')}</button></div></div></article>`;
}

function datasetGrid(limit) {
  let datasets = state.datasets.filter(d => `${d.name} ${d.description}`.toLowerCase().includes(state.search.toLowerCase()));
  datasets.sort((a,b) => state.sort==='name'?a.name.localeCompare(b.name):new Date(b[state.sort==='created'?'created_at':'updated_at'])-new Date(a[state.sort==='created'?'created_at':'updated_at']));
  if (limit) datasets = datasets.slice(0,limit);
  return datasets.length ? `<div class="dataset-grid">${datasets.map(datasetCard).join('')}</div>` : `<div class="empty"><span class="file-icon">${icon('data')}</span><h3>${state.search?'No matching datasets':'Your next discovery starts here.'}</h3><p>${state.search?'Try a different name or description.':'Create a dataset, paste observations, or import a CSV. Your work will be saved to your account.'}</p>${state.search?'':'<a href="#new" class="btn primary">'+icon('plus')+' Create your first dataset</a>'}</div>`;
}

function historyRow(analysis, full=false) {
  return `<div class="history-row"><div class="file-icon">${icon('calculator')}</div><div class="row-title"><a href="#analysis/${analysis.id}">${escapeHTML(analysis.name)}</a><small>${escapeHTML(analysis.dataset_name)} · ${analysis.summary.count} observations · ${datetime(analysis.created_at)}</small></div><span class="badge ${analysis.historical?'amber':'green'}">${analysis.historical?'Historical':'Current'} · v${analysis.dataset_revision}</span>${full?`<div class="actions"><button class="icon-btn" data-action="duplicate-analysis" data-id="${analysis.id}" title="Duplicate analysis" aria-label="Duplicate ${escapeHTML(analysis.name)}">${icon('copy')}</button><button class="icon-btn" data-action="delete-analysis" data-id="${analysis.id}" title="Delete analysis" aria-label="Delete ${escapeHTML(analysis.name)}">${icon('trash')}</button></div>`:''}</div>`;
}

function dashboard(datasetsOnly=false) {
  const total = state.datasets.reduce((sum,d) => sum+d.observation_count,0);
  const heading = datasetsOnly ? pageHead('YOUR DATA LIBRARY','My datasets','A home for every experiment, observation, and idea.',`<a href="#new" class="btn primary">${icon('plus')} New dataset</a>`) : pageHead('YOUR WORKSPACE, AT A GLANCE',`Hello, ${escapeHTML(state.user.username)} <span class="muted">.</span>`,'A fresh perspective on your data. What will you discover today?',`<a href="#new" class="btn primary">${icon('plus')} New dataset</a>`);
  const stats = `<div class="summary-grid"><div class="stat-card"><div class="stat-icon">${icon('data')}</div><div><small>Total datasets</small><div class="stat-number">${state.datasets.length}</div><div class="stat-foot">Saved in your workspace</div></div></div><div class="stat-card"><div class="stat-icon purple">${icon('calculator')}</div><div><small>Saved analyses</small><div class="stat-number">${state.analyses.length}</div><div class="stat-foot">Insights you can return to</div></div></div><div class="stat-card"><div class="stat-icon green">${icon('compare')}</div><div><small>Data observations</small><div class="stat-number">${total.toLocaleString()}</div><div class="stat-foot">Across all your datasets</div></div></div></div>`;
  const library = `<section class="panel"><div class="panel-head"><div><h2>${datasetsOnly?'Dataset library':'Your datasets'}</h2><p>Organize your data. Keep the context.</p></div>${datasetsOnly?'':'<a class="small" href="#datasets">View all '+icon('arrow')+'</a>'}</div><div class="toolbar"><div class="search">${icon('search')}<input id="datasetSearch" aria-label="Search datasets" placeholder="Search your datasets…" value="${escapeHTML(state.search)}"></div><select id="datasetSort" aria-label="Sort datasets"><option value="updated">Recently modified</option><option value="created">Recently created</option><option value="name">Name: A to Z</option></select></div><div id="datasetGrid">${datasetGrid(datasetsOnly?undefined:6)}</div></section>`;
  const bottom = `<div class="dashboard-bottom"><section class="panel"><div class="panel-head"><div><h2>Recent analyses</h2><p>Pick up where you left off.</p></div><a href="#analyses" class="small">View history ${icon('arrow')}</a></div>${state.analyses.length?state.analyses.slice(0,4).map(a=>historyRow(a)).join(''):'<div class="empty"><h3>Room for your first insight.</h3><p>Calculate statistics, then save an analysis to build your research history.</p></div>'}</section><aside class="panel help-card"><div class="help-symbol">Σ</div><h2>Big ideas start with small datasets.</h2><p>From a quick mean to a complete distribution, turn your observations into something you can understand.</p><a href="#new" class="btn">Explore a sample ${icon('arrow')}</a><p class="small">Try the “Experiment 01” reference dataset in the editor.</p></aside></div>`;
  shell(datasetsOnly?'My datasets':'Overview',datasetsOnly?'datasets':'dashboard',heading+stats+library+(datasetsOnly?'':bottom));
  $('#datasetSort').value = state.sort;
}

function editorView(dataset=null) {
  const editing = Boolean(dataset);
  const editor = state.editor;
  const modes = [['manual','Manual input'],['table','Data table'],['csv','CSV import'],['frequency','Value / frequency'],['interval','Class intervals']];
  const tabs = `<div class="tabs" role="group" aria-label="Input method">${modes.map(([id,label])=>`<button type="button" data-action="editor-mode" data-mode="${id}" class="${editor.mode===id?'active':''}" aria-pressed="${editor.mode===id}">${label}</button>`).join('')}</div>`;
  let input = '';
  if (editor.mode==='manual') input = `<div class="field"><label for="dataText">Numerical observations</label><textarea id="dataText" rows="9" maxlength="1000000" placeholder="10, 20, 30, 40, 50">${escapeHTML(editor.text)}</textarea><small>Separate numbers with commas, spaces, tabs, or new lines. Empty comma-delimited values are rejected.</small></div><button type="button" class="btn subtle" data-action="sample">${icon('calculator')} Load Experiment 01 sample</button>`;
  else {
    if (editor.mode==='csv') input += `<div class="upload-box">${icon('upload')}<h3 class="spacer">Bring your data with you.</h3><p>UTF-8 CSV · Up to 2 MB · 10,000 rows · 32 columns</p><input type="file" id="csvFile" accept=".csv,text/csv" aria-label="Choose CSV file"><div class="form-grid spacer"><label class="check"><input type="checkbox" id="csvHeader" checked> First row contains column names</label><select id="csvDelimiter" aria-label="CSV delimiter"><option value=",">Comma delimiter</option><option value=";">Semicolon delimiter</option><option value="tab">Tab delimiter</option></select></div><button type="button" class="btn primary spacer" data-action="import-csv">Preview CSV</button></div>`;
    if (editor.mode==='frequency') input += '<div class="notice">Exact value frequencies. Enter a numerical value and a nonnegative integer frequency. Total frequency must be 1–10,000.</div>';
    if (editor.mode==='interval') input += '<div class="notice">Class-interval estimates use midpoints. Enter ordered, nonoverlapping lower and upper bounds and integer frequencies. Results will be marked as estimates.</div>';
    input += `<div class="actions"><button type="button" class="btn" data-action="add-row">${icon('plus')} Add row</button>${['table','csv'].includes(editor.mode)?'<button type="button" class="btn" data-action="add-column">'+icon('plus')+' Add column</button>':''}<span class="small muted">Paste tab-separated cells directly from Excel.</span></div><div id="sheetContainer">${sheetHTML()}</div>`;
  }
  const content = pageHead('DATASET WORKSPACE',editing?'Edit dataset':'Create a new dataset','Give your data a name, a little context, and room to grow.',`<a href="#datasets" class="btn">Cancel</a>`) +
    `<form id="datasetForm"><div class="editor-layout"><section class="panel"><div class="form-grid"><div class="field"><label for="datasetName">Dataset name</label><input id="datasetName" maxlength="120" required placeholder="e.g. Experiment 01" value="${escapeHTML(editor.name)}"></div><div class="field"><label for="datasetDescription">Short description <span class="muted">(optional)</span></label><input id="datasetDescription" maxlength="2000" placeholder="What do these observations represent?" value="${escapeHTML(editor.description)}"></div></div>${tabs}${input}<div class="editor-status">${icon('lock')} ${editing?`Saved revision ${dataset.revision}. Data edits create a new revision.`:'Your dataset will be stored in your account when you save.'}</div><div class="actions spacer"><button class="btn primary" type="submit">${icon('check')} Save & analyze</button><button class="btn" type="submit" name="saveOnly" value="true">Save dataset</button></div></section><aside><section class="panel"><div class="panel-head"><div><h2>Live preview</h2><p>Updates as you edit. Not yet saved.</p></div></div><div class="field"><label for="previewColumn">Preview numerical column</label><select id="previewColumn">${editor.data.columns.map((c,i)=>`<option value="${i}">${escapeHTML(c)}</option>`).join('')}</select></div><div id="livePreview"><p class="small muted">Enter observations to preview the statistics.</p></div></section><section class="panel"><h3>A note on missing values</h3><p class="small muted spacer">Blank table cells stay missing. Analysis rejects missing selected values unless you explicitly choose to drop those rows.</p><p class="small muted">Sample and population measures are calculated and labeled separately.</p></section></aside></div></form>`;
  shell(editing?'Edit dataset':'New dataset','datasets',content);
  if (editor.text || editor.data.rows.some(r=>r.some(v=>v!==null))) schedulePreview();
}

function sheetHTML() {
  const editor=state.editor, start=editor.page*100, rows=editor.data.rows.slice(start,start+100);
  const pages=Math.max(1,Math.ceil(editor.data.rows.length/100));
  return `<div class="table-wrap"><table class="sheet" aria-label="Editable dataset"><thead><tr><th class="row-index">#</th>${editor.data.columns.map((c,j)=>`<th><input data-header="${j}" aria-label="Column ${j+1} name" value="${escapeHTML(c)}" maxlength="80"></th>`).join('')}<th></th></tr></thead><tbody>${rows.map((row,i)=>`<tr><td class="row-index">${start+i+1}</td>${row.map((v,j)=>`<td><input data-row="${start+i}" data-col="${j}" aria-label="Row ${start+i+1}, ${escapeHTML(editor.data.columns[j])}" value="${escapeHTML(v)}" maxlength="500"></td>`).join('')}<td><button type="button" class="icon-btn" data-action="remove-row" data-row="${start+i}" aria-label="Remove row ${start+i+1}">${icon('close')}</button></td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${editor.data.rows.length.toLocaleString()} rows · ${editor.data.columns.length} columns · Showing ${start+1}–${Math.min(start+100,editor.data.rows.length)}</span><div class="actions"><button type="button" class="btn" data-action="sheet-prev" ${editor.page===0?'disabled':''}>Previous</button><span>${editor.page+1} / ${pages}</span><button type="button" class="btn" data-action="sheet-next" ${editor.page>=pages-1?'disabled':''}>Next</button></div></div>`;
}

function editorPayload() {
  const editor = state.editor;
  const payload={name:editor.name, description:editor.description};
  if (editor.mode==='manual') payload.text=editor.text;
  else payload.data=editor.data;
  if (state.dataset) payload.revision=state.dataset.revision;
  return payload;
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer=setTimeout(async()=>{
    const sequence=++previewSequence;
    if (!state.editor || !$('#livePreview')) return;
    const payload=editorPayload(), column=Number($('#previewColumn')?.value || 0);
    try {
      const result=await api('statistics/preview',{method:'POST',data:{...payload,settings:{column,statistics:['count','mean','median','population_std','sample_std','minimum','maximum']}}});
      if (sequence!==previewSequence || !$('#livePreview')) return;
      $('#livePreview').innerHTML=`<div class="preview-stats">${Object.entries(result.calculation.results).map(([k,v])=>`<div><span>${escapeHTML(result.calculation.catalog[k].name)}</span><strong>${escapeHTML(fmt(v))}</strong></div>`).join('')}</div>${result.calculation.summary.estimated?'<span class="badge amber spacer">Class-midpoint estimates</span>':''}`;
    } catch(error) {
      if (sequence===previewSequence && $('#livePreview')) $('#livePreview').innerHTML=`<p class="small muted">${escapeHTML(error.message)}</p>`;
    }
  },450);
}

function analysisSetup() {
  const dataset=state.dataset, settings=state.settings;
  const sections={}; Object.entries(state.metrics).forEach(([key,metric])=>(sections[metric.section]??=[]).push([key,metric]));
  const content=pageHead('STATISTICAL ANALYSIS',escapeHTML(dataset.name),'Choose your numerical columns and the measures that answer your question.',`<a href="#dataset/${dataset.id}" class="btn">${icon('edit')} Edit data</a><a class="btn" href="/api/datasets/${dataset.id}/export">${icon('download')} Dataset CSV</a>`)+
    `<form id="calculateForm"><div class="calculation-grid"><section class="panel"><div class="panel-head"><div><h2>Calculation settings</h2><p>${dataset.observation_count.toLocaleString()} observations · Saved revision ${dataset.revision}</p></div><span class="badge">${dataset.kind==='interval'?'Estimates':'Exact data'}</span></div><div class="field"><label for="analysisColumn">Numerical column (X)</label><select id="analysisColumn">${dataset.columns.map((c,i)=>`<option value="${i}">${escapeHTML(c)}</option>`).join('')}</select></div><div class="field"><label for="missingPolicy">Missing selected values</label><select id="missingPolicy"><option value="reject">Reject — show a validation error</option><option value="drop">Drop — exclude affected rows explicitly</option></select></div><div class="field"><label for="percentiles">Percentiles</label><input id="percentiles" value="${escapeHTML((settings.percentiles || [5,25,50,75,95]).join(', '))}" required placeholder="5, 25, 50, 75, 95"><small>Positions from 0 to 100. Quartiles use linear interpolation (type 7).</small></div><details class="metric-section" ${settings.y_column!==undefined || settings.weights?'open':''}><summary>Paired & weighted analysis</summary><div class="field spacer"><label for="yColumn">Second numerical column (Y)</label><select id="yColumn" ${dataset.kind!=='raw'?'disabled':''}><option value="">None — univariate analysis</option>${dataset.columns.map((c,i)=>`<option value="${i}">${escapeHTML(c)}</option>`).join('')}</select><small>Choose a different column for Pearson, Spearman, and regression. Missing rows are dropped in pairs.</small></div><div class="field"><label for="weights">Observation weights</label><textarea id="weights" rows="3" ${dataset.kind!=='raw'?'disabled':''} placeholder="Optional: one nonnegative weight per source row">${escapeHTML((settings.weights||[]).join(', '))}</textarea><small>Positive total required. Include weights for any missing source rows.</small></div></details><div class="actions spacer"><button class="btn primary" type="submit">${icon('calculator')} Calculate statistics</button></div></section><section class="panel"><div class="panel-head"><div><h2>Select your statistics</h2><p>Calculated with explicit sample and population conventions.</p></div><button type="button" class="btn subtle" data-action="all-metrics">Select all</button></div>${Object.entries(sections).map(([section,metrics])=>`<details class="metric-section" open><summary>${section}<span>${metrics.length} measures</span></summary><div class="metric-options">${metrics.map(([key,metric])=>`<label class="check"><input type="checkbox" name="metric" value="${key}" ${!settings.statistics || settings.statistics.includes(key)?'checked':''}>${escapeHTML(metric.name)}</label>`).join('')}</div></details>`).join('')}</section></div></form>`;
  shell('Statistical analysis','datasets',content);
  $('#analysisColumn').value=String(settings.column || 0);
  $('#missingPolicy').value=settings.missing || 'reject';
  $('#yColumn').value=settings.y_column===undefined?'':String(settings.y_column);
}

function getSettings() {
  const percentiles=$('#percentiles').value.trim().split(/[,\s]+/).map(Number);
  if (percentiles.some(p=>!Number.isFinite(p) || p<0 || p>100)) throw new Error('Percentiles must be numbers between 0 and 100.');
  const settings={column:Number($('#analysisColumn').value),missing:$('#missingPolicy').value,percentiles,statistics:[...document.querySelectorAll('[name=metric]:checked')].map(el=>el.value)};
  if ($('#yColumn').value!=='') settings.y_column=Number($('#yColumn').value);
  if ($('#weights').value.trim()) {
    const tokens=$('#weights').value.trim().split(/[,\s]+/);
    if (tokens.some(t=>!t.trim() || !Number.isFinite(Number(t)))) throw new Error('Weights must be valid numbers.');
    settings.weights=tokens.map(Number);
  }
  return settings;
}

function parametersHTML(parameters) {
  return `<div class="parameters">${parameters.length?parameters.map(p=>`<article class="parameter"><div class="parameter-top"><h3>${escapeHTML(p.name)}</h3><span class="badge">Manual ${p.analysis_id?'· This analysis':'· Dataset'}</span></div><div class="parameter-value">${escapeHTML(fmt(p.value))} <small>${escapeHTML(p.unit)}</small></div>${p.formula?`<p class="small muted">${escapeHTML(p.formula)}</p>`:''}${p.description?`<p class="small muted">${escapeHTML(p.description)}</p>`:''}<div class="parameter-top"><small>Updated ${date(p.updated_at)}</small><div class="actions"><button class="icon-btn" data-action="edit-parameter" data-id="${p.id}" aria-label="Edit ${escapeHTML(p.name)}">${icon('edit')}</button><button class="icon-btn" data-action="delete-parameter" data-id="${p.id}" aria-label="Delete ${escapeHTML(p.name)}">${icon('trash')}</button></div></div></article>`).join(''):'<p class="small muted">Add experimental errors, theoretical values, units, or your own findings.</p>'}</div>`;
}

function resultsView() {
  const calculation=state.calculation, saved=state.saved, dataset=state.dataset;
  const title=saved?saved.name:dataset.name;
  const sourceName=saved?saved.snapshot.name:dataset.name;
  const historical=saved?.historical;
  const header=pageHead('YOUR DATA, EXPLAINED',escapeHTML(title),`${escapeHTML(sourceName)} · ${calculation.summary.count} observations · Revision ${state.revision}${saved?' · '+datetime(saved.created_at):' · Calculated preview'}`,
    `${saved?`<a class="btn" href="/api/analyses/${saved.id}/export?format=pdf">${icon('download')} PDF report</a><a class="btn" href="/api/analyses/${saved.id}/export">Statistics CSV</a>`:'<button class="btn primary" data-action="save-analysis">'+icon('check')+' Save analysis</button>'}<button class="btn" data-action="print">Print</button><a class="btn" href="#analyze/${dataset.id}">${icon('calculator')} New calculation</a>`);
  const notice=historical?`<div class="notice">Historical analysis · This snapshot uses revision ${saved.dataset_revision}; your dataset is now revision ${saved.current_revision}. The saved results remain reproducible.</div>`:(!saved?'<div class="notice">These results are calculated from your saved dataset. Save this analysis to keep a dated snapshot and enable report exports.</div>':'');
  const estimates=calculation.summary.estimated?'<div class="notice">Class-interval estimates · All statistics use class midpoints rather than the original observations.</div>':'';
  const highlights=['mean','median','population_std','sample_std'].filter(k=>k in calculation.results);
  const cards=`<div class="results-top">${highlights.map(k=>`<div class="result-card"><small>${escapeHTML(calculation.catalog[k].name)}</small><div class="result-value" data-result="${k}">${escapeHTML(fmt(calculation.results[k]))}</div><div class="formula">${escapeHTML(calculation.catalog[k].formula)}</div></div>`).join('')}</div>`;
  const sections={}; Object.entries(calculation.results).forEach(([key,value])=>(sections[calculation.catalog[key].section]??=[]).push([key,value]));
  const table=Object.entries(sections).map(([section,metrics])=>`<section class="result-section"><div class="result-section-head"><h2>${section}</h2><span class="badge">Calculated</span></div><table class="result-table"><thead><tr><th>Parameter / formula</th><th>Value</th><th class="no-print">Copy</th></tr></thead><tbody>${metrics.map(([key,value])=>{
    const metric=calculation.catalog[key];
    const large=(Array.isArray(value) && value.length>20) || (key==='frequency');
    const detail=large?`<details><summary>${Array.isArray(value)?value.length:'Multiple'} entries · View values</summary><span>${escapeHTML(fmt(value))}</span></details>`:escapeHTML(fmt(value));
    return `<tr><td>${escapeHTML(metric.name)}<span class="formula">${escapeHTML(metric.formula)}</span><small>${escapeHTML(calculation.issues[key] || metric.description)}</small></td><td class="value" data-result="${key}">${detail}</td><td class="no-print"><button class="icon-btn" data-action="copy-result" data-key="${key}" aria-label="Copy ${escapeHTML(metric.name)}">${icon('copy')}</button></td></tr>`;
  }).join('')}</tbody></table></section>`).join('');
  const parameters=saved?saved.parameters:dataset.parameters.filter(p=>p.analysis_id===null);
  const side=`<aside class="result-side"><section class="panel"><div class="panel-head"><div><h2>A visual perspective</h2><p>${escapeHTML(calculation.summary.column)} · ${calculation.summary.count} observations</p></div></div><div class="chart-toolbar no-print"><select id="chartType" aria-label="Chart type"><option value="histogram">Histogram</option><option value="box">Box plot</option><option value="line">Line chart</option><option value="bar">Observation bar chart</option><option value="frequency">Frequency distribution</option><option value="cumulative">Cumulative frequency</option>${calculation.chart_data.y.length?'<option value="scatter">Paired scatter plot</option>':''}</select><button class="icon-btn" data-action="export-chart" aria-label="Export chart as PNG" title="Export PNG">${icon('download')}</button></div><div id="resultChart" class="chart" role="img" aria-label="Interactive distribution chart"></div></section><section class="panel"><div class="panel-head"><div><h2>Your custom parameters</h2><p>Manually entered. Preserved on recalculation.</p></div><button class="icon-btn" data-action="add-parameter" aria-label="Add custom parameter" title="Add custom parameter">${icon('plus')}</button></div><div id="parameterList">${parametersHTML(parameters)}</div></section><section class="panel"><h2>Calculation notes</h2><div class="methodology"><p><strong>${calculation.summary.excluded_rows} missing rows excluded.</strong> Policy: ${escapeHTML(calculation.settings.missing || 'reject')}.</p><p>Algorithm ${escapeHTML(calculation.algorithm_version)} · Revision ${state.revision}</p>${Object.entries(calculation.conventions).map(([key,value])=>`<p><strong>${escapeHTML(key)}</strong><br>${escapeHTML(value)}</p>`).join('')}</div></section></aside>`;
  shell(saved?'Saved analysis':'Analysis results','analyses',header+notice+estimates+cards+`<div class="result-columns"><section class="panel"><div class="panel-head"><div><h2>Statistical results</h2><p>Every measure, with its method and meaning.</p></div><select id="precision" aria-label="Result decimal precision"><option value="4">4 decimals</option><option value="6">6 decimals</option><option value="8">8 decimals</option></select></div>${table}</section>${side}</div>`);
  $('#precision').value=String(state.precision);
  drawChart();
}

function plotLayout(title, xTitle, yTitle) {
  const dark=document.documentElement.dataset.theme==='dark';
  return {title:{text:title,font:{size:12}},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Segoe UI, Arial, sans-serif',size:10,color:dark?'#a6b8d4':'#738095'},margin:{l:45,r:12,t:43,b:48},xaxis:{title:{text:xTitle},gridcolor:dark?'#293a51':'#eef1f6',zeroline:false},yaxis:{title:{text:yTitle},gridcolor:dark?'#293a51':'#eef1f6',zeroline:false},showlegend:false,hoverlabel:{font:{size:11}}};
}

function drawChart() {
  const el=$('#resultChart'); if (!el || !window.Plotly) return;
  const calculation=state.calculation, data=calculation.chart_data, type=$('#chartType').value;
  const values=data.values, x=data.frequency.map(f=>f.value), counts=data.frequency.map(f=>f.frequency);
  let trace, title, xTitle=calculation.summary.column, yTitle='Frequency';
  const common={marker:{color:'#5276e5'},line:{color:'#5276e5',width:2}};
  if(type==='histogram'){trace={x:values,type:'histogram',...common};title='Distribution of observations';}
  if(type==='box'){
    const [min,q1,median,q3,max]=data.five_number_summary, iqr=q3-q1;
    const ordered=values.slice().sort((a,b)=>a-b);
    const inside=ordered.filter(v=>v>=q1-1.5*iqr && v<=q3+1.5*iqr);
    trace={type:'box',q1:[q1],median:[median],q3:[q3],lowerfence:[inside[0]??min],upperfence:[inside.at(-1)??max],y:[values],boxpoints:'outliers',...common,name:xTitle};title='Five-number distribution';yTitle=xTitle;xTitle='Selected column';
  }
  if(type==='frequency'){trace={x,y:counts,type:'bar',...common};title='Value frequencies';}
  if(type==='cumulative'){trace={x,y:data.frequency.map(f=>f.cumulative),type:'scatter',mode:'lines+markers',...common};title='Cumulative frequency curve';yTitle='Cumulative count';}
  if(type==='line' || type==='bar'){trace={x:values.map((_,i)=>i+1),y:values,type:type==='bar'?'bar':'scatter',mode:'lines+markers',...common};title='Observations in source order';xTitle='Observation';yTitle=calculation.summary.column;}
  if(type==='scatter'){trace={x:values,y:data.y,type:'scatter',mode:'markers',...common};title='Paired observations';yTitle=calculation.summary.y_column;}
  const traces=[trace];
  if(type==='scatter' && calculation.results.regression){const regression=calculation.results.regression;const edges=[Math.min(...values),Math.max(...values)];traces.push({x:edges,y:edges.map(v=>regression.intercept+regression.slope*v),mode:'lines',type:'scatter',line:{color:'#32a590',width:2},name:'OLS fit'});}
  Plotly.react(el,traces,plotLayout(title,xTitle,yTitle),{responsive:true,displayModeBar:false}).catch(error=>toast('Chart could not be rendered: '+error.message,true));
}

function analysesView() {
  shell('Saved analyses','analyses',pageHead('YOUR RESEARCH HISTORY','Saved analyses','A reproducible record of your calculations, with every revision in context.',`<a class="btn primary" href="#datasets">${icon('calculator')} Analyze a dataset</a>`)+`<section class="panel"><div class="panel-head"><div><h2>Analysis history</h2><p>${state.analyses.length} saved analyses · Calculated results remain unchanged when datasets are edited.</p></div></div>${state.analyses.length?state.analyses.map(a=>historyRow(a,true)).join(''):'<div class="empty"><span class="file-icon">'+icon('history')+'</span><h3>Your research history starts here.</h3><p>Create a dataset and save your first statistical analysis.</p><a class="btn" href="#datasets">Open your datasets</a></div>'}</section>`);
}

function compareView() {
  shell('Compare datasets','compare',pageHead('A SIDE-BY-SIDE PERSPECTIVE','Compare your datasets','Look for differences in location, spread, and distribution.')+`<section class="panel"><h2>Choose two to six datasets</h2><p class="small muted spacer">Select a numerical column for each. Missing values are rejected to keep the comparison explicit.</p><form id="compareForm"><div class="compare-list">${state.datasets.map(d=>`<div class="compare-item"><label class="check"><input type="checkbox" name="compare" value="${d.id}">${escapeHTML(d.name)}</label><select data-compare-column="${d.id}" aria-label="Column for ${escapeHTML(d.name)}">${d.columns.map((c,i)=>`<option value="${i}">${escapeHTML(c)}</option>`).join('')}</select></div>`).join('')}</div><button class="btn primary" ${state.datasets.length<2?'disabled':''} type="submit">${icon('compare')} Compare datasets</button>${state.datasets.length<2?'<p class="small muted spacer">Create at least two datasets to compare them.</p>':''}</form></section><div id="comparisonResults"></div>`);
}

function comparisonResults(comparisons) {
  const keys=['count','mean','median','population_variance','sample_variance','population_std','sample_std','q1','q3','iqr','skewness'];
  $('#comparisonResults').innerHTML=`<section class="panel"><div class="panel-head"><h2>Comparison results</h2><span class="small muted">${comparisons.length} datasets · Current saved revisions</span></div><div class="table-wrap"><table><thead><tr><th>Measure</th>${comparisons.map(c=>`<th>${escapeHTML(c.name)}<br><small>${escapeHTML(c.calculation.summary.column)} · v${c.revision}${c.calculation.summary.estimated?' · Estimated':''}</small></th>`).join('')}</tr></thead><tbody>${keys.map(k=>`<tr><td>${escapeHTML(comparisons[0].calculation.catalog[k].name)}</td>${comparisons.map(c=>`<td>${escapeHTML(fmt(c.calculation.results[k]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div id="compareChart" class="compare-chart" role="img" aria-label="Dataset distribution comparison"></div></section>`;
  const traces=comparisons.map(c=>{const f=c.calculation.chart_data.five_number_summary;return {type:'box',q1:[f[1]],median:[f[2]],q3:[f[3]],lowerfence:[f[0]],upperfence:[f[4]],name:c.name};});
  Plotly.newPlot($('#compareChart'),traces,plotLayout('Quartiles and full range by dataset','Dataset','Value'),{responsive:true,displayModeBar:false});
}

function profileView() {
  shell('Profile & settings','profile',pageHead('YOUR ACCOUNT','Profile & settings','A few details that make this workspace yours.')+`<section class="panel settings-card"><h2>Account details</h2><dl class="profile-dl"><dt>Username</dt><dd>${escapeHTML(state.user.username)}</dd><dt>Email address</dt><dd>${escapeHTML(state.user.email)}</dd><dt>Workspace storage</dt><dd>Your datasets and analyses are stored on the server and available from other devices after sign-in.</dd></dl><button class="btn" data-action="theme">${icon('moon')} Switch light / dark theme</button></section><section class="panel settings-card"><h2>Change password</h2><p class="small muted spacer">Changing your password signs out every active session, including this one.</p><form id="passwordForm"><div class="field"><label for="currentPassword">Current password</label><input id="currentPassword" name="current_password" type="password" autocomplete="current-password" maxlength="128" required></div><div class="field"><label for="newPassword">New password</label><input id="newPassword" name="new_password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></div><div class="field"><label for="confirmNewPassword">Confirm new password</label><input id="confirmNewPassword" type="password" autocomplete="new-password" minlength="8" maxlength="128" required></div><button type="submit" class="btn primary">Update password</button></form></section>`);
}

async function route() {
  const id=++state.renderId;
  clearTimeout(previewTimer); previewSequence++;
  const hash=location.hash.slice(1) || (state.user?'dashboard':'login');
  state.route=hash;
  if (!state.user) {auth(hash==='signup');return;}
  if (hash==='login' || hash==='signup') {location.hash='#dashboard';return;}
  try {
    if (['dashboard','datasets','analyses','compare'].includes(hash)) {
      state.editor=null; await refreshLists(); if(id!==state.renderId)return;
      if(hash==='dashboard' || hash==='datasets')dashboard(hash==='datasets');
      if(hash==='analyses')analysesView();
      if(hash==='compare')compareView();
    } else if(hash==='new') {
      state.dataset=null;state.saved=null;state.settings={};
      state.editor={name:'',description:'',mode:'manual',text:'',data:{kind:'raw',columns:['Value'],rows:[[null]]},page:0};
      editorView();
    } else if(hash.startsWith('dataset/') || hash.startsWith('analyze/')) {
      const result=await api(`datasets/${Number(hash.split('/')[1])}`);if(id!==state.renderId)return;
      const previousId=state.dataset?.id; state.dataset=result.dataset;state.saved=null;state.calculation=null;
      if(previousId!==state.dataset.id)state.settings={};
      if(hash.startsWith('dataset/')) {
        const dataset=state.dataset;
        state.editor={name:dataset.name,description:dataset.description,mode:dataset.kind==='raw'?'table':dataset.kind,text:dataset.data.rows.map(r=>r[0]??'').join('\n'),data:structuredClone(dataset.data),page:0};
        editorView(dataset);
      } else {state.editor=null;analysisSetup();}
    } else if(hash.startsWith('analysis/')) {
      const result=await api(`analyses/${Number(hash.split('/')[1])}`);if(id!==state.renderId)return;
      state.saved=result.analysis;state.calculation=result.analysis.calculation;state.settings=state.calculation.settings;
      state.revision=result.analysis.dataset_revision;
      state.dataset=(await api(`datasets/${result.analysis.dataset_id}`)).dataset;state.editor=null;
      if(id!==state.renderId)return; resultsView();
    } else if(hash==='results' && state.calculation) {state.editor=null;resultsView();}
    else if(hash==='profile'){state.editor=null;profileView();}
    else {location.hash='#dashboard';}
  } catch(error) {
    if(id===state.renderId && state.user)shell('Unable to open page','datasets',`<div class="panel"><h1>We couldn’t open this page.</h1><p class="muted">${escapeHTML(error.message)}</p><a class="btn" href="#dashboard">Return to overview</a></div>`);
    toast(error.message,true);
  }
}

function openModal(title, fields, submitLabel, onSubmit) {
  const modal=$('#modal');
  modal.innerHTML=`<h2 id="modalTitle">${escapeHTML(title)}</h2><div class="notice error modal-error" role="alert" hidden></div><form id="modalForm">${fields}<div class="actions"><button type="button" class="btn" data-action="close-modal">Cancel</button><button class="btn primary" type="submit">${submitLabel}</button></div></form>`;
  $('#modalForm').addEventListener('submit',event=>{event.preventDefault();busy(event.submitter,async()=>{await onSubmit(new FormData(event.target));modal.close();});});
  modal.showModal();
}

function parameterModal(parameter=null) {
  const saved=state.saved;
  const fields=`<div class="field"><label for="parameterName">Parameter name</label><input id="parameterName" name="name" value="${escapeHTML(parameter?.name || '')}" maxlength="120" required placeholder="e.g. Experimental Error"></div><div class="form-grid"><div class="field"><label for="parameterValue">Value</label><input id="parameterValue" name="value" value="${escapeHTML(parameter?.value ?? '')}" maxlength="1000" required placeholder="2.5 or a text value"></div><div class="field"><label for="parameterUnit">Unit <span class="muted">(optional)</span></label><input id="parameterUnit" name="unit" maxlength="40" value="${escapeHTML(parameter?.unit || '')}" placeholder="%"></div></div><div class="field"><label for="parameterType">Value type</label><select id="parameterType" name="type"><option value="number" ${typeof parameter?.value==='string'?'':'selected'}>Numerical</option><option value="text" ${typeof parameter?.value==='string'?'selected':''}>Text</option></select></div><div class="field"><label for="parameterScope">Association</label><select id="parameterScope" name="scope"><option value="dataset">This dataset (shared across analyses)</option>${saved?`<option value="${saved.id}" ${parameter?.analysis_id===saved.id?'selected':''}>Only this saved analysis</option>`:parameter?.analysis_id?`<option value="${parameter.analysis_id}" selected>Existing analysis association</option>`:''}</select></div><div class="field"><label for="parameterFormula">Formula <span class="muted">(optional)</span></label><input id="parameterFormula" name="formula" maxlength="500" value="${escapeHTML(parameter?.formula || '')}"></div><div class="field"><label for="parameterDescription">Description <span class="muted">(optional)</span></label><textarea id="parameterDescription" name="description" maxlength="2000" rows="2">${escapeHTML(parameter?.description || '')}</textarea></div>`;
  openModal(parameter?'Edit custom parameter':'Add custom parameter',fields,'Save parameter',async form=>{
    let value=form.get('value');
    if(form.get('type')==='number') {value=Number(value);if(!Number.isFinite(value))throw new Error('Enter a finite numerical value.');}
    const payload={name:form.get('name'),value,unit:form.get('unit'),formula:form.get('formula'),description:form.get('description'),analysis_id:form.get('scope')==='dataset'?null:Number(form.get('scope'))};
    await api(parameter?`parameters/${parameter.id}`:`datasets/${state.dataset.id}/parameters`,{method:parameter?'PUT':'POST',data:payload});
    await refreshParameters();toast('Custom parameter saved.');
  });
}

async function refreshParameters() {
  state.dataset=(await api(`datasets/${state.dataset.id}`)).dataset;
  if(state.saved)state.saved=(await api(`analyses/${state.saved.id}`)).analysis;
  $('#parameterList').innerHTML=parametersHTML(state.saved?state.saved.parameters:state.dataset.parameters.filter(p=>p.analysis_id===null));
}

const actions = {
  'theme':async()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=next;try{localStorage.setItem('statlab-theme',next);}catch{/* Optional preference. */}if($('#resultChart'))drawChart();},
  'logout':async()=>{await api('logout',{method:'POST',data:{}});state.user=null;state.datasets=[];state.analyses=[];state.editor=null;state.calculation=null;state.saved=null;location.hash='#login';toast('You have signed out.');},
  'show-password':async button=>{const showing=$('#password').type==='password';$('#password').type=showing?'text':'password';if($('#confirmation'))$('#confirmation').type=showing?'text':'password';button.textContent=showing?'Hide':'Show';button.setAttribute('aria-pressed',String(showing));},
  'editor-mode':async button=>{
    const editor=state.editor, next=button.dataset.mode;if(next===editor.mode)return;
    const kind=['frequency','interval'].includes(next)?next:'raw';
    if(kind!==editor.data.kind){
      if(editor.data.rows.some(r=>r.some(v=>v!==null)) && !confirm('Switching data format starts a new input table. Continue?'))return;
      editor.data={kind,columns:kind==='frequency'?['Value','Frequency']:kind==='interval'?['Lower bound','Upper bound','Frequency']:['Value'],rows:[Array(kind==='frequency'?2:kind==='interval'?3:1).fill(null)]};editor.text='';editor.page=0;
    }
    if(next==='manual') {
      if(editor.data.columns.length>1 && !confirm('Manual input uses the first column only. Continue?'))return;
      editor.text=editor.data.rows.map(r=>r[0]??'').join('\n');
    } else if(editor.mode==='manual' && editor.text.trim()) {
      const values=editor.text.trim().split(/[,\s]+/);editor.data={kind:'raw',columns:['Value'],rows:values.map(v=>[v])};
    }
    editor.mode=next;editorView(state.dataset);
  },
  'sample':async()=>{state.editor.text='10, 20, 30, 40, 50';if(!state.editor.name)state.editor.name='Experiment 01';if(!state.editor.description)state.editor.description='Reference dataset for an experimental analysis.';editorView(state.dataset);},
  'add-row':async()=>{const editor=state.editor;if(editor.data.rows.length>=10000)throw new Error('The row limit is 10,000.');editor.data.rows.push(Array(editor.data.columns.length).fill(null));editor.page=Math.floor((editor.data.rows.length-1)/100);$('#sheetContainer').innerHTML=sheetHTML();schedulePreview();},
  'remove-row':async button=>{const editor=state.editor;editor.data.rows.splice(Number(button.dataset.row),1);if(!editor.data.rows.length)editor.data.rows.push(Array(editor.data.columns.length).fill(null));editor.page=Math.min(editor.page,Math.floor((editor.data.rows.length-1)/100));$('#sheetContainer').innerHTML=sheetHTML();schedulePreview();},
  'add-column':async()=>{const editor=state.editor;if(editor.data.columns.length>=32)throw new Error('The column limit is 32.');let index=editor.data.columns.length+1;while(editor.data.columns.includes(`Column ${index}`))index++;editor.data.columns.push(`Column ${index}`);editor.data.rows.forEach(r=>r.push(null));editorView(state.dataset);},
  'sheet-prev':async()=>{state.editor.page--;$('#sheetContainer').innerHTML=sheetHTML();},
  'sheet-next':async()=>{state.editor.page++;$('#sheetContainer').innerHTML=sheetHTML();},
  'import-csv':async()=>{
    const file=$('#csvFile').files[0];if(!file)throw new Error('Choose a CSV file first.');if(file.size>2*1024*1024)throw new Error('CSV files must be at most 2 MB.');
    const form=new FormData();form.append('file',file);form.append('header',String($('#csvHeader').checked));form.append('delimiter',$('#csvDelimiter').value==='tab'?'\t':$('#csvDelimiter').value);
    const result=await api('import/csv',{method:'POST',form});state.editor.data=result.data;state.editor.page=0;if(!state.editor.name)state.editor.name=file.name.replace(/\.csv$/i,'');state.editor.mode='table';editorView(state.dataset);toast(`Imported ${result.row_count.toLocaleString()} rows. Review and correct cells before saving.`);
  },
  'all-metrics':async()=>{document.querySelectorAll('[name=metric]').forEach(el=>el.checked=true);},
  'rename-dataset':async button=>{const dataset=(await api(`datasets/${button.dataset.id}`)).dataset;openModal('Rename dataset',`<div class="field"><label for="renameName">Dataset name</label><input id="renameName" name="name" value="${escapeHTML(dataset.name)}" maxlength="120" required></div>`,'Save name',async form=>{await api(`datasets/${dataset.id}`,{method:'PUT',data:{name:form.get('name'),description:dataset.description,data:dataset.data,revision:dataset.revision}});await route();toast('Dataset renamed.');});},
  'duplicate-dataset':async button=>{await api(`datasets/${button.dataset.id}/duplicate`,{method:'POST',data:{}});await route();toast('Dataset duplicated, including its shared custom parameters.');},
  'delete-dataset':async button=>{if(!confirm('Delete this dataset, all its saved analyses, and custom parameters? This cannot be undone.'))return;await api(`datasets/${button.dataset.id}`,{method:'DELETE'});await route();toast('Dataset deleted.');},
  'duplicate-analysis':async button=>{await api(`analyses/${button.dataset.id}/duplicate`,{method:'POST',data:{}});await route();toast('Analysis snapshot duplicated.');},
  'delete-analysis':async button=>{if(!confirm('Delete this saved analysis? The dataset and custom parameters will be kept.'))return;await api(`analyses/${button.dataset.id}`,{method:'DELETE'});await route();toast('Analysis deleted.');},
  'save-analysis':async()=>{openModal('Save your analysis',`<div class="field"><label for="analysisName">Analysis name</label><input id="analysisName" name="name" value="${escapeHTML(state.dataset.name+' · Statistical analysis')}" maxlength="120" required><small>Results and the dataset revision are saved as a reproducible snapshot.</small></div>`,'Save analysis',async form=>{const result=await api('analyses',{method:'POST',data:{name:form.get('name'),dataset_id:state.dataset.id,dataset_revision:state.revision,settings:state.settings}});location.hash=`#analysis/${result.analysis.id}`;toast('Analysis saved to your research history.');});},
  'add-parameter':async()=>parameterModal(),
  'edit-parameter':async button=>{const parameters=state.saved?state.saved.parameters:state.dataset.parameters;parameterModal(parameters.find(p=>p.id===Number(button.dataset.id)));},
  'delete-parameter':async button=>{if(!confirm('Delete this manually entered parameter?'))return;await api(`parameters/${button.dataset.id}`,{method:'DELETE'});await refreshParameters();toast('Custom parameter deleted.');},
  'copy-result':async button=>{const value=state.calculation.results[button.dataset.key];const text=value===null?'Undefined':typeof value==='object'?JSON.stringify(value):String(value);try{await navigator.clipboard.writeText(text);toast('Result copied.');}catch{openModal('Copy result',`<div class="field"><label for="copyText">Select and copy this value</label><textarea id="copyText" rows="4" readonly>${escapeHTML(text)}</textarea></div>`,'Close',async()=>{});$('#copyText').select();}},
  'export-chart':async()=>{await Plotly.downloadImage($('#resultChart'),{format:'png',width:1200,height:700,filename:'statlab-chart'});},
  'print':async()=>window.print(),
  'close-modal':async()=>$('#modal').close(),
};

document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action]');if(!button || button.disabled)return;
  const action=actions[button.dataset.action];if(!action)return;
  event.preventDefault();
  if(['show-password','theme','close-modal','editor-mode','sample','all-metrics','sheet-prev','sheet-next','print'].includes(button.dataset.action))Promise.resolve(action(button)).catch(error=>toast(error.message,true));
  else busy(button,()=>action(button));
});

document.addEventListener('input',event=>{
  const target=event.target;
  if(target.id==='datasetSearch'){state.search=target.value;$('#datasetGrid').innerHTML=datasetGrid(state.route==='dashboard'?6:undefined);}
  if(!state.editor)return;
  if(target.id==='datasetName')state.editor.name=target.value;
  if(target.id==='datasetDescription')state.editor.description=target.value;
  if(target.id==='dataText'){state.editor.text=target.value;schedulePreview();}
  if(target.dataset.row!==undefined && target.dataset.col!==undefined){state.editor.data.rows[Number(target.dataset.row)][Number(target.dataset.col)]=target.value.trim() || null;schedulePreview();}
  if(target.dataset.header!==undefined){state.editor.data.columns[Number(target.dataset.header)]=target.value;schedulePreview();}
});

document.addEventListener('change',event=>{
  if(event.target.id==='datasetSort'){state.sort=event.target.value;$('#datasetGrid').innerHTML=datasetGrid(state.route==='dashboard'?6:undefined);}
  if(event.target.id==='previewColumn')schedulePreview();
  if(event.target.id==='chartType')drawChart();
  if(event.target.id==='precision'){state.precision=Number(event.target.value);resultsView();}
});

document.addEventListener('paste',event=>{
  const target=event.target;if(!state.editor || target.dataset.row===undefined)return;
  const text=event.clipboardData.getData('text');if(!/[\t\r\n]/.test(text))return;
  event.preventDefault();
  const pasted=text.replace(/\r/g,'').replace(/\n$/,'').split('\n').map(row=>row.split('\t'));
  const rowStart=Number(target.dataset.row), colStart=Number(target.dataset.col), cols=Math.max(...pasted.map(r=>r.length))+colStart;
  if(rowStart+pasted.length>10000 || cols>32 || (rowStart+pasted.length)*cols>100000){toast('Paste exceeds 10,000 rows, 32 columns, or 100,000 cells.',true);return;}
  const data=state.editor.data;
  if(data.kind!=='raw' && cols>data.columns.length){toast('Grouped data must match its existing columns.',true);return;}
  while(data.columns.length<cols){let i=data.columns.length+1;while(data.columns.includes(`Column ${i}`))i++;data.columns.push(`Column ${i}`);data.rows.forEach(r=>r.push(null));}
  while(data.rows.length<rowStart+pasted.length)data.rows.push(Array(data.columns.length).fill(null));
  pasted.forEach((row,i)=>row.forEach((v,j)=>data.rows[rowStart+i][colStart+j]=v.trim() || null));
  $('#sheetContainer').innerHTML=sheetHTML();schedulePreview();toast(`Pasted ${pasted.length} rows.`);
});

document.addEventListener('submit',event=>{
  const form=event.target;
  if(form.id==='modalForm')return;
  event.preventDefault();
  busy(event.submitter,async()=>{
    if(form.id==='signupForm'){
      if($('#password').value!==$('#confirmation').value)throw new Error('Passwords do not match.');
      await api('signup',{method:'POST',data:{username:$('#username').value,email:$('#email').value,password:$('#password').value}});form.reset();location.hash='#login';toast('Account created. Sign in to start your research.');
    }
    if(form.id==='loginForm'){
      const result=await api('login',{method:'POST',data:{identifier:$('#identifier').value,password:$('#password').value,remember:form.elements.remember.checked}});form.reset();state.user=result.user;state.metrics=(await api('statistics/catalog')).metrics;location.hash='#dashboard';
    }
    if(form.id==='datasetForm'){
      const result=await api(state.dataset?`datasets/${state.dataset.id}`:'datasets',{method:state.dataset?'PUT':'POST',data:editorPayload()});state.dataset=result.dataset;state.saved=null;state.editor=null;
      if(event.submitter?.name==='saveOnly'){location.hash='#datasets';toast('Dataset saved.');}
      else {
        try {
          const calculated=await api('statistics/calculate',{method:'POST',data:{dataset_id:state.dataset.id,settings:state.settings}});
          state.calculation=calculated.calculation;state.revision=calculated.dataset_revision;location.hash='#results';toast('Dataset saved and statistics recalculated.');
        } catch(error) {
          location.hash=`#analyze/${state.dataset.id}`;
          throw new Error('Dataset saved. '+error.message);
        }
      }
    }
    if(form.id==='calculateForm'){
      state.settings=getSettings();const result=await api('statistics/calculate',{method:'POST',data:{dataset_id:state.dataset.id,settings:state.settings}});state.calculation=result.calculation;state.revision=result.dataset_revision;state.saved=null;location.hash='#results';
    }
    if(form.id==='compareForm'){
      const selections=[...document.querySelectorAll('[name=compare]:checked')].map(el=>({dataset_id:Number(el.value),settings:{column:Number($(`[data-compare-column="${el.value}"]`).value)}}));
      if(selections.length<2 || selections.length>6)throw new Error('Select two to six datasets.');const result=await api('datasets/compare',{method:'POST',data:{selections}});comparisonResults(result.comparisons);
    }
    if(form.id==='passwordForm'){
      if($('#newPassword').value!==$('#confirmNewPassword').value)throw new Error('New passwords do not match.');await api('profile/password',{method:'POST',data:{current_password:$('#currentPassword').value,new_password:$('#newPassword').value}});form.reset();state.user=null;location.hash='#login';toast('Password updated. Sign in with your new password.');
    }
  });
});

window.addEventListener('hashchange',route);
window.addEventListener('beforeunload',event=>{if(state.editor){event.preventDefault();event.returnValue='';}});
(async()=>{
  try {const result=await api('me');state.user=result.user;if(state.user)state.metrics=(await api('statistics/catalog')).metrics;await route();}
  catch(error){auth();toast(error.message,true);}
})();

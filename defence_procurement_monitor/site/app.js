async function loadJSON(path){ const r = await fetch(path, {cache:'no-store'}); return r.json(); }

const state = {
  articles: [],
  themes: null,
  sortKey: 'date',
  sortDir: 'desc',
  search: '',
  tag: '',
  onlyRecommended: false,
};

function fmtDate(iso){
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {year:'numeric', month:'short', day:'2-digit'});
}

function setSort(key){
  if(state.sortKey===key){ state.sortDir = state.sortDir==='asc'?'desc':'asc'; }
  else { state.sortKey = key; state.sortDir = 'desc'; }
  renderTable();
}

function getLiked(){
  const raw = localStorage.getItem('likedArticles')||'[]';
  try { return new Set(JSON.parse(raw)); } catch(e){ return new Set(); }
}
function toggleLike(id){
  const set = getLiked();
  if(set.has(id)) set.delete(id); else set.add(id);
  localStorage.setItem('likedArticles', JSON.stringify([...set]));
  renderTable();
}

function renderCharts(){
  if(!state.themes) return;
  const tc = state.themes.themes.slice(0, 12);
  const sc = state.themes.top_solutions.slice(0, 12);
  const tctx = document.getElementById('themesChart');
  const sctx = document.getElementById('solutionsChart');

  new Chart(tctx, { type: 'bar', data: {
      labels: tc.map(x=>x.name),
      datasets: [{ label: 'Theme mentions', data: tc.map(x=>x.count) }]
    }, options:{ responsive:true, plugins:{legend:{display:false}}}
  );
  new Chart(sctx, { type: 'bar', data: {
      labels: sc.map(x=>x.text.slice(0,30)),
      datasets: [{ label: 'Solution mentions', data: sc.map(x=>x.count) }]
    }, options:{ responsive:true, plugins:{legend:{display:false}}}
  );
}

function renderTable(){
  const tb = document.querySelector('#articlesTable tbody');
  tb.innerHTML = '';
  const liked = getLiked();
  const threshold = 0.35;
  let rows = state.articles.slice();

  // Filters
  if(state.search){
    const q = state.search.toLowerCase();
    rows = rows.filter(a =>
      (a.title||'').toLowerCase().includes(q) ||
      (a.source||'').toLowerCase().includes(q) ||
      (a.tags||[]).some(t => t.toLowerCase().includes(q))
    );
  }
  if(state.tag){
    rows = rows.filter(a => (a.tags||[]).includes(state.tag));
  }
  if(state.onlyRecommended){
    rows = rows.filter(a => (a.relevance_score||0) >= threshold);
  }

  // Sort
  rows.sort((a,b)=>{
    let va = a[state.sortKey], vb = b[state.sortKey];
    if(state.sortKey==='date'){ va = new Date(va).getTime(); vb = new Date(vb).getTime(); }
    if(va<vb) return state.sortDir==='asc'?-1:1;
    if(va>vb) return state.sortDir==='asc'?1:-1;
    return 0;
  });

  // Render
  for(const a of rows){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${fmtDate(a.date)}</td>
      <td><a href="${a.url}" target="_blank" rel="noopener">${a.title||'(untitled)'}</a><div class="source">${a.summary||''}</div></td>
      <td>${a.source||''}</td>
      <td>${(a.relevance_score??0).toFixed(2)}</td>
      <td>${(a.tags||[]).map(t=>`<span class="badge">${t}</span>`).join('')}</td>
      <td class="star ${liked.has(a.id)?'on':''}" title="Like to steer future ranking">★</td>
    `;
    tr.querySelector('.star').addEventListener('click', ()=>toggleLike(a.id));
    tb.appendChild(tr);
  }
}

async function init(){
  try{
    const [articles, themes] = await Promise.all([
      loadJSON('../data/articles.json').catch(()=>loadJSON('./articles.sample.json')),
      loadJSON('../data/themes.json').catch(()=>loadJSON('./themes.sample.json'))
    ]);
    state.articles = articles;
    state.themes = themes;

    // Populate tag filter
    const counts = {};
    for(const a of articles){ for(const t of (a.tags||[])){ counts[t]=(counts[t]||0)+1; } }
    const tagFilter = document.getElementById('tagFilter');
    Object.entries(counts).sort((a,b)=>b[1]-a[1]).forEach(([t,c])=>{
      const opt = document.createElement('option'); opt.value=t; opt.textContent = `${t} (${c})`; tagFilter.appendChild(opt);
    });

    renderCharts();
    renderTable();

    // Wire up controls
    document.getElementById('search').addEventListener('input', (e)=>{ state.search=e.target.value; renderTable(); });
    tagFilter.addEventListener('change', (e)=>{ state.tag=e.target.value; renderTable(); });
    document.getElementById('recoFilter').addEventListener('change', (e)=>{ state.onlyRecommended = e.target.value==='recommended'; renderTable(); });
    document.querySelectorAll('th[data-key]').forEach(th=> th.addEventListener('click', ()=> setSort(th.dataset.key)) );
  }catch(e){
    console.error(e);
  }
}

init();

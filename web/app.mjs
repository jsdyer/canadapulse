import {isLanguageProject,articleURL,articleKey,topicMetrics,countryRows,topicRows,csv,sparkSegments} from './model.mjs';
import {validateManifest,neededMonths,archiveSnapshot} from './archive.mjs';
const $=s=>document.querySelector(s), NS='coolcode:canadapulse:followed';
const state={mode:'country',snapshot:null,latest:null,activeDate:null,archiveManifest:null,archiveCache:new Map(),historyRequest:0,rows:[],limit:24,saved:new Set()};
try {const saved=JSON.parse(localStorage.getItem(NS)||'[]');if(Array.isArray(saved))state.saved=new Set(saved.filter(x=>typeof x==='string').slice(0,300));}catch{}
const number=n=>Math.round(n).toLocaleString();
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function option(value,label){const o=el('option',label);o.value=value;return o;}
function showFollowed(){const box=$('#followed-links');box.replaceChildren();for(const key of state.saved){const split=key.indexOf('|'),project=key.slice(0,split),title=key.slice(split+1);try{const p=el('p'),a=el('a',`${title} (${project.split('.')[0]})`);a.href=articleURL(title,project);a.rel='noopener noreferrer';a.target='_blank';const b=el('button','Check views','secondary');b.type='button';b.style.marginLeft='1rem';b.onclick=()=>{$('#article').value=title;$('#language').value=project.split('.')[0];$('#lookup').requestSubmit();$('#lookup').scrollIntoView({block:'center'});};p.append(a,b);box.append(p);}catch{}}}
function save(){showFollowed();try{localStorage.setItem(NS,JSON.stringify([...state.saved]));}catch{$('#status').textContent='Browser storage is unavailable. Followed articles will last only for this visit.';}}
function follow(row){const b=el('button','', 'follow');b.type='button';const key=articleKey(row);function paint(){const on=state.saved.has(key);b.textContent=on?'Following':'Follow article';b.setAttribute('aria-pressed',String(on));}paint();b.onclick=()=>{if(state.saved.has(key))state.saved.delete(key);else state.saved.add(key);save();paint();if($('#saved-only').checked)render();};return b;}
function card(row,country){const article=el('article',undefined,'card'),meta=el('p',country?`${row.project.split('.')[0].toUpperCase()} Wikipedia · source rank ${row.rank}`:`${row.group||'Your lookup'} · ${row.project.split('.')[0].toUpperCase()} Wikipedia`,'meta');article.append(meta);const h=el('h3'),a=el('a',row.title);a.href=articleURL(row.title,row.project);a.target='_blank';a.rel='noopener noreferrer';h.append(a);article.append(h);const metric=el('div',undefined,'metric');metric.append(el('span',country?`≤ ${number(row.views_ceil)}`:number(row.views)));metric.append(el('small',country?' view upper bound':' worldwide views'));article.append(metric);
  if(country){let text=row.rankDate===null?'No earlier country ranking is archived.':row.previousRank===null?'Not present in the previous saved ranking.':row.previousRank===row.rank?'Same source rank as the previous saved date.':`${row.previousRank>row.rank?'Up':'Down'} ${Math.abs(row.previousRank-row.rank)} source ranks since ${row.rankDate}.`;article.append(el('p',text,'detail'));}
  else {const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('spark');svg.setAttribute('viewBox','0 0 300 58');svg.setAttribute('role','img');svg.setAttribute('aria-label',`Daily pageviews from ${row.history[0]?.date} through ${row.history.at(-1)?.date}; missing dates leave gaps`);for(const points of sparkSegments(row.history)){const poly=document.createElementNS(svg.namespaceURI,points.includes(' ')?'polyline':'circle');if(points.includes(' '))poly.setAttribute('points',points);else{const [x,y]=points.split(',');poly.setAttribute('cx',x);poly.setAttribute('cy',y);poly.setAttribute('r','2');}svg.append(poly);}article.append(svg);article.append(el('p',row.ratio===null?`A complete ${row.baselineDays}-day baseline is unavailable or zero (${row.baselineCount} observed days).`:`${row.ratio.toFixed(2)}× the previous ${row.baselineCount}-day mean (${number(row.average)} views/day).`,'detail'));}
  article.append(follow(row));return article;
}
function setFilters(){const country=state.mode==='country';$('#country-tab').setAttribute('aria-pressed',String(country));$('#topics-tab').setAttribute('aria-pressed',String(!country));$('#sort-wrap').hidden=country;$('#filter-label').textContent=country?'Language':'Topic group';const values=country?[...new Set(state.snapshot.country_days.flatMap(d=>d.articles.map(a=>a.project).filter(isLanguageProject)))].sort():[...new Set(state.snapshot.topics.map(t=>t.group))].sort();$('#filter').replaceChildren(option('all',country?'All languages':'All topic groups'),...values.map(v=>option(v,country?v.split('.')[0].toUpperCase():v)));$('#measure').textContent=country?'Articles read from Canada. Counts are privacy-protected upper bounds; ranks retain Wikimedia’s source ordering after utility pages are removed.':'Worldwide user views for an expandable list of Canadian topics. Ratios use the preceding days, excluding the selected day. English and French articles are measured separately.';state.limit=24;render();}
function render(){if(!state.snapshot)return;const date=state.activeDate||$('#date').value,query=$('#search').value,filter=$('#filter').value,saved=$('#saved-only').checked?state.saved:null;state.rows=state.mode==='country'?countryRows(state.snapshot,date,query,filter,saved):topicRows(state.snapshot,date,query,filter,$('#sort').value,saved);const rows=state.rows.slice(0,state.limit);$('#results').replaceChildren(...rows.map(row=>card(row,state.mode==='country')));if(!rows.length)$('#results').append(el('p','No articles match these filters. Try another date, broader search, or turn off the followed-only filter.','empty'));$('#result-count').textContent=`${state.rows.length} articles · ${date}`;$('#more').hidden=state.rows.length<=state.limit;$('#export').disabled=!state.rows.length;}
for(const id of ['search','filter','sort','saved-only'])$('#'+id).addEventListener(id==='search'?'input':'change',()=>{state.limit=24;render();});
$('#country-tab').onclick=()=>{state.mode='country';setFilters();historyNote();};$('#topics-tab').onclick=()=>{state.mode='topics';setFilters();historyNote();};$('#more').onclick=()=>{state.limit+=24;render();};
$('#clear-saved').onclick=()=>{state.saved.clear();save();render();$('#lookup-result').replaceChildren();};
$('#export').onclick=()=>{const data=csv(state.rows.map(r=>({...r,date:state.activeDate||$('#date').value})),state.mode==='country'),url=URL.createObjectURL(new Blob([data],{type:'text/csv;charset=utf-8'}));const a=el('a');a.href=url;a.download=`canadapulse-${state.mode}-${state.activeDate}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('#lookup').onsubmit=async event=>{event.preventDefault();const title=$('#article').value.trim(),language=$('#language').value.trim().toLowerCase();if(!title)return;if(!isLanguageProject(language+'.wikipedia')){$('#lookup-status').textContent='Enter a Wikipedia language code such as en, fr or simple.';return;}const button=$('#lookup button');button.disabled=true;$('#lookup-status').textContent='Checking worldwide daily pageviews…';$('#lookup-result').replaceChildren();try{const end=state.snapshot.report_date,start=new Date(end+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-28);const format=s=>s.replaceAll('-','')+'00';const project=language+'.wikipedia',url=`https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/${project}/all-access/user/${encodeURIComponent(title.replaceAll(' ','_'))}/daily/${format(start.toISOString().slice(0,10))}/${format(end)}`;const response=await fetch(url,{signal:AbortSignal.timeout(20000)});if(!response.ok)throw new Error(response.status===404?'No pageview series found. Use the exact Wikipedia article title.':`Wikimedia returned ${response.status}. Please try later.`);const data=await response.json();if(!Array.isArray(data.items)||data.items.length>100)throw new Error('Unexpected response.');const history=data.items.map(p=>{const s=String(p.timestamp);if(!/^\d{10}$/.test(s)||!Number.isSafeInteger(p.views)||p.views<0)throw new Error('Invalid source count.');return{date:`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`,views:p.views};});const row=topicMetrics({title,project,group:'Your lookup',history},end,28);if(row.views===null)throw new Error('The selected reporting day is not available.');$('#lookup-result').append(card(row,false));$('#lookup-status').textContent=`Worldwide views through ${end}. This custom lookup is not part of the published Canadian-topic catalogue.`;}catch(error){$('#lookup-status').textContent=error.message||'The lookup could not be completed.';}finally{button.disabled=false;}};
function historyNote(){
  const meta=state.snapshot?.archive_meta;
  if(!meta)return;
  const date=state.activeDate,time=state.mode==='country'?meta.country_saved_at:meta.first_saved_at;
  $('#history-status').textContent=state.mode==='country'&&!meta.has_country?`No Canadian-country ranking was archived for ${date}. The Canadian topics worldwide tab has saved observations for this date.`:`Viewing ${date} · first saved ${new Date(time||meta.first_saved_at).toLocaleString()} · archived values and topic selection are retained.`;
  const u=new URL(location.pathname,location.origin);u.searchParams.set('date',date);u.searchParams.set('view',state.mode);history.replaceState(null,'',u);
}
function monthDates(month,selected){
  const item=state.archiveManifest.months.find(m=>m.month===month);
  $('#date').replaceChildren(...item.dates.map(d=>option(d.date,d.date+(d.country?'':' · topics only'))));
  $('#date').value=item.dates.some(d=>d.date===selected)?selected:item.dates[0].date;
}
async function selectHistoryDate(selected){
  if(!state.archiveManifest){state.activeDate=selected;render();return;}
  const request=++state.historyRequest;
  $('#history-status').textContent=`Loading saved observations for ${selected}…`;
  $('#date').disabled=true;$('#month').disabled=true;
  try{
    const entries=neededMonths(state.archiveManifest,selected),months=[];
    for(const entry of entries){
      if(!state.archiveCache.has(entry.month)){
        const response=await fetch(entry.path,{signal:AbortSignal.timeout(20000)});
        if(!response.ok)throw new Error(`Archive month ${entry.month} is unavailable (${response.status}).`);
        const text=await response.text();
        if(new TextEncoder().encode(text).length!==entry.bytes)throw new Error('Archive file size does not match its manifest. Please retry after publication finishes.');
        if(globalThis.crypto?.subtle){const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));const hash=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');if(hash!==entry.sha256)throw new Error('Archive checksum does not match its manifest. Please retry after publication finishes.');}
        const data=JSON.parse(text);
        if(data.month!==entry.month)throw new Error('Archive month mismatch.');
        state.archiveCache.set(entry.month,data);if(state.archiveCache.size>8)state.archiveCache.delete(state.archiveCache.keys().next().value);
      }
      months.push(state.archiveCache.get(entry.month));
    }
    if(request!==state.historyRequest)return;
    state.snapshot=archiveSnapshot(months,selected);state.activeDate=selected;setFilters();historyNote();
  }catch(error){if(request===state.historyRequest){
      if(state.archiveManifest.months.some(m=>m.dates.some(d=>d.date===state.activeDate))){$('#month').value=state.activeDate.slice(0,7);monthDates($('#month').value,state.activeDate);}
      else{state.archiveManifest=null;$('#month-wrap').hidden=true;state.snapshot=state.latest;state.activeDate=state.latest.report_date;$('#date').replaceChildren(...state.latest.country_days.map(d=>option(d.date,d.date)));$('#date').value=state.activeDate;setFilters();}
      $('#history-status').textContent=error.message+' Previous results have been retained.';
    }}
  finally{if(request===state.historyRequest){$('#date').disabled=false;$('#month').disabled=false;}}
}
$('#date').onchange=()=>selectHistoryDate($('#date').value);
$('#month').onchange=()=>{monthDates($('#month').value);selectHistoryDate($('#date').value);};
$('#copy-date').onclick=async()=>{try{const u=new URL(location.pathname,location.origin);u.searchParams.set('date',state.activeDate);u.searchParams.set('view',state.mode);await navigator.clipboard.writeText(u.href);$('#history-status').textContent='Date link copied. It includes only the report date and view, not your searches or followed articles.';}catch{$('#history-status').textContent='Clipboard is unavailable. Copy the current address bar to share this date.';}};
try{
  const response=await fetch('./data/snapshot.json');if(!response.ok)throw new Error('Published data is unavailable.');
  const snapshot=await response.json();if(snapshot.schema_version!==1||!snapshot.country_days?.length||!snapshot.topics?.length)throw new Error('The published snapshot is not valid.');
  state.latest=snapshot;state.snapshot=snapshot;state.activeDate=snapshot.report_date;
  $('#date').replaceChildren(...snapshot.country_days.map(d=>option(d.date,d.date)));$('#date').value=snapshot.report_date;
  const age=Math.floor((Date.now()-Date.parse(snapshot.report_date+'T00:00:00Z'))/86400000);
  $('#status').textContent=`Latest report date ${snapshot.report_date} (UTC) · ${snapshot.topics.length} Canadian topics · sources checked ${new Date(snapshot.retrieved_at).toLocaleString()}${age>4?' · This latest snapshot is older than expected; its original dates are retained.':''}`;
  setFilters();
  try{
    const r=await fetch('./data/history/manifest.json');if(!r.ok)throw new Error('History manifest unavailable.');
    state.archiveManifest=validateManifest(await r.json());const manifest=state.archiveManifest;
    $('#month').replaceChildren(...manifest.months.map(m=>option(m.month,m.month)));$('#month-wrap').hidden=false;
    const params=new URL(location.href).searchParams,requested=params.get('date');
    const allDates=manifest.months.flatMap(m=>m.dates.map(d=>d.date)),selected=allDates.includes(requested)?requested:manifest.latest_date;
    if(params.get('view')==='topics')state.mode='topics';
    $('#month').value=selected.slice(0,7);monthDates($('#month').value,selected);
    const countryDates=manifest.months.flatMap(m=>m.dates.filter(d=>d.country).map(d=>d.date)).sort();
    $('#status').textContent+=` · ${manifest.day_count} archived dates since ${manifest.earliest_date} · ${manifest.country_days} Canadian-reader rankings${countryDates.length?' since '+countryDates[0]:''}`;
    await selectHistoryDate(selected);
  }catch(error){$('#history-status').textContent=error.message+' The recent verified snapshot is still available.';}
}catch(error){$('#status').textContent=error.message+' Please try again later; no live data has been substituted.';$('#export').disabled=true;$('#lookup button').disabled=true;$('#copy-date').disabled=true;}
showFollowed();

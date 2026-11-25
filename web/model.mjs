export function articleURL(title, project = 'en.wikipedia') {
  if (!/^[a-z][a-z0-9-]{0,20}\.wikipedia$/.test(project)) throw new Error('Unsupported Wikipedia language');
  return `https://${project}.org/wiki/${encodeURIComponent(title.replaceAll(' ', '_'))}`;
}
export function articleKey(row) { return `${row.project}|${row.title}`; }
export function topicMetrics(topic, date, baselineDays = 28) {
  const history = topic.history.filter(p => p.date <= date).sort((a,b)=>a.date.localeCompare(b.date));
  const point = history.find(p => p.date === date);
  const start=new Date(date+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-baselineDays);
  const first=start.toISOString().slice(0,10);
  const previous = history.filter(p => p.date >= first && p.date < date);
  const average = previous.length ? previous.reduce((s,p)=>s+p.views,0)/previous.length : null;
  return { ...topic, views: point?.views ?? null, average, baselineCount: previous.length, baselineDays,
    ratio: point && average > 0 && previous.length === baselineDays ? point.views/average : null,
    change: point && average !== null ? point.views-average : null, history };
}
export function countryRows(snapshot, date, query = '', language = 'all', saved = null) {
  const day = snapshot.country_days.find(d=>d.date===date);
  const before = snapshot.country_days.filter(d=>d.date<date).sort((a,b)=>b.date.localeCompare(a.date))[0];
  const ranks = new Map((before?.articles || []).map(a=>[articleKey(a),a.rank]));
  const q = query.trim().toLocaleLowerCase();
  return (day?.articles || []).filter(a=>(language==='all'||a.project===language)&&a.title.toLocaleLowerCase().includes(q)&&(!saved||saved.has(articleKey(a))))
    .map(a=>({...a, previousRank:ranks.get(articleKey(a))??null, rankDate:before?.date??null}));
}
export function topicRows(snapshot, date, query='', group='all', sort='ratio', saved=null) {
  const q=query.trim().toLocaleLowerCase();
  const rows=snapshot.topics.filter(a=>(group==='all'||a.group===group)&&a.title.toLocaleLowerCase().includes(q)&&(!saved||saved.has(articleKey(a))))
    .map(a=>topicMetrics(a,date,snapshot.baseline_days)).filter(a=>a.views!==null);
  const key=sort==='views'?'views':sort==='change'?'change':'ratio';
  return rows.sort((a,b)=>(b[key]??-Infinity)-(a[key]??-Infinity)||b.views-a.views);
}
export function csv(rows, country) {
  const quote=v=>'"'+(typeof v==='string'&&/^[=+@\-\t\r]/.test(v)?"'"+v:String(v??'')).replaceAll('"','""')+'"';
  const header=country?['Article','Project','Date','View upper bound','Source rank']:['Article','Project','Date','Worldwide user views','Baseline mean','Baseline days','Ratio'];
  return [header,...rows.map(r=>country?[r.title,r.project,r.date,r.views_ceil,r.rank]:[r.title,r.project,r.date,r.views,r.average,r.baselineCount,r.ratio])].map(r=>r.map(quote).join(',')).join('\r\n');
}
export function sparkSegments(history, width=300, height=58) {
  if(!history.length) return [];
  const max=Math.max(1,...history.map(p=>p.views));
  const times=history.map((p,i)=>Number.isFinite(Date.parse(p.date+'T00:00:00Z'))?Date.parse(p.date+'T00:00:00Z'):i*86400000);
  const span=Math.max(86400000,times.at(-1)-times[0]),segments=[];
  for(let i=0;i<history.length;i++){
    if(i===0||times[i]-times[i-1]!==86400000)segments.push([]);
    segments.at(-1).push(`${((times[i]-times[0])/span*width).toFixed(1)},${(height-4-history[i].views/max*(height-8)).toFixed(1)}`);
  }
  return segments.map(points=>points.join(' '));
}
export function sparkPoints(history,width=300,height=58){return sparkSegments(history,width,height).join(' ');}

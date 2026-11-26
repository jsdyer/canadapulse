import {articleKey} from './model.mjs';
const DATE=/^\d{4}-\d{2}-\d{2}$/;
function validDate(value){return typeof value==='string'&&DATE.test(value)&&!Number.isNaN(Date.parse(value+'T00:00:00Z'))&&new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value;}
export function validateManifest(raw){
  if(raw?.schema_version!==1||!Array.isArray(raw.months)||!raw.months.length)throw new Error('The history manifest is invalid.');
  const dates=new Set(),months=new Set();
  for(const month of raw.months){
    if(!/^\d{4}-\d{2}$/.test(month.month)||months.has(month.month)||month.path!==`./data/history/${month.month}.json`||!Array.isArray(month.dates)||month.dates.length>31||!Number.isSafeInteger(month.bytes)||month.bytes<1||month.bytes>10000000||!/^[a-f0-9]{64}$/.test(month.sha256))throw new Error('The history manifest contains an invalid month.');
    months.add(month.month);
    for(const row of month.dates){if(!validDate(row.date)||!row.date.startsWith(month.month+'-')||dates.has(row.date)||typeof row.country!=='boolean'||!Number.isSafeInteger(row.topics)||row.topics<0||row.topics>100||!Number.isInteger(row.baseline_days)||row.baseline_days<7||row.baseline_days>90)throw new Error('The history manifest contains an invalid date.');dates.add(row.date);}
  }
  const ordered=[...dates].sort();
  if(dates.size!==raw.day_count||ordered[0]!==raw.earliest_date||ordered.at(-1)!==raw.latest_date||raw.country_days!==raw.months.flatMap(m=>m.dates).filter(d=>d.country).length)throw new Error('The history date counts do not agree.');
  return raw;
}
export function neededMonths(manifest,selected){
  const row=manifest.months.flatMap(m=>m.dates).find(d=>d.date===selected);
  if(!row)throw new Error('That date has not been archived.');
  const start=new Date(selected+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-row.baseline_days);
  const first=start.toISOString().slice(0,10);
  const previousCountry=manifest.months.flatMap(m=>m.dates).filter(d=>d.country&&d.date<selected).sort((a,b)=>b.date.localeCompare(a.date))[0]?.date;
  return manifest.months.filter(m=>m.dates.some(d=>(d.date>=first&&d.date<=selected)||d.date===previousCountry));
}
export function archiveSnapshot(months,selected){
  const days=[];
  for(const month of months){
    if(month?.schema_version!==1||!Array.isArray(month.days))throw new Error('An archive file is invalid.');
    for(const d of month.days){if(!validDate(d.date)||!d.date.startsWith(month.month+'-')||!Array.isArray(d.topics))throw new Error('An archive day is invalid.');days.push(d);}
  }
  const day=days.find(d=>d.date===selected);
  if(!day)throw new Error('This saved day could not be loaded.');
  const start=new Date(selected+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-day.baseline_days);const first=start.toISOString().slice(0,10);
  const prior=days.filter(d=>d.date>=first&&d.date<=selected).sort((a,b)=>a.date.localeCompare(b.date));
  const topics=day.topics.map(topic=>({...topic,history:prior.flatMap(d=>{const match=d.topics.find(t=>articleKey(t)===articleKey(topic));return match?[{date:d.date,views:match.views}]:[];})}));
  return {schema_version:1,country:'CA',report_date:selected,retrieved_at:day.topics_saved_at??day.first_saved_at,baseline_days:day.baseline_days,topics,
    country_days:days.filter(d=>d.country).map(d=>({date:d.date,articles:d.country.articles})).sort((a,b)=>b.date.localeCompare(a.date)),
    archive_meta:{first_saved_at:day.topics_saved_at??day.first_saved_at,country_saved_at:day.country?.first_saved_at??null,has_country:!!day.country},source:months[0]?.source};
}

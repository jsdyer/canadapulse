import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateManifest,neededMonths,archiveSnapshot} from '../web/archive.mjs';
import {topicMetrics,sparkSegments} from '../web/model.mjs';
const topic=(title,views)=>({title,views,project:'en.wikipedia',group:'Places'});
const day=(date,topics,country)=>({date,first_saved_at:'2026-02-03T00:00:00Z',baseline_days:7,topics,...(country?{country:{first_saved_at:'2026-02-03T00:00:00Z',articles:country}}:{})});
const months=[{schema_version:1,month:'2026-01',days:[day('2026-01-30',[topic('Old topic',3)]),day('2026-01-31',[topic('Halifax',10)])]}, {schema_version:1,month:'2026-02',days:[day('2026-02-02',[topic('Halifax',20)], [{title:'Ranked',project:'en.wikipedia',rank:5,views_ceil:900}])]}];
test('checked-in manifest agrees with all durable months and bounded lazy date range',()=>{
 const manifest=validateManifest(JSON.parse(readFileSync(new URL('../web/data/history/manifest.json',import.meta.url))));
 const chosen=neededMonths(manifest,manifest.latest_date);
 assert.ok(chosen.length<=4);
 const files=chosen.map(m=>JSON.parse(readFileSync(new URL('../web/'+m.path,import.meta.url))));
 const snapshot=archiveSnapshot(files,manifest.latest_date);
 assert.equal(snapshot.report_date,manifest.latest_date);
 assert.ok(snapshot.topics.length>0);
 assert.throws(()=>neededMonths(manifest,'1900-01-01'));
});
test('selected historical topic list remains original and missing observations stay missing',()=>{
 const old=archiveSnapshot(months,'2026-01-30');
 assert.deepEqual(old.topics.map(t=>t.title),['Old topic']);
 assert.equal(old.archive_meta.has_country,false);
 const selected=archiveSnapshot(months,'2026-02-02');
 assert.deepEqual(selected.topics[0].history,[{date:'2026-01-31',views:10},{date:'2026-02-02',views:20}]);
 assert.equal(selected.country_days[0].articles[0].rank,5);
 assert.equal(topicMetrics(selected.topics[0],'2026-02-02',7).ratio,null);
});
test('calendar gaps have their true width and break sparklines',()=>{
 const lines=sparkSegments([{date:'2026-01-01',views:1},{date:'2026-01-02',views:2},{date:'2026-01-04',views:3}]);
 assert.equal(lines.length,2);
 assert.equal(lines[0].split(' ')[1].split(',')[0],'100.0');
 assert.equal(lines[1].split(',')[0],'300.0');
});
test('older observations cannot fill a missing baseline date',()=>{
 const history=Array.from({length:10},(_,i)=>({date:`2026-01-${String(i+1).padStart(2,'0')}`,views:10})).filter(p=>p.date!=='2026-01-05');
 const metric=topicMetrics({history},'2026-01-10',7);
 assert.equal(metric.baselineCount,6);assert.equal(metric.ratio,null);
});
test('manifest rejects unsafe paths, impossible dates and inconsistent coverage',()=>{
 const source=JSON.parse(readFileSync(new URL('../web/data/history/manifest.json',import.meta.url)));
 for(const mutate of [m=>m.months[0].path='https://evil.test/file',m=>m.months[0].dates[0].date='2026-02-31',m=>m.day_count++,m=>m.country_days++,m=>m.months[0].sha256='bad']){
  const value=structuredClone(source);mutate(value);assert.throws(()=>validateManifest(value));
 }
});

test('rank comparison loads the preceding country date even across a long collection gap',()=>{
 const manifest={months:[{month:'2026-06',dates:[{date:'2026-06-01',country:true,baseline_days:7}]},{month:'2026-01',dates:[{date:'2026-01-31',country:true,baseline_days:7}]}]};
 assert.deepEqual(neededMonths(manifest,'2026-06-01').map(m=>m.month),['2026-06','2026-01']);
});

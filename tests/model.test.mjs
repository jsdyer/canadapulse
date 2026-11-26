import test from 'node:test';
import assert from 'node:assert/strict';
import {isLanguageProject,articleURL,topicMetrics,countryRows,topicRows,csv,sparkPoints} from '../web/model.mjs';
const history=Array.from({length:8},(_,i)=>({date:`2026-01-0${i+1}`,views:i===7?80:10}));
test('baseline excludes chosen day and future observations',()=>{const m=topicMetrics({history},'2026-01-08',7);assert.equal(m.average,10);assert.equal(m.ratio,8);assert.equal(topicMetrics({history},'2026-01-07',7).ratio,null);});
test('missing date stays missing and zero baseline has no infinite ratio',()=>{assert.equal(topicMetrics({history},'2026-02-01').views,null);assert.equal(topicMetrics({history:history.map(p=>({...p,views:0}))},'2026-01-08').ratio,null);});
test('country ranks are compared only when present; upper bounds unchanged',()=>{const d={country_days:[{date:'2026-01-02',articles:[{title:'A',project:'en.wikipedia',rank:2,views_ceil:100}]},{date:'2026-01-01',articles:[]}]};const row=countryRows(d,'2026-01-02')[0];assert.equal(row.previousRank,null);assert.equal(row.views_ceil,100);assert.deepEqual(countryRows(d,'2026-01-02','','fr.wikipedia'),[]);});
test('arbitrary new configured groups are included',()=>{const d={topics:[{title:'New place',project:'en.wikipedia',group:'New group',history}],baseline_days:7};assert.equal(topicRows(d,'2026-01-08','','New group').length,1);});
test('URLs reject hostile project and encode path content',()=>{assert.throws(()=>articleURL('a','evil.example'));assert.equal(new URL(articleURL('A?x=<script>')).hostname,'en.wikipedia.org');assert.ok(articleURL('A/B').includes('%2F'));});
test('CSV quotes content and neutralizes formula text',()=>{const out=csv([{title:'=1+1',project:'en.wikipedia',date:'2026-01-01',rank:1,views_ceil:9}],true);assert.ok(out.includes('"\'=1+1"'));assert.ok(out.includes('View upper bound'));});
test('empty and zero sparklines are finite',()=>{assert.equal(sparkPoints([]),'');assert.ok(!sparkPoints([{views:0}]).includes('NaN'));});

test('country display excludes utility projects without mutating saved source data',()=>{
 const articles=[{title:'Thanks',project:'thankyou.wikipedia',rank:1,views_ceil:100},{title:'Canada',project:'en.wikipedia',rank:4,views_ceil:80}];
 const data={country_days:[{date:'2026-01-01',articles}]};
 assert.deepEqual(countryRows(data,'2026-01-01').map(r=>r.rank),[4]);assert.equal(data.country_days[0].articles.length,2);
 assert.equal(isLanguageProject('simple.wikipedia'),true);assert.equal(isLanguageProject('zh-min-nan.wikipedia'),true);
 assert.equal(isLanguageProject('www.wikipedia'),false);assert.equal(isLanguageProject('thankyou.wikipedia'),false);
});

test('the Dutch homepage is excluded only from its own project without changing source ranks',()=>{
 const articles=[
  {title:'Hoofdpagina',project:'nl.wikipedia',rank:2,views_ceil:9999},
  {title:'Canada',project:'en.wikipedia',rank:7,views_ceil:4100},
  {title:'Hoofdpagina',project:'en.wikipedia',rank:11,views_ceil:1200},
 ];
 const source={country_days:[{date:'2026-11-25',articles}]},before=structuredClone(source);
 const shown=countryRows(source,'2026-11-25');
 assert.deepEqual(shown.map(r=>[r.title,r.rank,r.views_ceil]),[['Canada',7,4100],['Hoofdpagina',11,1200]]);
 assert.deepEqual(source,before);
 assert.deepEqual(countryRows(source,'2026-11-25','','nl.wikipedia'),[]);
});

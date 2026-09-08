"""Make a browser-only interaction check; open resulting file in installed Firefox.

This test exercises the real generated UI via DOM events, then displays the result.
It neither drives other tabs nor opens a listening port.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runsignal.report import render

data = json.loads((Path(__file__).resolve().parents[1] / "docs/demo/report.json").read_text())
driver = r'''
<script>
const checks=[];
const check=(name,fn)=>{try{fn();checks.push([name,true]);}catch(e){checks.push([name,false,String(e)]);}};
const expect=(yes,reason)=>{if(!yes)throw Error(reason);};
const filter=name=>document.querySelector('[data-filter="'+name+'"]').click();
const search=q=>{document.getElementById('search').value=q;document.getElementById('search').dispatchEvent(new Event('input'));};
const run=id=>[...document.querySelectorAll('.bar')].find(b=>b.getAttribute('aria-label').startsWith(id+' ')).click();
check('Initial history: 24 runs and 40 tests',()=>{expect(document.getElementById('runs-stat').textContent==='24','run count');expect(document.getElementById('tests-stat').textContent==='40','test count');});
check('Mixed-outcome filter finds only planted cache test',()=>{filter('mixed');expect(document.querySelectorAll('#tests tr').length===1,'row count');expect(document.querySelector('.test-button').textContent==='test_preview_cache','identity');});
check('Search can display zero results',()=>{search('no-such-test');expect(!document.getElementById('empty').hidden,'empty state');expect(document.querySelectorAll('#tests tr').length===0,'rows remain');});
check('Search reset restores the active filter',()=>{search('');expect(document.querySelectorAll('#tests tr').length===1,'filter lost');});
check('Test detail opens with full selected-context history',()=>{document.querySelector('.test-button').click();expect(document.getElementById('detail').open,'dialog');expect(document.querySelectorAll('#detail-body table tr').length===25,'history rows');expect(document.querySelector('#detail-body code').textContent.length===64,'source digest');document.getElementById('close-detail').click();});
check('New failures use selected run baseline',()=>{run('demo-021');filter('new');expect(document.querySelectorAll('#tests tr').length===1,'new failure count');expect(document.querySelector('.test-button').textContent==='test_markdown_links','new failure identity');});
check('Duration filter finds planted increase',()=>{run('demo-019');filter('slow');expect(document.querySelectorAll('#tests tr').length===1,'slow count');expect(document.querySelector('.test-button').textContent==='test_thumbnail_index','slow identity');});
check('Missing shard warning visible',()=>{run('demo-020');expect(document.getElementById('warnings').textContent.includes('shard-3'),'missing warning');});
check('Run evidence shows expected and missing shards',()=>{document.querySelector('#selected-run button').click();expect(document.getElementById('detail-body').textContent.includes('Missing shards: shard-3'),'missing shard evidence');expect(document.querySelectorAll('#detail-body code').length===4,'run and three artifact hashes');document.getElementById('close-detail').click();});
check('All filter restores 40 observed identities',()=>{filter('all');expect(document.querySelectorAll('#tests tr').length===40,'identities');});
const passed=checks.filter(c=>c[1]).length;
document.body.replaceChildren();document.body.style.padding='35px';
const heading=document.createElement('h1');heading.textContent=passed+' / '+checks.length+' browser checks passed';heading.style.color=passed===checks.length?'#6bdbb2':'#fc8884';document.body.append(heading);
for(const [name,ok,error] of checks){const p=document.createElement('p');p.textContent=(ok?'PASS — ':'FAIL — ')+name+(error?' : '+error:'');p.style.color=ok?'#edf4f5':'#fc8884';document.body.append(p);}
document.title='RunSignal browser checks: '+passed+'/'+checks.length;
</script>'''
output = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/runsignal-browser-smoke.html")
output.write_text(render(data).replace("</body>", driver + "</body>"), encoding="utf-8")
print(output)

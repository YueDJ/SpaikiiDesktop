"""
Build wiki.html - no mermaid rendering, show as collapsible code blocks.
Clean, no errors, no external dependencies.
"""
import os, sys, json, re
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CONTENT_DIR = Path(r'c:\Users\YDJ\Desktop\SpaikiiDesktop\.qoder\repowiki\zh\content')
OUTPUT_FILE = Path(r'c:\Users\YDJ\Desktop\SpaikiiDesktop\.qoder\repowiki\wiki.html')

CAT_ORDER = [
    '项目概述', '核心概念', '架构设计', '用户指南', '开发者指南',
    'API参考', '高级特性', '运维管理', '部署指南', '故障排除',
]


def collect_files(content_dir):
    files = []
    for root, dirs, filenames in os.walk(content_dir):
        dirs.sort()
        for fname in sorted(filenames):
            if not fname.endswith('.md'):
                continue
            full_path = Path(root) / fname
            rel = full_path.relative_to(content_dir)
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            title = m.group(1).strip() if m else fname.replace('.md', '')
            cat = str(rel.parts[0]) if len(rel.parts) > 1 else '其他'
            files.append({
                'path': str(rel).replace('\\', '/'),
                'title': title,
                'content': content,
                'category': cat,
            })
    return files


def main():
    print('Collecting files...')
    files = collect_files(CONTENT_DIR)
    print(f'Found {len(files)} files')

    content_map = {f['path']: f['content'] for f in files}
    file_list = [{'path': f['path'], 'title': f['title'], 'cat': f['category']} for f in files]

    cat_counts = {}
    for f in files:
        cat_counts[f['category']] = cat_counts.get(f['category'], 0) + 1
    cat_list = []
    for c in CAT_ORDER:
        if c in cat_counts:
            cat_list.append({'name': c, 'count': cat_counts[c]})
    for c, n in cat_counts.items():
        if c not in CAT_ORDER:
            cat_list.append({'name': c, 'count': n})

    content_json = json.dumps(content_map, ensure_ascii=False)
    file_list_json = json.dumps(file_list, ensure_ascii=False)
    cat_list_json = json.dumps(cat_list, ensure_ascii=False)

    print('Generating wiki.html...')

    html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sparkii Agent Wiki</title>
<style>
:root{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--tx:#e6edf3;--tx2:#8b949e;--ac:#58a6ff;--ac2:#79c0ff;--bd:#30363d;--sw:280px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--tx);line-height:1.6;display:flex;min-height:100vh}
.sidebar{width:var(--sw);min-width:var(--sw);background:var(--bg2);border-right:1px solid var(--bd);overflow-y:auto;position:fixed;top:0;left:0;bottom:0;z-index:100}
.side-hd{padding:14px 16px 10px;border-bottom:1px solid var(--bd)}
.side-hd h2{font-size:16px;color:var(--ac)}.side-hd p{font-size:11px;color:var(--tx2)}
.search{padding:8px 12px;border-bottom:1px solid var(--bd)}
.search input{width:100%;padding:7px 10px;background:var(--bg);border:1px solid var(--bd);border-radius:5px;color:var(--tx);font-size:12px;outline:none}
.search input:focus{border-color:var(--ac)}
.nav{padding:6px 8px}
.cat{margin-bottom:2px}
.cat-hd{display:flex;align-items:center;padding:6px 8px;color:var(--tx);font-size:12px;font-weight:600;cursor:pointer;border-radius:4px;user-select:none}
.cat-hd:hover{background:var(--bg3)}
.cat-hd .arr{margin-right:6px;font-size:8px;transition:transform .15s;color:var(--tx2);display:inline-block}
.cat.collapsed .arr{transform:rotate(-90deg)}.cat.collapsed .cat-list{display:none}
.cat-list{padding-left:4px}
.pg{display:block;padding:3px 8px 3px 20px;color:var(--tx2);text-decoration:none;font-size:11.5px;border-radius:3px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pg:hover{color:var(--ac);background:var(--bg3)}.pg.on{color:var(--ac);background:rgba(88,166,255,.1);font-weight:500}
.main{margin-left:var(--sw);flex:1;padding:28px 44px;max-width:860px;min-width:0}
.bc{font-size:12px;color:var(--tx2);margin-bottom:12px}
.bc a{color:var(--tx2);cursor:pointer}.bc a:hover{color:var(--ac)}.bc s{margin:0 5px;text-decoration:none;color:var(--bd)}
h1{font-size:1.8em;border-bottom:1px solid var(--bd);padding-bottom:.25em;margin-bottom:.7em}
h2{font-size:1.35em;margin-top:1.3em;margin-bottom:.35em;padding-bottom:.2em;border-bottom:1px solid var(--bd)}
h3{font-size:1.1em;margin-top:1em;margin-bottom:.25em}h4{font-size:.95em;margin-top:.7em}
p{margin-bottom:.7em}a{color:var(--ac);text-decoration:none}a:hover{color:var(--ac2);text-decoration:underline}
ul,ol{margin-bottom:.7em;padding-left:1.6em}li{margin-bottom:.2em}
code{background:var(--bg2);border:1px solid var(--bd);border-radius:3px;padding:1px 4px;font-size:.86em;font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace}
pre{background:var(--bg2);border:1px solid var(--bd);border-radius:5px;padding:12px;overflow-x:auto;margin-bottom:.7em}
pre code{background:none;border:none;padding:0;font-size:.82em;line-height:1.45}
table{border-collapse:collapse;width:100%;margin-bottom:.7em}th,td{border:1px solid var(--bd);padding:5px 9px;text-align:left;font-size:.9em}
th{background:var(--bg3);font-weight:600}tr:nth-child(even){background:var(--bg2)}
blockquote{border-left:3px solid var(--ac);padding:7px 14px;margin-bottom:.7em;background:var(--bg2);border-radius:0 4px 4px 0}blockquote p{margin-bottom:0}
hr{border:none;border-top:1px solid var(--bd);margin:1.3em 0}img{max-width:100%;border-radius:4px}
.mm-box{background:var(--bg2);border:1px solid var(--bd);border-radius:5px;margin:.7em 0;overflow:hidden}
.mm-box summary{padding:8px 14px;cursor:pointer;color:var(--ac);font-size:12px;user-select:none;display:flex;align-items:center;gap:6px}
.mm-box summary:hover{background:var(--bg3)}
.mm-box summary .icon{font-size:14px}
.mm-box[open] summary{border-bottom:1px solid var(--bd)}
.mm-box pre{margin:0;border:none;border-radius:0}
cite{display:block;background:var(--bg2);border:1px solid var(--bd);border-radius:4px;padding:8px 12px;margin-bottom:.7em;font-size:.86em;color:var(--tx2);font-style:normal}cite strong{color:var(--tx)}
.welcome{text-align:center;padding:60px 30px}.welcome h1{border:none;font-size:1.9em}
.welcome p{color:var(--tx2);max-width:460px;margin:8px auto}
.stats{display:flex;gap:14px;justify-content:center;margin:24px 0;flex-wrap:wrap}
.st{text-align:center;padding:14px 20px;background:var(--bg2);border:1px solid var(--bd);border-radius:7px;cursor:pointer;min-width:100px;transition:border-color .15s}
.st:hover{border-color:var(--ac)}.st-v{font-size:24px;font-weight:700;color:var(--ac)}.st-l{font-size:11px;color:var(--tx2)}
.bt{position:fixed;bottom:20px;right:20px;width:34px;height:34px;background:var(--ac);color:#fff;border:none;border-radius:50%;cursor:pointer;font-size:15px;display:none;align-items:center;justify-content:center;z-index:1000}
.bt:hover{background:var(--ac2)}
</style>
</head>
<body>
<aside class="sidebar">
<div class="side-hd"><h2>Sparkii Agent</h2><p>Wiki 文档站</p></div>
<div class="search"><input type="text" id="q" placeholder="搜索..."></div>
<div class="nav" id="nav"></div>
</aside>
<main class="main" id="main"></main>
<button class="bt" id="bt">↑</button>
<script>
var C=''' + content_json + r''';
var F=''' + file_list_json + r''';
var G=''' + cat_list_json + r''';
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}
function buildNav(){
    var h='';
    G.forEach(function(g){
        h+='<div class="cat">';
        h+='<div class="cat-hd"><span class="arr">▼</span>'+esc(g.name)+' <span style="color:var(--tx2);font-weight:400;font-size:10px;margin-left:auto">'+g.count+'</span></div>';
        h+='<div class="cat-list">';
        F.forEach(function(f){if(f.cat===g.name) h+='<a class="pg" data-p="'+f.path+'">'+esc(f.title)+'</a>';});
        h+='</div></div>';
    });
    return h;
}
function showPage(path){
    var md=C[path]; if(!md){document.getElementById('main').innerHTML='<p>未找到</p>';return}
    var f=F.find(function(x){return x.path===path});
    var cat=f?f.cat:'';
    document.getElementById('main').innerHTML='<div class="bc"><a onclick="goHome()">首页</a><s>›</s>'+esc(cat)+'<s>›</s> '+esc(f?f.title:'')+'</div>'+md2html(md);
    document.querySelectorAll('.pg').forEach(function(el){el.classList.toggle('on',el.getAttribute('data-p')===path)});
    window.scrollTo(0,0);
    var a=document.querySelector('.pg.on');if(a){var g=a.closest('.cat');if(g)g.classList.remove('collapsed');a.scrollIntoView({block:'nearest'})}
}
function goHome(){
    var h='<div class="welcome"><h1>Sparkii Agent Wiki</h1><p>自改进 AI 代理平台文档</p>';
    h+='<div class="stats"><div class="st"><div class="st-v">'+F.length+'</div><div class="st-l">文档</div></div>';
    h+='<div class="st"><div class="st-v">'+G.length+'</div><div class="st-l">分类</div></div></div>';
    h+='<div class="stats" style="flex-wrap:wrap">';
    G.forEach(function(g){var first=F.find(function(f){return f.cat===g.name});if(first) h+='<div class="st" onclick="showPage(\''+first.path+'\')"><div class="st-v">'+g.count+'</div><div class="st-l">'+esc(g.name)+'</div></div>';});
    h+='</div></div>';
    document.getElementById('main').innerHTML=h;
    document.querySelectorAll('.pg').forEach(function(el){el.classList.remove('on')});
}
function md2html(md){
    // Replace mermaid blocks with collapsible details
    md=md.replace(/```mermaid\n([\s\S]*?)```/g,function(m,code){
        return '<details class="mm-box"><summary><span class="icon">📊</span> 图表</summary><pre><code>'+esc(code.trim())+'</code></details>';
    });
    var ls=md.split('\n'),out=[],inC=false,inT=false,inL=false,lt='',cB=[],tB=[],lB=[];
    for(var i=0;i<ls.length;i++){var l=ls[i];
        if(l.match(/^```/)){if(inC){out.push('<pre><code>'+esc(cB.join('\n'))+'</code></pre>');cB=[];inC=false}else{if(inT){out.push(mkT(tB));tB=[];inT=false}if(inL){out.push(mkL(lB,lt));lB=[];inL=false}inC=true}continue}
        if(inC){cB.push(l);continue}
        if(l.match(/^\|.*\|$/)){if(!inT){if(inL){out.push(mkL(lB,lt));lB=[];inL=false}inT=true;tB=[]}tB.push(l);continue}else if(inT){out.push(mkT(tB));tB=[];inT=false}
        var lm=l.match(/^(\s*)([-*]|\d+\.?)\s+(.*)/);
        if(lm){if(!inL){inL=true;lt=lm[2].match(/\d/)?'ol':'ul';lB=[]}lB.push({i:lm[1].length,t:lm[3]});continue}else if(inL){out.push(mkL(lB,lt));lB=[];inL=false}
        var hm=l.match(/^(#{1,6})\s+(.*)/);if(hm){out.push('<h'+hm[1].length+'>'+il(hm[2])+'</h'+hm[1].length+'>');continue}
        if(l.match(/^---+$/)){out.push('<hr>');continue}
        if(l.match(/^>\s?(.*)/)){out.push('<blockquote><p>'+il(RegExp.$1)+'</p></blockquote>');continue}
        if(l.trim()==='')continue;
        if(l.match(/^<details class="mm-box"/)||l.match(/^<\/details>/)){out.push(l);continue}
        if(l.match(/^<summary>/)||l.match(/^<\/summary>/)||l.match(/^<pre><code>/)){out.push(l);continue}
        out.push('<p>'+il(l)+'</p>');
    }
    if(inC)out.push('<pre><code>'+esc(cB.join('\n'))+'</code></pre>');
    if(inT)out.push(mkT(tB));
    if(inL)out.push(mkL(lB,lt));
    return out.join('\n');
}
function mkT(r){if(r.length<2)return '<table>'+r.map(function(x){return '<tr>'+x.split('|').filter(function(c){return c.trim()}).map(function(c){return '<td>'+il(c.trim())+'</td>'}).join('')+'</tr>'}).join('')+'</table>';
    var hd=r[0].split('|').filter(function(c){return c.trim()}),bd=r.slice(2),h='<table><thead><tr>';
    hd.forEach(function(x){h+='<th>'+il(x.trim())+'</th>'});h+='</tr></thead><tbody>';
    bd.forEach(function(x){h+='<tr>';x.split('|').filter(function(c){return c.trim()}).forEach(function(c){h+='<td>'+il(c.trim())+'</td>'});h+='</tr>'});
    return h+'</tbody></table>';}
function mkL(its,t){var h='<'+t+'>';its.forEach(function(x){h+='<li>'+il(x.t)+'</li>'});return h+'</'+t+'>'}
function il(t){t=t.replace(/!\[([^\]]*)\]\(([^)]+)\)/g,'<img src="$2" alt="$1">');t=t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2">$1</a>');t=t.replace(/\[([^\]]+)\]\(file:\/\/([^)]+)\)/g,'<a title="$2">$1</a>');t=t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');t=t.replace(/\*(.+?)\*/g,'<em>$1</em>');t=t.replace(/`([^`]+)`/g,'<code>$1</code>');return t;}
document.getElementById('nav').innerHTML='<a class="pg" onclick="goHome()" style="padding-left:8px;font-weight:600">🏠 首页</a>'+buildNav();
document.getElementById('nav').addEventListener('click',function(e){var p=e.target.closest('.pg[data-p]');if(p){showPage(p.getAttribute('data-p'));return}var t=e.target.closest('.cat-hd');if(t)t.parentElement.classList.toggle('collapsed');});
document.getElementById('q').addEventListener('input',function(){var q=this.value.toLowerCase();document.querySelectorAll('.pg[data-p]').forEach(function(el){el.style.display=el.textContent.toLowerCase().includes(q)?'':'none'});document.querySelectorAll('.cat').forEach(function(g){if(!q){g.style.display='';return}var v=g.querySelectorAll('.pg[data-p]:not([style*="display: none"])');g.style.display=v.length?'':'none';});});
var bt=document.getElementById('bt');window.addEventListener('scroll',function(){bt.style.display=window.scrollY>300?'flex':'none'});bt.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'})});
var h=decodeURIComponent(location.hash.slice(1));if(h&&C[h])showPage(h);else goHome();
</script>
</body>
</html>'''

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(OUTPUT_FILE) // 1024
    print(f'Done! {OUTPUT_FILE}')
    print(f'Size: {size_kb} KB, Pages: {len(files)}, Categories: {len(cat_list)}')


if __name__ == '__main__':
    main()

import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createElement as h} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

let server,hub,contexts,editor;
before(async()=>{
 server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error'});
 hub=await server.ssrLoadModule('/src/features/visualization/AgentHub.tsx');
 contexts=await server.ssrLoadModule('/src/features/visualization/agentHubContext.ts');
 editor=await server.ssrLoadModule('/src/features/visualization/EditorWorkspace.tsx');
});
after(async()=>{await server?.close();});

function render({open=false,narrow=false,tab='work',error='',editing=false}={}){
 let actions=0;const noop=()=>{actions++;};
 const layout={open,narrow,tab,selectTab:noop,toggle:noop,close:noop,origin:{current:null}};
 const work={snapshot:{active:[{id:'synthetic-running',kind:'plan_semantics',status:'running',activity:{title:'合成局部修正',items:[]},phase:'只處理所選物件'}],history:[],history_total:0,unavailable:0},error,updated:null,now:Date.now(),page:0,loadedPage:0,setPage:noop,refresh:noop};
 const tasks={connection:null,busy:false,error:'',tests:[],candidates:[],check:noop,test:noop,stop:noop,addCandidate:noop};
 const body=h('div',{className:'studio-app'},h('header',null,h(hub.AgentTrigger)),h('textarea',{'aria-label':'未保存草稿',defaultValue:'keep my edits'}));
 const frame=editing?h(editor.EditorWorkspace,{editing:true},body):h(hub.AgentHubFrame,null,body);
 const html=renderToStaticMarkup(h(contexts.AgentLayoutContext.Provider,{value:layout},h(contexts.AgentModelContext.Provider,{value:{model:'saved-model',setModel:noop}},h(contexts.AgentActionsContext.Provider,{value:tasks},h(contexts.AgentWorkContext.Provider,{value:work},frame)))));
 return {html,actions};
}

test('one Agent entry owns work and settings with no task submissions during rendering',()=>{
 const {html,actions}=render();
 assert.equal((html.match(/data-agent-trigger=/g)||[]).length,1);
 assert.equal((html.match(/id="agent-hub-panel"/g)||[]).length,1);
 assert.match(html,/aria-label="1 進行中，0 等待"/);
 assert.match(html,/role="tab"[^>]*>工作/);
 assert.match(html,/role="tab"[^>]*>設定/);
 assert.match(html,/只處理所選物件/);
 assert.match(html,/value="saved-model" selected/);
 assert.equal(actions,0);
});

test('wide panel remains a sibling of live content, including in the fullscreen workspace',()=>{
 const {html}=render({open:true,editing:true});
 assert.match(html,/class="agent-hub-layout agent-is-open[^\"]*editor-workspace is-editing/);
 assert.match(html,/<div class="agent-hub-main"><div class="studio-app">/);
 assert.match(html,/textarea[^>]*>keep my edits<\/textarea>/);
 assert.ok(html.indexOf('id="agent-hub-panel"')>html.indexOf('class="agent-hub-main"'));
 assert.doesNotMatch(html,/aria-modal="true"/);
});

test('narrow takeover hides and inerts the main content without removing its draft',()=>{
 const {html}=render({open:true,narrow:true,tab:'settings'});
 assert.match(html,/<div class="agent-hub-main" hidden="" inert="">/);
 assert.match(html,/role="dialog" aria-modal="true"/);
 assert.match(html,/textarea[^>]*>keep my edits<\/textarea>/);
 assert.match(html,/id="agent-content-work"[^>]*hidden=""/);
 assert.doesNotMatch(html,/id="agent-content-settings"[^>]*hidden=""/);
 const closed=render({open:false,narrow:true,tab:'settings'}).html;
 assert.match(closed,/<div class="agent-hub-main">/);
 assert.match(closed,/<aside[^>]*id="agent-hub-panel"[^>]*hidden=""/);
});

test('an update failure preserves known work instead of replacing it with a fake zero',()=>{
 const {html}=render({error:'offline'});
 assert.match(html,/工作狀態更新失敗/);
 assert.match(html,/aria-label="1 進行中，0 等待"/);
 assert.match(html,/合成局部修正/);
 assert.match(html,/保留上次讀取結果/);
});

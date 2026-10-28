import test from 'node:test';
import assert from 'node:assert/strict';
import {elapsed,workCounts,workStatus,workSummary} from '../src/features/visualization/agentWorklistState.ts';

test('submitted work, stopping work and terminal outcomes have distinct labels',()=>{
 assert.deepEqual(workCounts([{status:'running'},{status:'stopping'},{status:'queued'}]),{running:2,queued:1});
 assert.equal(workStatus('passed'),'已完成');
 assert.equal(workStatus('interrupted'),'已中斷');
 assert.equal(workStatus('failed'),'失敗');
});
test('summary keeps the actual current phase visible even when another task is queued',()=>{
 assert.equal(workSummary({active:[{status:'queued'},{status:'running',phase:'原生來源核對'}]}),'原生來源核對');
 assert.equal(workSummary({active:[{status:'queued'}]}),'等待 Agent 工作槽');
 assert.match(workSummary(null),/讀取/);
 assert.match(workSummary({active:[]}),/沒有進行中/);
});
test('durations use saved timestamps and freeze on completion, without claiming unknown times',()=>{
 const start='2026-10-25T10:00:00Z';
 assert.equal(elapsed(start,Date.parse('2026-10-25T10:01:05Z')),'1 分 5 秒');
 assert.equal(elapsed(start,Date.parse('2026-10-25T11:02:00Z')),'1 小時 2 分');
 assert.equal(elapsed(start,Date.parse('2026-10-25T09:59:00Z')),'0 秒');
 assert.equal(elapsed(undefined),'時間未記錄');
 assert.equal(elapsed(start,NaN),'時間未記錄');
});

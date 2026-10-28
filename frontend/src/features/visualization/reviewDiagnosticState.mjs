export function reviewStatus(status){return ({passed:'通過',failed:'未通過',deferred:'前置條件不足，尚未檢查'})[status]||'尚無檢查紀錄';}
export function taskStatus(status){return ({passed:'處理完成',failed:'處理失敗',running:'處理中',queued:'等待處理',stopped:'已停止',interrupted:'已中斷'})[status]||'尚未處理';}
export function continuationBody(planRevision,reviewId,model,operationId){return {base_revision:planRevision,base_review_id:reviewId,model,operation_id:operationId,mode:'review',handoff:false,use_object_recognition:false};}

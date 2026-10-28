import type {AssetRequirements,ObjectGroup,PlacementConstraints} from './api';
export const purposes:Record<string,string>={dishwasher:'洗碗機',washer:'洗衣機',cooker:'爐具',fridge:'冰箱',sink:'水槽',toilet:'馬桶',vanity:'洗手台',shower:'淋浴設備',television:'電視',bunk_bed:'上下舖',nightstand:'床頭櫃',wardrobe:'衣櫃',bookcase:'書櫃',shoe_cabinet:'鞋櫃',dresser:'梳妝台',desk:'書桌',sofa:'沙發',chair:'椅子',bed:'床',cabinet:'收納櫃',table:'桌子',light:'燈具',vase:'花瓶',books:'書籍',cookware:'鍋具',tableware:'餐具',soap:'洗手用品',plant:'植栽',rug:'地毯'};
export default function AssetConstraints({group,onChange,onPlacement,onDraw,mode='all'}:{mode?:'all'|'matching'|'placement';group:ObjectGroup;onChange:(v:AssetRequirements)=>void;onPlacement:(v:PlacementConstraints|null)=>void;onDraw:(kind:'area'|'keep_out')=>void}){
 const value=group.asset_requirements||{purpose:'',dimension_source:'unknown',dimensions:null,evidence:''};
 const patch=(v:Partial<AssetRequirements>)=>onChange({...value,...v});
 const placement=group.placement_constraints||{area:null,max_distance:0,keep_out:[]};
 const rectangle=(r:[number,number,number,number],change:(v:[number,number,number,number])=>void)=>['最小 X','最小 Y','最大 X','最大 Y'].map((label,i)=><label key={label}>{label}（m）<input type="number" step="0.05" value={r[i]} onChange={e=>{const next:[number,number,number,number]=[...r];next[i]=Number(e.target.value);change(next);}}/></label>);
 return <details key={group.id} open={mode==='all'?undefined:true}><summary>{mode==='placement'?'自動移動範圍':'配對限制 · 用途與尺寸來源'}</summary>
 {mode!=='placement'&&<>
 <label>必要用途<select value={value.purpose} onChange={e=>patch({purpose:e.target.value})}><option value="">依原物件名稱辨識；不明時暫停</option>{Object.entries(purposes).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
 <label>尺寸來源<select value={value.dimension_source} onChange={e=>patch({dimension_source:e.target.value as AssetRequirements['dimension_source']})}><option value="unknown">來源未知（不自行放寬）</option><option value="confirmed">已確認尺寸（保留數字）</option><option value="envelope">可用範圍（上限）</option><option value="estimated">概念估計（仍不超出占位）</option></select></label>
 {['confirmed','envelope'].includes(value.dimension_source)&&<>{['寬','深','高'].map((label,i)=><label key={label}>{label}（公尺）<input type="number" min="0.001" step="0.01" value={value.dimensions?.[i]||''} onChange={e=>{const dims:[number,number,number]=[...(value.dimensions||[0,0,0])];dims[i]=Number(e.target.value);patch({dimensions:dims});}}/></label>)}</>}
 <label>尺寸來源紀錄<input value={value.evidence} placeholder="例如：業主確認、圖面 D12；不可自行宣稱已確認" onChange={e=>patch({evidence:e.target.value})}/></label>
 </>}
 {mode!=='matching'&&<details open={mode==='placement'?true:undefined}><summary hidden={mode==='placement'}>局部避碰 · 允許移動範圍</summary><p>世界平面座標（公尺）；只平移，不改家具尺寸或牆壁。沒有區域就不自動移動。碰撞檢查為保守外框，不等於完整動線驗收。</p>
 <button type="button" onClick={()=>onDraw('area')}>{placement.area?'重新框選允許區域':'在 2D 框選允許移動區域'}</button>{placement.area&&<button type="button" onClick={()=>onPlacement(null)}>取消自動移動區域</button>}
 {placement.area&&<>{mode==='placement'?<details><summary>精確座標</summary>{rectangle(placement.area,area=>onPlacement({...placement,area}))}</details>:rectangle(placement.area,area=>onPlacement({...placement,area}))}<label>最多平移（m，最高 0.5）<input type="number" min="0" max="0.5" step="0.05" value={placement.max_distance} onChange={e=>onPlacement({...placement,max_distance:Number(e.target.value)})}/></label>
 <p>不可侵犯區域：門扇開啟範圍／通道</p>{placement.keep_out.map((zone,i)=><fieldset key={i}><legend>保留區 {i+1}</legend>{mode==='placement'?<details><summary>精確座標</summary>{rectangle(zone,v=>onPlacement({...placement,keep_out:placement.keep_out.map((z,j)=>i===j?v:z)}))}</details>:rectangle(zone,v=>onPlacement({...placement,keep_out:placement.keep_out.map((z,j)=>i===j?v:z)}))}<button onClick={()=>onPlacement({...placement,keep_out:placement.keep_out.filter((_,j)=>i!==j)})}>移除保留區</button></fieldset>)}<button disabled={placement.keep_out.length>=50} onClick={()=>onDraw('keep_out')}>在 2D 框選通道／門區</button></>}
 </details>}
 <small>必要家具不會因找不到素材而刪除。用途不符會跳過，尺寸不明保留原件；修改後請保存再配對。</small></details>;
}

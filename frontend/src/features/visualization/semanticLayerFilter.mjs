export const semanticLayers=[['all','全部'],['rooms','用途區域'],['walls','牆體'],['floors','地坪'],['openings','門窗'],['furniture','家具'],['equipment','設備'],['lighting','燈具'],['decoration','裝飾物'],['other','其他']];
export const categoryNames={floor_surface:'地坪',plant:'植栽',rug:'地毯',curtain:'窗簾',art:'掛畫',mirror:'鏡子',decor:'擺飾',air_conditioner:'空調',switch:'開關',socket:'插座',vent:'通風口',column:'柱體',wall_junction:'牆體交接',beam:'梁',room:'用途區域',wall:'牆體',door:'門',window:'窗',cabinet:'櫃子',chair:'椅子',table:'桌子',television:'電視',toilet:'馬桶',kitchen:'廚房用具',bed:'床',sofa:'沙發',sink:'洗手台／水槽',shower:'淋浴／浴缸',appliance:'家電',other:'其他家具',wall_light:'壁燈',ceiling:'天花燈',pendant:'吊燈',track:'軌道燈',floor:'落地燈',unknown:'其他燈具',annotation:'原圖燈具註記'};
export function filterSemanticItems(items,layer,category='all'){
 return items.filter(item=>(layer==='all'?item.status!=='annotation':item.layer===layer)&&(category==='all'||item.category===category));
}
export function semanticCategories(items,layer){
 const counts=new Map();
 for(const item of filterSemanticItems(items,layer))counts.set(item.category,(counts.get(item.category)||0)+1);
 return [...counts].map(([key,count])=>({key,name:categoryNames[key]||key,count}));
}
export function semanticItemBox(item){
 const xs=item.points.map(p=>p[0]),ys=item.points.map(p=>p[1]);
 return [Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)];
}

export const semanticCategoryKey=item=>`${item.layer}:${item.category}`;
/** @param {any[]} items @param {string[] | null} selection */
export function filterSemanticSelection(items,selection=null){
 const keys=selection===null?null:new Set(selection);
 return items.filter(item=>keys===null?item.status!=='annotation'&&item.layer!=='floors':keys.has(semanticCategoryKey(item)));
}
export function semanticSelectionGroups(items){
 return semanticLayers.filter(([id])=>id!=='all').map(([id,name])=>{
  const counts=new Map();
  for(const item of items.filter(item=>item.layer===id)){
   const key=semanticCategoryKey(item),entry=counts.get(key)||{key,name:categoryNames[item.category]||item.category,count:0};
   entry.count++;counts.set(key,entry);
  }
  return {id,name,options:[...counts.values()]};
 }).filter(group=>group.options.length);
}
export function toggleSemanticKeys(items,selection,keys,checked){
 const next=new Set(selection??filterSemanticSelection(items).map(semanticCategoryKey));
 for(const key of keys)if(checked)next.add(key);else next.delete(key);
 return [...next];
}

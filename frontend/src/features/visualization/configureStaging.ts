// Both buttons use the same proposal/apply path; preview never adopts a scene.
export async function configureStaging<P extends {items:{id:string}[];lights:unknown[]},R,B>(flow:{
 save:()=>Promise<string|null|undefined>;propose:(revision:string)=>Promise<P>;show:(proposal:P)=>void;
 apply:(proposal:P,revision:string)=>Promise<{revision:R;batch:B|null}>;
 accept:(result:{revision:R;batch:B|null})=>void;automatic:boolean;
}){
 const revision=await flow.save();
 if(!revision)throw new Error('請先保存設計');
 const proposal=await flow.propose(revision);flow.show(proposal);
 if(flow.automatic&&(proposal.items.length||proposal.lights.length))flow.accept(await flow.apply(proposal,revision));
}

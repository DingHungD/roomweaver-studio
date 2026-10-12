import type {ReactNode} from 'react';

export default function EditorToolbar({views,actions,children,label='空間檢視方式'}:{views:ReactNode;actions:ReactNode;children?:ReactNode;label?:string}){
  return <><div className="editor-toolbar"><div className="space-navigation" role="tablist" aria-label={label}>{views}</div><div className="editor-toolbar-actions" role="group" aria-label="編輯操作">{actions}</div></div>{children&&<div className="editor-toolbar-secondary">{children}</div>}</>;
}

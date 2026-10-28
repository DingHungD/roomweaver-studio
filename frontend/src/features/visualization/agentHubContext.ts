import {createContext,useContext} from 'react';
import type {Dispatch,RefObject,SetStateAction} from 'react';
import type {Connection,Task} from './api';
import type {AgentWorkSnapshot} from './agentWorklistState';

export type AgentTab='work'|'settings';
export type AgentLayout={open:boolean;tab:AgentTab;narrow:boolean;selectTab:(tab:AgentTab)=>void;toggle:(origin:HTMLButtonElement)=>void;close:()=>void;origin:RefObject<HTMLButtonElement|null>};
export type CandidateWork={task:Task;project:string;revision:string|null};
export type AgentActions={connection:Connection|null;busy:boolean;error:string;tests:Task[];candidates:CandidateWork[];check:()=>Promise<void>;test:(kind:string)=>Promise<void>;stop:(id:string)=>Promise<void>;addCandidate:(project:string,revision:string|null,task:Task)=>void};
export type AgentWorkState={snapshot:AgentWorkSnapshot|null;error:string;updated:string|null;now:number;page:number;loadedPage:number|null;setPage:(page:number)=>void;refresh:()=>void};
export const AgentLayoutContext=createContext<AgentLayout|null>(null);
export const AgentModelContext=createContext<{model:string;setModel:Dispatch<SetStateAction<string>>}|null>(null);
export const AgentActionsContext=createContext<AgentActions|null>(null);
export const AgentWorkContext=createContext<AgentWorkState|null>(null);
export const useOptionalAgentLayout=()=>useContext(AgentLayoutContext);
export function useAgentLayout(){const value=useOptionalAgentLayout();if(!value)throw new Error('AgentHubProvider is required');return value;}
export function useAgentModel(){const value=useContext(AgentModelContext);if(!value)throw new Error('AgentHubProvider is required');return value;}
export function useAgentActions(){const value=useContext(AgentActionsContext);if(!value)throw new Error('AgentHubProvider is required');return value;}
export function useAgentWork(){const value=useContext(AgentWorkContext);if(!value)throw new Error('AgentHubProvider is required');return value;}

"use client";
import { create } from "zustand";

export type View="command"|"data"|"strategy"|"combination"|"replay"|"patterns"|"robustness"|"trades"|"playbook"|"automation";
type LabState={view:View;variant:string;risk:number;target:number;slippage:number;balance:number;overview:Record<string,any>|null;dataStatus:Record<string,any>|null;setView:(v:View)=>void;set:(patch:Partial<LabState>)=>void};
export const useLab=create<LabState>(set=>({view:"command",variant:"A1",risk:.5,target:2,slippage:1,balance:100000,overview:null,dataStatus:null,setView:view=>set({view}),set:patch=>set(patch)}));

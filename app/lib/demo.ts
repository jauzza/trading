export type Candle = { time: number; open: number; high: number; low: number; close: number; volume: number };
export type TradeRow = { id:string; date:string; strategy:string; variant:string; side:"Long"|"Short"; contracts:number; entry:number; stop:number; target:number; net:number; r:number; outcome:string; regime:string; reason:string };

export function candles(seed=17): Candle[] {
  let value=18482.25, state=seed;
  const start=Date.UTC(2025,9,14,12,30)/1000;
  const random=()=>{state=(state*1664525+1013904223)>>>0;return state/4294967296};
  return Array.from({length:390},(_,i)=>{const open=value; const shock=(random()-.49)*(i<70?13:8)+Math.sin(i/17)*1.1; const close=open+shock; const high=Math.max(open,close)+random()*4.5; const low=Math.min(open,close)-random()*4.5; value=close; return {time:start+i*60,open:+open.toFixed(2),high:+high.toFixed(2),low:+low.toFixed(2),close:+close.toFixed(2),volume:Math.round(400+random()*1700)};});
}

export const equityYears=["2018","2019","2020","2021","2022","2023","2024","2025"];
export const equitySeries={
  a:[100,104,101,111,107,119,121,128,125,137,141,146,143,151,158,163],
  b:[100,98,105,109,117,113,124,132,129,136,145,143,151,156,154,161],
  c:[100,104,109,116,121,128,136,144,151,159,168,176,185,193,204,213],
};

const names=["10:00 level","5m + EMA","Directional confluence","First-candle baseline"];
const variantLabels=["A1 · Faithful","B2 · Breakout","C3 · Agreement","B0 · Control"];
const outcomes=["Target","Stop","Time exit","Target","Target","Rejected"];
export const trades:TradeRow[]=Array.from({length:42},(_,i)=>{const long=i%3!==1;const entry=18120+i*11.75;const stop=entry+(long?-24:24);const target=entry+(long?48:-48);const outcome=outcomes[i%outcomes.length];const r=outcome==="Target"?1.92:outcome==="Stop"?-1.08:outcome==="Rejected"?0:+(.15+(i%5)*.11).toFixed(2);return {id:`OT-25-${String(i+1).padStart(4,"0")}`,date:`2025-${String((i%9)+1).padStart(2,"0")}-${String((i*3%25)+1).padStart(2,"0")} 10:${String((i*7)%60).padStart(2,"0")}`,strategy:names[i%4],variant:variantLabels[i%4],side:long?"Long":"Short",contracts:(i%4)+1,entry:+entry.toFixed(2),stop:+stop.toFixed(2),target:+target.toFixed(2),net:outcome==="Rejected"?0:+(r*420-18.6).toFixed(2),r, outcome,regime:["High vol","Trend up","Balanced","News proximity"][i%4],reason:outcome==="Rejected"?"One contract exceeded the strict risk budget":"Confirmed signal; next observable event fill"};});

export const variants=[
  {id:"A1",name:"Faithful sweep → displacement → retest",trades:142,expectancy:.31,dd:-11.4,oos:.09,label:"Discretionary structure"},
  {id:"A2",name:"Mechanical level rejection",trades:496,expectancy:.12,dd:-18.7,oos:-.03,label:"Up to 3 attempts"},
  {id:"B1",name:"Immediate 09:35 directional",trades:701,expectancy:.06,dd:-22.1,oos:-.08,label:"Overnight EMA"},
  {id:"B2",name:"First-candle breakout",trades:386,expectancy:.18,dd:-15.9,oos:.04,label:"Next-event entry"},
  {id:"B3",name:"Breakout + retest",trades:207,expectancy:.23,dd:-13.2,oos:.07,label:"Confirmed retest"},
  {id:"C3",name:"Directional confluence",trades:84,expectancy:.37,dd:-8.8,oos:.11,label:"A agrees with B"},
];

export const months=[[-.3,.2,.8,.1,.4,-.2,.5,.7,.1,-.4,.2,.6],[.1,.4,-.2,.3,.7,.2,-.1,.5,.4,.3,-.2,.8],[.6,-.1,.3,.5,.2,.4,.8,-.3,.1,.6,.3,-.1],[.2,.5,.1,-.2,.6,.7,.4,.2,-.1,.3,.5,.4],[.4,.2,.6,.3,-.1,.5,.2,.8,.4,-.2,.3,.7],[-.2,.3,.1,.5,.4,-.1,.6,.2,.7,.1,.4,.3],[.3,.1,.4,.2,.5,.3,-.2,.6,.1,.4,.2,.5],[.2,-.1,.3,.1,.4,.2,.5,-.2,.3,.1,.4,.2]];

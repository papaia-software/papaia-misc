export type Row = Record<string, any>;
export async function api<T=Row>(path:string,options:RequestInit={}):Promise<T>{
  const isForm=options.body instanceof FormData;
  const response=await fetch('/api'+path,{credentials:'include',...options,headers:{...(!isForm?{'Content-Type':'application/json'}:{}),...options.headers}});
  if(!response.ok){const body=await response.json().catch(()=>({}));const details=body.error?.details?.map((e:Row)=>`${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ');throw new Error(details||body.error?.message||`Erro HTTP ${response.status}`);}
  return response.status===204?undefined as T:response.json();
}
export const send=(method:string,body?:unknown):RequestInit=>({method,body:body===undefined?undefined:JSON.stringify(body)});
export const stages=['Descoberto','Em análise','Qualificado','Contato pendente','Contatado','Respondeu','Em negociação','Parceria fechada','Parceria concluída','Descartado'];
export const categories=['Lançamento de produto','Nova funcionalidade','Parceria','Campanha de marketing','Investimento','Expansão','Alteração comercial','Atualização institucional','Tendência de mercado','Outros'];
export const fmt=(v:unknown,suffix='')=>v===null||v===undefined?'Não disponível':typeof v==='number'?v.toLocaleString('pt-BR')+suffix:String(v)+suffix;
export const date=(v:string|undefined)=>v?new Date(v).toLocaleDateString('pt-BR'):'Não disponível';

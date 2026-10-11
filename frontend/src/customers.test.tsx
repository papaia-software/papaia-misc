import { render,screen,waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient,QueryClientProvider } from '@tanstack/react-query';
import { expect,it,vi } from 'vitest';
import { CustomersPage,customerPayload } from './customers';
function mount(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><CustomersPage/></QueryClientProvider>);}
function response(data:unknown){return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});}
it('cadastra um cliente sem inventar sinais ou seguidores',async()=>{
 let payload:any;const user=userEvent.setup();
 vi.stubGlobal('fetch',vi.fn(async(url,options)=>{if(options?.method==='POST'){payload=JSON.parse(options.body);return response({id:1,...payload});}return response(String(url).endsWith('/summary')?{total:0,qualified:0,trial:0,subscribers:0}:{items:[],total:0});}));
 mount();await user.click(screen.getByRole('button',{name:'Novo potencial cliente'}));
 await user.type(screen.getByLabelText(/^Nome/),'Teste');await user.type(screen.getByLabelText(/^Username/),'teste');await user.type(screen.getByLabelText(/^URL do perfil/),'https://example.org/teste');
 await user.click(screen.getByRole('button',{name:'Salvar registro'}));
 await waitFor(()=>expect(payload).toMatchObject({name:'Teste',stage:'Novo',platform:'Instagram'}));expect(payload.followers).toBeUndefined();expect(payload.expressed_interest).toBeUndefined();
});
it('distingue desconhecido, sim e não na avaliação manual',()=>{
 expect(customerPayload({offers_consultations:'unknown',expressed_interest:'false'})).toEqual({offers_consultations:null,expressed_interest:false});expect(customerPayload({offers_consultations:'true'}).offers_consultations).toBe(true);
});
it('prepara pesquisa pública sem apresentar extração automática',async()=>{
 const user=userEvent.setup();vi.stubGlobal('fetch',vi.fn(async(url,options)=>response(options?.method==='POST'?{message:'Pesquisa manual, sem coleta',searches:[{query:'nutricionista',url:'https://www.google.com/search?q=nutricionista'}],local_matches:[]}:String(url).endsWith('/summary')?{total:0}:{items:[],total:0})));
 mount();await user.click(screen.getByRole('button',{name:'Encontrar perfis'}));await user.click(screen.getByRole('button',{name:'Preparar pesquisa'}));expect(await screen.findByText('Pesquisa manual, sem coleta')).toBeInTheDocument();expect(screen.getByRole('link',{name:'nutricionista'})).toHaveAttribute('href','https://www.google.com/search?q=nutricionista');
});

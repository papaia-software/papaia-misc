import { render,screen,waitFor,fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient,QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe,it,expect,vi } from 'vitest';
import App from './App';
import { Influencers,Pipeline } from './influencers';
import { NewsPage } from './market';
import { api } from './api';

function wrap(node:React.ReactNode,path='/'){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><MemoryRouter initialEntries={[path]}>{node}</MemoryRouter></QueryClientProvider>);}
function respond(data:unknown,status=200){return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});}
const profile={id:1,name:'Perfil fictício de teste',stage:'Descoberto',niches:[],profiles:[{username:'teste',platform:'Instagram',metrics:{followers:null,engagement:null}}],score:null};
describe('Fluxos principais',()=>{
 it('protege o workspace e permite login com erro visível',async()=>{
  const user=userEvent.setup();
  vi.stubGlobal('fetch',vi.fn(async(url,options)=>{if(String(url).endsWith('/auth/me'))return respond({error:{message:'Autenticação necessária'}},401);return respond({error:{message:'E-mail ou senha inválidos'}},401);}));
  wrap(<App/>);
  await screen.findByText('Entre no seu workspace');
  await user.type(screen.getByLabelText('E-mail'),'teste@example.org');
  await user.type(screen.getByLabelText('Senha'),'senhaerrada');
  await user.click(screen.getByRole('button',{name:/Acessar workspace/}));
  expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha inválidos');
 });
 it('cadastra influenciador com payload real e invalida a listagem',async()=>{
  const user=userEvent.setup();let payload:any;
  vi.stubGlobal('fetch',vi.fn(async(url,options)=>{if(options?.method==='POST'){payload=JSON.parse(options.body);return respond(profile,201);}return respond({items:[],total:0});}));
  wrap(<Influencers/>,'/influencers');
  await user.click(screen.getByRole('button',{name:'Novo influenciador'}));
  await user.type(screen.getByLabelText(/^Nome/),'Teste');
  await user.type(screen.getByLabelText(/^Username/),'teste');
  await user.type(screen.getByLabelText(/^URL pública do perfil/),'https://example.org/teste');
  await user.click(screen.getByRole('button',{name:'Salvar registro'}));
  await waitFor(()=>expect(payload).toMatchObject({name:'Teste',username:'teste',platform:'Instagram',url:'https://example.org/teste'}));
  expect(payload.followers).toBeUndefined();
 });
 it('mostra métricas ausentes sem inventar valores',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>respond({items:[profile],total:1})));
  wrap(<Influencers/>,'/influencers');
  expect(await screen.findByText('Perfil fictício de teste')).toBeInTheDocument();
  expect(screen.getAllByText('Não disponível')).toHaveLength(2);
  expect(screen.getByText('Não avaliado')).toBeInTheDocument();
 });
 it('move cards no pipeline usando uma ação acessível',async()=>{
  const user=userEvent.setup();let patch:any;
  vi.stubGlobal('fetch',vi.fn(async(url,options)=>{if(options?.method==='PATCH'){patch=JSON.parse(options.body);return respond({...profile,...patch});}return respond({items:[profile],total:1});}));
  wrap(<Pipeline/>,'/negotiations');
  const select=await screen.findByLabelText('Etapa de Perfil fictício de teste');
  await user.selectOptions(select,'Qualificado');
  await waitFor(()=>expect(patch).toEqual({stage:'Qualificado'}));
 });
 it('expõe falha de RSS sem substituir por notícias fictícias',async()=>{
  const user=userEvent.setup();
  vi.stubGlobal('fetch',vi.fn(async(url,options)=>options?.method==='POST'?respond({status:'failed',imported:0,error:'Fonte indisponível'}):respond({items:[],total:0})));
  wrap(<NewsPage/>,'/news');
  await user.click(screen.getByRole('button',{name:'Atualizar notícias'}));
  expect(await screen.findByText(/Fonte indisponível/)).toBeInTheDocument();
  expect(screen.getByText('Seu feed de inteligência está pronto')).toBeInTheDocument();
 });
 it('mantém tokens de integração fora do fluxo de cadastro',async()=>{
  const user=userEvent.setup();
  vi.stubGlobal('fetch',vi.fn(async(url)=>String(url).includes('integrations')?respond({providers:[{name:'Apify dataset',status:'pending'}]}):respond({items:[],total:0})));
  wrap(<Influencers/>,'/influencers');
  await user.click(screen.getByRole('button',{name:'Prospectar'}));
  expect(await screen.findByText(/Integração pendente/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Revisar busca'})).toBeDisabled();
 });
});

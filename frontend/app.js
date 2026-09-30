const $=id=>document.getElementById(id);
let token=null,role=null,user=null,advSel=0,advData=[];

/* ---------- veilige HTML ----------
   h`...` escapet ELKE ingevoegde waarde automatisch; enkel andere h`...`-resultaten
   worden als HTML doorgelaten. render() is het enige punt dat HTML in de pagina zet:
   via DOMParser (voert geen scripts uit) en replaceChildren. */
class Safe{constructor(s){this.s=s}}
const escHTML=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const enc=v=>v instanceof Safe?v.s:Array.isArray(v)?v.map(enc).join(""):escHTML(v);
const h=(strs,...vals)=>new Safe(strs.reduce((out,s,i)=>out+s+(i<vals.length?enc(vals[i]):""),""));
function render(el,safe){
 if(!(safe instanceof Safe))throw new TypeError("render verwacht h`...`");
 const doc=new DOMParser().parseFromString(`<!doctype html><body>${safe.s}</body>`,"text/html");
 el.replaceChildren(...doc.body.childNodes)}

async function api(path,opts={}){
 const r=await fetch(path,{...opts,headers:{"Content-Type":"application/json",...(token?{Authorization:"Bearer "+token}:{})}});
 if(r.status===401&&token){logout();throw new Error("Sessie verlopen")}
 const d=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(typeof d.detail==="string"?d.detail:"Er ging iets mis");
 return d}

/* ---------- login ---------- */
document.querySelectorAll("[data-u]").forEach(b=>b.onclick=()=>{$("u").value=b.dataset.u;$("pw").focus()});
$("loginForm").onsubmit=async e=>{e.preventDefault();$("lerr").textContent="";
 try{const u=$("u").value.trim();const d=await api("/api/login",{method:"POST",body:JSON.stringify({username:u,password:$("pw").value})});
  token=d.token;role=d.role;user=d.name;$("pw").value="";start()}catch(err){$("lerr").textContent=err.message}};
function logout(){if(token)fetch("/api/logout",{method:"POST",headers:{Authorization:"Bearer "+token}}).catch(()=>{});
 token=null;role=null;user=null;$("appView").hidden=true;$("session").hidden=true;$("loginView").hidden=false}
$("logout").onclick=logout;

async function start(){$("loginView").hidden=true;$("appView").hidden=false;$("session").hidden=false;
 $("customerView").hidden=role!=="customer";$("advisorView").hidden=role!=="advisor";
 const nm=user||"";
 $("av").textContent=nm.charAt(0);
 render($("who"),h`<b>${nm}</b>${role==="advisor"?"Adviseur":"Klant"}`);
 try{if(role==="customer")renderCustomer(await api("/api/me"));
  else{advData=await api("/api/advisor/clients");advSel=0;renderAdvisor()}}
 catch(err){if(token)$("cerr").textContent=err.message}
 loadStats()}

/* ---------- timing: het juiste moment ---------- */
function timingBlock(t){if(!t)return"";
 return h`<div class="when"><span class="label">Gepland</span><b>${t.label}</b><small>${t.why}</small>${t.held?h`<small class="held">${t.held}</small>`:""}</div>`}

/* ---------- gedeelde bouwstenen (klant en adviseur) ---------- */
const whyItems=why=>why.map(w=>h`<li>${w.label}<small>${w.evidence}</small></li>`);
const chips=(m,...extra)=>h`<div class="meta"><span class="chip">Kanaal: ${m.channel}</span><span class="chip">Toon: ${m.tone}</span>${extra.map(x=>h`<span class="chip">${x}</span>`)}</div>`;

/* ---------- klant ---------- */
function momentBlock(v){
 const pct=Math.round(v.score*100);
 $("mt").textContent=v.active?v.moment.title:"Geen duidelijk moment";
 $("cl").textContent="Zekerheid "+pct+"%";$("cb").style.width=pct+"%";}

function renderPhone(v){
 const t=v.timing,when=t?new Date(t.date+"T00:00:00"):new Date();
 const hh=t?String(t.hour).padStart(2,"0")+":00":String(when.getHours()).padStart(2,"0")+":"+String(when.getMinutes()).padStart(2,"0");
 const head=h`<div class="clock">${hh}</div><div class="date">${when.toLocaleDateString("nl-BE",{weekday:"long",day:"numeric",month:"long"})}</div>`;
 let body;
 if(!v.active)body=h`<div class="empty">Geen melding.<br>Liever niets dan een verkeerd bericht.</div>`;
 else if(/geen app-melding/i.test(v.moment.channel))body=h`<div class="empty">Geen app-melding.<br>Je adviseur neemt persoonlijk contact op.</div>`;
 else body=h`<div class="notif"><div class="app"><i>KBC</i> KBC Mobile · nu</div><b>${v.moment.action}</b>${v.message.text}</div>`;
 render($("phone"),h`${head}${body}`)}

function renderCustomer(v){
 $("cname").textContent=v.customer.name+", "+v.customer.age;$("cdesc").textContent=v.customer.desc;
 render($("sigs"),h`${v.signals.map(s=>h`<label class="sig ${s.consent&&s.present?"":"off"}"><input type="checkbox" data-s="${s.key}" ${s.consent?h`checked`:""}><span>${s.label}</span><span class="tag ${s.present?"yes":""}">${s.present?"aanwezig":"n.v.t."}</span></label>`)}`);
 momentBlock(v);renderPhone(v);
 const bub=$("bub");bub.className="bubble"+(v.active?"":" none");
 if(v.active){
  const src=v.message.source==="taalmodel"?"Gepersonaliseerd door taalmodel":"Standaardtekst";
  render(bub,h`<b>${v.moment.action}</b>${v.message.text}${chips(v.moment,src)}${timingBlock(v.timing)}`);
  render($("acts"),h`<button class="btn small ghost" id="wrong" data-m="${v.moment.key}">Klopt niet voor mij</button>`);
  render($("why"),h`<div class="w">Dit zijn de signalen die meetellen, met het bewijs:</div><ul>${whyItems(v.why)}</ul>`);
 }else{
  render(bub,h`<b>Er wordt niets gestuurd</b>${v.score>=.5?"Het doorslaggevende signaal ontbreekt, of je gaf er geen toestemming voor.":"De zekerheid is te laag (minder dan 50%)."} Liever geen bericht dan een verkeerd bericht.`);
  render($("acts"),v.suppressed.length?h`<button class="btn small ghost" id="reset">Eerder voorstel opnieuw tonen</button>`:h``);
  render($("why"),h`<div class="w">${v.suppressed.length?"Je gaf aan dat een eerder voorstel niet klopte. Dat onthouden we. ":""}${v.score>=.5?"Een moment wordt pas herkend als het doorslaggevende signaal meetelt, zoals een eerste loon of een woonlening-simulatie.":"Er zijn te weinig signalen met toestemming om een moment te herkennen."}</div>`)}}

/* Elke actie: toon de serverstaat. Bij een fout de melding tonen en opnieuw ophalen,
   zodat een vinkje nooit iets anders toont dan wat de server bewaarde. */
async function act(path,opts){$("cerr").textContent="";
 try{renderCustomer(await api(path,opts))}
 catch(err){if(!token)return;$("cerr").textContent=err.message;
  try{renderCustomer(await api("/api/me"))}catch{}}}
$("sigs").onchange=e=>{const s=e.target.dataset.s;if(!s)return;
 act("/api/me/consent",{method:"PUT",body:JSON.stringify({signal:s,enabled:e.target.checked})})};
$("acts").onclick=e=>{
 if(e.target.id==="wrong")act("/api/me/feedback",{method:"POST",body:JSON.stringify({moment:e.target.dataset.m})});
 if(e.target.id==="reset")act("/api/me/reset",{method:"POST"})};

/* ---------- adviseur ---------- */
function renderAdvisor(){
 render($("clients"),h`${advData.map((c,i)=>h`<button aria-pressed="${i===advSel}" data-i="${i}">${c.customer.name}, ${c.customer.age}<small>${c.active?c.moment.title:"Geen moment"}</small></button>`)}`);
 const c=advData[advSel];if(!c){render($("abrief"),h`<p>Geen klanten toegewezen.</p>`);return}
 const pct=Math.round(c.score*100);
 render($("abrief"),h`<div class="moment"><div><span class="label">Briefing voor je gesprek met ${c.customer.name}</span><h3>${c.active?c.moment.title:"Geen duidelijk moment"}</h3></div><div class="conf"><span>Zekerheid ${pct}%</span><div class="bar"><i id="abar"></i></div></div></div>
 <div class="bubble ${c.active?"":"none"}"><b>${c.active?"Voorgestelde aanpak: "+c.moment.action:"Geen actie nodig"}</b>${c.active?h`${chips(c.moment)}${timingBlock(c.timing)}`:"Laat deze klant met rust tot er een duidelijk moment is."}</div>
 <div class="why"><h2 class="sub">Waarom</h2><ul>${c.why.length?whyItems(c.why):h`<li>Geen signalen met toestemming</li>`}</ul></div>`);
 $("abar").style.width=pct+"%"}
$("clients").onclick=e=>{const b=e.target.closest("button");if(b){advSel=+b.dataset.i;renderAdvisor()}};

/* ---------- schaal ---------- */
async function loadStats(){try{const s=await api("/api/stats");
 render($("stats"),h`<div><b>${s.customers.toLocaleString("nl-BE")}</b><span>klanten geanalyseerd</span></div>
 <div><b>${s.ms} ms</b><span>detectie, 1 CPU-kern</span></div>
 <div><b>${s.trigger_rate}%</b><span>met een moment, de rest krijgt niets</span></div>
 ${s.moments.map(m=>h`<div><b>${m.count}</b><span>${m.title}</span></div>`)}
 <div><b>±${s.projected_seconds_2_3m} s</b><span>geschat voor 2,3 miljoen klanten</span></div>`);
 const p=Math.max(.5,Math.min(10,Math.round(s.trigger_rate*2)/2));$("p").value=p;scale()}catch(e){render($("stats"),h`<div><span>${e.message}</span></div>`)}}
const eur=v=>"€"+v.toLocaleString("nl-BE",{maximumFractionDigits:v<100?2:0});
function scale(){const n=+$("n").value,p=+$("p").value;
 const tr=n*p/100,naive=n*.002,ours=n*.00001+tr*.002;
 $("no").textContent=n.toLocaleString("nl-BE");$("po").textContent=p+"% ("+Math.round(tr).toLocaleString("nl-BE")+" klanten)";
 $("c1").textContent=eur(naive)+" per dag";$("c2").textContent=eur(ours)+" per dag";
 const mx=2300000*.002;$("b1").style.width=naive/mx*100+"%";$("b2").style.width=Math.max(ours/mx*100,1)+"%";
 $("sum").textContent="Ongeveer "+Math.round(naive/ours)+"x goedkoper, met dezelfde uitleg per klant.";}
$("n").oninput=$("p").oninput=scale;scale();

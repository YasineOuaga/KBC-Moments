const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let token=null,role=null,user=null,advSel=0,advData=[];

async function api(path,opts={}){
 const r=await fetch(path,{...opts,headers:{"Content-Type":"application/json",...(token?{Authorization:"Bearer "+token}:{})}});
 if(r.status===401&&token){logout();throw new Error("Sessie verlopen")}
 const d=await r.json().catch(()=>({}));
 if(!r.ok)throw new Error(d.detail||"Er ging iets mis");
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
 $("who").innerHTML=`<b>${esc(nm)}</b>${role==="advisor"?"Adviseur":"Klant"}`;
 if(role==="customer")renderCustomer(await api("/api/me"));
 else{advData=await api("/api/advisor/clients");advSel=0;renderAdvisor()}
 loadStats()}

/* ---------- timing: het juiste moment ---------- */
function timingBlock(t){if(!t)return"";
 return `<div class="when"><span class="label">Gepland</span><b>${esc(t.label)}</b><small>${esc(t.why)}</small>${t.held?`<small class="held">${esc(t.held)}</small>`:""}</div>`}

/* ---------- klant ---------- */
function momentBlock(v){
 const pct=Math.round(v.score*100);
 $("mt").textContent=v.active?v.moment.title:"Geen duidelijk moment";
 $("cl").textContent="Zekerheid "+pct+"%";$("cb").style.width=pct+"%";}

function renderPhone(v){
 const t=v.timing,when=t?new Date(t.date+"T00:00:00"):new Date();
 const hh=t?String(t.hour).padStart(2,"0")+":00":String(when.getHours()).padStart(2,"0")+":"+String(when.getMinutes()).padStart(2,"0");
 const head=`<div class="clock">${esc(hh)}</div><div class="date">${esc(when.toLocaleDateString("nl-BE",{weekday:"long",day:"numeric",month:"long"}))}</div>`;
 let body;
 if(!v.active)body=`<div class="empty">Geen melding.<br>Liever niets dan een verkeerd bericht.</div>`;
 else if(/geen app-melding/i.test(v.moment.channel))body=`<div class="empty">Geen app-melding.<br>Je adviseur neemt persoonlijk contact op.</div>`;
 else body=`<div class="notif"><div class="app"><i>KBC</i> KBC Mobile · nu</div><b>${esc(v.moment.action)}</b>${esc(v.message.text)}</div>`;
 $("phone").innerHTML=head+body}

function renderCustomer(v){
 $("cname").textContent=v.customer.name+", "+v.customer.age;$("cdesc").textContent=v.customer.desc;
 $("sigs").innerHTML=v.signals.map(s=>`<label class="sig ${s.consent&&s.present?"":"off"}"><input type="checkbox" data-s="${esc(s.key)}" ${s.consent?"checked":""}><span>${esc(s.label)}</span><span class="tag ${s.present?"yes":""}">${s.present?"aanwezig":"n.v.t."}</span></label>`).join("");
 momentBlock(v);renderPhone(v);
 const bub=$("bub");bub.className="bubble"+(v.active?"":" none");
 if(v.active){
  const src=v.message.source==="taalmodel"?"Gepersonaliseerd door taalmodel":"Standaardtekst";
  bub.innerHTML=`<b>${esc(v.moment.action)}</b>${esc(v.message.text)}<div class="meta"><span class="chip">Kanaal: ${esc(v.moment.channel)}</span><span class="chip">Toon: ${esc(v.moment.tone)}</span><span class="chip">${src}</span></div>${timingBlock(v.timing)}`;
  $("acts").innerHTML=`<button class="btn small ghost" id="wrong" data-m="${esc(v.moment.key)}">Klopt niet voor mij</button>`;
  $("why").innerHTML=`<div class="w">Dit zijn de signalen die meetellen, met het bewijs:</div><ul>${v.why.map(w=>`<li>${esc(w.label)}<small>${esc(w.evidence)}</small></li>`).join("")}</ul>`;
 }else{
  bub.innerHTML=`<b>Er wordt niets gestuurd</b>De zekerheid is te laag (minder dan 50%). Liever geen bericht dan een verkeerd bericht.`;
  $("acts").innerHTML=(v.suppressed.length||v.signals.some(s=>!s.consent))?`<button class="btn small ghost" id="reset">Alles terugzetten</button>`:"";
  $("why").innerHTML=`<div class="w">${v.suppressed.length?"Je gaf aan dat een eerder voorstel niet klopte. Dat onthouden we. ":""}Er zijn te weinig signalen met toestemming om een moment te herkennen.</div>`}}

$("sigs").onchange=async e=>{const s=e.target.dataset.s;if(!s)return;
 renderCustomer(await api("/api/me/consent",{method:"PUT",body:JSON.stringify({signal:s,enabled:e.target.checked})}))};
$("acts").onclick=async e=>{
 if(e.target.id==="wrong")renderCustomer(await api("/api/me/feedback",{method:"POST",body:JSON.stringify({moment:e.target.dataset.m})}));
 if(e.target.id==="reset")renderCustomer(await api("/api/me/reset",{method:"POST"}))};

/* ---------- adviseur ---------- */
function renderAdvisor(){
 $("clients").innerHTML=advData.map((c,i)=>`<button aria-pressed="${i===advSel}" data-i="${i}">${esc(c.customer.name)}, ${esc(c.customer.age)}<small>${c.active?esc(c.moment.title):"Geen moment"}</small></button>`).join("");
 const c=advData[advSel];if(!c){$("abrief").innerHTML="<p>Geen klanten toegewezen.</p>";return}
 const pct=Math.round(c.score*100);
 $("abrief").innerHTML=`<div class="moment"><div><span class="label">Briefing voor je gesprek met ${esc(c.customer.name)}</span><h3>${c.active?esc(c.moment.title):"Geen duidelijk moment"}</h3></div><div class="conf"><span>Zekerheid ${pct}%</span><div class="bar"><i style="width:${pct}%"></i></div></div></div>
 <div class="bubble ${c.active?"":"none"}"><b>${c.active?"Voorgestelde aanpak: "+esc(c.moment.action):"Geen actie nodig"}</b>${c.active?`<div class="meta"><span class="chip">Kanaal: ${esc(c.moment.channel)}</span><span class="chip">Toon: ${esc(c.moment.tone)}</span></div>${timingBlock(c.timing)}`:"Laat deze klant met rust tot er een duidelijk moment is."}</div>
 <div class="why"><h2 style="font-size:18px">Waarom</h2><ul>${c.why.map(w=>`<li>${esc(w.label)}<small>${esc(w.evidence)}</small></li>`).join("")||"<li>Geen signalen met toestemming</li>"}</ul></div>`}
$("clients").onclick=e=>{const b=e.target.closest("button");if(b){advSel=+b.dataset.i;renderAdvisor()}};

/* ---------- schaal ---------- */
async function loadStats(){try{const s=await api("/api/stats");
 $("stats").innerHTML=`<div><b>${s.customers.toLocaleString("nl-BE")}</b><span>klanten geanalyseerd</span></div>
 <div><b>${s.ms} ms</b><span>detectie, 1 CPU-kern</span></div>
 <div><b>${s.trigger_rate}%</b><span>met een moment, de rest krijgt niets</span></div>
 ${s.moments.map(m=>`<div><b>${m.count}</b><span>${esc(m.title)}</span></div>`).join("")}
 <div><b>±${s.projected_seconds_2_3m} s</b><span>geschat voor 2,3 miljoen klanten</span></div>`;
 const p=Math.max(.5,Math.min(10,Math.round(s.trigger_rate*2)/2));$("p").value=p;scale()}catch(e){$("stats").innerHTML=`<div><span>${esc(e.message)}</span></div>`}}
const eur=v=>"€"+v.toLocaleString("nl-BE",{maximumFractionDigits:v<100?2:0});
function scale(){const n=+$("n").value,p=+$("p").value;
 const tr=n*p/100,naive=n*.002,ours=n*.00001+tr*.002;
 $("no").textContent=n.toLocaleString("nl-BE");$("po").textContent=p+"% ("+Math.round(tr).toLocaleString("nl-BE")+" klanten)";
 $("c1").textContent=eur(naive)+" per dag";$("c2").textContent=eur(ours)+" per dag";
 const mx=2300000*.002;$("b1").style.width=naive/mx*100+"%";$("b2").style.width=Math.max(ours/mx*100,1)+"%";
 $("sum").textContent="Ongeveer "+Math.round(naive/ours)+"x goedkoper, met dezelfde uitleg per klant.";}
$("n").oninput=$("p").oninput=scale;scale();

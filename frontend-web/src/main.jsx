import React,{useEffect,useState} from "react";import{createRoot}from"react-dom/client";import{Activity,ArrowUpRight,BriefcaseBusiness,Check,ChevronRight,CircleHelp,FileText,FolderKanban,Gauge,Globe2,LayoutDashboard,LoaderCircle,MapPin,Menu,Play,RefreshCw,Search,Settings2,ShieldCheck,Sparkles,Square,Target,Upload,UserRound,X,Zap}from"lucide-react";import"./styles.css";
const BASE=()=>localStorage.getItem("jobflow_api_base")||"/api";const TOKEN=()=>sessionStorage.getItem("jobflow_api_token")||"";
async function req(path,opt={}){const h=new Headers(opt.headers||{});if(TOKEN())h.set("X-API-Token",TOKEN());if(opt.body&&!(opt.body instanceof FormData))h.set("Content-Type","application/json");const r=await fetch(BASE()+path,{...opt,headers:h});if(!r.ok){let d=r.statusText;try{const x=await r.json();d=typeof x.detail==="string"?x.detail:JSON.stringify(x.detail||x)}catch{}throw Error("HTTP "+r.status+": "+d)}return r.headers.get("content-type")?.includes("json")?r.json():r.blob()}
const api={metrics:()=>req("/metrics"),applications:()=>req("/applications"),analytics:()=>req("/analytics/applications"),commonAnswers:()=>req("/common-answers"),jobs:()=>req("/jobs"),profiles:()=>req("/profiles"),profile:id=>req("/profiles/"+id),saveProfile:(id,b)=>req("/profiles/"+id,{method:"PUT",body:JSON.stringify(b)}),deleteProfile:id=>req("/profiles/"+id,{method:"DELETE"}),upload:f=>{const b=new FormData();b.append("file",f);return req("/profiles/upload",{method:"POST",body:b})},plan:(jobId,profileId)=>req("/jobs/"+jobId+"/application-plan?profile_id="+encodeURIComponent(profileId)),match:id=>req("/jobs/match",{method:"POST",body:JSON.stringify({profile_id:id,limit:50})}),runs:()=>req("/runs"),run:id=>req("/runs/"+id),create:b=>req("/runs",{method:"POST",body:JSON.stringify(b)}),command:(id,b)=>req("/runs/"+id+"/commands",{method:"POST",body:JSON.stringify(b)}),resolve:(id,a)=>req("/applications/"+id+"/resolve",{method:"POST",body:JSON.stringify({action:a})})};
const nav=[["overview","Overview",LayoutDashboard],["jobs","Discover jobs",BriefcaseBusiness],["applications","Applications",FolderKanban],["profile","Candidate profile",UserRound],["automation","Automation",Zap]];
const tones={submitted:"success",submission_uncertain:"warning",queued:"neutral",running:"info",waiting:"warning",failed:"danger",stopped:"neutral",review:"warning",awaiting_approval:"warning",missing_information:"danger",validation_error:"danger"};
const label=s=>String(s||"unknown").replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
function Badge({children,tone="neutral"}){return <span className={"badge "+tone}><i/> {children}</span>}
function Btn({children,primary=false,icon:Icon,loading=false,...p}){return <button className={"btn "+(primary?"primary":"")} disabled={loading||p.disabled} {...p}>{loading?<LoaderCircle size={15} className="spin"/>:Icon&&<Icon size={15}/>} {children}</button>}
function Stat({name,value,note,icon:Icon}){return <div className="stat"><div className="stat-head"><span>{name}</span><Icon size={16}/></div><strong>{value}</strong><small>{note}</small></div>}
function Empty({title,text,icon:Icon=FolderKanban}){return <div className="empty"><div><Icon size={20}/></div><strong>{title}</strong><span>{text}</span></div>}
function App(){const[page,setPage]=useState("overview"),[data,setData]=useState({metrics:null,apps:[],analytics:null,jobs:[],profiles:[]}),[profile,setProfile]=useState(null),[selectedJob,setSelectedJob]=useState(null),[runId,setRunId]=useState(null),[run,setRun]=useState(null),[mobile,setMobile]=useState(false),[settings,setSettings]=useState(false),[error,setError]=useState(""),[loading,setLoading]=useState(true);
const load=async()=>{setLoading(true);try{const[m,a,n,j,p]=await Promise.all([api.metrics(),api.applications(),api.analytics(),api.jobs(),api.profiles()]);setData({metrics:m,apps:a,analytics:n,jobs:j,profiles:p});if(!profile&&p[0]){try{setProfile(await api.profile(p[0].id))}catch{setProfile(p[0])}}}catch(e){setError(e.message)}finally{setLoading(false)}};const selectProfile=async(p)=>{if(!p)return;setProfile(p);try{setProfile(await api.profile(p.id))}catch(e){setError("Could not load the full candidate profile: "+e.message)}};useEffect(()=>{if(TOKEN())load();else setLoading(false)},[]);
useEffect(()=>{if(!runId)return;let refreshed=false;const f=async()=>{try{const next=await api.run(runId);setRun(next);if(!refreshed&&["completed","failed","stopped","expired"].includes(next.status)){refreshed=true;await load()}}catch{}};f();const t=setInterval(f,1800);return()=>clearInterval(t)},[runId]);

const review=data.apps.filter(a=>a.status==="submission_uncertain"||a.missing_fields?.length||a.sensitive_fields?.length||a.validation_errors?.length).length;
const go=p=>{setPage(p);setMobile(false)};const current=nav.find(x=>x[0]===page);
return <div className="shell"><aside className={mobile?"side open":"side"}><div className="brand"><b><Zap size={18}/></b><div><strong>ApplyFlow</strong><span>Job application workspace</span></div></div><div className="nav-title">Workspace</div>{nav.map(([id,text,Icon])=><button key={id} className={page===id?"nav active":"nav"} onClick={()=>go(id)}><Icon size={17}/><span>{text}</span>{id==="applications"&&review>0&&<em>{review}</em>}</button>)}<div className="grow"/><div className="connected"><i/> Backend connected</div><button className="nav" onClick={()=>setSettings(true)}><Settings2 size={17}/><span>Settings</span></button><div className="mini-profile"><div>{profile?.profile?.name?.[0]||"C"}</div><span>{profile?.profile?.name||"Candidate"}</span></div></aside>{mobile&&<button className="veil" onClick={()=>setMobile(false)}/>}<main className="main"><header><div className="head-left"><button className="mobile-menu" onClick={()=>setMobile(true)}><Menu size={20}/></button><div><small>JOB APPLICATION WORKSPACE</small><h1>{current?.[1]}</h1></div></div><div className="head-actions"><button className="icon" onClick={load}><RefreshCw size={16}/></button>{run?.status==="waiting"&&<Btn primary icon={CircleHelp} onClick={()=>go("automation")}>Action required</Btn>}<span className="live"><i/> Live</span></div></header>{error&&<div className="error">{error}<button onClick={()=>setError("")}><X size={14}/></button></div>}<div className="content">{loading&&!data.metrics?<Skeleton/>:page==="overview"?<Overview d={data} review={review} go={go}/>:page==="jobs"?<Jobs d={data} profile={profile} setProfile={setProfile} setRunId={setRunId} setSelectedJob={setSelectedJob} go={go} load={load}/>:page==="applications"?<Applications d={data} load={load}/>:page==="profile"?<Profile d={data} profile={profile} setProfile={setProfile} load={load}/>:<Automation d={data} profile={profile} setProfile={setProfile} run={run} setRunId={setRunId} selectedJob={selectedJob}/>}</div></main>{settings&&<Settings close={()=>setSettings(false)}/>}</div>}
function Connect({onDone}){const[b,setB]=useState("http://127.0.0.1:8000"),[t,setT]=useState(""),[busy,setBusy]=useState(false),[err,setErr]=useState("");return <div className="connect"><div className="connect-card"><div className="brand large"><b><Zap size={19}/></b><div><strong>ApplyFlow</strong><span>Job application automation</span></div></div><h1>Your job search, under control.</h1><p>Connect the workspace to your local automation backend.</p><label>Backend URL<input value={b} onChange={e=>setB(e.target.value)}/></label><label>API token<input type="password" value={t} onChange={e=>setT(e.target.value)}/></label>{err&&<div className="error">{err}</div>}<Btn primary loading={busy} icon={ShieldCheck} onClick={async()=>{setBusy(true);try{localStorage.setItem("jobflow_api_base",b.replace(/\/$/,""));sessionStorage.setItem("jobflow_api_token",t);await req("/health");onDone()}catch(e){sessionStorage.removeItem("jobflow_api_token");setErr(e.message)}finally{setBusy(false)}}}>Connect workspace</Btn><small>API credentials stay in this browser session.</small></div></div>}
function Overview({d,review,go}){return <div className="page"><section className="hero"><div><span className="kicker"><Sparkles size={13}/> AUTOMATION COMMAND CENTER</span><h2>Move from searching to applying<br/><span>without losing control.</span></h2><p>Discover relevant roles, prepare applications with your saved profile, and step in only when a human decision is required.</p><div className="actions"><Btn primary icon={Search} onClick={()=>go("jobs")}>Discover jobs</Btn><Btn icon={Play} onClick={()=>go("automation")}>Start automation</Btn></div></div><div className="orb"><div className="orb-core"><Zap size={23}/></div><i/><i/><span>DISCOVER</span><span>PREPARE</span><span>REVIEW</span></div></section>{review>0&&<button className="attention" onClick={()=>go("applications")}><CircleHelp size={19}/><div><strong>{review} application{review>1?"s":""} need your attention</strong><span>Review uncertain submissions or missing information before continuing.</span></div><ArrowUpRight size={17}/></button>}<div className="section"><div><small>AT A GLANCE</small><h3>Workspace health</h3></div><span>Updated just now</span></div><div className="stats"><Stat name="Resume profiles" value={d.profiles?.length||0} note="Saved candidate profiles" icon={UserRound}/><Stat name="Applications" value={d.metrics?.applications_total||0} note={(d.analytics?.submitted||0)+" submitted"} icon={FolderKanban}/><Stat name="Saved jobs" value={d.metrics?.jobs_saved||0} note="Ready to match" icon={BriefcaseBusiness}/><Stat name="Submission rate" value={Math.round((d.analytics?.submission_rate||0)*100)+"%"} note="Tracked applications" icon={Target}/><Stat name="Avg. lifecycle" value={d.analytics?.average_lifecycle_seconds?Math.round(d.analytics.average_lifecycle_seconds/60)+"m":"—"} note="Average application lifecycle" icon={Activity}/><Stat name="Automation" value={d.metrics?.active_portals?"Active":"Ready"} note={d.metrics?.queue?.running_workers?d.metrics.queue.running_workers+" worker running":"No active browser"} icon={Activity}/></div><div className="analytics-strip"><span>Status breakdown</span>{Object.entries(d.analytics?.by_status||{}).map(([k,v])=><b key={k}>{label(k)} <em>{v}</em></b>)}</div><div className="columns"><section className="panel"><div className="panel-head"><div><small>RECENT ACTIVITY</small><h3>Application pipeline</h3></div><button onClick={()=>go("applications")}>View all <ArrowUpRight size={13}/></button></div>{d.apps.slice(0,5).map(a=><AppRow key={a.id} a={a}/>)}{!d.apps.length&&<Empty title="No applications yet" text="Start with job discovery and prepare your first application."/>}</section><section className="panel"><div className="panel-head"><div><small>AUTOMATION STATUS</small><h3>System overview</h3></div><Gauge size={17}/></div><div className="health"><p><span><i/>Backend API</span><b>Connected</b></p><p><span><i/>Browser automation</span><b>{d.metrics?.active_portals?"Running":"Ready"}</b></p><p><span><i/>Queue workers</span><b>{d.metrics?.queue?.worker_count||0}</b></p><p><span><i/>Scheduled runs</span><b>{d.metrics?.scheduler?.scheduled||0}</b></p></div><div className="notice"><ShieldCheck size={15}/> Authentication, CAPTCHAs and final application decisions stay under your control.</div></section></div></div>}
function AppRow({a}){return <div className="app-row"><div className="logo">{(a.company||a.portal||"J")[0].toUpperCase()}</div><div><strong>{a.title||"Untitled role"}</strong><span>{a.company||a.portal||"Unknown company"}</span></div><Badge tone={tones[a.status]}>{label(a.status)}</Badge></div>}
function Jobs({d,profile,setProfile,setRunId,setSelectedJob,go,load}){useEffect(()=>{load()},[]);const[q,setQ]=useState(""),[matched,setMatched]=useState([]),[busy,setBusy]=useState(false),[only,setOnly]=useState(false),[plan,setPlan]=useState(null),[planBusy,setPlanBusy]=useState(false);const list=only?matched.map(x=>({...x.job,score:x.match?.score})):d.jobs;const shown=list.filter(j=>(j.title+" "+j.company+" "+j.location).toLowerCase().includes(q.toLowerCase()));const analyze=async j=>{if(!profile){alert("Select a candidate profile first.");return}setPlanBusy(true);try{setPlan(await api.plan(j.id,profile.id))}catch(e){alert("Application intelligence unavailable: "+e.message)}finally{setPlanBusy(false)}};return <div className="page"><div className="intro"><div><small>DISCOVERY</small><h2>Find roles worth applying to.</h2><p>Your saved job library stays reusable. Match roles against the active candidate profile before preparing an application.</p></div><Btn primary icon={Zap} onClick={()=>go("automation")}>New discovery run</Btn></div><div className="toolbar"><div className="search"><Search size={15}/><input placeholder="Search title, company or location…" value={q} onChange={e=>setQ(e.target.value)}/></div><select value={profile?.id||""} onChange={async e=>{const p=d.profiles.find(x=>x.id===e.target.value);setProfile(p);if(p)try{setProfile(await api.profile(p.id))}catch(err){alert(err.message)}}}><option value="">Candidate profile</option>{d.profiles.map(p=><option key={p.id} value={p.id}>{p.full_name||p.original_name}</option>)}</select><Btn icon={Target} loading={busy} disabled={!profile} onClick={async()=>{setBusy(true);try{setMatched(await api.match(profile.id));setOnly(true)}catch(e){alert(e.message)}finally{setBusy(false)}}}>Match profile</Btn><button className={only?"filter active":"filter"} onClick={()=>setOnly(!only)}>{only?"Matched only":"All jobs"}</button></div>{shown.length?<div className="job-grid">{shown.map(j=><article className="job-card" key={j.id||j.url}><div className="job-top"><div className="logo big">{(j.company||"J")[0].toUpperCase()}</div><div><h3>{j.title||"Untitled role"}</h3><span>{j.company||"Company not specified"}</span></div>{j.score!=null&&<strong className="score">{Math.round(j.score*100)}%<small>match</small></strong>}</div><div className="job-meta"><span><MapPin size={13}/>{j.location||"Location not specified"}</span><span><Globe2 size={13}/>{j.portal||"Portal"}</span></div><p>{j.description?j.description.slice(0,150)+"…":"Saved role ready for application planning."}</p><div className="job-actions"><a href={j.url} target="_blank" rel="noreferrer">Open posting <ArrowUpRight size={13}/></a><div className="job-buttons"><Btn icon={Gauge} loading={planBusy} disabled={!profile} onClick={()=>analyze(j)}>Analyze</Btn><Btn primary icon={Play} onClick={()=>{setSelectedJob(j);setRunId(null);go("automation")}}>Prepare</Btn></div></div></article>)}</div>:<Empty icon={BriefcaseBusiness} title="No matching jobs" text="Run a discovery session or change your search."/>}{plan&&<section className="panel planner"><div className="section-row"><div><small>APPLICATION INTELLIGENCE</small><h3>{plan.job?.title||"Job readiness analysis"}</h3><p>{plan.job?.company||"Company"} · {plan.job?.location||"Location"}</p></div><button className="icon" onClick={()=>setPlan(null)}><X size={15}/></button></div><div className="planner-stats"><Stat name="Matched skills" value={plan.matched_skills?.length||0} note="Profile overlap" icon={Check}/><Stat name="Missing skills" value={plan.missing_skills?.length||0} note="Not found in profile" icon={Target}/><Stat name="Experience" value={plan.experience_requirement_satisfied?"Satisfied":"Review"} note="Based on job requirements" icon={Activity}/></div><div className="planner-cols"><div><b>Matched</b><div className="tag-list">{(plan.matched_skills||[]).map(x=><span key={x}>{x}</span>)}</div></div><div><b>Missing</b><div className="tag-list">{(plan.missing_skills||[]).map(x=><span key={x}>{x}</span>)}{!plan.missing_skills?.length&&<span>None detected</span>}</div></div></div><div className="planning-notes">{(plan.planning_notes||[]).map((x,i)=><p key={i}><ShieldCheck size={13}/>{x}</p>)}</div></section>}</div>}function Applications({d,load}){const[q,setQ]=useState(""),[f,setF]=useState("all"),[selected,setSelected]=useState(null);const statuses=[...new Set(d.apps.map(x=>x.status))],list=d.apps.filter(a=>(f==="all"||a.status===f)&&(a.title+" "+a.company+" "+a.portal).toLowerCase().includes(q.toLowerCase()));return <div className="page"><div className="intro"><div><small>TRACKING</small><h2>Every application, one place.</h2><p>See what is moving, what is waiting and which submissions need explicit review.</p></div><Btn icon={RefreshCw} onClick={load}>Refresh</Btn></div><div className="mini"><span><b>{d.apps.length}</b>Total</span><span><b>{d.analytics?.submitted||0}</b>Submitted</span><span><b>{d.apps.filter(x=>x.status==="running").length}</b>Running</span><span><b>{d.apps.filter(x=>x.status==="submission_uncertain").length}</b>Needs review</span></div><div className="toolbar"><div className="search"><Search size={15}/><input placeholder="Search applications…" value={q} onChange={e=>setQ(e.target.value)}/></div><select value={f} onChange={e=>setF(e.target.value)}><option value="all">All statuses</option>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select></div><section className="panel table"><div className="table-head"><span>Role</span><span>Portal</span><span>Status</span><span>Updated</span><span/></div>{list.map(a=><AppTable key={a.id} a={a} select={()=>setSelected(a)}/>)}{!list.length&&<Empty title="Nothing here" text="No applications match the current filters."/>}</section>{selected&&<section className="panel review-panel"><div className="section-row"><div><small>APPLICATION REVIEW</small><h3>{selected.title||"Untitled role"}</h3><p>{selected.company||"Unknown company"} · {label(selected.status)}</p></div><button className="icon" onClick={()=>setSelected(null)}><X size={15}/></button></div>{selected.review_fields?.length>0&&<div className="review-list">{selected.review_fields.map((field,i)=><div className="review-field" key={i}><div><b>{field.label||field.question||"Field"}</b><span>{field.category||"Application field"}</span></div><strong>{field.value||field.current_value||"Not provided"}</strong></div>)}</div>}{selected.missing_fields?.length>0&&<div className="review-alert danger">Missing required information: {selected.missing_fields.join(", ")}</div>}{selected.sensitive_fields?.length>0&&<div className="review-alert warning">Sensitive fields require explicit review: {selected.sensitive_fields.join(", ")}</div>}{selected.validation_errors?.length>0&&<div className="review-alert danger">Validation errors: {selected.validation_errors.join(" | ")}</div>}{selected.human_approved&&<div className="review-alert success">Human approval recorded for the final submission action.</div>}<div className="review-actions">{selected.job_url&&<a className="open-link" href={selected.job_url} target="_blank" rel="noreferrer">Open job <ArrowUpRight size={13}/></a>}{selected.status==="submission_uncertain"&&<><Btn primary icon={Check} onClick={async()=>{try{await api.resolve(selected.id,"submitted");await load();setSelected(null)}catch(e){alert(e.message)}}}>Mark Applied</Btn><Btn icon={X} onClick={async()=>{try{await api.resolve(selected.id,"cancelled");await load();setSelected(null)}catch(e){alert(e.message)}}}>Cancel</Btn></>}</div></section>}</div>}function AppTable({a,select}){const[busy,setBusy]=useState(false),uncertain=a.status==="submission_uncertain";const resolve=async(action)=>{setBusy(true);try{await api.resolve(a.id,action);window.location.reload()}catch(e){alert(e.message)}finally{setBusy(false)}};return <div className="table-row" onClick={select}><div className="role"><div className="logo">{(a.company||a.portal||"J")[0]}</div><div><strong>{a.title||"Untitled role"}</strong><span>{a.company||"Unknown company"}</span></div></div><span className="muted">{a.portal}</span><Badge tone={tones[a.status]}>{label(a.status)}</Badge><span className="muted">{a.updated_at?new Date(a.updated_at).toLocaleDateString():"—"}</span><div>{uncertain?<div className="row-buttons"><Btn primary loading={busy} icon={Check} onClick={()=>resolve("submitted")}>Applied</Btn><Btn loading={busy} icon={X} onClick={()=>resolve("cancelled")}>Cancel</Btn></div>:<a className="open-link" href={a.job_url} target="_blank" rel="noreferrer"><ArrowUpRight size={15}/></a>}</div></div>}
function Profile({d,profile,setProfile,load}){
  const [file,setFile]=useState(null);
  const [busy,setBusy]=useState(false);
  const [editing,setEditing]=useState(false);
  const [draft,setDraft]=useState(null);
  const [commonQuestions,setCommonQuestions]=useState([]);

  useEffect(()=>{api.commonAnswers().then(setCommonQuestions).catch(()=>{})},[]);

  const full=profile?.profile||{};
  const personal=full.personal||{};
  const answers={...(full.ats_defaults||{}),...(full.custom_answers||{})};

  const beginEdit=()=>{
    setDraft(JSON.parse(JSON.stringify(full)));
    setEditing(true);
  };

  const update=(section,key,value)=>{
    setDraft(x=>({...x,[section]:{...(x?.[section]||{}),[key]:value}}));
  };

  const updateCustom=(key,value)=>{
    setDraft(x=>({...x,custom_answers:{...(x.custom_answers||{}),[key]:value}}));
  };

  const removeAnswer=key=>{
    setDraft(x=>{
      const next={...(x.custom_answers||{})};
      delete next[key];
      return {...x,custom_answers:next};
    });
  };

  const addAnswer=()=>{
    const key=window.prompt("Application question");
    if(!key?.trim()) return;
    setDraft(x=>({...x,custom_answers:{...(x.custom_answers||{}),[key.trim()]:""}}));
  };

  const commonValue=q=>draft?.custom_answers?.[q.key]||draft?.custom_answers?.[q.label]||"";

  const setCommon=(q,value)=>{
    setDraft(x=>({
      ...x,
      custom_answers:{
        ...(x.custom_answers||{}),
        [q.key]:value
      }
    }));
  };

  const setAlias=(q,value)=>{
    setDraft(x=>({
      ...x,
      common_answer_aliases:{
        ...(x.common_answer_aliases||{}),
        [q.key]:value.split(",").map(v=>v.trim()).filter(Boolean)
      }
    }));
  };

  const deleteCurrent=async()=>{
    if(!window.confirm("Delete this candidate profile and its stored resume? This cannot be undone.")) return;
    setBusy(true);
    try{
      await api.deleteProfile(profile.id);
      setProfile(null);
      setEditing(false);
      setDraft(null);
      await load();
    }catch(e){
      alert("Could not delete profile: "+e.message);
    }finally{
      setBusy(false);
    }
  };

  const save=async()=>{
    setBusy(true);
    try{
      const saved=await api.saveProfile(profile.id,{
        ...draft,
        years_of_experience:draft.years_of_experience===""?null:Number(draft.years_of_experience)
      });
      setProfile(saved);
      setEditing(false);
      setDraft(null);
      await load();
    }catch(e){
      alert("Could not save profile: "+e.message);
    }finally{
      setBusy(false);
    }
  };

  const upload=async()=>{
    if(!file) return;
    setBusy(true);
    try{
      await api.upload(file);
      setFile(null);
      await load();
    }catch(e){
      alert("Could not parse resume: "+e.message);
    }finally{
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="intro">
        <div>
          <small>CANDIDATE WORKSPACE</small>
          <h2>Build a profile the automation can trust.</h2>
          <p>Keep resume facts, experience, education and reusable answers in one controlled candidate profile.</p>
        </div>
        <div className="intro-actions">
          <Badge tone="success">Protected workspace</Badge>
          {profile&&!editing&&<Btn icon={Settings2} onClick={beginEdit}>Edit profile</Btn>}
          {profile&&editing&&<>
            <Btn onClick={()=>{setEditing(false);setDraft(null)}}>Cancel</Btn>
            <Btn primary loading={busy} icon={Check} onClick={save}>Save changes</Btn>
            <Btn icon={X} onClick={deleteCurrent}>Delete profile</Btn>
          </>}
        </div>
      </div>

      <div className="profile-grid">
        <section className="panel profile-list-panel">
          <div className="panel-head">
            <div><small>RESUME LIBRARY</small><h3>Candidate profiles</h3></div>
            <FileText size={17}/>
          </div>

          <label className="upload">
            <input type="file" accept=".pdf,.docx" onChange={e=>setFile(e.target.files?.[0]||null)}/>
            <Upload size={20}/>
            <strong>{file?file.name:"Upload a resume"}</strong>
            <span>{file?"Ready to parse":"PDF or DOCX · up to 200 MB"}</span>
          </label>
          <Btn primary disabled={!file} loading={busy} icon={Upload} onClick={upload}>Upload & parse</Btn>

          <div className="profiles">
            {d.profiles.map(p=>
              <button
                className={profile?.id===p.id?"profile active":"profile"}
                key={p.id}
                onClick={async()=>{
                  setProfile(p);
                  try{setProfile(await api.profile(p.id))}
                  catch(e){alert("Could not load the full candidate profile: "+e.message)}
                }}
              >
                <div className="avatar">{(p.full_name||"C")[0].toUpperCase()}</div>
                <div><b>{p.full_name||"Candidate"}</b><span>{p.original_name}</span></div>
                <ChevronRight size={15}/>
              </button>
            )}
          </div>
        </section>

        <section className="panel profile-detail">
          {profile ? (
            <>
              <div className="profile-title">
                <div className="avatar xl">{(personal.full_name||"C")[0].toUpperCase()}</div>
                <div>
                  <small>ACTIVE PROFILE</small>
                  <h3>{personal.full_name||"Candidate"}</h3>
                  <span>{personal.email||"Email not extracted"}{personal.phone?" · "+personal.phone:""}</span>
                </div>
                <div className="profile-title-actions">
                  <Btn icon={ArrowUpRight} onClick={async()=>{
                    try{
                      const blob=await req("/profiles/"+profile.id+"/resume");
                      const href=URL.createObjectURL(blob);
                      const a=document.createElement("a");
                      a.href=href;
                      a.download=profile.original_name||"resume";
                      a.click();
                      URL.revokeObjectURL(href);
                    }catch(e){alert("Could not download resume: "+e.message)}
                  }}>Download resume</Btn>
                </div>
              </div>

              <div className="details">
                <div>
                  <small>EXPERIENCE</small>
                  {editing
                    ? <input className="inline-input" type="number" min="0" step="0.1" value={draft.years_of_experience??""} onChange={e=>setDraft({...draft,years_of_experience:e.target.value})}/>
                    : <b>{full.years_of_experience!=null?full.years_of_experience+" years":"Not set"}</b>}
                </div>
                <div>
                  <small>LOCATION</small>
                  {editing
                    ? <input className="inline-input" value={draft.personal?.location||""} onChange={e=>update("personal","location",e.target.value)} placeholder="Current location"/>
                    : <b>{personal.city||personal.location||"Not set"}{personal.state?", "+personal.state:""}</b>}
                </div>
                <div>
                  <small>SKILLS</small>
                  {editing
                    ? <input className="inline-input" value={(draft.skills||[]).join(", ")} onChange={e=>setDraft({...draft,skills:e.target.value.split(",").map(v=>v.trim()).filter(Boolean)})}/>
                    : <b>{(full.skills||[]).slice(0,4).join(", ")||"Not set"}</b>}
                </div>
                <div>
                  <small>CONTACT</small>
                  {editing
                    ? <input className="inline-input" value={draft.personal?.email||""} onChange={e=>update("personal","email",e.target.value)} placeholder="Email"/>
                    : <b>{personal.email||"Not set"}</b>}
                </div>
              </div>

              <div className="profile-sections">
                <section className="sub">
                  <small>PROFESSIONAL EXPERIENCE</small>
                  <h4>Work history</h4>
                  {(full.work_history||[]).length
                    ? full.work_history.map((job,i)=>
                      <div className="profile-item" key={i}>
                        <div><b>{job.title||"Role"}</b><span>{job.company||"Company"}{job.location?" · "+job.location:""}</span></div>
                        <small>{job.start_date||"—"} → {job.current?"Present":(job.end_date||"—")}</small>
                      </div>
                    )
                    : <p>No work history extracted from this resume.</p>}
                </section>

                <section className="sub">
                  <small>EDUCATION</small>
                  <h4>Education</h4>
                  {(full.education||[]).length
                    ? full.education.map((edu,i)=>
                      <div className="profile-item" key={i}>
                        <div><b>{edu.degree||"Degree"}{edu.field_of_study?" · "+edu.field_of_study:""}</b><span>{edu.institution||"Institution"}</span></div>
                        <small>{edu.start_date||"—"} → {edu.end_date||"—"}</small>
                      </div>
                    )
                    : <p>No education details extracted from this resume.</p>}
                </section>

                <section className="sub">
                  <small>SKILLS & LINKS</small>
                  <h4>Candidate snapshot</h4>
                  <div className="tag-list">
                    {(full.skills||[]).map((skill,i)=><span key={i}>{skill}</span>)}
                  </div>
                  <div className="links">
                    {full.online_profiles?.linkedin&&<a href={full.online_profiles.linkedin} target="_blank" rel="noreferrer">LinkedIn <ArrowUpRight size={13}/></a>}
                    {full.online_profiles?.github&&<a href={full.online_profiles.github} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={13}/></a>}
                    {full.online_profiles?.portfolio&&<a href={full.online_profiles.portfolio} target="_blank" rel="noreferrer">Portfolio <ArrowUpRight size={13}/></a>}
                  </div>
                </section>

                <section className="sub reusable">
                  <div className="section-row">
                    <div><small>REUSABLE ANSWERS</small><h4>Application answers</h4></div>
                    {editing&&<Btn icon={Sparkles} onClick={addAnswer}>Add answer</Btn>}
                  </div>
                  <p>Values saved here are reused by the automation when it encounters the same or equivalent application questions.</p>

                  {editing ? (
                    <>
                      <div className="common-library">
                        <div className="section-row">
                          <div><small>COMMON QUESTION LIBRARY</small><h4>Reusable question catalog</h4></div>
                          <span className="muted">{commonQuestions.length} standardized questions</span>
                        </div>
                        <p>Save answers against canonical questions and add variants so the automation can recognize different wording across ATS platforms.</p>
                        {commonQuestions.map(q=>
                          <div className="common-row" key={q.key}>
                            <div className="common-question">
                              <b>{q.label}</b>
                              <span>{q.category}</span>
                              <small>{q.aliases?.slice(0,3).join(" · ")}</small>
                            </div>
                            {q.input_type==="yes_no"
                              ? <select value={commonValue(q)} onChange={e=>setCommon(q,e.target.value)}>
                                  <option value="">Not set</option>
                                  <option value="Yes">Yes</option>
                                  <option value="No">No</option>
                                </select>
                              : <input value={commonValue(q)} onChange={e=>setCommon(q,e.target.value)} placeholder="Enter reusable answer…"/>}
                            <input
                              className="alias-input"
                              value={(draft.common_answer_aliases?.[q.key]||[]).join(", ")}
                              onChange={e=>setAlias(q,e.target.value)}
                              placeholder="Custom variants, comma separated"
                            />
                          </div>
                        )}
                      </div>

                      <div className="editable-answers">
                        {Object.entries(draft.custom_answers||{}).map(([k,v])=>
                          <div className="answer-edit" key={k}>
                            <div>
                              <label>Question</label>
                              <input value={k} readOnly/>
                              <label>Saved answer</label>
                              <textarea value={v} onChange={e=>updateCustom(k,e.target.value)} placeholder="Enter the answer the automation should use..."/>
                            </div>
                            <button className="remove-answer" title="Remove answer" onClick={()=>removeAnswer(k)}><X size={15}/></button>
                          </div>
                        )}
                        {Object.keys(draft.custom_answers||{}).length===0&&<p>No custom answers yet. Add a question and answer.</p>}
                      </div>

                      <div className="defaults-edit">
                        <div className="section-row"><div><small>ATS DEFAULTS</small><h4>Standard application fields</h4></div></div>
                        {["notice_period","salary_currency","salary_period","gender","ethnicity","disability","veteran_status"].map(k=>
                          <label className="field" key={k}>
                            <span>{k.replaceAll("_"," ")}</span>
                            <input value={draft.ats_defaults?.[k]??""} onChange={e=>update("ats_defaults",k,e.target.value)}/>
                          </label>
                        )}
                        {["work_authorized","requires_sponsorship"].map(k=>
                          <label className="check-field" key={k}>
                            <input type="checkbox" checked={draft.ats_defaults?.[k]===true} onChange={e=>update("ats_defaults",k,e.target.checked)}/>
                            <span>{k.replaceAll("_"," ")}</span>
                          </label>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="answers">
                      {Object.entries(answers)
                        .filter(([,v])=>v!==null&&v!==""&&v!==undefined)
                        .slice(0,12)
                        .map(([k,v])=>
                          <div key={k}><span>{k.replaceAll("_"," ")}</span><b>{typeof v==="boolean"?(v?"Yes":"No"):String(v)}</b></div>
                        )}
                      {!Object.keys(answers).length&&<p>No reusable answers have been extracted yet.</p>}
                    </div>
                  )}
                </section>
              </div>
            </>
          ) : (
            <Empty icon={UserRound} title="No profile selected" text="Upload a resume to create your first candidate profile."/>
          )}
        </section>
      </div>
    </div>
  );
}
function Guide({I:Icon,t,d}){return <div className="guide"><div className="guide-icon"><Icon size={16}/></div><div><b>{t}</b><span>{d}</span></div></div>}
function Automation({d,profile,setProfile,run,setRunId,selectedJob}){const[mode,setMode]=useState(selectedJob?"apply":"discover"),[portal,setPortal]=useState(selectedJob?.portal||"linkedin"),[url,setUrl]=useState(selectedJob?.url||""),[keywords,setKeywords]=useState(""),[location,setLocation]=useState("India"),[workplace,setWorkplace]=useState("any"),[priority,setPriority]=useState(100),[scheduled,setScheduled]=useState(""),[headless,setHeadless]=useState(false),[busy,setBusy]=useState(false);const active=run&&["queued","running","waiting"].includes(run.status);const waiting=run?.status==="waiting";useEffect(()=>{if(selectedJob){setMode("apply");setUrl(selectedJob.url||"");setPortal(selectedJob.portal||"linkedin")}},[selectedJob]);const start=async()=>{setBusy(true);try{const r=await api.create({mode,portal,profile_id:profile?.id||null,job_url:url||null,keywords,search_location:location,workplace_type:workplace,headless,priority:Number(priority),scheduled_at:(scheduled?new Date(scheduled).toISOString():null)});setRunId(r.id)}catch(e){alert(e.message)}finally{setBusy(false)}};const cmd=async(body)=>{try{await api.command(run.id,{...body,pause_token:run.pending?.token})}catch(e){alert(e.message)}};return <div className="page"><div className="intro"><div><small>BROWSER AUTOMATION</small><h2>Run the work. Keep the decision.</h2><p>Set the goal here. The browser handles repetitive steps and pauses whenever a human decision is required.</p></div>{active&&<Badge tone={waiting?"warning":"info"}>{waiting?"Waiting for you":"Browser running"}</Badge>}</div>{waiting?<Intervention run={run} cmd={cmd}/>:active?<Run run={run} stop={()=>cmd({action:"stop"})}/>:<div className="automation-grid"><section className="panel setup"><div className="steps"><i>1</i><b/><i className="current">2</i><b/><i>3</i></div><small>CONFIGURE AUTOMATION</small><h3>{selectedJob&&mode==="apply"?"Prepare selected job":"What should ApplyFlow do?"}</h3><div className="choices">{[["discover","Discover jobs",Search],["apply","Prepare an application",FileText],["login","Refresh login",ShieldCheck]].map(([id,text,I])=><button className={mode===id?"choice active":"choice"} key={id} onClick={()=>{setMode(id);if(id!=="apply")setUrl("")}}><I size={18}/><b>{text}</b><span>{id==="discover"?"Find and save relevant roles.":id==="apply"?"Open a specific role and prepare the form.":"Open a visible browser session."}</span></button>)}</div><div className="form2"><label>Portal<select value={portal} onChange={e=>setPortal(e.target.value)}><option value="linkedin">LinkedIn</option><option value="naukri">Naukri</option><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="workday">Workday</option><option value="custom">Custom ATS</option></select></label><label>Candidate profile<select value={profile?.id||""} disabled={mode==="login"} onChange={async e=>{const p=d.profiles.find(x=>x.id===e.target.value);if(p)try{setProfile?.(await api.profile(p.id))}catch(err){alert(err.message)}}}><option value="">Select profile</option>{d.profiles.map(p=><option key={p.id} value={p.id}>{p.full_name||p.original_name}</option>)}</select></label></div>{mode==="apply"&&<><label>Job URL<input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://www.linkedin.com/jobs/view/…"/></label>{selectedJob&&<div className="selected-job"><b>{selectedJob.title}</b><span>{selectedJob.company||"Company"} · {selectedJob.location||"Location not specified"}</span></div>}</>}{mode==="discover"&&<><label>Search keywords<input value={keywords} onChange={e=>setKeywords(e.target.value)} placeholder="Machine Learning Engineer, Python, AI…"/></label><div className="form2"><label>Location<input value={location} onChange={e=>setLocation(e.target.value)}/></label><label>Workplace<select value={workplace} onChange={e=>setWorkplace(e.target.value)}><option value="any">Any</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></select></label></div></>}{mode!=="login"&&<div className="form2"><label>Queue priority<input type="number" min="1" max="1000" value={priority} onChange={e=>setPriority(e.target.value)}/></label><label>Schedule for later<input type="datetime-local" value={scheduled} onChange={e=>setScheduled(e.target.value)} /></label></div>}{mode!=="discover"&&<label className="check-field"><input type="checkbox" checked={headless} onChange={e=>setHeadless(e.target.checked)} disabled={mode==="login"}/><span>Run headless</span></label>}<div className="safe"><ShieldCheck size={16}/><span>CAPTCHAs and authentication are never bypassed. Final submission remains a deliberate candidate action.</span></div><Btn primary loading={busy} icon={Play} disabled={(mode==="apply"&&!url)||(mode==="apply"&&!profile)} onClick={start}>{mode==="discover"?"Start discovery":mode==="apply"?"Prepare application":"Open login session"}</Btn></section><aside className="panel guide-panel"><small>HOW IT WORKS</small><h3>Automation with guardrails.</h3><Guide I={Search} t="Discover" d="Collect roles and normalize them into your job library."/><Guide I={Sparkles} t="Prepare" d="Use saved profile facts for known fields."/><Guide I={CircleHelp} t="Pause" d="Stop safely for verification or questions."/><Guide I={ShieldCheck} t="Submit" d="Uncertain submissions are never replayed automatically."/></aside></div>}</div>}function Settings({close}){const[b,setB]=useState(BASE()),[t,setT]=useState(TOKEN());return <div className="modal-bg"><div className="modal"><div className="modal-head"><div><small>WORKSPACE</small><h3>Connection settings</h3></div><button className="icon" onClick={close}><X size={17}/></button></div><label>Backend URL<input value={b} onChange={e=>setB(e.target.value)}/></label><label>API token<input type="password" value={t} onChange={e=>setT(e.target.value)}/></label><div className="modal-actions"><Btn onClick={close}>Cancel</Btn><Btn primary onClick={()=>{localStorage.setItem("jobflow_api_base",b.replace(/\/$/,""));sessionStorage.setItem("jobflow_api_token",t);close();window.location.reload()}}>Save connection</Btn></div></div></div>}
function Skeleton(){return <div className="skeleton"><div/><div className="skrow">{[1,2,3,4].map(i=><i key={i}/>)}</div><section/></div>}

function Intervention({run,cmd}){
  const p=run.pending||{};
  const [answer,setAnswer]=useState(p.suggestion||"");
  const [remember,setRemember]=useState(false);
  const [batch,setBatch]=useState({});
  const [batchRemember,setBatchRemember]=useState({});
  const browserOnly=["login","challenge","navigation","upload","widget"].includes(p.reason);
  const options=p.options||[];
  const submit=()=>cmd({action:"answer",answer,remember});
  const batchQuestions=p.batch_questions||[];
  const setBatchValue=(id,v)=>setBatch(x=>({...x,[id]:v}));

  return (
    <section className="intervention">
      <div className="intervention-head">
        <div className="warn-icon"><CircleHelp size={20}/></div>
        <div>
          <small>YOUR ATTENTION IS NEEDED</small>
          <h3>{p.question||p.message||"Review the next application step"}</h3>
          <p>The browser is paused. Nothing continues until you explicitly respond.</p>
        </div>
        <Badge tone="warning">Paused</Badge>
      </div>

      {p.url&&<a className="pending-url" href={p.url} target="_blank" rel="noreferrer">Open current browser page <ArrowUpRight size={13}/></a>}
      {p.errors?.map((x,i)=><div className="pending-error" key={i}>{x}</div>)}

      {browserOnly ? (
        <div className="browser-action">
          <ShieldCheck size={16}/>
          <div><b>Browser action required</b><span>Keep the browser visible, complete the requested action, then return here and resume.</span></div>
        </div>
      ) : (
        <div className="live-banner">Answer the application question below. Your browser will remain paused until you submit.</div>
      )}

      {p.category&&<div className="chips"><span>{p.category}</span><span>{p.required?"Required":"Optional"}</span>{p.current_value&&<span>Current: {p.current_value}</span>}</div>}
      {p.explanation&&<div className="pending-explanation">{p.explanation}</div>}

      {batchQuestions.length&&p.allowed?.includes("answer") ? (
        <div className="batch-review">
          <h4>{batchQuestions.length} questions are ready</h4>
          <p>Review every proposed answer. Required questions must be completed before the browser can continue.</p>
          {batchQuestions.map((q,i)=>(
            <div className="batch-question" key={q.id||i}>
              <b>{q.question}</b>
              {q.options?.length ? (
                <div className="options">
                  {q.options.map(o=>(
                    <button className={batch[q.id]===o?"selected":""} key={o} onClick={()=>setBatchValue(q.id,o)}>
                      {batch[q.id]===o&&<Check size={13}/>} {o}
                    </button>
                  ))}
                </div>
              ) : (
                <textarea value={batch[q.id]??q.suggestion??""} onChange={e=>setBatchValue(q.id,e.target.value)} rows="3" placeholder="Enter answer…"/>
              )}
              <label className="remember">
                <input type="checkbox" checked={!!batchRemember[q.id]} onChange={e=>setBatchRemember(x=>({...x,[q.id]:e.target.checked}))}/>
                Remember this answer for this resume profile
              </label>
            </div>
          ))}
          <Btn
            primary
            icon={Check}
            disabled={!batchQuestions.every(q=>!q.required||String(batch[q.id]??q.suggestion??"").trim().length>0)}
            onClick={()=>cmd({
              action:"answer",
              answer:JSON.stringify({
                answers:Object.fromEntries(batchQuestions.map(q=>[q.id,batch[q.id]??q.suggestion??""])),
                remember:batchRemember
              })
            })}
          >
            Submit all answers & resume
          </Btn>
        </div>
      ) : (
        !browserOnly&&p.allowed?.includes("answer") ? (
          <>
            {options.length ? (
              <div className="options">
                {options.map(o=>(
                  <button className={answer===o?"selected":""} key={o} onClick={()=>setAnswer(o)}>
                    {answer===o&&<Check size={14}/>} {o}
                  </button>
                ))}
              </div>
            ) : (
              <textarea value={answer} onChange={e=>setAnswer(e.target.value)} placeholder="Type your answer…" rows="4"/>
            )}
            <label className="remember">
              <input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/>
              Remember this answer for this resume profile
            </label>
          </>
        ) : null
      )}

      <div className="intervention-actions">
        {p.allowed?.includes("skip")&&<Btn onClick={()=>cmd({action:"skip"})}>Skip optional field</Btn>}
        {p.allowed?.includes("resume")&&<Btn onClick={()=>cmd({action:"resume"})}>Resume / re-check</Btn>}
        {p.allowed?.includes("approve")&&<Btn primary icon={ShieldCheck} onClick={()=>{if(window.confirm("I reviewed this action and authorize it, including submission if applicable."))cmd({action:"approve"})}}>Approve browser click</Btn>}
        {p.allowed?.includes("mark_submitted")&&<Btn icon={Check} onClick={()=>{if(window.confirm("I personally verified a successful submission or receipt."))cmd({action:"mark_submitted"})}}>Mark submitted</Btn>}
        {p.allowed?.includes("answer")&&!browserOnly&&!batchQuestions.length&&<Btn primary icon={Check} disabled={!answer.trim()} onClick={submit}>Submit & resume</Btn>}
      </div>
    </section>
  );
}

function Run({run,stop}){
  const results=run.results||[];
  return (
    <section className="panel run">
      <div className="run-head">
        <div>
          <small>AUTOMATION SESSION</small>
          <h3>{run.request?.mode==="discover"?"Discovering roles":run.request?.mode==="apply"?"Preparing application":"Portal session"}</h3>
          <span>Run {run.id.slice(0,12)} · {run.request?.portal} · {run.status}</span>
        </div>
        {["queued","running","waiting"].includes(run.status)&&<Btn icon={Square} onClick={stop}>Stop run</Btn>}
      </div>
      <div className="progress"/>
      <div className="runsteps"><span>Start browser</span><span>Work through portal</span><span>Human review</span><span>Complete</span></div>

      {run.request?.mode==="discover"&&(
        <div className="run-discovery">
          <div className="section-row">
            <div><small>DISCOVERY RESULTS</small><h4>{results.length} roles found</h4></div>
            {run.status==="completed"&&<Badge tone="success">Saved to job library</Badge>}
          </div>
          {results.slice(0,20).map((j,i)=>(
            <div className="discovery-row" key={j.url||i}>
              <div><b>{j.title||"Untitled role"}</b><span>{j.company||"Company not specified"}{j.location?" · "+j.location:""}</span></div>
              <a href={j.url} target="_blank" rel="noreferrer">Open <ArrowUpRight size={12}/></a>
            </div>
          ))}
          {!results.length&&<p className="muted">Jobs will appear here as the browser discovers them.</p>}
        </div>
      )}

      <div className="logs">
        {(run.logs||[]).slice(-10).map((x,i)=><div key={i}><b>{x.level||"info"}</b>{x.message}</div>)}
      </div>
    </section>
  );
}

export default App;
createRoot(document.getElementById("root")).render(<App />);

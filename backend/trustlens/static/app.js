(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const titles = {dashboard: 'Overview', new: 'New analysis', history: 'Investigations', detail: 'Investigation', system: 'System status'};
  const state = {view: 'dashboard', selected: null, previewUrl: null, historyOffset: 0, historyTotal: 0, searchTimer: null, uploading: false, adminToken: sessionStorage.getItem('trustlens_admin_token') || null};
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const fmtDate = value => { const date = new Date(value); return Number.isNaN(date.valueOf()) ? 'Unknown date' : new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(date); };
  const fmtBytes = value => { let n = Number(value) || 0; const units = ['B','KiB','MiB','GiB']; let i=0; while(n >= 1024 && i < units.length-1){n/=1024;i++;} return `${n.toFixed(i ? 1 : 0)} ${units[i]}`; };
  const notice = (id, message) => { const el = $(`#${id}`); if (!el) return; el.textContent = message; el.classList.toggle('hidden', !message); };
  function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.remove('visible'),3000);}
  async function api(url, options={}){const response=await fetch(url,{...options,headers:{Accept:'application/json',...(options.headers||{})}});if(!response.ok){let message=`Request failed (${response.status})`;try{const body=await response.json();message=body.error?.message||message;}catch{}throw new Error(message);}if(response.status===204)return null;return response.json();}
  function go(view, options={}){if(!titles[view])return;state.view=view;$$('.view').forEach(el=>el.classList.toggle('active',el.id===`view-${view}`));$$('.nav-item').forEach(el=>{const active=el.dataset.view===view;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});$('#page-title').textContent=titles[view];if(view==='dashboard')loadDashboard();if(view==='history')loadHistory();if(view==='system')loadSystem();if(options.focus!==false)$('#main').focus({preventScroll:true});if(location.hash!==`#${view}`)history.replaceState(null,'',`#${view}`);}
  function statusBadge(status){const klass=status==='SUCCESS'?'success':(['PARTIAL','FAILED'].includes(status)?'warning':'unavailable');return `<span class="badge ${klass}">${escapeHtml(status||'UNKNOWN')}</span>`;}
  function row(item){const media=item.media||{};return `<div class="table-row"><div class="table-name"><strong title="${escapeHtml(media.filename)}">${escapeHtml(media.filename||'Untitled upload')}</strong><small>${escapeHtml(item.analysis_id)} · ${escapeHtml((media.sha256||'').slice(0,16))}…</small></div><div class="table-cell">${escapeHtml(media.media_type||'unknown')}</div><div class="table-cell">${statusBadge(item.processing_status)}</div><div class="table-cell">${escapeHtml(fmtDate(item.created_at))}</div><button class="open-report" data-open="${escapeHtml(item.analysis_id)}">Open →</button></div>`;}
  function listMarkup(items){return items.length?`<div class="table-head"><span>INVESTIGATION</span><span>MEDIA</span><span>STATUS</span><span>CREATED</span><span></span></div>${items.map(row).join('')}`:'<div class="empty-state">No saved investigations match this view.</div>';}
  function sessionMarkup(item){const media=item.media||{};return `<article class="session-tile"><div class="session-tile-top"><span class="session-type">${escapeHtml((media.media_type||'media').toUpperCase())}</span>${statusBadge(item.processing_status)}</div><h3 title="${escapeHtml(media.filename)}">${escapeHtml(media.filename||'Untitled upload')}</h3><p>${escapeHtml(fmtDate(item.created_at))}</p><div class="session-tile-foot"><span class="mono">SHA · ${escapeHtml((media.sha256||'').slice(0,12))}${media.sha256?'…':'Unavailable'}</span><button class="open-report" data-open="${escapeHtml(item.analysis_id)}">Open report →</button></div></article>`;}
  function recentMarkup(items){return items.length?items.map(sessionMarkup).join(''):'<div class="empty-state">No saved investigations match this view.</div>';}
  function updateCompletionTrace(items){const svg=$('#completion-sparkline');if(!svg)return;const recent=[...items].slice(0,5).reverse();if(!recent.length){svg.setAttribute('aria-label','Recent outcome trace unavailable until reports exist');svg.querySelector('.sparkline-line').setAttribute('d','M0 32 L120 32');svg.querySelector('.sparkline-fill').setAttribute('d','M0 32 L120 32 L120 33 L0 33 Z');return;}const points=recent.map((item,index)=>`${recent.length===1?60:Math.round(index*120/(recent.length-1))},${item.processing_status==='SUCCESS'?8:25}`);const path=`M${points.join(' L')}`;svg.setAttribute('aria-label',`Recent report outcomes, newest at right: ${recent.map(item=>item.processing_status==='SUCCESS'?'completed':'review required').join(', ')}`);svg.querySelector('.sparkline-line').setAttribute('d',path);svg.querySelector('.sparkline-fill').setAttribute('d',`${path} L120 33 L0 33 Z`);}
  function updatePlayer({filename='',hash='',label='Pipeline idle',detail='Exact stage telemetry unavailable',processing=false,complete=false,error=false}={}){const name=$('#player-filename'),hashEl=$('#player-hash'),stateLabel=$('#player-state-label'),detailLabel=$('#player-progress-label'),track=$('#player-progress-track');if(!name)return;name.textContent=filename||'No active file';hashEl.textContent=hash?`SHA-256 · ${hash.slice(0,16)}…`:'SHA-256 · generated with saved report';stateLabel.textContent=label;detailLabel.textContent=detail;track.classList.toggle('is-processing',processing);track.classList.toggle('is-complete',complete);track.classList.toggle('is-error',error);if(processing){track.removeAttribute('aria-valuenow');track.setAttribute('aria-valuetext','Request in progress; stage percentage is not reported');}else{track.setAttribute('aria-valuenow',complete?'100':'0');track.setAttribute('aria-valuetext',complete?'Analysis request complete':'Idle; stage progress is not reported');}}
  async function loadDashboard(){notice('dashboard-error','');try{const [stats,list]=await Promise.all([api('/api/stats'),api('/api/analyses?limit=5')]);$('[data-stat="total"]').textContent=stats.total;$('[data-stat="completed"]').textContent=stats.completed;$('[data-stat="partial-failed"]').textContent=stats.partial+stats.failed+stats.unavailable;$('[data-stat="human_review"]').textContent=stats.human_review;$('#human-review-card').classList.toggle('has-review',stats.human_review>0);$('#recent-list').innerHTML=recentMarkup(list.items);updateCompletionTrace(list.items);}catch(error){notice('dashboard-error',error.message);$('#recent-list').innerHTML='<div class="empty-state">History could not be loaded.</div>';updateCompletionTrace([]);}}
  async function loadHistory(){notice('history-error','');const q=$('#history-search').value.trim();const params=new URLSearchParams({limit:'20',offset:String(state.historyOffset)});if(q)params.set('q',q);if($('#status-filter').value)params.set('status',$('#status-filter').value);if($('#media-filter').value)params.set('media_type',$('#media-filter').value);$('#history-list').innerHTML='<div class="loading-row">Loading investigations…</div>';try{const data=await api(`/api/analyses?${params}`);state.historyTotal=data.total;$('#history-list').innerHTML=listMarkup(data.items);$('#history-count').textContent=data.total?`Showing ${state.historyOffset+1}–${Math.min(state.historyOffset+data.items.length,data.total)} of ${data.total}`:'0 investigations';$('#page-prev').disabled=state.historyOffset===0;$('#page-next').disabled=state.historyOffset+data.limit>=data.total;}catch(error){notice('history-error',error.message);$('#history-list').innerHTML='<div class="empty-state">Investigations could not be loaded.</div>';$('#history-count').textContent='';}}
  function kvRows(obj){return Object.entries(obj||{}).map(([key,value])=>`<div class="system-row"><span>${escapeHtml(key.replaceAll('_',' '))}</span><span>${escapeHtml(typeof value==='object'?JSON.stringify(value):value)}</span></div>`).join('');}
  async function loadSystem(){
    notice('system-error','');
    const authPanel=$('#admin-auth-panel');
    const statusCont=$('#admin-status-container');
    const lockBtn=$('#lock-admin');
    if(!authPanel||!statusCont)return;

    if(state.adminToken){
      $('#system-content').innerHTML='<div class="loading-row">Checking privileged diagnostic telemetry…</div>';
      try{
        const statusData=await api('/api/admin/status',{
          headers:{'Authorization':`Bearer ${state.adminToken}`}
        });
        authPanel.classList.add('hidden');
        statusCont.classList.remove('hidden');
        if(lockBtn)lockBtn.classList.remove('hidden');
        const sessionTime=$('#admin-session-time');
        if(sessionTime)sessionTime.textContent=`Verified session · ${new Date().toLocaleTimeString()}`;

        const groups=[
          ['Backend & runtime health',{
            status:statusData.status,
            python_version:statusData.python_version,
            process_uptime_seconds:statusData.uptime_seconds,
            pid:statusData.pid
          }],
          ['Database store',{
            status:statusData.database?.status,
            investigations_count:statusData.database?.investigations_count,
            storage_path:statusData.database?.path
          }],
          ['Primary image detector',{
            model_name:statusData.models?.image_detector?.name,
            status:statusData.models?.image_detector?.status,
            model_file_present:statusData.models?.image_detector?.model_file_present,
            device:statusData.models?.image_detector?.device,
            fallback_mode:statusData.models?.image_detector?.fallback_mode
          }],
          ['Video analysis pipeline',{
            status:statusData.pipelines?.video?.status,
            frame_extraction:statusData.pipelines?.video?.frame_extraction,
            opencv_available:statusData.pipelines?.video?.opencv_available,
            ffmpeg_available:statusData.pipelines?.video?.ffmpeg_available
          }],
          ['Audio analysis pipeline (BETA)',{
            status:statusData.pipelines?.audio?.status,
            badge:'AUDIO DETECTION — BETA',
            warning:statusData.pipelines?.audio?.warning,
            supported_codecs:(statusData.pipelines?.audio?.supported_codecs||[]).join(', '),
            features:(statusData.pipelines?.audio?.features||[]).join(', ')
          }],
          ['Security & authorization',{
            access_control:'admin_only',
            admin_key_configured:statusData.security?.admin_key_configured,
            rate_limiting:statusData.security?.rate_limiting
          }],
          ['Test suite & integrity verification',{
            status:statusData.test_suite?.status,
            summary:statusData.test_suite?.last_run_summary
          }]
        ];

        $('#system-content').innerHTML=groups.map(([name,values])=>{
          const isBeta=name.includes('BETA');
          return `<article class="system-card ${isBeta?'audio-beta-card':''}"><h2>${escapeHtml(name)} ${isBeta?'<span class="badge badge-beta">BETA</span>':''}</h2>${kvRows(values)}</article>`;
        }).join('');
        return;
      }catch(err){
        state.adminToken=null;
        sessionStorage.removeItem('trustlens_admin_token');
        notice('system-error','Admin session expired or unauthorized. Please re-authenticate.');
      }
    }

    authPanel.classList.remove('hidden');
    statusCont.classList.add('hidden');
    if(lockBtn)lockBtn.classList.add('hidden');
    $('#system-content').innerHTML='';
  }

  function showEvidence(record, evidence){
    const report=record.report||{},analysis=report.analysis||{},result=analysis.result||{},source=report.source||{},fusion=report.fusion||{};
    $('#detail-heading').textContent=source.filename||'Investigation';
    $('#detail-subtitle').textContent=`${record.analysis_id} · ${fmtDate(record.created_at)}`;
    const resultLabel=report.proposed_outcome||analysis.decision||analysis.status||report.processing_status;
    const isAudio=(record.media?.media_type==='audio')||(source.media_type==='audio');
    const audioBetaBanner=isAudio?`<div class="audio-beta-banner" role="alert"><strong>AUDIO DETECTION — BETA</strong><p>Audio detection is experimental. Results may contain false positives or false negatives and should not be treated as definitive proof of authenticity.</p></div>`:'';

    const summary=`<div class="detail-hero"><article class="detail-card"><span>Processing status</span><strong>${escapeHtml(record.processing_status)} ${statusBadge(record.processing_status)}</strong></article><article class="detail-card"><span>Assessment</span><strong>${escapeHtml(resultLabel||'Review required')}</strong></article><article class="detail-card"><span>Human review</span><strong>${record.human_review_required?'Required':'Not flagged'}</strong></article></div>`;
    const sourceHash=source.sha256||record.media?.sha256||'';
    const sourceHtml=`<section class="detail-section"><h2>Source & integrity</h2><div class="system-row"><span>Media</span><span>${escapeHtml(source.media_type||record.media?.media_type)} · ${escapeHtml(fmtBytes(source.size_bytes))}</span></div><div class="system-row"><span>SHA-256</span><span class="mono">${escapeHtml(sourceHash)} ${sourceHash?`<button class="text-button" data-copy="${escapeHtml(sourceHash)}" aria-label="Copy source SHA-256">Copy</button>`:''}</span></div><div class="system-row"><span>Metadata observed</span><span>${escapeHtml(JSON.stringify(source.metadata||record.media?.metadata||{}))}</span></div></section>`;
    
    let audioDescriptorsHtml='';
    if(isAudio&&analysis.signal_descriptors){
      const sd=analysis.signal_descriptors;
      audioDescriptorsHtml=`<section class="detail-section"><h2>Acoustic signal descriptors (BETA)</h2><div class="system-row"><span>Sample rate</span><span>${escapeHtml(sd.sample_rate_hz)} Hz</span></div><div class="system-row"><span>Channels</span><span>${escapeHtml(sd.channels)}</span></div><div class="system-row"><span>Duration</span><span>${escapeHtml(sd.duration_seconds)} s</span></div><div class="system-row"><span>RMS energy</span><span>${escapeHtml(sd.rms_energy)}</span></div><div class="system-row"><span>Zero-crossing rate</span><span>${escapeHtml(sd.zero_crossing_rate)}</span></div><div class="system-row"><span>Spectral centroid</span><span>${escapeHtml(sd.spectral_centroid_hz)} Hz</span></div></section>`;
    }

    const ev=evidence.evidence||[];
    const evidenceHtml=`<section class="detail-section"><h2>Evidence signals</h2>${ev.length?ev.map(item=>`<div class="evidence-item"><strong>${escapeHtml(item.method||item.type||'Observed signal')} ${statusBadge(item.status||'AVAILABLE')}</strong><p>${escapeHtml(item.description||item.summary||JSON.stringify(item))}</p>${item.value!==undefined?`<p>Measurement: ${escapeHtml(JSON.stringify(item.value))}</p>`:''}</div>`).join(''):'<p>No evidence signal was emitted for this media.</p>'}</section>`;
    const provenance=evidence.provenance||result.provenance||{};
    const provenanceHtml=`<section class="detail-section"><h2>Metadata & provenance checks</h2>${Object.entries(provenance).length?Object.entries(provenance).map(([name,value])=>`<div class="evidence-item"><strong>${escapeHtml(name.replaceAll('_',' '))} ${value?.status?statusBadge(value.status):''}</strong><p>${escapeHtml(value?.interpretation||value?.reason||'Parser observation only; it does not verify source claims.')}</p>${value?.observed_fields?`<p>Observed fields: ${escapeHtml(JSON.stringify(value.observed_fields))}</p>`:''}</div>`).join(''):'<p>No provenance assessment is available for this report.</p>'}</section>`;
    const frames=evidence.frames||[];
    const frameHtml=`<section class="detail-section"><h2>Sampled video frames</h2>${frames.length?`<ul>${frames.map((frame,index)=>`<li>Frame ${index+1}${frame.timestamp_seconds!=null?` at ${escapeHtml(frame.timestamp_seconds)} s`:''}: ${escapeHtml(frame.status||'sampled')}${frame.sha256?` · SHA-256 ${escapeHtml(frame.sha256)}`:''}</li>`).join('')}</ul><p>Frame image artifacts are not retained after processing.</p>`:'<p>No sampled frames are available for this report.</p>'}</section>`;
    const fusionHtml=`<section class="detail-section"><h2>Evidence fusion & abstention</h2><p>${escapeHtml(fusion.summary||fusion.decision||'Fusion preserves available evidence and does not aggregate calibrated likelihoods.')}</p><pre>${escapeHtml(JSON.stringify(fusion,null,2))}</pre></section>`;
    const limitations=[...(evidence.limitations||[]),...(evidence.uncertainty?.reasons||[])];
    const limitHtml=`<section class="detail-section"><h2>Limitations & uncertainty</h2>${limitations.length?`<ul>${[...new Set(limitations)].map(value=>`<li>${escapeHtml(typeof value==='string'?value:JSON.stringify(value))}</li>`).join('')}</ul>`:'<p>Review the report fields and processing status. This tool does not provide a calibrated authenticity verdict.</p>'}</section>`;
    
    let modelAssessmentHtml = '';
    const det = result.detector;
    if (det && det.status === 'SUCCESS' && det.raw_scores) {
      const pred = (det.predicted_label || 'unknown').toUpperCase();
      const isReal = pred === 'REAL';
      const realScore = det.raw_scores.real !== undefined ? det.raw_scores.real : 0;
      const synthScore = det.raw_scores.synthetic !== undefined ? det.raw_scores.synthetic : 0;
      const realPct = (realScore * 100).toFixed(1);
      const synthPct = (synthScore * 100).toFixed(1);
      const modelName = det.model?.name || 'ResNet-18 Deepfake Classifier';
      const modelVer = det.model?.version || '1.0.0';
      const threshold = det.model?.threshold != null ? det.model.threshold : '0.50';

      modelAssessmentHtml = `<section class="detail-section model-assessment-hero">
        <div class="model-hero-top">
          <div>
            <span class="eyebrow" style="color:var(--accent-cyan-forensics,#00f0ff);font-size:10px;font-weight:700;letter-spacing:1px;">PRIMARY ML MODEL INFERENCE</span>
            <h2>${escapeHtml(modelName)} <small style="color:#888;font-size:13px;font-weight:400;">v${escapeHtml(modelVer)}</small></h2>
          </div>
          <span class="badge ${isReal ? 'badge-success' : 'badge-warning'} model-verdict-badge">
            ${isReal ? '● PREDICTED: AUTHENTIC (REAL)' : '▲ PREDICTED: SYNTHETIC (AI-GENERATED)'}
          </span>
        </div>
        <div class="model-confidence-bars">
          <div class="confidence-bar-group">
            <div class="confidence-bar-header">
              <span>Authentic (Real) Confidence</span>
              <strong>${realPct}%</strong>
            </div>
            <div class="confidence-track">
              <div class="confidence-fill real-fill" style="width: ${realPct}%"></div>
            </div>
          </div>
          <div class="confidence-bar-group">
            <div class="confidence-bar-header">
              <span>Synthetic (AI-Generated) Confidence</span>
              <strong>${synthPct}%</strong>
            </div>
            <div class="confidence-track">
              <div class="confidence-fill synth-fill" style="width: ${synthPct}%"></div>
            </div>
          </div>
        </div>
        <div class="model-meta-row">
          <span><strong>Decision Threshold:</strong> ${escapeHtml(threshold)}</span>
          <span><strong>Inference Status:</strong> SUCCESS (Evaluated)</span>
          <span><strong>Architecture:</strong> Deep Convolutional Neural Network (PyTorch ResNet-18)</span>
        </div>
      </section>`;
    }

    $('#detail-content').innerHTML=audioBetaBanner+summary+modelAssessmentHtml+sourceHtml+audioDescriptorsHtml+evidenceHtml+provenanceHtml+frameHtml+fusionHtml+limitHtml;
    $('#download-report').dataset.id=record.analysis_id;
    $('#delete-analysis').dataset.id=record.analysis_id;
  }

  async function openDetail(id){notice('detail-error','');state.selected=id;go('detail');$('#detail-content').innerHTML='<div class="loading-row">Loading report…</div>';try{const [record,evidence]=await Promise.all([api(`/api/analyses/${encodeURIComponent(id)}`),api(`/api/analyses/${encodeURIComponent(id)}/evidence`)]);showEvidence(record,evidence);const source=record.report?.source||record.media||{};updatePlayer({filename:source.filename||'Saved investigation',hash:source.sha256||record.media?.sha256||'',label:'Saved report loaded',detail:`${record.processing_status} · recorded ${fmtDate(record.created_at)}`,complete:true});}catch(error){notice('detail-error',error.message);$('#detail-content').innerHTML='';}}
  const allowed=new Set(['.jpg','.jpeg','.png','.webp','.mp4','.mov','.avi','.wav','.mp3']);
  function selectedFile(file){
    if(state.uploading)return;
    const error=$('#file-error');error.textContent='';error.classList.add('hidden');
    if(state.previewUrl){URL.revokeObjectURL(state.previewUrl);state.previewUrl=null;}
    state.selected=null;$('#preview').replaceChildren();$('#preview').classList.add('hidden');$('#selected-file').classList.add('hidden');
    if(!file){updateSubmit();updatePlayer();return;}
    const ext='.'+(file.name.split('.').pop()||'').toLowerCase();
    if(!allowed.has(ext)){
      error.textContent='Choose a supported image, video, WAV, or MP3 file.';
    }else if(file.size>100*1024*1024){
      error.textContent='The file exceeds the 100 MiB limit.';
    }else{
      state.selected=file;
      $('#selected-file').textContent=`${file.name} · ${fmtBytes(file.size)}`;
      $('#selected-file').classList.remove('hidden');
      updatePlayer({filename:file.name,label:'Ready for analysis',detail:`${fmtBytes(file.size)} · source hash will be returned with the saved report`});
      const type=file.type;
      if(type.startsWith('image/')){
        state.previewUrl=URL.createObjectURL(file);
        const img=document.createElement('img');img.src=state.previewUrl;img.alt='Selected image preview';
        $('#preview').append(img);$('#preview').classList.remove('hidden');
      }else if(type.startsWith('video/')||ext==='.mp4'||ext==='.mov'||ext==='.avi'){
        state.previewUrl=URL.createObjectURL(file);
        const video=document.createElement('video');video.src=state.previewUrl;video.controls=true;video.preload='metadata';video.setAttribute('aria-label','Selected video preview');video.style.maxWidth='100%';video.style.maxHeight='320px';video.style.borderRadius='8px';
        $('#preview').append(video);$('#preview').classList.remove('hidden');
      }else if(ext==='.wav'||ext==='.mp3'||type.startsWith('audio/')){
        state.previewUrl=URL.createObjectURL(file);
        const audioBox=document.createElement('div');
        audioBox.innerHTML=`<div class="audio-beta-banner" style="margin-top:10px;"><strong>AUDIO DETECTION — BETA</strong><p>Audio detection is experimental. Results may contain false positives or false negatives and should not be treated as definitive proof of authenticity.</p><audio controls src="${state.previewUrl}" style="margin-top:10px; width:100%;"></audio></div>`;
        $('#preview').append(audioBox);$('#preview').classList.remove('hidden');
      }
    }
    if(error.textContent){error.classList.remove('hidden');updatePlayer({filename:file.name,label:'File not accepted',detail:error.textContent,error:true});}
    updateSubmit();
  }
  function updateSubmit(){$('#analyze-button').disabled=state.uploading||!(state.selected&&$('#evidence-consent').checked);$('#media-file').disabled=state.uploading;$('#evidence-consent').disabled=state.uploading;}
  async function submit(){if(!state.selected||!$('#evidence-consent').checked||state.uploading)return;const file=state.selected,button=$('#analyze-button'),status=$('#upload-state');state.uploading=true;updateSubmit();status.textContent='Uploading and analyzing locally…';status.classList.remove('hidden');updatePlayer({filename:file.name,label:'Analysis request active',detail:'Backend stage percentage and GPU telemetry are not reported',processing:true});try{const body=new FormData();body.append('file',file,file.name);const result=await api('/api/analyses',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body});status.textContent='Analysis complete. Opening the saved report…';state.selected=null;$('#media-file').value='';$('#evidence-consent').checked=false;state.uploading=false;updateSubmit();await openDetail(result.analysis_id);toast('Report saved to this local workspace.');}catch(error){status.textContent=error.message;state.uploading=false;updateSubmit();button.disabled=false;updatePlayer({filename:file.name,label:'Analysis request failed',detail:error.message,error:true});}}
  document.addEventListener('click',async event=>{const copy=event.target.closest('[data-copy]');if(copy){try{await navigator.clipboard.writeText(copy.dataset.copy);toast('SHA-256 copied.');}catch{toast('Clipboard access is unavailable in this browser context.');}return;}const nav=event.target.closest('[data-view]');if(nav){go(nav.dataset.view);return;}const goButton=event.target.closest('[data-go]');if(goButton){go(goButton.dataset.go);return;}const open=event.target.closest('[data-open]');if(open){openDetail(open.dataset.open);return;}});
  $('#media-file').addEventListener('change',event=>selectedFile(event.target.files?.[0]));$('#evidence-consent').addEventListener('change',updateSubmit);$('#analyze-button').addEventListener('click',submit);
  const drop=$('#drop-zone');drop.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();$('#media-file').click();}});for(const name of ['dragenter','dragover'])drop.addEventListener(name,event=>{event.preventDefault();drop.classList.add('dragging');});for(const name of ['dragleave','drop'])drop.addEventListener(name,event=>{event.preventDefault();drop.classList.remove('dragging');});drop.addEventListener('drop',event=>selectedFile(event.dataTransfer.files?.[0]));
  for(const id of ['history-search','status-filter','media-filter'])$(`#${id}`).addEventListener(id==='history-search'?'input':'change',()=>{state.historyOffset=0;clearTimeout(state.searchTimer);state.searchTimer=setTimeout(loadHistory,id==='history-search'?220:0);});$('#page-prev').addEventListener('click',()=>{state.historyOffset=Math.max(0,state.historyOffset-20);loadHistory();});$('#page-next').addEventListener('click',()=>{if(state.historyOffset+20<state.historyTotal){state.historyOffset+=20;loadHistory();}});$('#refresh-system').addEventListener('click',loadSystem);
  const adminForm=$('#admin-auth-form');if(adminForm){adminForm.addEventListener('submit',async event=>{event.preventDefault();notice('admin-auth-error','');const keyInput=$('#admin-key-input');const key=(keyInput?.value||'').trim();try{const resp=await api('/api/admin/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});state.adminToken=resp.token;sessionStorage.setItem('trustlens_admin_token',resp.token);if(keyInput)keyInput.value='';toast('Admin authenticated successfully.');await loadSystem();}catch(err){notice('admin-auth-error',err.message||'Authentication failed.');}});}
  const lockAdmin=$('#lock-admin');if(lockAdmin){lockAdmin.addEventListener('click',()=>{state.adminToken=null;sessionStorage.removeItem('trustlens_admin_token');toast('Admin session locked.');loadSystem();});}
  $('#download-report').addEventListener('click',async event=>{const id=event.currentTarget.dataset.id;if(!id)return;try{const response=await fetch(`/api/analyses/${encodeURIComponent(id)}/report`);if(!response.ok)throw new Error('Report download failed.');const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`trustlens-${id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){toast(error.message);}});
  $('#print-report').addEventListener('click',()=>window.print());
  $('#delete-analysis').addEventListener('click',async event=>{const id=event.currentTarget.dataset.id;if(!id||!window.confirm('Delete this saved report from local history? This cannot be undone.'))return;try{await api(`/api/analyses/${encodeURIComponent(id)}`,{method:'DELETE'});toast('Report deleted from local history.');go('history');}catch(error){notice('detail-error',error.message);}});
  window.addEventListener('hashchange',()=>{const view=location.hash.slice(1);if(titles[view])go(view,{focus:false});});window.addEventListener('beforeunload',()=>{if(state.previewUrl)URL.revokeObjectURL(state.previewUrl);});
  async function initCapabilitiesAndSamples() {
    try {
      const caps = await api('/api/capabilities');
      const card = $('#detector-status-card');
      if (card) {
        if (caps.image?.trained_detector === 'available') {
          card.className = 'capability-success';
          const m = caps.image.model || {};
          card.innerHTML = `<span>✓</span><p><strong>ML Model Active: ${escapeHtml(m.name || 'ResNet-18 Frame Baseline')}</strong><br>PyTorch deepfake classifier loaded and active for real vs. synthetic inference.</p>`;
        } else {
          card.className = 'capability-warning';
          card.innerHTML = `<span>!</span><p><strong>Detector status: Fallback Mode</strong><br>Primary ML model weights unconfigured. Using deterministic DCT frequency descriptors.</p>`;
        }
      }
    } catch (e) {
      console.warn('Capabilities error:', e);
    }

    try {
      const samplesData = await api('/api/test-samples');
      const container = $('#demo-samples-grid');
      const filterTabs = $('#demo-filter-tabs');
      if (container && samplesData.samples && samplesData.samples.length) {
        const allSamples = samplesData.samples;

        const renderSampleButton = (sample) => {
          const isReal = sample.ground_truth === 'real';
          const isVid = sample.modality === 'video';
          const icon = sample.modality === 'image' ? '🖼️' : (isVid ? '🎥' : '🎙️');
          const tagText = isVid ? (isReal ? 'REAL VIDEO' : 'AI VIDEO') : (isReal ? 'REAL' : 'SYNTHETIC');
          return `<button type="button" class="demo-sample-btn ${isVid ? 'video-sample-btn' : ''}" data-sample-id="${escapeHtml(sample.sample_id)}" data-sample-name="${escapeHtml(sample.file_name)}" data-modality="${escapeHtml(sample.modality)}">
            <span class="sample-name">${icon} ${escapeHtml(sample.file_name)}</span>
            <span class="sample-tag ${isReal ? 'tag-real' : 'tag-synthetic'}">${escapeHtml(tagText)}</span>
          </button>`;
        };

        const renderSamples = (filter) => {
          if (filterTabs) {
            filterTabs.querySelectorAll('.demo-tab').forEach(tab => {
              tab.classList.toggle('active', tab.dataset.filter === filter);
            });
          }

          if (filter === 'all') {
            const videos = allSamples.filter(s => s.modality === 'video');
            const images = allSamples.filter(s => s.modality === 'image');
            const audios = allSamples.filter(s => s.modality === 'audio');

            container.innerHTML = `
              <div class="demo-category-group">
                <div class="demo-category-header">🎥 Video Verification Samples (${videos.length}) <span class="badge badge-success">READY</span></div>
                <div class="demo-samples-grid">${videos.map(renderSampleButton).join('')}</div>
              </div>
              <div class="demo-category-group">
                <div class="demo-category-header">🖼️ Photographic Verification Samples (${images.length})</div>
                <div class="demo-samples-grid">${images.map(renderSampleButton).join('')}</div>
              </div>
              <div class="demo-category-group">
                <div class="demo-category-header">🎙️ Audio Verification Samples (${audios.length}) <span class="badge badge-beta">BETA</span></div>
                <div class="demo-samples-grid">${audios.map(renderSampleButton).join('')}</div>
              </div>
            `;
          } else {
            const filtered = allSamples.filter(s => s.modality === filter);
            container.innerHTML = `<div class="demo-samples-grid">${filtered.map(renderSampleButton).join('')}</div>`;
          }

          container.querySelectorAll('.demo-sample-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
              const sampleId = btn.dataset.sampleId;
              const sampleName = btn.dataset.sampleName;
              const modality = btn.dataset.modality;
              toast(`Loading ${modality} sample: ${sampleName}…`);
              try {
                const res = await fetch(`/api/test-samples/${encodeURIComponent(sampleId)}/file`);
                if (!res.ok) throw new Error('Could not download sample');
                const blob = await res.blob();
                let mime = blob.type;
                if (!mime || mime === 'application/octet-stream') {
                  if (modality === 'video' || sampleName.endsWith('.mp4')) mime = 'video/mp4';
                  else if (modality === 'image') mime = 'image/jpeg';
                  else if (modality === 'audio') mime = 'audio/wav';
                }
                const file = new File([blob], sampleName, {type: mime});
                selectedFile(file);
                const consent = $('#evidence-consent');
                if (consent) {
                  consent.checked = true;
                  updateSubmit();
                }
                toast(`Loaded ${sampleName}! Click "Analyze media" to evaluate.`);
              } catch (err) {
                toast(`Failed to load test sample: ${err.message}`);
              }
            });
          });
        };

        if (filterTabs) {
          filterTabs.querySelectorAll('.demo-tab').forEach(tab => {
            tab.addEventListener('click', () => {
              renderSamples(tab.dataset.filter || 'all');
            });
          });
        }

        renderSamples('all');
      }
    } catch (e) {
      console.warn('Samples load error:', e);
      const grid = $('#demo-samples-grid');
      if (grid) grid.innerHTML = '<span class="muted">Test samples available in tests/fixtures/multimodal</span>';
    }
  }
  initCapabilitiesAndSamples();

  const initial=location.hash.slice(1);go(titles[initial]?initial:'dashboard',{focus:false});
})();

'use strict';
(() => {
 const el=id=>document.getElementById(id), camera=el('wordCamera');
 let stream=null,recorder=null,chunks=[],timer=null,busy=false,generation=0,controller=null,recordToken=0,starting=false,previewURL=null;
 function controls(){el('wordStart').disabled=busy||starting||!!stream;el('wordRecord').disabled=busy||!stream;el('wordStop').disabled=!stream&&!previewURL;el('wordUpload').disabled=busy;}
 function clearPreview(){
  camera.pause();camera.removeAttribute('src');camera.controls=false;
  if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null;}
  el('wordUploadInfo').textContent='';el('wordUploadInfo').hidden=true;
 }
 function previewClip(blob,name){
  if(stream){stream.getTracks().forEach(track=>track.stop());stream=null;}
  camera.srcObject=null;clearPreview();previewURL=URL.createObjectURL(blob);
  camera.src=previewURL;camera.controls=true;camera.load();el('cameraHint').hidden=true;
  el('wordUploadInfo').textContent='Selected video: '+name+' · '+(blob.size/1024/1024).toFixed(2)+' MB';
  el('wordUploadInfo').hidden=false;
 }
 camera.addEventListener('error',()=>{if(previewURL)el('wordUploadInfo').textContent+=' · Preview cannot play this format in your browser.';});
 let recognizedWord=null,autoVoice=false;
 const wordVoice=new LetterVoice(window.speechSynthesis,window.SpeechSynthesisUtterance,
  message=>{el('wordVoiceStatus').textContent=message;});
 function speakResult(){if(recognizedWord)wordVoice.speakMessage(recognizedWord);}
 el('wordSpeak').onclick=speakResult;
 el('wordVoice').onclick=()=>{
  autoVoice=!autoVoice;wordVoice.enable(autoVoice);
  el('wordVoice').setAttribute('aria-pressed',String(autoVoice));
  el('wordVoice').textContent=autoVoice?'Disable voice':'Enable voice';
  if(autoVoice&&recognizedWord)speakResult();
 };
 if(!window.speechSynthesis){el('wordVoice').disabled=true;el('wordVoiceStatus').textContent='Speech playback is unavailable in this browser.';}
 function clearResult(){recognizedWord=null;el('wordSpeak').disabled=true;wordVoice.reset();el('wordResult').textContent='—';el('wordDetails').textContent='';el('wordAlternatives').replaceChildren();}
 function uploadClip(form,token){
  return new Promise((resolve,reject)=>{
   const xhr=new XMLHttpRequest();controller=xhr;xhr.open('POST','/api/words/predict');xhr.timeout=120000;
   xhr.upload.onprogress=event=>{
    if(token!==generation)return;
    if(event.lengthComputable){const percent=Math.round(event.loaded/event.total*100);el('wordProgress').value=percent;el('wordProgressLabel').textContent='Uploading video · '+percent+'%';}
   };
   xhr.upload.onload=()=>{if(token===generation){el('wordProgress').removeAttribute('value');el('wordProgressLabel').textContent='Upload complete · Recognizing your sign…';el('wordStatus').textContent='Processing on this computer…';}};
   xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);resolve({ok:xhr.status>=200&&xhr.status<300,json:async()=>data});}catch{reject(Error('The server returned an unreadable response. Try again.'));}};
   xhr.onerror=()=>reject(TypeError('Cannot reach the server'));
   xhr.ontimeout=()=>reject(Error('Recognition timed out. Try a shorter clip.'));
   xhr.onabort=()=>{const error=Error('Cancelled');error.name='AbortError';reject(error);};
   xhr.send(form);
  });
 }
 async function submit(blob,name){
  if(blob.size>8*1024*1024){busy=false;clearResult();controls();el('wordStatus').textContent='Video is too large. Use a clip under 8 MB.';return;}
  const token=++generation;busy=true;clearResult();controls();
  el('wordProgressWrap').hidden=false;el('wordProgress').value=0;el('wordProgressLabel').textContent='Uploading video · 0%';
  el('wordStatus').textContent='Uploading video…';
  const form=new FormData();form.append('video',blob,name);
  try{
   const response=await uploadClip(form,token);
   const result=await response.json();if(token!==generation)return;
   if(!response.ok)throw Error(result.error||'Prediction failed');
   if(result.status==='insufficient_detection'){
    el('wordDetails').textContent='Not enough hand or body detection. Keep your face, shoulders and hands in view.';
   }else if(result.status==='uncertain_word'){
    el('wordDetails').textContent='No clear supported-word match. The sign may be unsupported or uncertain.';
   }else{
    el('wordResult').textContent=result.label;
    recognizedWord=result.label;el('wordSpeak').disabled=!window.speechSynthesis;if(autoVoice)speakResult();
    el('wordDetails').textContent='Experimental match. Hand detection '+Math.round(result.quality.any_hand_coverage*100)+'% of sampled frames.';
    for(const candidate of result.candidates){const li=document.createElement('li');li.textContent=candidate.label;el('wordAlternatives').append(li);}
   }
   el('wordStatus').textContent='Finished in '+(result.processing_ms/1000).toFixed(1)+' seconds. Try another isolated sign.';
  }catch(error){if(token===generation&&error.name!=='AbortError'){el('wordStatus').textContent=error instanceof TypeError?'Cannot reach the local recognition server. Reconnect to the server, then upload again.':error.message;el('wordDetails').textContent='No result. Try a short, supported video.';}}
  finally{if(token===generation){busy=false;controller=null;el('wordProgressWrap').hidden=true;controls();}}
 }
 el('wordStart').onclick=async()=>{
  const token=++generation;starting=true;controls();
  try{
   if(!navigator.mediaDevices?.getUserMedia)throw Error('Camera access is unavailable. Upload a video instead.');
   const incoming=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480}},audio:false});
   if(token!==generation){incoming.getTracks().forEach(t=>t.stop());return;}
   clearPreview();stream=incoming;camera.srcObject=stream;await camera.play();el('cameraHint').hidden=true;
   el('wordStatus').textContent='Camera preview ready. Click Record 3 seconds to run recognition. Sign once with your face, shoulders and hands visible.';
  }catch(error){if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}el('wordStatus').textContent=error.message;}
  finally{starting=false;controls();}
 };
 el('wordRecord').onclick=()=>{
  if(!stream||busy)return;
  if(!window.MediaRecorder){el('wordStatus').textContent='Recording is unavailable in this browser. Upload a video instead.';return;}
  clearResult();const token=++recordToken;chunks=[];busy=true;controls();
  const type=['video/webm;codecs=vp8','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
  if(!type){busy=false;controls();el('wordStatus').textContent='No supported recording format. Upload a video instead.';return;}
  try{
   recorder=new MediaRecorder(stream,{mimeType:type,videoBitsPerSecond:1200000});
   recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
   recorder.onerror=()=>{clearTimeout(timer);recordToken++;busy=false;controls();el('wordStatus').textContent='Recording failed. Try uploading a video.';};
   recorder.onstop=()=>{clearTimeout(timer);if(token!==recordToken)return;const blob=new Blob(chunks,{type});submit(blob,type.includes('mp4')?'sign.mp4':'sign.webm');};
   recorder.start();let remaining=3;el('wordStatus').textContent='Recording: 3 seconds. Sign once now.';
   timer=setInterval(()=>{remaining--;if(remaining>0)el('wordStatus').textContent='Recording: '+remaining+' seconds…';else{clearInterval(timer);if(recorder.state==='recording')recorder.stop();}},1000);
  }catch(error){busy=false;controls();el('wordStatus').textContent=error.message;}
 };
 function stop(){el('wordProgressWrap').hidden=true;wordVoice.reset();generation++;recordToken++;clearInterval(timer);controller?.abort();controller=null;
  if(recorder&&recorder.state!=='inactive')recorder.stop();recorder=null;
  if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;camera.srcObject=null;clearPreview();
  busy=false;el('cameraHint').hidden=false;controls();
 }
 el('wordStop').onclick=()=>{stop();clearResult();el('wordStatus').textContent='Stopped. No pending result will be displayed.';};
 el('wordUpload').onchange=event=>{const file=event.target.files[0];if(file&&!busy){if(file.size<=8*1024*1024)previewClip(file,file.name);submit(file,file.name);}event.target.value='';};
 el('wordExample').onchange=event=>{el('exampleVideo').src='/api/words/example/'+encodeURIComponent(event.target.value);el('exampleVideo').load();};
 addEventListener('pagehide',stop);controls();
})();

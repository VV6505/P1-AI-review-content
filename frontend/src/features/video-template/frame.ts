import { safeMedia, type Project, type Scene, type Ratio } from "./model.ts";
import { featureStoryRuntime } from "./feature-story-runtime.ts";

export type Resources = string;
export type FrameSequence = { directory: string; times: number[]; width: number; height: number };
export async function loadResources(fetchResource: typeof fetch = fetch): Promise<Resources> {
  const response = await fetchResource("/video-template.css");
  if (!response.ok) throw new Error("Không tải được CSS preview.");
  let css = await response.text();
  // Embed licensed local fonts so the exported scene has no network dependencies.
  const fonts = [...new Set([...css.matchAll(/url\("(\/fonts\/video-template\/[^"\s]+)"\)/g)].map(match => match[1]))];
  for (const path of fonts) {
    const font = await fetchResource(path);
    if (!font.ok) throw new Error("Không tải được font template.");
    const bytes = new Uint8Array(await font.arrayBuffer());
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
    css = css.replaceAll(path, `data:font/ttf;base64,${btoa(binary)}`);
  }
  for (const name of ["BeVietnamPro", "NotoSerif"]) {
    const license = await fetchResource(`/fonts/video-template/${name}-OFL.txt`);
    if (!license.ok) throw new Error("Không tải được giấy phép font template.");
    css += `\n/* ${name}: ${(await license.text()).replaceAll("*/", "* /")} */`;
  }
  return css;
}
export async function readMedia(file: File, kind: string): Promise<string> {
  const types: Record<string, string[]> = { video: ["video/mp4", "video/webm"], image: ["image/png", "image/jpeg", "image/webp"], audio: ["audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/ogg", "audio/webm"] };
  if (!types[kind]?.includes(file.type) || !file.size || file.size > 25 * 1024 * 1024) throw new Error("File sai loại, rỗng hoặc vượt 25 MB.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(safeMedia(String(reader.result))!);
    reader.onerror = () => reject(new Error("Không đọc được media."));
    reader.readAsDataURL(file);
  });
}
const json = (value: unknown) => JSON.stringify(value).replace(/[<>&\u2028\u2029]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);

export function buildFrame(project: Project, scene: Scene, ratio: Ratio, preset: string, media: Record<string, string>, css: Resources, options: { captions?: boolean } = {}): string {
  const bindings: Record<string, string> = Object.create(null);
  for (const asset of project.assets) if (Object.hasOwn(media, asset.id)) bindings[asset.id] = safeMedia(media[asset.id])!;
  return frameDocument(project, scene, ratio, preset, bindings, css, options.captions !== false, false);
}

/** Renderer files are resolved by the local export tool, never by M2/LLM paths. */
export function buildRenderFrame(project: Project, scene: Scene, ratio: Ratio, preset: string, files: Record<string, string>, css: Resources, frames: Record<string, FrameSequence> = {}): string {
  const bindings: Record<string, string> = Object.create(null);
  for (const asset of project.assets) {
    const path = files[asset.id];
    if (!path || !/^media\/[A-Za-z0-9_-]+\.(mp4|webm|wav|mp3|m4a|ogg|png|jpg|webp)$/.test(path)) throw new Error("Renderer cần file media tương đối trong gói đã resolve.");
    bindings[asset.id] = path;
  }
  for (const sequence of Object.values(frames)) {
    if (!/^media\/decoded-\d+$/.test(sequence.directory) || !sequence.times.length || sequence.times.some((t, i) => !Number.isFinite(t) || t < 0 || (i > 0 && t <= sequence.times[i - 1])) || !(sequence.width > 0 && sequence.height > 0)) throw new Error("Invalid decoded frame sequence");
  }
  return frameDocument(project, scene, ratio, preset, bindings, css, false, true, frames);
}

function frameDocument(project: Project, scene: Scene, ratio: Ratio, preset: string, bindings: Record<string, string>, css: Resources, captions: boolean, localFiles: boolean, frames: Record<string, FrameSequence> = {}): string {
  if (!["cinematic", "animation", "vintage"].includes(preset)) throw new Error("Preset chưa hỗ trợ.");
  if (!["16:9", "9:16"].includes(ratio)) throw new Error("Tỷ lệ chưa hỗ trợ.");
  const data = { project, scene, ratio, preset, media: bindings, captions, frames };
  const mediaPolicy = localFiles ? "'self' file:" : "data:";
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src ${mediaPolicy}; media-src ${mediaPolicy}"><title>Creator template</title><style>${css}</style></head><body><main id="root"></main><script>const DATA=JSON.parse(${json(JSON.stringify(data))});DATA.media=Object.assign(Object.create(null),DATA.media);${runtime}</script></body></html>`;
}

// The iframe and exported HTML execute the same four layouts and timeline.
const runtime = `
const root=document.getElementById('root'), {scene,project}=DATA;
root.className=DATA.preset+(DATA.ratio==='9:16'?' portrait':'');
root.dataset.layout=scene.layout;root.dataset.scene=scene.id;
if(project.design){const d=project.design;for(const [key,value] of Object.entries({bg:d.background,fg:d.foreground,accent:d.accent,surface:d.surface??d.background,line:d.border??d.foreground+'33'}))root.style.setProperty('--'+key,value);
  const fonts={'be-vietnam-pro':'TemplateSans,sans-serif','noto-serif':'TemplateSerif,serif'};
  if(fonts[d.heading_font]){root.style.setProperty('--heading-font',fonts[d.heading_font]);root.dataset.headingFont=d.heading_font;}
  if(fonts[d.body_font]){root.style.fontFamily=fonts[d.body_font];root.dataset.bodyFont=d.body_font;}}
function node(tag,parent,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;parent.appendChild(n);return n;}
${featureStoryRuntime}
const header=node('header',root);node('div',header,scene.props.eyebrow?.text||project.title,'brand');node('h1',header,scene.props.title?.text||scene.subtitle);
const content=node('section',root,undefined,'content'),caption=node('p',root,undefined,'caption');
if(!DATA.captions)caption.style.visibility='hidden';
const reveals=[];
function reveal(element,at){reveals.push({element,at});}
function missing(parent,message){let n=parent.querySelector('.missing');if(!n)n=node('div',parent,undefined,'missing');n.textContent=message;}
function picture(parent,id){
  if(!DATA.media[id]){missing(parent,'Chưa có ảnh được bàn giao');return;}
  const image=node('img',parent);image.alt='Tư liệu bàn giao';image.src=DATA.media[id];
  image.addEventListener('error',()=>missing(parent,'Không đọc được ảnh'));
  return image;
}
let screen,inner,video,image,story;
if(scene.layout==='feature_clip'||scene.layout==='highlight_zoom'){
  screen=node('div',content,undefined,'screen');inner=node('div',screen,undefined,'media-inner');
  if(scene.parts.length){const crop=node('div',inner,undefined,'media-crop');crop.style.cssText='position:absolute;inset:0;overflow:hidden';video=node('video',crop);video.muted=true;video.playsInline=true;video.preload='auto';
    if(scene.crop){const [x,y,w,h]=scene.crop.rect;video.style.cssText='position:absolute;max-width:none;object-fit:fill;width:'+100/w+'%;height:'+100/h+'%;left:'+(-x/w*100)+'%;top:'+(-y/h*100)+'%';}}
  else image=picture(inner,scene.imageId);
  if(scene.layout==='feature_clip'){
    story=createFeatureStory(root,header,content,screen,inner,scene,project);
  }
}else if(scene.layout==='steps'){
  const list=node('ol',content,undefined,'steps');
  scene.props.items.forEach((item,i)=>{const card=node('li',list,undefined,'card');node('b',card,item.number);node('span',card,item.text);reveal(card,item.at??i*.3);});
}else if(scene.layout==='before_after'){
  const comparison=node('div',content,undefined,'comparison');
  scene.props.panels.forEach((panel,i)=>{const card=node('article',comparison,undefined,'card');node('strong',card,panel.label);picture(node('div',card,undefined,'picture'),scene.compareIds[i]);node('p',card,panel.text);reveal(card,i*.22);});
}
function fit(){const portrait=DATA.ratio==='9:16';root.style.transform='scale('+Math.min(innerWidth/(portrait?1080:1920),innerHeight/(portrait?1920:1080))+')';}
addEventListener('resize',fit);fit();
function sizeScreen(width,height){if(story){screen.style.aspectRatio=width+' / '+height;screen.style.width='100%';return;}const columns=getComputedStyle(content).gridTemplateColumns.split(' '),notes=content.querySelector('.notes');const reserve=columns.length===1&&notes&&notes.clientHeight?notes.clientHeight+parseFloat(getComputedStyle(content).rowGap):0;screen.style.aspectRatio=width+' / '+height;screen.style.width=Math.max(1,Math.min(parseFloat(columns[0])||content.clientWidth,(content.clientHeight-reserve)*width/height))+'px';}
function sizeImage(){if(image?.naturalWidth)sizeScreen(image.naturalWidth,image.naturalHeight);}
image?.addEventListener('load',sizeImage);sizeImage();
let generation=0,mediaReady=true,fontsReady=true,captureImage;
const fontsLoaded=Promise.all([document.fonts.load('400 36px TemplateSans'),document.fonts.load('700 72px TemplateSans'),document.fonts.load('700 72px TemplateSerif')]).catch(()=>{fontsReady=false;});
function waitMedia(event,ready){return new Promise(resolve=>{
  if(ready()){resolve(true);return;}let timer;
  const done=()=>{clearTimeout(timer);video.removeEventListener(event,done);video.removeEventListener('error',done);resolve(ready());};
  video.addEventListener(event,done,{once:true});video.addEventListener('error',done,{once:true});timer=setTimeout(done,2500);
});}
async function seek(time){
  const version=++generation,t=Math.max(0,Math.min(scene.duration,Number(time)||0));
  const cue=scene.segments.find(c=>c.start<=t&&t<c.end);caption.textContent=DATA.captions?(scene.segments.length?(cue?.text||''):scene.subtitle):'';
  const entrance=Math.min(1,t/(DATA.preset==='animation'?.35:.7));
  if(story)story.seek(t);else{content.style.opacity=String(entrance);content.style.transform=entrance===1?'none':'translateY('+((1-entrance)*(DATA.preset==='animation'?50:20))+'px)';}
  for(const {element,at} of reveals){const progress=Math.max(0,Math.min(1,(t-at)/(DATA.preset==='animation'?.3:.55)));const eased=1-(1-progress)**3;element.style.opacity=String(progress);element.style.transform=progress===1?'none':'translateY('+((1-eased)*26)+'px)';}
  if(inner&&scene.focus){const [x,y,w,h]=scene.focus.rect,progress=story?story.focusProgress(t):Math.max(0,Math.min(1,(t-scene.focus.at)/.9));const scale=1+(Math.min(story?1.65:2.2,1/w,1/h)-1)*progress;
    const tx=Math.max(1-scale,Math.min(0,.5-(x+w/2)*scale)),ty=Math.max(1-scale,Math.min(0,.5-(y+h/2)*scale));inner.style.transform='translate('+tx*100+'%,'+ty*100+'%) scale('+scale+')';}
  if(video){
    // Cuts play at source speed; hold the last frame during any remaining narration.
    let offset=t,part=scene.parts.at(-1);
    for(let i=0;i<scene.parts.length;i++){const p=scene.parts[i];if(offset<p.end-p.start||i===scene.parts.length-1){part=p;break;}offset-=p.end-p.start;}
    const url=DATA.media[part.assetId];mediaReady=false;
    if(!url){video.removeAttribute('src');missing(screen,'Chưa có clip được bàn giao');}
    else{
      screen.querySelector('.missing')?.remove();
      const sequence=Object.hasOwn(DATA.frames,part.assetId)?DATA.frames[part.assetId]:null;
      if(sequence){
        // Decode once with FFmpeg; reuse the same CSS, crop, focus and timeline.
        if(!captureImage){captureImage=node('img',video.parentNode);captureImage.style.cssText=video.style.cssText;captureImage.alt='';}
        video.style.display='none';captureImage.style.display='block';
        const target=Math.min(part.end-.001,part.start+Math.max(0,offset));
        let low=0,high=sequence.times.length;
        while(low<high){const mid=(low+high)>>>1;if(sequence.times[mid]<=target+1e-5)low=mid+1;else high=mid;}
        captureImage.src=sequence.directory+'/'+String(Math.max(0,low-1)+1).padStart(6,'0')+'.png';
        try{await captureImage.decode();mediaReady=true;}catch{missing(screen,'Không đọc được frame đã giải mã');}
        if(scene.crop&&(sequence.width!==scene.crop.sourceSize[0]||sequence.height!==scene.crop.sourceSize[1])){mediaReady=false;missing(screen,'Kích thước clip khác nguồn dùng để tính crop/focus');}
        sizeScreen(sequence.width*(scene.crop?.rect[2]??1),sequence.height*(scene.crop?.rect[3]??1));
      }else{
      if(captureImage)captureImage.style.display='none';video.style.display='block';
      if(video.getAttribute('src')!==url){video.src=url;video.load();}
      let ready=await waitMedia('loadedmetadata',()=>video.readyState>=1);
      if(version!==generation)return;
      const target=Math.min(part.end-.001,part.start+Math.max(0,offset));
      if(ready&&(!video.videoWidth||part.end>video.duration+.01)){ready=false;missing(screen,'Clip không có hình hoặc ngắn hơn điểm cắt');}
      if(ready&&scene.crop&&(video.videoWidth!==scene.crop.sourceSize[0]||video.videoHeight!==scene.crop.sourceSize[1])){ready=false;missing(screen,'Kích thước clip khác nguồn dùng để tính crop/focus');}
      // Chromium stores seek time in microseconds. At e.g. 362/30 seconds,
      // truncation can land just before the intended frame. Bias inside it.
      if(ready){sizeScreen(video.videoWidth*(scene.crop?.rect[2]??1),video.videoHeight*(scene.crop?.rect[3]??1));if(Math.abs(video.currentTime-target)>.005)video.currentTime=Math.min(part.end-.001,target+1e-5);ready=await waitMedia('seeked',()=>!video.seeking&&video.readyState>=2);}
      mediaReady=ready;
      }
    }
  }
  if(version===generation)return diagnostics();
}
function diagnostics(){
  // Check intrinsic layout; entrance transforms of hidden cards are not text overflow.
  const animated=[content,...(story?[header,...story.panels]:[]),...reveals.map(r=>r.element)].map(n=>[n,n.style.transform]);for(const [n] of animated)n.style.transform='none';
  const bounds=root.getBoundingClientRect(),overflow=[];
  root.querySelectorAll('h1,.brand,.card,.caption,.content,.story-beat-text').forEach(n=>{const r=n.getBoundingClientRect();if(n.scrollWidth>n.clientWidth+2||n.scrollHeight>n.clientHeight+2||r.left<bounds.left-2||r.right>bounds.right+2||r.top<bounds.top-2||r.bottom>bounds.bottom+2)overflow.push(n.className||n.tagName);});
  for(const [n,transform] of animated)n.style.transform=transform;
  const missingMedia=!!root.querySelector('.missing');
  return {sceneId:scene.id,fontsReady,mediaReady:mediaReady&&!missingMedia&&fontsReady,textOverflow:overflow,missingMedia};
}
let renderQueue=Promise.resolve();
function renderAt(t,options){const job=renderQueue.then(async()=>{await fontsLoaded;await document.fonts.ready;await seek(t);await Promise.all([...root.querySelectorAll('img')].map(img=>img.decode().catch(()=>missing(img.parentNode,'Không đọc được ảnh'))));sizeImage();if(!options?.capture||(video&&(!captureImage||captureImage.style.display==='none')))await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));fit();return diagnostics();});renderQueue=job.catch(()=>{});return job;}
// CDP captureScreenshot flushes paint itself. Preview callers still wait for RAF.
window.CreatorTemplate={version:1,seek:renderAt,renderAt,diagnostics};
let pendingMessage=null,messageRendering=false;
addEventListener('message',async event=>{if(event.source!==parent||event.data?.type!=='creator-template-seek')return;pendingMessage=event.data;if(messageRendering)return;messageRendering=true;try{while(pendingMessage){const request=pendingMessage;pendingMessage=null;const result=await renderAt(request.time);parent.postMessage({type:'creator-template-status',requestId:request.requestId,time:request.time,...result},'*');}}finally{messageRendering=false;}});
renderAt(0);
`;

// All motion is a function of scene time, so preview, backward seek and render agree.
export const featureStoryRuntime = `
function createFeatureStory(root,header,content,screen,inner,scene,project){
  // A landscape output shows the whole recorded desktop; portrait retains the
  // supplied closer crop. Reproject focus so neither output distorts the source.
  const crop=scene.crop;
  if(DATA.ratio==='16:9'&&crop){
    if(scene.focus){const [x,y,w,h]=scene.focus.rect,[cx,cy,cw,ch]=crop.rect;scene.focus={...scene.focus,rect:[cx+x*cw,cy+y*ch,w*cw,h*ch]};}
    scene.crop=undefined;const video=screen.querySelector('video');if(video)video.style.cssText='';
  }
  root.classList.add('feature-story');
  root.dataset.motionMode=scene.motion?.mode??'adaptive';
  header.className='story-intro';
  header.querySelector('.brand').className='brand story-eyebrow';
  const title=header.querySelector('h1'),text=title.textContent,split=text.lastIndexOf(' vào ');
  title.textContent='';
  node('span',title,split>0?text.slice(0,split):text,'story-title-main');
  if(split>0)node('span',title,text.slice(split+1),'story-title-tail');
  node('span',header,'↗','story-intro-arrow');
  const masthead=node('div',root,undefined,'story-masthead');
  node('span',masthead,Array.from(project.title.trim())[0]?.toLocaleUpperCase('vi')||'•','story-monogram');node('span',masthead,project.title,'story-product');
  node('span',masthead,'/','story-masthead-divider');node('span',masthead,'TÍNH NĂNG','story-category');
  node('div',root,scene.id.replace(/^s/,''),'story-page');
  node('div',root,undefined,'story-grid');node('div',root,undefined,'story-orbit');
  content.className='content story-stage';screen.classList.add('story-screen');
  const chrome=node('div',content,undefined,'story-window');content.insertBefore(chrome,screen);
  const dots=node('span',chrome,undefined,'story-window-dots');for(let i=0;i<3;i++)node('i',dots);
  node('span',chrome,new URL(project.sourceUrl).hostname,'story-window-url');node('span',chrome,'↗','story-window-expand');
  const introEnd=scene.motion?.introEnd??Math.min(1.2,scene.duration*.18);
  const beats=scene.motion?.beats??[];
  const panels=beats.map((beat,i)=>{
    const panel=node('section',root,undefined,'story-beat'+(beat.result?' is-result':''));panel.dataset.beat=String(i+1);panel.dataset.start=String(beat.start);panel.dataset.end=String(beat.end);panel.dataset.placement=i%2===0?'top':'bottom';panel.dataset.side=beat.side??(i%2===0?'left':'right');
    const kicker=node('div',panel,undefined,'story-beat-kicker');
    node('span',kicker,beat.result?'✓':String(i+1).padStart(2,'0'),'story-beat-marker');
    node('span',kicker,beat.result?'KẾT QUẢ':'THAO TÁC','story-beat-label');
    node('h2',panel,beat.text,'story-beat-text');
    const line=node('div',panel,undefined,'story-beat-line');node('i',line);
    return {beat,panel};
  });
  const timeline=node('div',root,undefined,'story-timeline');
  for(let i=0;i<beats.length+1;i++)node('span',timeline);
  const target=scene.focus?node('div',inner,undefined,'story-focus'):null;
  if(target){const [x,y,w,h]=scene.focus.rect;target.style.cssText='left:'+x*100+'%;top:'+y*100+'%;width:'+w*100+'%;height:'+h*100+'%';for(let i=0;i<4;i++)node('i',target);}
  function smooth(v){v=Math.max(0,Math.min(1,v));return v*v*(3-2*v);}
  function windowAt(t,start,end){return smooth((t-start)/.26)*(1-smooth((t-(end-.22))/.22));}
  function guideAt(t,beat){
    if(beat.result)return 0;
    const duration=beat.end-beat.start,enter=Math.min(.34,duration*.22),exit=Math.min(.42,duration*.28);
    return smooth((t-beat.start-.08)/enter)*(1-smooth((t-(beat.end-exit-.08))/exit));
  }
  function show(element,alpha,shift){element.style.opacity=String(alpha);element.style.visibility=alpha>.0001?'visible':'hidden';element.style.transform=alpha===1?'none':'translateY('+shift+'px)';}
  function seek(t){
    const intro=introEnd>0?windowAt(t,-.12,introEnd+.16):0;show(header,intro,(1-intro)*32);
    const camera=smooth((t-introEnd+.1)/.9);
    content.style.opacity=String(smooth((t+.15)/.6));
    const portrait=DATA.ratio==='9:16';
    const adaptive=!portrait&&root.dataset.motionMode==='adaptive';
    let layoutAmount=0,layoutDirection=1;
    beats.forEach((beat,i)=>{const amount=guideAt(t,beat);if(amount>layoutAmount){layoutAmount=amount;layoutDirection=panels[i].panel.dataset.side==='left'?1:-1;}});
    // Each cut opens wide, makes room for its instruction, then returns wide.
    // Portrait keeps the centered video and only animates the instruction.
    const shift=adaptive?layoutDirection*320*layoutAmount:0;
    const scale=(.99+camera*.01)*(adaptive?1-.36*layoutAmount:1);
    content.style.transform='translate('+shift+'px,'+((1-camera)*12)+'px) scale('+scale+')';
    root.dataset.composition=portrait?'portrait':(adaptive&&layoutAmount>.01?'guide':'wide');
    root.dataset.layoutAmount=String(adaptive?layoutAmount:0);
    let active=-1;
    panels.forEach(({beat,panel},i)=>{
      const alpha=!adaptive||beat.result?windowAt(t,beat.start-.08,beat.end):smooth((guideAt(t,beat)-.2)/.8);
      show(panel,alpha,t>beat.end-.22?-(1-alpha)*24:(1-alpha)*36);
      panel.querySelector('.story-beat-line i').style.transform='scaleX('+smooth((t-beat.start)/(beat.end-beat.start))+')';
      if(t>=beat.start&&t<beat.end)active=i;
    });
    root.dataset.phase=active<0?'intro':(beats[active].result?'result':'step-'+(active+1));
    [...timeline.children].forEach((n,i)=>n.classList.toggle('is-active',i===(active+1)));
    const orbit=root.querySelector('.story-orbit');orbit.style.transform='translateY('+(-t*5)+'px) rotate('+(t*4)+'deg)';
    if(target){target.style.opacity=String(windowAt(t,scene.focus.at-.12,Math.min(scene.duration,scene.focus.at+1.8)));}
  }
  function focusProgress(t){return smooth((t-scene.focus.at)/.75)*(1-smooth((t-(scene.duration-1.15))/.65));}
  return {seek,focusProgress,panels:panels.map(p=>p.panel)};
}
`;

// Preserve saved research links and reveal detail panels reached by a hash.
(() => {
  const oldResearch=/(?:^|\/)research(?:\.html)?$/.test(location.pathname);
  const moved=new Set(['#primary','#stability','#research-method','#reference-model']);
  if(oldResearch&&moved.has(location.hash)){
    location.replace(new URL(`framework.html${location.hash}`,location.href).href);
    return;
  }
  function reveal(){
    if(!location.hash)return;
    let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
    const target=document.getElementById(id);
    if(!target)return;
    for(let parent=target;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
    requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
  }
  window.addEventListener('hashchange',reveal);
  reveal();
})();

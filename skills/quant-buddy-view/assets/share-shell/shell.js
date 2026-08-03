(function(){
  const VERSION = "research-warehouse-v1";
  const OFFICIAL_ORIGIN = "https://www.quantbuddy.cn";
  const CHANNEL = "qb-research-warehouse-v1";
  const $ = id => document.getElementById(id);
  let state={};
  let pageContext=null;
  let warehouseReady=false;
  let warehouseTimer=0;
  let warehouseHelloTimer=0;
  let warehouseHelloAttempts=0;
  function callMaybe(v){ return typeof v === "function" ? v() : v; }
  function setStatus(msg){ const el=$("sharePosterStatus"); if(el) el.textContent=msg; }
  function setBusy(busy){ ["copyPoster","downloadPoster"].forEach(id=>{ const el=$(id); if(el) el.disabled=!!busy; }); }
  function setRefreshBusy(busy,label){
    const btn=$("refresh");
    if(!btn) return;
    const text=btn.querySelector(".action-label") || btn;
    btn.disabled=!!busy;
    if(label) text.textContent=label;
  }
  async function runRefresh(){
    if(!state.onRefresh) return;
    try{ setRefreshBusy(true,"取数中"); await state.onRefresh(); }
    finally{ setRefreshBusy(false,"刷新数据"); }
  }
  function derivePageContext(url){
    try{
      const parsed=new URL(url || location.href, location.href);
      const parts=parsed.pathname.split("/").filter(Boolean);
      const pagesIndex=parts.indexOf("pages");
      if(pagesIndex<0 || parts.length<pagesIndex+3) return null;
      const routeParts=parts.slice(pagesIndex+1);
      const file=routeParts.pop() || "";
      if(!/\.html$/i.test(file)) return null;
      const pageId=file.replace(/\.html$/i,"");
      if(!pageId || !routeParts.length) return null;
      const encoded=[...routeParts,pageId].map(value=>encodeURIComponent(decodeURIComponent(value)));
      return {
        pageId:pageId,
        playgroundUrl:OFFICIAL_ORIGIN+"/playground/"+encoded.join("/"),
        embedUrl:OFFICIAL_ORIGIN+"/embed/research-warehouse?page_id="+encodeURIComponent(pageId)
      };
    }catch(e){ return null; }
  }
  function setFavoriteState(favorited){
    const btn=$("favoriteBtn");
    if(!btn) return;
    btn.classList.toggle("is-favorited",!!favorited);
    btn.setAttribute("aria-pressed",favorited ? "true" : "false");
    const label=btn.querySelector(".action-label");
    if(label) label.textContent=favorited ? "已收藏" : "收藏";
    btn.title=favorited ? "管理投研仓收藏" : "收藏到投研仓";
  }
  function warehouseFrame(){ return $("researchWarehouseFrame"); }
  function buildWarehouseHello(context){
    if(!context || !context.pageId) return null;
    return {channel:CHANNEL,type:"hello",page_id:context.pageId};
  }
  function postWarehouseHello(){
    const frame=warehouseFrame(), message=buildWarehouseHello(pageContext);
    if(!frame || !frame.contentWindow || !message) return false;
    frame.contentWindow.postMessage(message,OFFICIAL_ORIGIN);
    return true;
  }
  function stopWarehouseHelloRetries(){
    window.clearTimeout(warehouseHelloTimer);
    warehouseHelloTimer=0;
    warehouseHelloAttempts=0;
  }
  function scheduleWarehouseHelloRetries(){
    stopWarehouseHelloRetries();
    const send=()=>{
      if(warehouseReady || warehouseHelloAttempts>=8){ stopWarehouseHelloRetries(); return; }
      warehouseHelloAttempts+=1;
      postWarehouseHello();
      warehouseHelloTimer=window.setTimeout(send,500);
    };
    send();
  }
  function ensureWarehouseFrame(){
    const frame=warehouseFrame();
    if(!frame || !pageContext) return null;
    if(!frame.dataset.qbWarehouseLoadBound){
      frame.addEventListener("load",()=>{ warehouseReady=false; scheduleWarehouseHelloRetries(); });
      frame.dataset.qbWarehouseLoadBound="1";
    }
    if(!frame.src) frame.src=pageContext.embedUrl;
    if(!warehouseReady) scheduleWarehouseHelloRetries();
    return frame;
  }
  function fallbackWarehouseWindow(){
    if(!pageContext) return;
    window.open(pageContext.embedUrl,"_blank","noopener,noreferrer");
  }
  function openWarehouse(){
    const modal=$("researchWarehouseModal");
    if(!pageContext || !modal){ fallbackWarehouseWindow(); return; }
    ensureWarehouseFrame();
    if(warehouseReady) postWarehouseHello();
    else scheduleWarehouseHelloRetries();
    if(!warehouseReady){
      window.clearTimeout(warehouseTimer);
      warehouseTimer=window.setTimeout(()=>{ if(!warehouseReady){ closeWarehouse(); fallbackWarehouseWindow(); } },5000);
    }
    modal.classList.add("open");
    modal.setAttribute("aria-hidden","false");
    document.documentElement.style.overflow="hidden";
  }
  function closeWarehouse(){
    window.clearTimeout(warehouseTimer);
    warehouseTimer=0;
    const modal=$("researchWarehouseModal");
    if(!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden","true");
    document.documentElement.style.overflow="";
    const btn=$("favoriteBtn"); if(btn) btn.focus();
  }
  function isTrustedWarehouseMessage(event,frame,context){
    const data=event && event.data;
    return !!(
      frame
      && context
      && event.origin===OFFICIAL_ORIGIN
      && event.source===frame.contentWindow
      && data
      && data.channel===CHANNEL
      && data.page_id===context.pageId
    );
  }
  function onWarehouseMessage(event){
    const frame=warehouseFrame();
    if(!isTrustedWarehouseMessage(event,frame,pageContext)) return;
    const data=event.data;
    warehouseReady=true;
    stopWarehouseHelloRetries();
    window.clearTimeout(warehouseTimer);
    warehouseTimer=0;
    if(data.type==="state" || data.type==="collected") setFavoriteState(data.favorited===true);
    if(data.type==="close") closeWarehouse();
  }
  async function generatePoster(){
    const canvas=$("sharePosterCanvas"), img=$("sharePosterImage");
    if(!canvas || !img || !window.QBSharePoster) return;
    setBusy(true); setStatus("生成中");
    try{
      const data = state.getPosterData ? (await state.getPosterData()) : {};
      await window.QBSharePoster.generate(canvas,img,data || {},{
        templateName: callMaybe(state.templateName), title: callMaybe(state.title), subtitle: callMaybe(state.subtitle),
        asof: callMaybe(state.asof), shareUrl: state.shareUrl || location.href,
      });
      setStatus("已生成 PNG 海报");
    }catch(e){ setStatus("生成失败：" + (e && e.message ? e.message : e)); }
    finally{ setBusy(false); }
  }
  function openSharePoster(){
    const modal=$("sharePosterModal"); if(!modal) return;
    modal.classList.add("open"); modal.setAttribute("aria-hidden","false"); generatePoster();
    const btn=$("copyPoster"); if(btn) btn.focus();
  }
  function closeSharePoster(){
    const modal=$("sharePosterModal"); if(!modal) return;
    modal.classList.remove("open"); modal.setAttribute("aria-hidden","true");
  }
  function canvasBlob(canvas){ return new Promise(resolve=>canvas.toBlob(resolve,"image/png",1)); }
  function shareUrl(){ return state.shareUrl || location.href; }
  function ensureCopyLinkButton(){
    if($("copyLink")) return;
    const tools=document.querySelector(".share-tools"); if(!tools) return;
    const btn=document.createElement("button"); btn.className="share-tool"; btn.id="copyLink"; btn.type="button"; btn.textContent="复制链接";
    tools.insertBefore(btn, tools.firstElementChild || null);
  }
  function copyTextFallback(value){
    const input=document.createElement("textarea"); input.value=value; input.setAttribute("readonly",""); input.style.position="fixed"; input.style.left="-9999px";
    document.body.appendChild(input);
    try{ input.select(); if(!document.execCommand("copy")) throw new Error("copy command unavailable"); }
    finally{ input.remove(); }
  }
  async function copyShareLink(){
    const url=shareUrl(), btn=$("copyLink");
    try{
      if(btn) btn.disabled=true;
      if(navigator.clipboard && navigator.clipboard.writeText){ try{ await navigator.clipboard.writeText(url); } catch(e){ copyTextFallback(url); } }
      else copyTextFallback(url);
      setStatus("已复制链接，可直接粘贴分享");
    }catch(e){ setStatus("复制链接受限，请从浏览器地址栏复制"); }
    finally{ if(btn) btn.disabled=false; }
  }
  async function copyPosterImage(){
    const canvas=$("sharePosterCanvas"), btn=$("copyPoster"); if(!canvas) return;
    try{
      if(btn) btn.disabled=true;
      const blob=await canvasBlob(canvas);
      if(!blob || !navigator.clipboard || !window.ClipboardItem) throw new Error("clipboard image unavailable");
      await navigator.clipboard.write([new ClipboardItem({"image/png":blob})]); setStatus("已复制图片，可直接粘贴");
    }catch(e){ setStatus("复制图片受限，可右键预览图复制或下载 PNG"); }
    finally{ if(btn) btn.disabled=false; }
  }
  async function downloadPosterImage(){
    const img=$("sharePosterImage"); if(!img || !img.src) await generatePoster();
    const a=document.createElement("a"); a.href=$("sharePosterImage").src; a.download=(callMaybe(state.title) || document.title || "quantbuddy") + "-分享海报.png";
    document.body.appendChild(a); a.click(); a.remove(); setStatus("已开始下载 PNG");
  }
  function init(opts){
    state=Object.assign({},opts || {}); ensureCopyLinkButton();
    pageContext=derivePageContext(location.href);
    const start=$("startUsing"); if(start && pageContext) start.href=pageContext.playgroundUrl;
    if(pageContext) ensureWarehouseFrame();
    const refresh=$("refresh"), share=$("shareBtn"), favorite=$("favoriteBtn");
    if(refresh && !refresh.dataset.qbBound){ refresh.addEventListener("click",runRefresh); refresh.dataset.qbBound="1"; }
    if(share && !share.dataset.qbBound){ share.addEventListener("click",openSharePoster); share.dataset.qbBound="1"; }
    if(favorite && !favorite.dataset.qbBound){ favorite.addEventListener("click",openWarehouse); favorite.dataset.qbBound="1"; }
    const link=$("copyLink"), copy=$("copyPoster"), down=$("downloadPoster"), close=$("closePoster"), modal=$("sharePosterModal"), warehouseModal=$("researchWarehouseModal");
    if(link && !link.dataset.qbBound){ link.addEventListener("click",copyShareLink); link.dataset.qbBound="1"; }
    if(copy && !copy.dataset.qbBound){ copy.addEventListener("click",copyPosterImage); copy.dataset.qbBound="1"; }
    if(down && !down.dataset.qbBound){ down.addEventListener("click",downloadPosterImage); down.dataset.qbBound="1"; }
    if(close && !close.dataset.qbBound){ close.addEventListener("click",closeSharePoster); close.dataset.qbBound="1"; }
    if(modal && !modal.dataset.qbBound){ modal.addEventListener("click",e=>{ if(e.target===modal) closeSharePoster(); }); modal.dataset.qbBound="1"; }
    if(warehouseModal && !warehouseModal.dataset.qbBound){ warehouseModal.addEventListener("click",e=>{ if(e.target===warehouseModal) closeWarehouse(); }); warehouseModal.dataset.qbBound="1"; }
    if(!document.documentElement.dataset.qbShareEsc){
      document.addEventListener("keydown",e=>{ if(e.key==="Escape"){ closeSharePoster(); closeWarehouse(); } });
      window.addEventListener("message",onWarehouseMessage);
      document.documentElement.dataset.qbShareEsc="1";
    }
  }
  window.QB_SHARE_SHELL_VERSION=VERSION;
  window.QBShareShell={init:init, open:openSharePoster, close:closeSharePoster, refresh:runRefresh, setRefreshBusy:setRefreshBusy, derivePageContext:derivePageContext, buildWarehouseHello:buildWarehouseHello, isTrustedWarehouseMessage:isTrustedWarehouseMessage, openWarehouse:openWarehouse, closeWarehouse:closeWarehouse};
})();

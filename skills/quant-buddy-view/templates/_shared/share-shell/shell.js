(function(){
  const VERSION = "copy-link-v1";
  const $ = id => document.getElementById(id);
  let state={};
  function callMaybe(v){ return typeof v === "function" ? v() : v; }
  function setStatus(msg){ const el=$("sharePosterStatus"); if(el) el.textContent=msg; }
  function setBusy(busy){
    ["copyPoster","downloadPoster"].forEach(id=>{ const el=$(id); if(el) el.disabled=!!busy; });
  }
  function setRefreshBusy(busy,label){
    const btn=$("refresh");
    if(!btn) return;
    const text=btn.querySelector(".action-label") || btn;
    btn.disabled=!!busy;
    if(label) text.textContent=label;
  }
  async function runRefresh(){
    if(!state.onRefresh) return;
    try{
      setRefreshBusy(true,"取数中");
      await state.onRefresh();
    }finally{
      setRefreshBusy(false,"刷新数据");
    }
  }
  async function generatePoster(){
    const canvas=$("sharePosterCanvas"), img=$("sharePosterImage");
    if(!canvas || !img || !window.QBSharePoster) return;
    setBusy(true); setStatus("生成中");
    try{
      const data = state.getPosterData ? (await state.getPosterData()) : {};
      await window.QBSharePoster.generate(canvas,img,data || {},{
        templateName: callMaybe(state.templateName),
        title: callMaybe(state.title),
        subtitle: callMaybe(state.subtitle),
        asof: callMaybe(state.asof),
        shareUrl: state.shareUrl || location.href,
      });
      setStatus("已生成 PNG 海报");
    }catch(e){
      setStatus("生成失败：" + (e && e.message ? e.message : e));
    }finally{
      setBusy(false);
    }
  }
  function openSharePoster(){
    const modal=$("sharePosterModal");
    if(!modal) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden","false");
    generatePoster();
    const btn=$("copyPoster");
    if(btn) btn.focus();
  }
  function closeSharePoster(){
    const modal=$("sharePosterModal");
    if(!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden","true");
  }
  function canvasBlob(canvas){
    return new Promise(resolve=>canvas.toBlob(resolve,"image/png",1));
  }
  function shareUrl(){
    return state.shareUrl || location.href;
  }
  function ensureCopyLinkButton(){
    if($("copyLink")) return;
    const tools=document.querySelector(".share-tools");
    if(!tools) return;
    const btn=document.createElement("button");
    btn.className="share-tool";
    btn.id="copyLink";
    btn.type="button";
    btn.textContent="复制链接";
    tools.insertBefore(btn, tools.firstElementChild || null);
  }
  function copyTextFallback(value){
    const input=document.createElement("textarea");
    input.value=value;
    input.setAttribute("readonly","");
    input.style.position="fixed";
    input.style.left="-9999px";
    document.body.appendChild(input);
    try{
      input.select();
      if(!document.execCommand("copy")) throw new Error("copy command unavailable");
    }finally{
      input.remove();
    }
  }
  async function copyShareLink(){
    const url=shareUrl(), btn=$("copyLink");
    try{
      if(btn) btn.disabled=true;
      if(navigator.clipboard && navigator.clipboard.writeText){
        try{ await navigator.clipboard.writeText(url); }
        catch(e){ copyTextFallback(url); }
      }else{
        copyTextFallback(url);
      }
      setStatus("已复制链接，可直接粘贴分享");
    }catch(e){
      setStatus("复制链接受限，请从浏览器地址栏复制");
    }finally{
      if(btn) btn.disabled=false;
    }
  }
  async function copyPosterImage(){
    const canvas=$("sharePosterCanvas"), btn=$("copyPoster");
    if(!canvas) return;
    try{
      if(btn) btn.disabled=true;
      const blob=await canvasBlob(canvas);
      if(!blob || !navigator.clipboard || !window.ClipboardItem) throw new Error("clipboard image unavailable");
      await navigator.clipboard.write([new ClipboardItem({"image/png":blob})]);
      setStatus("已复制图片，可直接粘贴");
    }catch(e){
      setStatus("复制图片受限，可右键预览图复制或下载 PNG");
    }finally{
      if(btn) btn.disabled=false;
    }
  }
  async function downloadPosterImage(){
    const img=$("sharePosterImage");
    if(!img || !img.src) await generatePoster();
    const a=document.createElement("a");
    a.href=$("sharePosterImage").src;
    a.download=(callMaybe(state.title) || document.title || "quantbuddy") + "-分享海报.png";
    document.body.appendChild(a); a.click(); a.remove();
    setStatus("已开始下载 PNG");
  }
  function init(opts){
    state=Object.assign({},opts || {});
    ensureCopyLinkButton();
    const refresh=$("refresh"), share=$("shareBtn");
    if(refresh && !refresh.dataset.qbBound){ refresh.addEventListener("click",runRefresh); refresh.dataset.qbBound="1"; }
    if(share && !share.dataset.qbBound){ share.addEventListener("click",openSharePoster); share.dataset.qbBound="1"; }
    const link=$("copyLink"), copy=$("copyPoster"), down=$("downloadPoster"), close=$("closePoster"), modal=$("sharePosterModal");
    if(link && !link.dataset.qbBound){ link.addEventListener("click",copyShareLink); link.dataset.qbBound="1"; }
    if(copy && !copy.dataset.qbBound){ copy.addEventListener("click",copyPosterImage); copy.dataset.qbBound="1"; }
    if(down && !down.dataset.qbBound){ down.addEventListener("click",downloadPosterImage); down.dataset.qbBound="1"; }
    if(close && !close.dataset.qbBound){ close.addEventListener("click",closeSharePoster); close.dataset.qbBound="1"; }
    if(modal && !modal.dataset.qbBound){ modal.addEventListener("click",e=>{ if(e.target===modal) closeSharePoster(); }); modal.dataset.qbBound="1"; }
    if(!document.documentElement.dataset.qbShareEsc){
      document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeSharePoster(); });
      document.documentElement.dataset.qbShareEsc="1";
    }
  }
  window.QB_SHARE_SHELL_VERSION=VERSION;
  window.QBShareShell={init:init, open:openSharePoster, close:closeSharePoster, refresh:runRefresh, setRefreshBusy:setRefreshBusy};
})();

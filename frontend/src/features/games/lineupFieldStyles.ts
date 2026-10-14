export const FIELD_CSS = `
.lu-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;padding:14px 16px;border-bottom:1px solid var(--line)}
.lu-head .side{display:flex;align-items:center;gap:8px;min-width:0}
.lu-head .side>div{min-width:0}
.lu-head .side.rt{flex-direction:row-reverse;text-align:right}
.lu-head .tn{font-size:13px;font-weight:800;overflow-wrap:anywhere}
.lu-head .pers{font-size:10px;color:var(--t3);margin-top:2px}
.lu-chips{display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px 0;align-items:center}
.upill{display:inline-flex;align-items:center;min-height:44px;border:none;border-radius:999px;padding:6px 12px;font-size:11.5px;font-weight:700;background:var(--raise);color:var(--t2);cursor:pointer}
.upill.on{background:var(--acc-fill);color:#fff}
.upill .mini{width:14px;height:14px;flex:none;border-radius:50%;display:inline-block;margin-right:7px}
.info-btn{margin-left:auto;flex:none;width:44px;height:44px;border-radius:50%;border:1px solid var(--line);background:none;color:var(--t2);font-size:13px;font-weight:700;cursor:pointer}
.ol-summary{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--t2)}
.ratings-help{margin:12px 16px 0;background:var(--raise);border:1px solid var(--line);border-radius:10px;padding:12px 14px;font-size:12px;color:var(--t2);line-height:1.6}
.ratings-help b{color:var(--t1)}
.ratings-help .ramp{display:flex;gap:10px;margin-top:10px;flex-wrap:wrap}
.fieldwrap{padding:16px 16px 6px;display:flex;justify-content:center}
.fieldbox{position:relative;width:100%;max-width:500px;aspect-ratio:500/860}
.fieldbox svg.turf{position:absolute;inset:0;display:block;width:100%;height:100%;border-radius:12px}
.player{position:absolute;display:flex;flex-direction:column;align-items:center;justify-content:center;width:clamp(44px,12%,64px);height:50px;transform:translate(-50%,-50%);margin:0;text-align:center;cursor:pointer;background:none;border:0;border-radius:6px;padding:0}
.player:focus-visible{outline:2px solid var(--acc);outline-offset:2px;z-index:5}
.pav{position:relative;width:32px;height:32px;flex:none;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff;box-shadow:0 1px 4px rgba(0,0,0,.55),0 0 0 1.5px rgba(14,13,21,.55)}
.player:hover .pav{box-shadow:0 0 0 2px var(--acc)}
.pav img{width:100%;height:100%;border-radius:50%;object-fit:cover;object-position:top}
.fieldbox .badge{position:absolute;top:-5px;right:-6px;min-width:24px;padding:1.5px 4px;border-radius:6px;font-size:9px;font-weight:800;font-variant-numeric:tabular-nums;text-align:center;box-shadow:0 0 0 1.5px rgba(14,13,21,.7)}
.td-pip{position:absolute;left:-7px;top:-5px;width:14px;height:14px;border-radius:50%;background:rgba(14,13,21,.85);display:flex;align-items:center;justify-content:center;font-size:9px}
.pname{display:block;max-width:100%;margin-top:3px;font-size:10px;line-height:14px;font-weight:600;color:rgba(255,255,255,.92);text-shadow:0 1px 3px rgba(0,0,0,.9);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pname .no{color:rgba(255,255,255,.55);font-weight:700;margin-right:2px}
.player.ol .pav{width:26px;height:26px;font-size:8.5px;opacity:.85}
.field-cap{padding:10px 16px 14px;font-size:10px;line-height:1.6;color:var(--t3);display:flex;gap:6px;align-items:baseline;justify-content:center}
@media(max-width:480px){.lu-head{padding:12px;gap:10px}.lu-head .side{gap:6px}.lu-head .tn{font-size:12px}.lu-head .chip{width:18px;height:18px;font-size:7px}.lu-head .avg{min-width:30px;padding:3px 4px}.fieldwrap{padding-left:8px;padding-right:8px}}
`

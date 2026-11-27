"""Read the actual JS-exported DXF in an independent CAD parser."""
import io
import json
import subprocess
import ezdxf

source=r'''
const fs=require("node:fs"),html=fs.readFileSync("index.html","utf8");
const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);
const keys=["window.LerikaDecors=(()=>","window.LerikaFurniture=(()=>","window.LerikaEngineering=(()=>"];
const w=new Function("const window={};"+keys.map(k=>scripts.find(s=>s.includes(k))).join("\n")+";return window")();
const E=w.LerikaFurniture,Q=w.LerikaEngineering,out=[];
for(const [type,p] of Object.entries(E.presets)){
 const m=Q.build({type,w:p[1],h:p[2],d:p[3],n:p[4],t:16,ft:16});
 for(const mode of ["front","side","top","section"]){
  const q=Q.panelProjection(m,mode);
  out.push({type,mode,rects:q.rects.length,dxf:Q.dxf(m,mode)});
 }
}
console.log(JSON.stringify(out));
'''
samples=json.loads(subprocess.check_output(["node","-e",source],text=True))
assert len(samples)==48
for s in samples:
    doc=ezdxf.read(io.StringIO(s["dxf"],newline=None))
    label=s["type"]+"/"+s["mode"]
    assert doc.units==4,label
    assert doc.layers.get("HIDDEN").dxf.linetype=="DASHED",label
    auditor=doc.audit()
    assert not auditor.errors and not auditor.fixes,(label,auditor.errors,auditor.fixes)
    entities=list(doc.modelspace())
    assert all(e.dxf.layer in {"VISIBLE","HIDDEN","DIMENSIONS"} for e in entities),label
    if s["rects"]:
        assert any(e.dxftype()=="LINE" and e.dxf.layer=="VISIBLE" for e in entities),label
        assert sum(e.dxftype()=="TEXT" and e.dxf.layer=="DIMENSIONS" for e in entities)==2,label
    else:
        assert not entities,label
print("PASS: 48 DXF files opened by ezdxf, units mm, layers and audit clean")

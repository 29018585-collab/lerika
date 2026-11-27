"""Reproducible optimization of checked-in public LeriKa images. No uploaded client data."""
import argparse, base64, hashlib, io
from pathlib import Path
from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[1]
GALLERY={
    "logo":"file_000000009ab0820ab36b48bd9c6cebc7.png",
    "wardrobes":"file_000000008770820a9218605c4e124fc0.png",
    "hall":"file_00000000d2dc820aaeb9c3a13b7da81b.png",
    "bedroom":"file_0000000064c4820a9dcd3f726dee3d23.png",
    "children":"file_0000000027b8820abb66b1f996915841.png",
    "living":"file_000000000824820a9c84d7035cefb21f.png",
    "dressing":"file_00000000f254820ab16a02bfed7755be.png",
}
PORTFOLIO={
    "kitchen":("Screenshot_20261127_020103_VK.jpg",(480,520),(1880,1920)),
    "stairs":("Screenshot_20261127_030255_Telegram.jpg",(600,650),(1620,1670)),
}
LABS={
    "lab-3d":(300,248,389,203),
    "lab-design":(300,456,389,203),
    "lab-config":(300,664,389,201),
    "lab-room":(300,870,389,204),
    "lab-engineering":(300,1080,389,206),
}
def load(name):
    with Image.open(ROOT/name) as image:
        im=ImageOps.exif_transpose(image)
        return im.convert("RGBA" if "A" in im.getbands() else "RGB")
def trim_photo(im,top_range,bottom_range):
    # Source thumbnails were reviewed: full-width photo centered on a black screen.
    # Limit detection to observed transitions; reject unexpected source changes.
    assert im.size==(1080,2400),im.size
    g=im.convert("L")
    def active(y):
        hist=g.crop((8,y,1072,y+1)).histogram()
        return sum(hist[32:])>106
    top=next(y for y in range(*top_range) if active(y))
    bottom=max(y for y in range(*bottom_range) if active(y))+1
    assert 900<bottom-top<1600,(top,bottom)
    print("CROP",top,bottom)
    return im.crop((0,top,1080,bottom))
def encode(im,size_limit=200_000,max_size=1408):
    im=im.copy();im.thumbnail((max_size,max_size),Image.Resampling.LANCZOS)
    for _ in range(7):
        for quality in (90,86,82,78,74,70):
            out=io.BytesIO()
            im.save(out,"WEBP",quality=quality,method=6,alpha_quality=100)
            data=out.getvalue()
            if len(data)<=size_limit:
                return data,im.size,quality
        im.thumbnail((int(im.width*.87),int(im.height*.87)),Image.Resampling.LANCZOS)
    raise RuntimeError("could not meet public asset size limit")
def assets(group):
    if group=="gallery":
        for key,name in GALLERY.items(): yield key,name,load(name),1000 if key=="logo" else 1408
    elif group=="portfolio":
        for key,(name,top,bottom) in PORTFOLIO.items():yield key,name,trim_photo(load(name),top,bottom),1408
    else:
        name="Screenshot_20261127_080304_ChatGPT.jpg"
        im=load(name);assert im.size==(1080,2400)
        for key,(x,y,w,h) in LABS.items():
            # Exactly the existing SVG viewport; rasterize only that region.
            box=(round(x*1080/691),round(y*2400/1536),round((x+w)*1080/691),round((y+h)*2400/1536))
            yield key,name,im.crop(box),800
def main():
    p=argparse.ArgumentParser();p.add_argument("--group",choices=["gallery","portfolio","labs"],required=True)
    p.add_argument("--emit",action="store_true");p.add_argument("--check",action="store_true")
    args=p.parse_args()
    for key,source,im,max_size in assets(args.group):
        data,dimensions,quality=encode(im,max_size=max_size)
        digest=hashlib.sha256(data).hexdigest()[:16]
        name=f"public-{key}-{digest}.webp"
        print("ASSET",key,name,len(data),dimensions[0],dimensions[1],quality,(ROOT/source).stat().st_size)
        if args.emit:
            s=base64.b64encode(data).decode()
            for start in range(0,len(s),3000): print("WEBP",key,start,s[start:start+3000])
        if args.check:
            existing=ROOT/name
            assert existing.is_file() and existing.read_bytes()==data,name
            assert name in (ROOT/"index.html").read_text(),name
            with Image.open(existing) as result:
                assert result.format=="WEBP" and result.size==dimensions
            print("PASS",name)
if __name__=="__main__":main()

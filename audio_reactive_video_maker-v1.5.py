import os, math, random, shutil, subprocess, tempfile, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
except ImportError:
    np = None
    Image = None
IMAGE_EXTS={'.jpg','.jpeg','.png','.webp','.bmp'}
EFFECTS=['Pulsing Color Field','Particle Emissions','Tesla Ball','Lightning Storm','Waveform Line','Mirrored Waveform','Radial / CQT Spectrum','Equalizer Bars','Energy Rings','Nebula','Kaleidoscope','Audio Tunnel','Audio Reactive Fractal Zoom','Blooming Fractals','Plasma Field']
PALETTES={'Neon Rainbow':[(0,255,255),(255,0,255),(255,255,0),(0,128,255)],'Fire':[(255,50,0),(255,140,0),(255,230,40),(180,0,0)],'Electric Blue':[(0,220,255),(0,80,255),(180,240,255),(40,0,180)],'Purple Neon':[(180,0,255),(255,0,200),(120,80,255),(255,255,255)],'Gold':[(255,210,40),(255,140,0),(255,255,190),(140,80,0)],'Emerald':[(0,255,120),(0,180,80),(180,255,220),(0,80,40)],'Cyberpunk':[(0,255,255),(255,0,160),(140,0,255),(255,255,255)],'Ice':[(255,255,255),(150,230,255),(0,160,255),(80,80,255)],'Solar':[(255,255,0),(255,120,0),(255,40,0),(120,0,0)],'Monochrome':[(255,255,255),(180,180,180),(90,90,90),(30,30,30)]}
PRESETS={'EDM':{'palette':'Cyberpunk','effects':['Particle Emissions','Equalizer Bars','Tesla Ball'],'overlap':'3','section':'8','size':1.25},'Ambient':{'palette':'Ice','effects':['Pulsing Color Field','Nebula','Energy Rings'],'overlap':'2','section':'20','size':1.0},'Metal':{'palette':'Fire','effects':['Lightning Storm','Equalizer Bars','Plasma Field'],'overlap':'3','section':'10','size':1.2},'Classical':{'palette':'Gold','effects':['Energy Rings','Blooming Fractals','Nebula'],'overlap':'2','section':'18','size':0.9},'Synthwave':{'palette':'Purple Neon','effects':['Audio Tunnel','Radial / CQT Spectrum','Pulsing Color Field'],'overlap':'3','section':'12','size':1.1}}
def check_tool(n):
    try: subprocess.run([n,'-version'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True); return True
    except Exception: return False
def ffprobe_duration(path): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],text=True).strip())
def list_images(folder):
    if not folder: return []
    p=Path(folder)
    if not p.exists(): return []
    return sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGE_EXTS],key=lambda x:x.name.lower())
def res_tuple(text):
    w,h=text.lower().split('x'); return int(w),int(h)
def run_cmd(cmd, log):
    log(' '.join(f'"{c}"' if ' ' in str(c) else str(c) for c in cmd))
    si=None; flags=0
    if os.name=='nt':
        si=subprocess.STARTUPINFO(); si.dwFlags|=subprocess.STARTF_USESHOWWINDOW; flags=subprocess.CREATE_NO_WINDOW
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',startupinfo=si,creationflags=flags)
    for line in p.stdout: log(line.rstrip())
    return p.wait()
def extract_audio_wav(audio,wav,dur=None):
    cmd=['ffmpeg','-y']
    if dur: cmd+=['-t',str(dur)]
    cmd+=['-i',str(audio),'-ac','1','-ar','22050','-f','wav',str(wav)]
    subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
def read_wav(path):
    import wave
    with wave.open(str(path),'rb') as wf:
        n=wf.getnframes(); rate=wf.getframerate(); data=wf.readframes(n)
    return np.frombuffer(data,dtype=np.int16).astype(np.float32)/32768.0, rate
def features(samples,rate,fps,total):
    amp=np.zeros(total,np.float32); bass=np.zeros(total,np.float32); tre=np.zeros(total,np.float32); win=max(256,int(rate/fps))
    for i in range(total):
        seg=samples[i*win:min(len(samples),i*win+win)]
        if len(seg)==0: continue
        amp[i]=float(np.sqrt(np.mean(seg*seg))); fft=np.abs(np.fft.rfft(seg*np.hanning(len(seg))))
        if len(fft)>4: bass[i]=float(np.mean(fft[:max(3,len(fft)//12)])); tre[i]=float(np.mean(fft[len(fft)//3:]))
    def norm(x):
        m=np.percentile(x,95) if np.max(x)>0 else 1
        return np.clip(x/max(m,1e-6),0,1)
    return norm(amp),norm(bass),norm(tre)
def load_bg(path,w,h,mode):
    if not path: return None
    try:
        im=Image.open(path).convert('RGB'); iw,ih=im.size; scale=max(w/iw,h/ih) if mode=='cover' else min(w/iw,h/ih); nw,nh=int(iw*scale),int(ih*scale); im=im.resize((nw,nh),Image.LANCZOS)
        if mode=='cover': return im.crop(((nw-w)//2,(nh-h)//2,(nw+w)//2,(nh+h)//2))
        bg=Image.new('RGB',(w,h),'black'); bg.paste(im,((w-nw)//2,(h-nh)//2)); return bg
    except Exception: return None
def add_glow(img,radius=12,strength=1.45):
    b=img.filter(ImageFilter.GaussianBlur(radius)); return Image.blend(img,ImageEnhance.Brightness(b).enhance(strength),0.42)
class ParticleSystem:
    def __init__(self,w,h,colors):
        self.w=w; self.h=h; self.colors=colors; self.parts=[]; cx,cy=w/2,h/2
        for _ in range(500): self.parts.append([cx+random.uniform(-80,80),cy+random.uniform(-80,80),random.uniform(-3,3),random.uniform(-3,3),random.choice(colors),random.randint(3,8)])
    def draw(self,img,a,b,size):
        d=ImageDraw.Draw(img,'RGBA'); cx,cy=self.w/2,self.h/2; burst=1+a*18+b*12
        for p in self.parts:
            dx,dy=p[0]-cx,p[1]-cy; dist=max(1,math.sqrt(dx*dx+dy*dy)); p[2]+=(dx/dist)*0.1*burst+random.uniform(-.2,.2); p[3]+=(dy/dist)*0.1*burst+random.uniform(-.2,.2); p[0]+=p[2]; p[1]+=p[3]; p[2]*=.965; p[3]*=.965
            if p[0]<-50 or p[0]>self.w+50 or p[1]<-50 or p[1]>self.h+50: p[0],p[1]=cx+random.uniform(-40,40),cy+random.uniform(-40,40); p[2],p[3]=random.uniform(-3,3),random.uniform(-3,3)
            r=max(1,int((p[5]+a*12)*size)); d.ellipse([p[0]-r,p[1]-r,p[0]+r,p[1]+r],fill=p[4]+(235,))
def draw_effect(img,e,frame,total,amp,bass,tre,colors,particles,size):
    w,h=img.size; d=ImageDraw.Draw(img,'RGBA'); t=frame/max(1,total); cx,cy=w//2,h//2; a=float(amp); b=float(bass); c1=colors[frame%len(colors)]; c2=colors[(frame//7+1)%len(colors)]; S=max(.2,size)
    if e=='Pulsing Color Field':
        img.alpha_composite(Image.new('RGBA',(w,h),tuple(int(c1[i]*.5+c2[i]*.5) for i in range(3))+(120+int(a*90),))); ov=Image.new('RGBA',(w,h),(0,0,0,0)); od=ImageDraw.Draw(ov,'RGBA')
        for i in range(10):
            rr=int((i+1)*max(w,h)/9*(.45+a*.65)*S); od.ellipse([cx-rr,cy-rr,cx+rr,cy+rr],outline=colors[(i+frame//5)%len(colors)]+(90+int(a*120),),width=max(2,int((42+a*50)*S)))
        img.alpha_composite(ov.filter(ImageFilter.GaussianBlur(max(1,int(30*S)))))
    elif e=='Particle Emissions':
        if particles: particles.draw(img,a,b,S)
    elif e in ('Tesla Ball','Lightning Storm'):
        if e=='Tesla Ball':
            r=int((70+a*50)*S); d.ellipse([cx-r,cy-r,cx+r,cy+r],fill=c1+(230,)); count=28; starts=[(cx,cy)]*count
        else: count=22; starts=[(random.randint(0,w),0) for _ in range(count)]
        for i,start in enumerate(starts):
            if e=='Tesla Ball': ang=(i/count)*math.tau+t*math.tau*.8; rad=min(w,h)*(.18+.36*((i%7)/7)+b*.22)*S; end=(cx+math.cos(ang)*rad,cy+math.sin(ang)*rad)
            else: end=(start[0]+random.randint(-120,120),h)
            pts=[start]
            for s in range(1,9):
                q=s/9; pts.append((start[0]*(1-q)+end[0]*q+math.sin(frame*.17+s+i)*35*S,start[1]*(1-q)+end[1]*q+math.cos(frame*.13+s+i)*35*S))
            pts.append(end); d.line(pts,fill=colors[i%len(colors)]+(235,),width=max(1,int((3+a*5)*S)))
    elif e in ('Equalizer Bars','Radial / CQT Spectrum'):
        bars=64
        for i in range(bars):
            val=(math.sin(frame*.11+i*.6)+1)/2*.35+a*.75+random.random()*.07
            if e=='Equalizer Bars': x0=int(i*w/bars); x1=int((i+.75)*w/bars); bh=int(h*min(.95,val)*S); d.rectangle([x0,h-bh,x1,h],fill=colors[i%len(colors)]+(225,))
            else: ang=i*math.tau/bars; r0=min(w,h)*.12; r1=r0+min(w,h)*.38*min(1,val)*S; d.line([(cx+math.cos(ang)*r0,cy+math.sin(ang)*r0),(cx+math.cos(ang)*r1,cy+math.sin(ang)*r1)],fill=colors[i%len(colors)]+(220,),width=max(1,int(4*S)))
    elif e in ('Waveform Line','Mirrored Waveform'):
        pts=[]; pts2=[]; n=160
        for i in range(n):
            x=i*w/(n-1); y=cy+math.sin(i*.25+frame*.2)*h*.18*a*S+math.sin(i*.06+frame*.04)*h*.04; pts.append((x,y)); pts2.append((x,h-y))
        d.line(pts,fill=c1+(230,),width=max(1,int(4*S)))
        if e=='Mirrored Waveform': d.line(pts2,fill=c2+(210,),width=max(1,int(4*S)))
    elif e=='Energy Rings':
        for i in range(14): rr=int(((i*70+frame*9)%max(w,h))*S); alpha=max(0,230-int(rr/max(w,h)*230)); d.ellipse([cx-rr,cy-rr,cx+rr,cy+rr],outline=colors[i%len(colors)]+(alpha,),width=max(2,int((8+a*18)*S)))
    elif e=='Nebula':
        cloud=Image.new('RGBA',(w,h),(0,0,0,0)); cd=ImageDraw.Draw(cloud,'RGBA')
        for i in range(26): x=int((math.sin(frame*.011+i)*.5+.5)*w); y=int((math.cos(frame*.017+i*2)*.5+.5)*h); rr=int((120+a*300+(i%5)*45)*S); cd.ellipse([x-rr,y-rr,x+rr,y+rr],fill=colors[i%len(colors)]+(42,))
        img.alpha_composite(cloud.filter(ImageFilter.GaussianBlur(max(1,int(42*S)))))
    elif e=='Kaleidoscope':
        for i in range(24): ang=i*math.tau/24+frame*.025; length=min(w,h)*(.18+a*.75)*S; p1=(cx+math.cos(ang)*length,cy+math.sin(ang)*length); p2=(cx+math.cos(ang+.15)*length,cy+math.sin(ang+.15)*length); d.polygon([(cx,cy),p1,p2],fill=colors[i%len(colors)]+(88,))
    elif e=='Audio Tunnel':
        for i in range(28):
            scale=max(.08,1-i/32); rw=int(w*scale*(.28+a*.55)*S); rh=int(h*scale*(.28+a*.55)*S); off=int(math.sin(frame*.08+i)*50*S); x0,x1=cx-rw//2+off,cx+rw//2-off; y0,y1=cy-rh//2,cy+rh//2
            if x1<x0: x0,x1=x1,x0
            d.rectangle([x0,y0,x1,y1],outline=colors[i%len(colors)]+(190,),width=max(1,int(4*S)))
    elif e=='Audio Reactive Fractal Zoom':
        for i in range(110): ang=i*2.399+frame*.015; rad=((i*8+frame*(2+a*12))%(min(w,h)*.55))*S; sz=(6+i%8+a*16)*S; x=cx+math.cos(ang)*rad; y=cy+math.sin(ang)*rad; d.rectangle([x-sz,y-sz,x+sz,y+sz],outline=colors[i%len(colors)]+(170,),width=max(1,int(3*S)))
    elif e=='Blooming Fractals':
        for i in range(10):
            petals=7+i; rad=(42+i*34+a*130)*S
            for j in range(petals): ang=j*math.tau/petals+frame*.015*i; x=cx+math.cos(ang)*rad; y=cy+math.sin(ang)*rad; rr=(25+i*5+a*32)*S; d.ellipse([x-rr,y-rr,x+rr,y+rr],outline=colors[(i+j)%len(colors)]+(190,),width=max(1,int(4*S)))
    elif e=='Plasma Field':
        step=max(8,int(12*S))
        for y in range(0,h,step): pts=[(x,y+math.sin(x*.015+frame*.08)*30*a*S+math.cos(y*.02+frame*.05)*25*S) for x in range(0,w,24)]; d.line(pts,fill=colors[(y//step)%len(colors)]+(125,),width=max(2,int(10*S)))
def render_frames(audio,output,effects_pool,mode,single,overlap,resolution,fps,palette,bg_image,bg_folder,bg_mode,section,preview,esize,log,progress):
    w,h=res_tuple(resolution); dur=ffprobe_duration(audio); dur=min(dur,preview) if preview else dur; total=max(1,int(dur*fps)); temp=Path(tempfile.mkdtemp(prefix='arvm6_'))
    try:
        wav=temp/'audio.wav'; extract_audio_wav(audio,wav,dur); samples,rate=read_wav(wav); amp,bass,tre=features(samples,rate,fps,total); colors=PALETTES[palette]; bgs=list_images(bg_folder) if bg_folder else []; bg_static=load_bg(bg_image,w,h,bg_mode) if bg_image else None; particles=ParticleSystem(w,h,colors)
        fixed=effects_pool[:min(overlap,len(effects_pool))] if mode=='overlap' else None; log(f'Rendering {total} frames...')
        for f in range(total):
            if bg_static: img=bg_static.copy().convert('RGBA')
            elif bgs: bg=load_bg(bgs[int((f/fps)//section)%len(bgs)],w,h,bg_mode); img=bg.convert('RGBA') if bg else Image.new('RGBA',(w,h),(0,0,0,255))
            else: img=Image.new('RGBA',(w,h),(0,0,0,255))
            if mode=='single': effects=[single]
            elif mode=='overlap': effects=fixed
            else: random.seed(int((f/fps)//section)); effects=random.sample(effects_pool,min(overlap,len(effects_pool)))
            for e in effects: draw_effect(img,e,f,total,amp[f],bass[f],tre[f],colors,particles,esize)
            img=add_glow(img.convert('RGB'),radius=max(4,int(10*esize)),strength=1.4); img.save(temp/f'frame_{f:06d}.jpg',quality=92)
            if f%max(1,fps//2)==0: progress(int(f/total*85)); log(f'Rendered frame {f+1}/{total}')
        cmd=['ffmpeg','-y','-framerate',str(fps),'-i',str(temp/'frame_%06d.jpg'),'-i',str(audio)]
        if preview: cmd+=['-t',str(dur)]
        cmd+=['-c:v','libx264','-pix_fmt','yuv420p','-r',str(fps),'-c:a','aac','-shortest',str(output)]
        rc=run_cmd(cmd,log); progress(100 if rc==0 else 0); return rc
    finally: shutil.rmtree(temp,ignore_errors=True)
class CommandWindow:
    def __init__(self,parent,theme):
        self.win=tk.Toplevel(parent); self.win.title('Render / Command Output'); self.win.geometry('920x520'); self.text=tk.Text(self.win,wrap='word'); self.text.pack(fill='both',expand=True); self.apply(theme)
    def apply(self,theme):
        bg,fg=('#fff','#000') if theme=='Light' else ('#111','#d7ffd7'); self.text.configure(bg=bg,fg=fg,insertbackground=fg)
    def append(self,msg): self.text.insert('end',msg+'\n'); self.text.see('end')
class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Audio Reactive Video Maker v6'); self.geometry('1060x920'); self.q=queue.Queue(); self.cmdw=None; self.last_render=None
        self.audio=tk.StringVar(); self.output=tk.StringVar(value='audio_visualizer.mp4'); self.bg_image=tk.StringVar(); self.bg_folder=tk.StringVar(); self.resolution=tk.StringVar(value='1920x1080'); self.fps=tk.StringVar(value='30'); self.bg_mode=tk.StringVar(value='cover'); self.palette=tk.StringVar(value='Neon Rainbow'); self.mode=tk.StringVar(value='single'); self.single=tk.StringVar(value='Pulsing Color Field'); self.overlap=tk.StringVar(value='2'); self.section=tk.StringVar(value='12'); self.preview=tk.StringVar(value='20'); self.show_cmd=tk.BooleanVar(value=False); self.cmd_theme=tk.StringVar(value='Dark'); self.size=tk.DoubleVar(value=1.0); self.preset=tk.StringVar(value='Custom')
        self.effect_vars={e:tk.BooleanVar(value=e in ['Pulsing Color Field','Particle Emissions','Tesla Ball','Equalizer Bars']) for e in EFFECTS}; self.effect_cbs=[]; self.effect_controls=[]; self.single_widgets=[]; self.build(); self.update_mode(); self.after(100,self.process_q)
    def build(self):
        frm=ttk.Frame(self); frm.pack(fill='both',expand=True,padx=10,pady=10); frm.columnconfigure(1,weight=1)
        def row_file(r,label,var,cmd): ttk.Label(frm,text=label).grid(row=r,column=0,sticky='w',padx=8,pady=5); ttk.Entry(frm,textvariable=var).grid(row=r,column=1,sticky='ew',padx=8,pady=5); ttk.Button(frm,text='Browse',command=cmd).grid(row=r,column=2,padx=8,pady=5)
        row_file(0,'Audio file:',self.audio,self.pick_audio); row_file(1,'Output file:',self.output,self.pick_output); row_file(2,'Background image optional:',self.bg_image,self.pick_bg_image); row_file(3,'Background folder optional:',self.bg_folder,self.pick_bg_folder)
        opts=ttk.LabelFrame(frm,text='Output Settings'); opts.grid(row=4,column=0,columnspan=3,sticky='ew',padx=8,pady=8); ttk.Label(opts,text='Resolution').grid(row=0,column=0,padx=6); ttk.Combobox(opts,textvariable=self.resolution,values=['1280x720','1920x1080','2560x1440'],width=14).grid(row=0,column=1,padx=6); ttk.Label(opts,text='FPS').grid(row=0,column=2,padx=6); ttk.Combobox(opts,textvariable=self.fps,values=['24','30','60'],width=8).grid(row=0,column=3,padx=6); ttk.Label(opts,text='Background fit').grid(row=0,column=4,padx=6); ttk.Combobox(opts,textvariable=self.bg_mode,values=['contain','cover'],width=10).grid(row=0,column=5,padx=6)
        modes=ttk.LabelFrame(frm,text='Visual Mode'); modes.grid(row=5,column=0,columnspan=3,sticky='ew',padx=8,pady=8)
        for txt,val,col in [('Single effect','single',0),('Random by section','random',1),('Overlapping effects','overlap',2)]: ttk.Radiobutton(modes,text=txt,variable=self.mode,value=val,command=self.update_mode).grid(row=0,column=col,sticky='w',padx=8)
        ttk.Label(modes,text='Single effect').grid(row=1,column=0,padx=8,pady=5); self.single_widgets.append(ttk.Combobox(modes,textvariable=self.single,values=EFFECTS,width=32)); self.single_widgets[-1].grid(row=1,column=1,padx=8,pady=5); ttk.Label(modes,text='Color palette').grid(row=1,column=2,padx=8); ttk.Combobox(modes,textvariable=self.palette,values=list(PALETTES.keys()),width=18).grid(row=1,column=3,padx=8); ttk.Label(modes,text='Effect size').grid(row=2,column=0,padx=8); ttk.Scale(modes,from_=0.5,to=2.0,variable=self.size,orient='horizontal').grid(row=2,column=1,columnspan=2,sticky='ew',padx=8); ttk.Label(modes,text='Preset').grid(row=2,column=3,padx=8); ttk.Combobox(modes,textvariable=self.preset,values=['Custom']+list(PRESETS.keys()),width=14).grid(row=2,column=4,padx=8); ttk.Button(modes,text='Apply Preset',command=self.apply_preset).grid(row=2,column=5,padx=8)
        eff=ttk.LabelFrame(frm,text='Effects Available for Random and Overlap Mode'); eff.grid(row=6,column=0,columnspan=3,sticky='ew',padx=8,pady=8)
        for i,(e,v) in enumerate(self.effect_vars.items()): cb=ttk.Checkbutton(eff,text=e,variable=v,command=lambda name=e:self.effect_checked(name)); cb.grid(row=i//3,column=i%3,sticky='w',padx=10,pady=4); self.effect_cbs.append(cb); self.effect_controls.append(cb)
        self.effect_controls.append(ttk.Label(eff,text='Section length for random:')); self.effect_controls[-1].grid(row=5,column=0,sticky='w',padx=10,pady=6); self.effect_controls.append(ttk.Entry(eff,textvariable=self.section,width=8)); self.effect_controls[-1].grid(row=5,column=1,sticky='w',padx=10,pady=6); self.effect_controls.append(ttk.Label(eff,text='Number of overlapping effects:')); self.effect_controls[-1].grid(row=6,column=0,sticky='w',padx=10,pady=6)
        for txt,val,col in [('1','1',1),('2','2',2),('3','3',3)]: rb=ttk.Radiobutton(eff,text=txt,variable=self.overlap,value=val,command=self.enforce_overlap); rb.grid(row=6,column=col,sticky='w',padx=10,pady=6); self.effect_controls.append(rb)
        act=ttk.LabelFrame(frm,text='Preview / Render'); act.grid(row=7,column=0,columnspan=3,sticky='ew',padx=8,pady=8); ttk.Label(act,text='Preview seconds').grid(row=0,column=0,padx=8); ttk.Entry(act,textvariable=self.preview,width=10).grid(row=0,column=1,padx=8); ttk.Checkbutton(act,text='Show command output window',variable=self.show_cmd).grid(row=0,column=2,padx=8); ttk.Label(act,text='Command theme').grid(row=0,column=3,padx=8); ttk.Combobox(act,textvariable=self.cmd_theme,values=['Dark','Light'],width=8).grid(row=0,column=4,padx=8); ttk.Button(act,text='Render Preview',command=self.render_preview).grid(row=1,column=0,padx=8,pady=5); ttk.Button(act,text='Render Full Video',command=self.render_full).grid(row=1,column=1,padx=8,pady=5); ttk.Button(act,text='Open Last Render',command=self.open_last_render).grid(row=1,column=2,padx=8,pady=5); ttk.Button(act,text='Help / README',command=self.open_readme).grid(row=1,column=3,padx=8,pady=5)
        self.progress=ttk.Progressbar(frm,orient='horizontal',mode='determinate'); self.progress.grid(row=8,column=0,columnspan=3,sticky='ew',padx=8,pady=6); self.log=tk.Text(frm,height=16,wrap='word'); self.log.grid(row=9,column=0,columnspan=3,sticky='nsew',padx=8,pady=8); frm.rowconfigure(9,weight=1)
    def log_msg(self,m): self.q.put(('log',m))
    def prog(self,v): self.q.put(('progress',v))
    def process_q(self):
        try:
            while True:
                typ,val=self.q.get_nowait()
                if typ=='log': self.log.insert('end',val+'\n'); self.log.see('end'); self.cmdw and self.cmdw.append(val)
                elif typ=='progress': self.progress['value']=val
        except queue.Empty: pass
        self.after(100,self.process_q)
    def update_mode(self):
        ss='normal' if self.mode.get()=='single' else 'disabled'; es='normal' if self.mode.get() in ('random','overlap') else 'disabled'
        for w in self.single_widgets: w.configure(state=ss)
        for w in self.effect_controls:
            try: w.configure(state=es)
            except: pass
        if self.mode.get()=='overlap': self.enforce_overlap()
    def effect_checked(self,name):
        if self.mode.get()=='overlap':
            maxc=int(self.overlap.get()); checked=[e for e,v in self.effect_vars.items() if v.get()]
            if len(checked)>maxc: self.effect_vars[name].set(False); messagebox.showinfo('Overlap limit',f'Overlap mode is limited to {maxc} selected effect(s).')
    def enforce_overlap(self):
        if self.mode.get()=='overlap':
            maxc=int(self.overlap.get()); checked=[e for e,v in self.effect_vars.items() if v.get()]
            for e in checked[maxc:]: self.effect_vars[e].set(False)
    def apply_preset(self):
        p=PRESETS.get(self.preset.get())
        if not p: return
        self.palette.set(p['palette']); self.overlap.set(p['overlap']); self.section.set(p['section']); self.size.set(p['size'])
        for e,v in self.effect_vars.items(): v.set(e in p['effects'])
        self.mode.set('random'); self.update_mode()
    def pick_audio(self):
        p=filedialog.askopenfilename(filetypes=[('Audio','*.mp3 *.wav *.m4a *.flac *.ogg'),('All','*.*')])
        if p: self.audio.set(p)
    def pick_output(self):
        p=filedialog.asksaveasfilename(defaultextension='.mp4',filetypes=[('MP4','*.mp4')])
        if p: self.output.set(p)
    def pick_bg_image(self):
        p=filedialog.askopenfilename(filetypes=[('Images','*.jpg *.jpeg *.png *.webp *.bmp'),('All','*.*')])
        if p: self.bg_image.set(p)
    def pick_bg_folder(self):
        p=filedialog.askdirectory()
        if p: self.bg_folder.set(p)
    def selected(self): return [e for e,v in self.effect_vars.items() if v.get()]
    def validate(self):
        if np is None or Image is None: messagebox.showerror('Missing packages','Install Pillow and NumPy:\npython -m pip install pillow numpy'); return False
        if not self.audio.get() or not Path(self.audio.get()).exists(): messagebox.showerror('Missing audio','Please select an audio file.'); return False
        if self.mode.get() in ('random','overlap') and not self.selected(): messagebox.showerror('No effects','Please select at least one effect.'); return False
        return True
    def render_preview(self):
        if self.validate(): self.start(str(Path(self.output.get()).with_name('preview_'+Path(self.output.get()).name)),True)
    def render_full(self):
        if self.validate(): self.start(self.output.get(),False)
    def open_last_render(self):
        if self.last_render and Path(self.last_render).exists(): os.startfile(self.last_render)
        else: messagebox.showinfo('No render','No rendered video found yet.')
    def open_readme(self):
        readme=Path(__file__).with_name('AUDIO_REACTIVE_VIDEO_MAKER_V6_README.md')
        if readme.exists(): os.startfile(readme)
        else: messagebox.showinfo('README not found',f'Place AUDIO_REACTIVE_VIDEO_MAKER_V6_README.md beside this script.\n{readme}')
    def start(self,out,preview):
        self.cmdw=CommandWindow(self,self.cmd_theme.get()) if self.show_cmd.get() else None
        if self.cmdw: self.cmdw.append('Command output window enabled.')
        def work():
            self.log_msg('=== Render started ==='); self.prog(0)
            rc=render_frames(self.audio.get(),out,self.selected(),self.mode.get(),self.single.get(),int(self.overlap.get()),self.resolution.get(),int(self.fps.get()),self.palette.get(),self.bg_image.get().strip() or None,self.bg_folder.get().strip() or None,self.bg_mode.get(),float(self.section.get()),float(self.preview.get()) if preview else None,float(self.size.get()),self.log_msg,self.prog)
            if rc==0:
                self.last_render=out; self.log_msg(f'Done: {out}'); self.after(0,lambda: messagebox.askyesno('Render Complete',f'Open video?\n{out}') and os.startfile(out))
            else: self.after(0,lambda: messagebox.showerror('Render failed','FFmpeg returned an error.'))
        threading.Thread(target=work,daemon=True).start()
if __name__=='__main__':
    if not check_tool('ffmpeg') or not check_tool('ffprobe'):
        root=tk.Tk(); root.withdraw(); messagebox.showerror('Missing FFmpeg','FFmpeg and FFprobe must be on PATH.')
    else: App().mainloop()

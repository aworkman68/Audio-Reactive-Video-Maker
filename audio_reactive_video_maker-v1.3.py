import os, math, random, shutil, subprocess, tempfile, threading, wave
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
EFFECTS=['Pulsing Color Field','Particle Emissions','Tesla Ball','Equalizer Bars','Energy Rings','Nebula','Kaleidoscope','Audio Tunnel','Blooming Fractals','Plasma Field']
PALETTES={
'Neon Rainbow':[(0,255,255),(255,0,255),(255,255,0),(0,128,255)],
'Fire':[(255,50,0),(255,140,0),(255,230,40),(180,0,0)],
'Electric Blue':[(0,220,255),(0,80,255),(180,240,255),(40,0,180)],
'Purple Neon':[(180,0,255),(255,0,200),(120,80,255),(255,255,255)],
'Gold':[(255,210,40),(255,140,0),(255,255,190),(140,80,0)],
'Emerald':[(0,255,120),(0,180,80),(180,255,220),(0,80,40)],
'Cyberpunk':[(0,255,255),(255,0,160),(140,0,255),(255,255,255)],
'Ice':[(255,255,255),(150,230,255),(0,160,255),(80,80,255)],
'Solar':[(255,255,0),(255,120,0),(255,40,0),(120,0,0)],
'Monochrome':[(255,255,255),(180,180,180),(90,90,90),(30,30,30)],
}

def check_tool(n):
    try: subprocess.run([n,'-version'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True); return True
    except Exception: return False

def run_cmd(cmd,log):
    log(' '.join(f'"{c}"' if ' ' in str(c) else str(c) for c in cmd))
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    for l in p.stdout: log(l.rstrip())
    return p.wait()

def ffprobe_duration(p):
    out=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],text=True).strip()
    return float(out)

def res_tuple(s):
    w,h=s.lower().split('x'); return int(w),int(h)

def list_images(folder):
    if not folder: return []
    p=Path(folder)
    if not p.exists(): return []
    return sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGE_EXTS],key=lambda x:x.name.lower())

def extract_wav(audio,wav_path,dur=None):
    cmd=['ffmpeg','-y']
    if dur: cmd+=['-t',str(dur)]
    cmd+=['-i',str(audio),'-ac','1','-ar','22050','-f','wav',str(wav_path)]
    subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)

def read_wav(path):
    with wave.open(str(path),'rb') as wf:
        rate=wf.getframerate(); n=wf.getnframes(); data=wf.readframes(n)
    s=np.frombuffer(data,dtype=np.int16).astype(np.float32)/32768.0
    return s,rate

def features(samples,rate,fps,total):
    amp=np.zeros(total,dtype=np.float32); bass=np.zeros(total,dtype=np.float32); tre=np.zeros(total,dtype=np.float32)
    win=max(256,int(rate/fps))
    for i in range(total):
        seg=samples[i*win:min(len(samples),(i+1)*win)]
        if len(seg)==0: continue
        amp[i]=float(np.sqrt(np.mean(seg*seg)))
        fft=np.abs(np.fft.rfft(seg*np.hanning(len(seg))))
        if len(fft)>8:
            bass[i]=float(np.mean(fft[:max(4,len(fft)//12)])); tre[i]=float(np.mean(fft[len(fft)//3:]))
    def norm(x):
        m=np.percentile(x,95) if np.max(x)>0 else 1
        return np.clip(x/max(m,1e-6),0,1)
    return norm(amp),norm(bass),norm(tre)

def blend(c1,c2,t): return tuple(int(c1[i]*(1-t)+c2[i]*t) for i in range(3))
def glow(img):
    b=img.filter(ImageFilter.GaussianBlur(10))
    return Image.blend(img,ImageEnhance.Brightness(b).enhance(1.4),0.45)

def load_bg(path,w,h,mode):
    if not path: return None
    try:
        im=Image.open(path).convert('RGB'); iw,ih=im.size
        sc=max(w/iw,h/ih) if mode=='cover' else min(w/iw,h/ih)
        nw,nh=int(iw*sc),int(ih*sc); im=im.resize((nw,nh),Image.LANCZOS)
        if mode=='cover': return im.crop(((nw-w)//2,(nh-h)//2,(nw+w)//2,(nh+h)//2))
        bg=Image.new('RGB',(w,h),'black'); bg.paste(im,((w-nw)//2,(h-nh)//2)); return bg
    except Exception: return None

class ParticleSystem:
    def __init__(self,w,h,colors,count=260):
        self.w=w; self.h=h; self.colors=colors; self.parts=[]
        for _ in range(count): self.parts.append([w/2,h/2,random.uniform(-4,4),random.uniform(-4,4),random.choice(colors),random.randint(2,5)])
    def draw(self,img,a,b):
        d=ImageDraw.Draw(img,'RGBA'); cx=self.w/2; cy=self.h/2; burst=1+a*12+b*8
        for p in self.parts:
            dx=p[0]-cx; dy=p[1]-cy; dist=max(1,math.sqrt(dx*dx+dy*dy))
            p[2]+=(dx/dist)*0.10*burst+random.uniform(-.2,.2); p[3]+=(dy/dist)*0.10*burst+random.uniform(-.2,.2)
            p[0]+=p[2]; p[1]+=p[3]; p[2]*=.955; p[3]*=.955
            if p[0]<0 or p[0]>self.w or p[1]<0 or p[1]>self.h:
                p[0]=cx+random.uniform(-30,30); p[1]=cy+random.uniform(-30,30); p[2]=random.uniform(-3,3); p[3]=random.uniform(-3,3)
            r=p[5]+int(a*10); d.ellipse([p[0]-r,p[1]-r,p[0]+r,p[1]+r],fill=p[4]+(230,))

def draw_effect(img,effect,frame,total,a,b,tr,colors,particles):
    w,h=img.size; d=ImageDraw.Draw(img,'RGBA'); cx=w//2; cy=h//2; t=frame/max(1,total); c1=colors[frame%len(colors)]; c2=colors[(frame//7+1)%len(colors)]
    if effect=='Pulsing Color Field':
        img.alpha_composite(Image.new('RGBA',(w,h),blend(c1,c2,.5)+(110+int(a*100),)))
        lay=Image.new('RGBA',(w,h),(0,0,0,0)); ld=ImageDraw.Draw(lay,'RGBA')
        for i in range(8):
            rr=int((i+1)*max(w,h)/8*(.65+a*.8)); ld.ellipse([cx-rr,cy-rr,cx+rr,cy+rr],outline=colors[(i+frame//5)%len(colors)]+(60+int(a*130),),width=28+int(a*35))
        img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(28)))
    elif effect=='Particle Emissions': particles.draw(img,a,b)
    elif effect=='Tesla Ball':
        for i in range(24):
            ang=i*math.tau/24+t*math.tau*.7; r=min(w,h)*(.18+.35*((i%6)/6)+b*.25); x=cx+math.cos(ang)*r; y=cy+math.sin(ang)*r
            pts=[(cx,cy)]
            for s in range(1,8):
                q=s/8; pts.append((cx*(1-q)+x*q+math.sin(frame*.17+s+i)*30,cy*(1-q)+y*q+math.cos(frame*.13+s+i)*30))
            pts.append((x,y)); d.line(pts,fill=colors[i%len(colors)]+(240,),width=3+int(a*5))
        d.ellipse([cx-45-a*45,cy-45-a*45,cx+45+a*45,cy+45+a*45],fill=c1+(230,))
    elif effect=='Equalizer Bars':
        bars=56
        for i in range(bars):
            val=(math.sin(frame*.11+i*.6)+1)/2*.35+a*.75+random.random()*.05; bh=int(h*min(.95,val)); x0=int(i*w/bars); x1=int((i+.75)*w/bars)
            d.rectangle([x0,h-bh,x1,h],fill=colors[i%len(colors)]+(220,))
    elif effect=='Energy Rings':
        for i in range(12):
            rr=int((i*75+frame*9)%(max(w,h))); alpha=max(0,220-int(rr/max(w,h)*220)); d.ellipse([cx-rr,cy-rr,cx+rr,cy+rr],outline=colors[i%len(colors)]+(alpha,),width=7+int(a*15))
    elif effect=='Nebula':
        cloud=Image.new('RGBA',(w,h),(0,0,0,0)); cd=ImageDraw.Draw(cloud,'RGBA')
        for i in range(22):
            x=int((math.sin(frame*.011+i)*.5+.5)*w); y=int((math.cos(frame*.017+i*2)*.5+.5)*h); rr=int(120+a*260+(i%5)*40)
            cd.ellipse([x-rr,y-rr,x+rr,y+rr],fill=colors[i%len(colors)]+(40,))
        img.alpha_composite(cloud.filter(ImageFilter.GaussianBlur(45)))
    elif effect=='Kaleidoscope':
        for i in range(20):
            ang=i*math.tau/20+frame*.025; length=min(w,h)*(.2+a*.65); x=cx+math.cos(ang)*length; y=cy+math.sin(ang)*length
            d.polygon([(cx,cy),(x,y),(cx+math.cos(ang+.16)*length,cy+math.sin(ang+.16)*length)],fill=colors[i%len(colors)]+(85,))
    elif effect=='Audio Tunnel':
        for i in range(30):
            sc=1-i/32; rw=int(w*sc*(.25+a*.75)); rh=int(h*sc*(.25+a*.75)); off=int((frame*10+i*15)%120)
            d.rectangle([cx-rw//2+off,cy-rh//2,cx+rw//2-off,cy+rh//2],outline=colors[i%len(colors)]+(180,),width=4)
    elif effect=='Blooming Fractals':
        for i in range(9):
            petals=7+i; rad=40+i*34+a*120
            for j in range(petals):
                ang=j*math.tau/petals+frame*.015*i; x=cx+math.cos(ang)*rad; y=cy+math.sin(ang)*rad; rr=25+i*5+int(a*30)
                d.ellipse([x-rr,y-rr,x+rr,y+rr],outline=colors[(i+j)%len(colors)]+(190,),width=4)
    elif effect=='Plasma Field':
        for y in range(0,h,12):
            pts=[]
            for x in range(0,w,24): pts.append((x,y+math.sin(x*.015+frame*.08)*30*a+math.cos(y*.02+frame*.05)*25))
            d.line(pts,fill=colors[(y//12)%len(colors)]+(110,),width=10)

def render_frames(audio,out,pool,mode,single,overlap,resolution,fps,palette,bg_image,bg_folder,bg_mode,section,preview,log,progress):
    w,h=res_tuple(resolution); dur=ffprobe_duration(audio); dur=min(dur,preview) if preview else dur; total=max(1,int(dur*fps)); temp=Path(tempfile.mkdtemp(prefix='arvm4_'))
    try:
        wav=temp/'audio.wav'; extract_wav(audio,wav,dur); samples,rate=read_wav(wav); amp,bass,tre=features(samples,rate,fps,total)
        colors=PALETTES[palette]; bgs=list_images(bg_folder) if bg_folder else []; bg_static=load_bg(bg_image,w,h,bg_mode) if bg_image else None; particles=ParticleSystem(w,h,colors)
        fixed_overlap=None
        if mode=='overlap': random.seed(5678); fixed_overlap=random.sample(pool,min(overlap,len(pool)))
        if mode=='single':
            fixed_overlap=[single]
            if overlap>1:
                random.seed(1234); extra=[e for e in EFFECTS if e!=single]; fixed_overlap+=random.sample(extra,min(overlap-1,len(extra)))
        for f in range(total):
            bg=None
            if bg_static: bg=bg_static
            elif bgs: bg=load_bg(bgs[int((f/fps)//section)%len(bgs)],w,h,bg_mode)
            img=(bg.copy().convert('RGBA') if bg else Image.new('RGBA',(w,h),(0,0,0,255)))
            if mode=='random':
                random.seed(int((f/fps)//section)); effects=random.sample(pool,min(overlap,len(pool)))
            else: effects=fixed_overlap
            for e in effects: draw_effect(img,e,f,total,amp[f],bass[f],tre[f],colors,particles)
            glow(img.convert('RGB')).save(temp/f'frame_{f:06d}.jpg',quality=92)
            if f%max(1,fps//2)==0: progress(int(f/total*85)); log(f'Rendered frame {f+1}/{total}')
        cmd=['ffmpeg','-y','-framerate',str(fps),'-i',str(temp/'frame_%06d.jpg'),'-i',str(audio)]
        if preview: cmd+=['-t',str(dur)]
        cmd+=['-c:v','libx264','-pix_fmt','yuv420p','-r',str(fps),'-c:a','aac','-shortest',str(out)]
        rc=run_cmd(cmd,log); progress(100 if rc==0 else 0); return rc
    finally: shutil.rmtree(temp,ignore_errors=True)

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Audio Reactive Video Maker v4'); self.geometry('1000x860')
        self.audio=tk.StringVar(); self.output=tk.StringVar(value='audio_visualizer.mp4'); self.bg_image=tk.StringVar(); self.bg_folder=tk.StringVar(); self.resolution=tk.StringVar(value='1920x1080'); self.fps=tk.StringVar(value='30'); self.bg_mode=tk.StringVar(value='cover'); self.palette=tk.StringVar(value='Neon Rainbow'); self.mode=tk.StringVar(value='single'); self.single=tk.StringVar(value='Pulsing Color Field'); self.overlap=tk.StringVar(value='2'); self.section=tk.StringVar(value='12'); self.preview=tk.StringVar(value='20'); self.vars={e:tk.BooleanVar(value=e in ['Pulsing Color Field','Particle Emissions','Tesla Ball','Equalizer Bars']) for e in EFFECTS}; self.last=None; self.build()
    def build(self):
        frm=ttk.Frame(self); frm.pack(fill='both',expand=True,padx=10,pady=10); frm.columnconfigure(1,weight=1)
        def row(r,label,var,cmd): ttk.Label(frm,text=label).grid(row=r,column=0,sticky='w',padx=8,pady=5); ttk.Entry(frm,textvariable=var).grid(row=r,column=1,sticky='ew',padx=8,pady=5); ttk.Button(frm,text='Browse',command=cmd).grid(row=r,column=2,padx=8,pady=5)
        row(0,'Audio file:',self.audio,self.pick_audio); row(1,'Output file:',self.output,self.pick_output); row(2,'Background image optional:',self.bg_image,self.pick_bg_image); row(3,'Background folder optional:',self.bg_folder,self.pick_bg_folder)
        opts=ttk.LabelFrame(frm,text='Output Settings'); opts.grid(row=4,column=0,columnspan=3,sticky='ew',padx=8,pady=8)
        ttk.Label(opts,text='Resolution').grid(row=0,column=0,padx=6); ttk.Combobox(opts,textvariable=self.resolution,values=['1280x720','1920x1080','2560x1440'],width=14).grid(row=0,column=1,padx=6)
        ttk.Label(opts,text='FPS').grid(row=0,column=2,padx=6); ttk.Combobox(opts,textvariable=self.fps,values=['24','30','60'],width=8).grid(row=0,column=3,padx=6)
        ttk.Label(opts,text='Background fit').grid(row=0,column=4,padx=6); ttk.Combobox(opts,textvariable=self.bg_mode,values=['contain','cover'],width=10).grid(row=0,column=5,padx=6)
        modes=ttk.LabelFrame(frm,text='Visual Mode'); modes.grid(row=5,column=0,columnspan=3,sticky='ew',padx=8,pady=8)
        ttk.Radiobutton(modes,text='Single effect',variable=self.mode,value='single').grid(row=0,column=0,sticky='w',padx=8); ttk.Radiobutton(modes,text='Random by section',variable=self.mode,value='random').grid(row=0,column=1,sticky='w',padx=8); ttk.Radiobutton(modes,text='Overlapping effects',variable=self.mode,value='overlap').grid(row=0,column=2,sticky='w',padx=8)
        ttk.Label(modes,text='Single effect').grid(row=1,column=0,padx=8,pady=5); ttk.Combobox(modes,textvariable=self.single,values=EFFECTS,width=28).grid(row=1,column=1,padx=8,pady=5); ttk.Label(modes,text='Color palette').grid(row=1,column=2,padx=8); ttk.Combobox(modes,textvariable=self.palette,values=list(PALETTES.keys()),width=18).grid(row=1,column=3,padx=8); ttk.Label(modes,text='Section length').grid(row=1,column=4,padx=8); ttk.Entry(modes,textvariable=self.section,width=8).grid(row=1,column=5,padx=8)
        eff=ttk.LabelFrame(frm,text='Effects Available for Random and Overlap Mode'); eff.grid(row=6,column=0,columnspan=3,sticky='ew',padx=8,pady=8)
        for i,(e,v) in enumerate(self.vars.items()): ttk.Checkbutton(eff,text=e,variable=v).grid(row=i//3,column=i%3,sticky='w',padx=10,pady=4)
        ttk.Label(eff,text='Number of overlapping effects:').grid(row=4,column=0,sticky='w',padx=10,pady=6); ttk.Radiobutton(eff,text='1',variable=self.overlap,value='1').grid(row=4,column=1,sticky='w'); ttk.Radiobutton(eff,text='2',variable=self.overlap,value='2').grid(row=4,column=1); ttk.Radiobutton(eff,text='3',variable=self.overlap,value='3').grid(row=4,column=1,sticky='e')
        act=ttk.LabelFrame(frm,text='Preview / Render'); act.grid(row=7,column=0,columnspan=3,sticky='ew',padx=8,pady=8); ttk.Label(act,text='Preview seconds').grid(row=0,column=0,padx=8); ttk.Entry(act,textvariable=self.preview,width=10).grid(row=0,column=1,padx=8); ttk.Button(act,text='Render Preview',command=self.render_preview).grid(row=0,column=2,padx=8); ttk.Button(act,text='Render Full Video',command=self.render_full).grid(row=0,column=3,padx=8); ttk.Button(act,text='Open Last Render',command=self.open_last).grid(row=0,column=4,padx=8)
        self.progress=ttk.Progressbar(frm,orient='horizontal',mode='determinate'); self.progress.grid(row=8,column=0,columnspan=3,sticky='ew',padx=8,pady=6); self.log=tk.Text(frm,height=18,wrap='word'); self.log.grid(row=9,column=0,columnspan=3,sticky='nsew',padx=8,pady=8); frm.rowconfigure(9,weight=1)
    def log_msg(self,m): self.log.insert('end',m+'\n'); self.log.see('end'); self.update_idletasks()
    def prog(self,v): self.progress['value']=v; self.update_idletasks()
    def pick_audio(self):
        p=filedialog.askopenfilename(filetypes=[('Audio','*.mp3 *.wav *.m4a *.flac *.ogg'),('All','*.*')]); self.audio.set(p or self.audio.get())
    def pick_output(self):
        p=filedialog.asksaveasfilename(defaultextension='.mp4',filetypes=[('MP4','*.mp4')]); self.output.set(p or self.output.get())
    def pick_bg_image(self):
        p=filedialog.askopenfilename(filetypes=[('Images','*.jpg *.jpeg *.png *.webp *.bmp'),('All','*.*')]); self.bg_image.set(p or self.bg_image.get())
    def pick_bg_folder(self):
        p=filedialog.askdirectory(); self.bg_folder.set(p or self.bg_folder.get())
    def selected(self): return [e for e,v in self.vars.items() if v.get()]
    def validate(self):
        if np is None or Image is None: messagebox.showerror('Missing packages','Install Pillow and numpy:\npython -m pip install pillow numpy'); return False
        if not self.audio.get() or not Path(self.audio.get()).exists(): messagebox.showerror('Missing audio','Please select an audio file.'); return False
        return True
    def render_preview(self):
        if self.validate(): self.start(str(Path(self.output.get()).with_name('preview_'+Path(self.output.get()).name)),True)
    def render_full(self):
        if self.validate(): self.start(self.output.get(),False)
    def open_last(self):
        if self.last and Path(self.last).exists(): os.startfile(self.last)
    def start(self,out,preview):
        def work():
            self.log_msg('=== Render started ==='); self.prog(0); pool=self.selected()
            if not pool: messagebox.showerror('No effects','Select at least one effect.'); return
            rc=render_frames(self.audio.get(),out,pool,self.mode.get(),self.single.get(),int(self.overlap.get()),self.resolution.get(),int(self.fps.get()),self.palette.get(),self.bg_image.get().strip() or None,self.bg_folder.get().strip() or None,self.bg_mode.get(),float(self.section.get()),float(self.preview.get()) if preview else None,self.log_msg,self.prog)
            if rc==0:
                self.last=out; self.log_msg('Done: '+out)
                if messagebox.askyesno('Render Complete',f'Open video?\n{out}'): os.startfile(out)
            else: messagebox.showerror('Render failed','FFmpeg returned an error.')
        threading.Thread(target=work,daemon=True).start()

if __name__=='__main__':
    if not check_tool('ffmpeg') or not check_tool('ffprobe'):
        root=tk.Tk(); root.withdraw(); messagebox.showerror('Missing FFmpeg','FFmpeg and FFprobe must be on PATH.')
    else: App().mainloop()

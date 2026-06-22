import os
import math
import random
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
except ImportError:
    np = None
    Image = None

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

EFFECTS = [
    "Pulsing Color Field", "Particle Emissions", "Tesla Ball", "Lightning Storm",
    "Equalizer Bars", "Energy Rings", "Nebula", "Kaleidoscope", "Audio Tunnel",
    "Audio Reactive Fractal Zoom", "Blooming Fractals", "Plasma Field",
]

PALETTES = {
    "Neon Rainbow": [(0,255,255), (255,0,255), (255,255,0), (0,128,255)],
    "Fire": [(255,50,0), (255,140,0), (255,230,40), (180,0,0)],
    "Electric Blue": [(0,220,255), (0,80,255), (180,240,255), (40,0,180)],
    "Purple Neon": [(180,0,255), (255,0,200), (120,80,255), (255,255,255)],
    "Gold": [(255,210,40), (255,140,0), (255,255,190), (140,80,0)],
    "Emerald": [(0,255,120), (0,180,80), (180,255,220), (0,80,40)],
    "Cyberpunk": [(0,255,255), (255,0,160), (140,0,255), (255,255,255)],
    "Ice": [(255,255,255), (150,230,255), (0,160,255), (80,80,255)],
    "Solar": [(255,255,0), (255,120,0), (255,40,0), (120,0,0)],
    "Monochrome": [(255,255,255), (180,180,180), (90,90,90), (30,30,30)],
}

def check_tool(name):
    try:
        subprocess.run([name, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def ffprobe_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    return float(subprocess.check_output(cmd, text=True).strip())

def list_images(folder):
    if not folder:
        return []
    p = Path(folder)
    if not p.exists():
        return []
    return sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGE_EXTS], key=lambda x: x.name.lower())

def res_tuple(text):
    w, h = text.lower().split("x")
    return int(w), int(h)

class CommandWindow:
    def __init__(self, parent, theme="Dark"):
        self.win = tk.Toplevel(parent)
        self.win.title("Render / Command Output")
        self.win.geometry("900x520")
        self.text = tk.Text(self.win, wrap="word")
        self.text.pack(fill="both", expand=True)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        if theme == "Light":
            bg, fg = "#ffffff", "#000000"
        else:
            bg, fg = "#111111", "#d7ffd7"
        self.text.configure(bg=bg, fg=fg, insertbackground=fg)

    def log(self, msg):
        self.text.insert("end", msg + "\n")
        self.text.see("end")
        self.win.update_idletasks()

def run_cmd(cmd, log, cmd_window=None):
    line = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
    log(line)
    if cmd_window:
        cmd_window.log(line)

    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", startupinfo=startupinfo, creationflags=creationflags)
    for line in p.stdout:
        line = line.rstrip()
        log(line)
        if cmd_window:
            cmd_window.log(line)
    return p.wait()

def extract_audio_wav(audio_path, wav_path, duration=None):
    cmd = ["ffmpeg", "-y"]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-i", str(audio_path), "-ac", "1", "-ar", "22050", "-f", "wav", str(wav_path)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def read_wav_samples(path):
    import wave
    with wave.open(str(path), "rb") as wf:
        n = wf.getnframes()
        rate = wf.getframerate()
        data = wf.readframes(n)
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, rate

def audio_features(samples, rate, fps, total_frames):
    amp = np.zeros(total_frames, dtype=np.float32)
    bass = np.zeros(total_frames, dtype=np.float32)
    treble = np.zeros(total_frames, dtype=np.float32)
    win = max(256, int(rate / fps))
    for i in range(total_frames):
        a = i * win
        b = min(len(samples), a + win)
        seg = samples[a:b]
        if len(seg) == 0:
            continue
        amp[i] = float(np.sqrt(np.mean(seg * seg)))
        fft = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        if len(fft) > 4:
            bass[i] = float(np.mean(fft[:max(3, len(fft)//12)]))
            treble[i] = float(np.mean(fft[len(fft)//3:]))
    def norm(x):
        m = np.percentile(x, 95) if np.max(x) > 0 else 1
        return np.clip(x / max(m, 1e-6), 0, 1)
    return norm(amp), norm(bass), norm(treble)

def blend(c1, c2, t):
    return tuple(int(c1[i]*(1-t)+c2[i]*t) for i in range(3))

def add_glow(img, radius=12, strength=1.5):
    blurred = img.filter(ImageFilter.GaussianBlur(radius))
    return Image.blend(img, ImageEnhance.Brightness(blurred).enhance(strength), 0.45)

def load_background(bg_path, w, h, mode):
    if not bg_path:
        return None
    try:
        im = Image.open(bg_path).convert("RGB")
        iw, ih = im.size
        if mode == "cover":
            scale = max(w/iw, h/ih)
            nw, nh = int(iw*scale), int(ih*scale)
            im = im.resize((nw, nh), Image.LANCZOS)
            return im.crop(((nw-w)//2, (nh-h)//2, (nw+w)//2, (nh+h)//2))
        scale = min(w/iw, h/ih)
        nw, nh = int(iw*scale), int(ih*scale)
        im = im.resize((nw, nh), Image.LANCZOS)
        bg = Image.new("RGB", (w,h), "black")
        bg.paste(im, ((w-nw)//2, (h-nh)//2))
        return bg
    except Exception:
        return None

class ParticleSystem:
    def __init__(self, w, h, colors, count=420):
        self.w, self.h, self.colors = w, h, colors
        self.parts = []
        cx, cy = self.w/2, self.h/2
        for _ in range(count):
            self.parts.append([cx + random.uniform(-70,70), cy + random.uniform(-70,70), random.uniform(-3,3), random.uniform(-3,3), random.choice(self.colors), random.randint(3,8)])

    def draw(self, img, amp, bass):
        d = ImageDraw.Draw(img, "RGBA")
        cx, cy = self.w/2, self.h/2
        burst = 1 + amp*18 + bass*12
        for p in self.parts:
            dx, dy = p[0]-cx, p[1]-cy
            dist = max(1, math.sqrt(dx*dx+dy*dy))
            p[2] += (dx/dist)*0.10*burst + random.uniform(-0.2,0.2)
            p[3] += (dy/dist)*0.10*burst + random.uniform(-0.2,0.2)
            p[0] += p[2]
            p[1] += p[3]
            p[2] *= 0.965
            p[3] *= 0.965
            if p[0] < -50 or p[0] > self.w+50 or p[1] < -50 or p[1] > self.h+50:
                p[0], p[1] = cx + random.uniform(-40,40), cy + random.uniform(-40,40)
                p[2], p[3] = random.uniform(-3,3), random.uniform(-3,3)
            r = p[5] + int(amp*12)
            d.ellipse([p[0]-r,p[1]-r,p[0]+r,p[1]+r], fill=p[4]+(230,))

def draw_effect(img, effect, frame, total, amp, bass, treble, colors, particles=None):
    w,h = img.size
    d = ImageDraw.Draw(img, "RGBA")
    t = frame / max(1,total)
    cx, cy = w//2, h//2
    c1 = colors[frame % len(colors)]
    c2 = colors[(frame//7 + 1) % len(colors)]
    a = float(amp)
    b = float(bass)

    if effect == "Pulsing Color Field":
        base = Image.new("RGBA", (w,h), blend(c1,c2,0.5)+(120+int(a*90),))
        img.alpha_composite(base)
        overlay = Image.new("RGBA", (w,h), (0,0,0,0))
        od = ImageDraw.Draw(overlay, "RGBA")
        for i in range(10):
            rr = int((i+1)*max(w,h)/9*(0.45+a*0.65))
            od.ellipse([cx-rr, cy-rr, cx+rr, cy+rr], outline=colors[(i+frame//5)%len(colors)]+(80+int(a*120),), width=42+int(a*50))
        img.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(30)))

    elif effect == "Particle Emissions":
        if particles:
            particles.draw(img, a, b)

    elif effect == "Tesla Ball":
        d.ellipse([cx-70-a*50,cy-70-a*50,cx+70+a*50,cy+70+a*50], fill=c1+(230,))
        for i in range(28):
            ang = (i/28)*math.tau + t*math.tau*0.8
            r = min(w,h)*(0.18 + 0.36*((i%7)/7) + b*0.22)
            x = cx + math.cos(ang)*r
            y = cy + math.sin(ang)*r
            col = colors[i%len(colors)] + (240,)
            pts=[(cx,cy)]
            for s in range(1,8):
                q=s/8
                pts.append((cx*(1-q)+x*q+math.sin(frame*.17+s+i)*35, cy*(1-q)+y*q+math.cos(frame*.13+s+i)*35))
            pts.append((x,y))
            d.line(pts, fill=col, width=4+int(a*5))

    elif effect == "Lightning Storm":
        random.seed(frame)
        for i in range(18):
            x = random.randint(0,w)
            y = 0
            pts=[(x,y)]
            for _ in range(9):
                x += random.randint(-55,55)
                y += random.randint(35,90)
                pts.append((x,y))
            d.line(pts, fill=colors[i%len(colors)]+(220,), width=2+int(a*5))

    elif effect == "Equalizer Bars":
        bars = 56
        for i in range(bars):
            x0 = int(i*w/bars)
            x1 = int((i+0.75)*w/bars)
            val = (math.sin(frame*0.11+i*0.6)+1)/2 * 0.35 + a*0.75 + random.random()*0.07
            bh = int(h*min(0.95,val))
            d.rectangle([x0,h-bh,x1,h], fill=colors[i%len(colors)]+(225,))

    elif effect == "Energy Rings":
        for i in range(14):
            rr = int((i*70 + frame*9) % (max(w,h)))
            alpha = max(0, 230 - int(rr/max(w,h)*230))
            d.ellipse([cx-rr,cy-rr,cx+rr,cy+rr], outline=colors[i%len(colors)]+(alpha,), width=8+int(a*18))

    elif effect == "Nebula":
        cloud = Image.new("RGBA",(w,h),(0,0,0,0))
        cd = ImageDraw.Draw(cloud,"RGBA")
        for i in range(26):
            x = int((math.sin(frame*0.011+i)*0.5+0.5)*w)
            y = int((math.cos(frame*0.017+i*2)*0.5+0.5)*h)
            rr = int(120 + a*300 + (i%5)*45)
            cd.ellipse([x-rr,y-rr,x+rr,y+rr], fill=colors[i%len(colors)]+(42,))
        img.alpha_composite(cloud.filter(ImageFilter.GaussianBlur(42)))

    elif effect == "Kaleidoscope":
        for i in range(24):
            ang = i*math.tau/24 + frame*0.025
            length = min(w,h)*(0.18+a*0.75)
            x = cx + math.cos(ang)*length
            y = cy + math.sin(ang)*length
            x2 = cx + math.cos(ang+0.15)*length
            y2 = cy + math.sin(ang+0.15)*length
            d.polygon([(cx,cy),(x,y),(x2,y2)], fill=colors[i%len(colors)]+(88,))

    elif effect == "Audio Tunnel":
        for i in range(28):
            scale = max(0.08, 1 - i/32)
            rw = int(w*scale*(0.28+a*0.55))
            rh = int(h*scale*(0.28+a*0.55))
            off = int(math.sin(frame*0.08+i)*50)
            x0 = cx - rw//2 + off
            x1 = cx + rw//2 - off
            y0 = cy - rh//2
            y1 = cy + rh//2
            if x1 < x0:
                x0, x1 = x1, x0
            if y1 < y0:
                y0, y1 = y1, y0
            d.rectangle([x0,y0,x1,y1], outline=colors[i%len(colors)]+(190,), width=4)

    elif effect == "Audio Reactive Fractal Zoom":
        for i in range(90):
            ang = i * 2.399 + frame*0.015
            rad = (i*8 + frame*(2+a*12)) % (min(w,h)*0.55)
            size = 6 + (i % 8) + int(a*16)
            x = cx + math.cos(ang)*rad
            y = cy + math.sin(ang)*rad
            d.rectangle([x-size,y-size,x+size,y+size], outline=colors[i%len(colors)]+(170,), width=3)

    elif effect == "Blooming Fractals":
        for i in range(10):
            petals = 7+i
            rad = 42+i*34+a*130
            for j in range(petals):
                ang = j*math.tau/petals + frame*0.015*i
                x = cx + math.cos(ang)*rad
                y = cy + math.sin(ang)*rad
                rr = 25+i*5+int(a*32)
                d.ellipse([x-rr,y-rr,x+rr,y+rr], outline=colors[(i+j)%len(colors)]+(190,), width=4)

    elif effect == "Plasma Field":
        for y in range(0,h,12):
            pts=[]
            for x in range(0,w,24):
                yy = y + math.sin(x*0.015 + frame*0.08)*30*a + math.cos(y*0.02+frame*0.05)*25
                pts.append((x,yy))
            d.line(pts, fill=colors[(y//12)%len(colors)]+(125,), width=10)

def render_frames(audio, output, effects_pool, mode, single_effect, overlap, resolution, fps, palette, bg_image, bg_folder, bg_mode, section_len, preview_seconds, log, progress, cmd_window=None):
    w,h = res_tuple(resolution)
    dur = ffprobe_duration(audio)
    if preview_seconds:
        dur = min(dur, preview_seconds)
    total = max(1, int(dur*fps))
    temp = Path(tempfile.mkdtemp(prefix="arvm5_"))
    try:
        wav = temp/"audio.wav"
        extract_audio_wav(audio, wav, dur)
        samples, rate = read_wav_samples(wav)
        amp, bass, treble = audio_features(samples, rate, fps, total)
        colors = PALETTES[palette]
        bgs = list_images(bg_folder) if bg_folder else []
        bg_static = load_background(bg_image, w, h, bg_mode) if bg_image else None
        particles = ParticleSystem(w,h,colors)

        log(f"Rendering {total} frames...")
        if cmd_window:
            cmd_window.log(f"Rendering {total} frames...")

        fixed_overlap_effects = None
        if mode == "overlap":
            random.seed(5678)
            fixed_overlap_effects = random.sample(effects_pool, min(overlap, len(effects_pool)))

        for f in range(total):
            if bg_static:
                img = bg_static.copy().convert("RGBA")
            elif bgs:
                bg = load_background(bgs[int((f/fps)//section_len) % len(bgs)], w,h,bg_mode)
                img = bg.convert("RGBA") if bg else Image.new("RGBA",(w,h),(0,0,0,255))
            else:
                img = Image.new("RGBA",(w,h),(0,0,0,255))

            if mode == "single":
                effects = [single_effect]
            elif mode == "overlap":
                effects = fixed_overlap_effects
            else:
                section = int((f/fps)//section_len)
                random.seed(section)
                effects = random.sample(effects_pool, min(overlap, len(effects_pool)))

            for eff in effects:
                draw_effect(img, eff, f, total, amp[f], bass[f], treble[f], colors, particles)

            img = add_glow(img.convert("RGB"), radius=10, strength=1.4)
            img.save(temp/f"frame_{f:06d}.jpg", quality=92)
            if f % max(1, fps//2) == 0:
                pct = int(f/total*85)
                progress(pct)
                msg = f"Rendered frame {f+1}/{total}"
                log(msg)
                if cmd_window:
                    cmd_window.log(msg)

        cmd = ["ffmpeg","-y","-framerate",str(fps),"-i",str(temp/"frame_%06d.jpg"),"-i",str(audio)]
        if preview_seconds:
            cmd += ["-t", str(dur)]
        cmd += ["-c:v","libx264","-pix_fmt","yuv420p","-r",str(fps),"-c:a","aac","-shortest",str(output)]
        rc = run_cmd(cmd, log, cmd_window)
        progress(100 if rc == 0 else 0)
        return rc
    finally:
        shutil.rmtree(temp, ignore_errors=True)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Audio Reactive Video Maker v5")
        self.geometry("1040x900")
        self.audio=tk.StringVar()
        self.output=tk.StringVar(value="audio_visualizer.mp4")
        self.bg_image=tk.StringVar()
        self.bg_folder=tk.StringVar()
        self.resolution=tk.StringVar(value="1920x1080")
        self.fps=tk.StringVar(value="30")
        self.bg_mode=tk.StringVar(value="cover")
        self.palette=tk.StringVar(value="Neon Rainbow")
        self.mode=tk.StringVar(value="single")
        self.single_effect=tk.StringVar(value="Pulsing Color Field")
        self.overlap=tk.StringVar(value="2")
        self.section_len=tk.StringVar(value="12")
        self.preview_seconds=tk.StringVar(value="20")
        self.show_command=tk.BooleanVar(value=False)
        self.command_theme=tk.StringVar(value="Dark")
        self.effect_vars={e:tk.BooleanVar(value=e in ["Pulsing Color Field","Particle Emissions","Tesla Ball","Equalizer Bars"]) for e in EFFECTS}
        self.effect_widgets=[]
        self.last_render=None
        self.build()
        self.update_effect_state()

    def build(self):
        frm=ttk.Frame(self); frm.pack(fill="both",expand=True,padx=10,pady=10); frm.columnconfigure(1,weight=1)
        def row_file(r,label,var,cmd):
            ttk.Label(frm,text=label).grid(row=r,column=0,sticky="w",padx=8,pady=5)
            ttk.Entry(frm,textvariable=var).grid(row=r,column=1,sticky="ew",padx=8,pady=5)
            ttk.Button(frm,text="Browse",command=cmd).grid(row=r,column=2,padx=8,pady=5)
        row_file(0,"Audio file:",self.audio,self.pick_audio)
        row_file(1,"Output file:",self.output,self.pick_output)
        row_file(2,"Background image optional:",self.bg_image,self.pick_bg_image)
        row_file(3,"Background folder optional:",self.bg_folder,self.pick_bg_folder)

        opts=ttk.LabelFrame(frm,text="Output Settings"); opts.grid(row=4,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        ttk.Label(opts,text="Resolution").grid(row=0,column=0,padx=6,pady=5)
        ttk.Combobox(opts,textvariable=self.resolution,values=["1280x720","1920x1080","2560x1440"],width=14).grid(row=0,column=1,padx=6)
        ttk.Label(opts,text="FPS").grid(row=0,column=2,padx=6)
        ttk.Combobox(opts,textvariable=self.fps,values=["24","30","60"],width=8).grid(row=0,column=3,padx=6)
        ttk.Label(opts,text="Background fit").grid(row=0,column=4,padx=6)
        ttk.Combobox(opts,textvariable=self.bg_mode,values=["contain","cover"],width=10).grid(row=0,column=5,padx=6)

        modes=ttk.LabelFrame(frm,text="Visual Mode"); modes.grid(row=5,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        for txt,val,col in [("Single effect","single",0),("Random by section","random",1),("Overlapping effects","overlap",2)]:
            ttk.Radiobutton(modes,text=txt,variable=self.mode,value=val,command=self.update_effect_state).grid(row=0,column=col,sticky="w",padx=8)
        ttk.Label(modes,text="Single effect").grid(row=1,column=0,padx=8,pady=5)
        ttk.Combobox(modes,textvariable=self.single_effect,values=EFFECTS,width=32).grid(row=1,column=1,padx=8,pady=5)
        ttk.Label(modes,text="Color palette").grid(row=1,column=2,padx=8,pady=5)
        ttk.Combobox(modes,textvariable=self.palette,values=list(PALETTES.keys()),width=18).grid(row=1,column=3,padx=8,pady=5)

        self.effects_frame=ttk.LabelFrame(frm,text="Effects Available for Random and Overlap Mode")
        self.effects_frame.grid(row=6,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        for i,(e,v) in enumerate(self.effect_vars.items()):
            cb=ttk.Checkbutton(self.effects_frame,text=e,variable=v)
            cb.grid(row=i//3,column=i%3,sticky="w",padx=10,pady=4)
            self.effect_widgets.append(cb)
        self.effect_widgets.append(ttk.Label(self.effects_frame,text="Section length for random:"))
        self.effect_widgets[-1].grid(row=4,column=0,sticky="w",padx=10,pady=6)
        self.effect_widgets.append(ttk.Entry(self.effects_frame,textvariable=self.section_len,width=8))
        self.effect_widgets[-1].grid(row=4,column=1,sticky="w",padx=10,pady=6)
        self.effect_widgets.append(ttk.Label(self.effects_frame,text="Number of overlapping effects:"))
        self.effect_widgets[-1].grid(row=5,column=0,sticky="w",padx=10,pady=6)
        for txt,val,col in [("1","1",1),("2","2",2),("3","3",3)]:
            rb=ttk.Radiobutton(self.effects_frame,text=txt,variable=self.overlap,value=val)
            rb.grid(row=5,column=col,sticky="w",padx=10,pady=6)
            self.effect_widgets.append(rb)

        act=ttk.LabelFrame(frm,text="Preview / Render"); act.grid(row=7,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        ttk.Label(act,text="Preview seconds").grid(row=0,column=0,padx=8,pady=5)
        ttk.Entry(act,textvariable=self.preview_seconds,width=10).grid(row=0,column=1,padx=8)
        ttk.Checkbutton(act,text="Show command output window",variable=self.show_command).grid(row=0,column=2,padx=8)
        ttk.Label(act,text="Command window theme").grid(row=0,column=3,padx=8)
        ttk.Combobox(act,textvariable=self.command_theme,values=["Dark","Light"],width=8).grid(row=0,column=4,padx=8)
        ttk.Button(act,text="Render Preview",command=self.render_preview).grid(row=1,column=0,padx=8,pady=5)
        ttk.Button(act,text="Render Full Video",command=self.render_full).grid(row=1,column=1,padx=8,pady=5)
        ttk.Button(act,text="Open Last Render",command=self.open_last_render).grid(row=1,column=2,padx=8,pady=5)

        self.progress=ttk.Progressbar(frm,orient="horizontal",mode="determinate")
        self.progress.grid(row=8,column=0,columnspan=3,sticky="ew",padx=8,pady=6)
        self.log=tk.Text(frm,height=18,wrap="word")
        self.log.grid(row=9,column=0,columnspan=3,sticky="nsew",padx=8,pady=8)
        frm.rowconfigure(9,weight=1)

    def update_effect_state(self):
        state = "normal" if self.mode.get() in ("random","overlap") else "disabled"
        for w in self.effect_widgets:
            try:
                w.configure(state=state)
            except tk.TclError:
                pass

    def log_msg(self,m): self.log.insert("end",m+"\n"); self.log.see("end"); self.update_idletasks()
    def prog(self,v): self.progress["value"]=v; self.update_idletasks()
    def pick_audio(self):
        p=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.m4a *.flac *.ogg"),("All","*.*")])
        if p: self.audio.set(p)
    def pick_output(self):
        p=filedialog.asksaveasfilename(defaultextension=".mp4",filetypes=[("MP4","*.mp4")])
        if p: self.output.set(p)
    def pick_bg_image(self):
        p=filedialog.askopenfilename(filetypes=[("Images","*.jpg *.jpeg *.png *.webp *.bmp"),("All","*.*")])
        if p: self.bg_image.set(p)
    def pick_bg_folder(self):
        p=filedialog.askdirectory()
        if p: self.bg_folder.set(p)
    def selected(self): return [e for e,v in self.effect_vars.items() if v.get()]
    def validate(self):
        if np is None or Image is None:
            messagebox.showerror("Missing packages","Install Pillow and numpy:\npython -m pip install pillow numpy")
            return False
        if not self.audio.get() or not Path(self.audio.get()).exists():
            messagebox.showerror("Missing audio","Please select an audio file.")
            return False
        return True
    def render_preview(self):
        if self.validate(): self.start(str(Path(self.output.get()).with_name("preview_"+Path(self.output.get()).name)), True)
    def render_full(self):
        if self.validate(): self.start(self.output.get(), False)
    def open_last_render(self):
        if self.last_render and Path(self.last_render).exists():
            os.startfile(self.last_render)
        else:
            messagebox.showinfo("No render","No rendered video found yet.")
    def start(self,out,preview):
        cmd_window = CommandWindow(self, self.command_theme.get()) if self.show_command.get() else None
        def work():
            self.log_msg("=== Render started ===")
            if cmd_window: cmd_window.log("=== Render started ===")
            self.prog(0)
            pool=self.selected()
            if self.mode.get() in ("random","overlap") and not pool:
                messagebox.showerror("No effects","Select at least one effect.")
                return
            rc=render_frames(self.audio.get(),out,pool,self.mode.get(),self.single_effect.get(),int(self.overlap.get()),self.resolution.get(),int(self.fps.get()),self.palette.get(),self.bg_image.get().strip() or None,self.bg_folder.get().strip() or None,self.bg_mode.get(),float(self.section_len.get()),float(self.preview_seconds.get()) if preview else None,self.log_msg,self.prog,cmd_window)
            if rc==0:
                self.last_render=out
                self.log_msg(f"Done: {out}")
                if cmd_window: cmd_window.log(f"Done: {out}")
                if messagebox.askyesno("Render Complete",f"Open video?\n{out}"): os.startfile(out)
            else:
                messagebox.showerror("Render failed","FFmpeg returned an error.")
        threading.Thread(target=work,daemon=True).start()

if __name__=="__main__":
    if not check_tool("ffmpeg") or not check_tool("ffprobe"):
        root=tk.Tk(); root.withdraw(); messagebox.showerror("Missing FFmpeg","FFmpeg and FFprobe must be on PATH.")
    else:
        App().mainloop()

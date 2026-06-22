
import os, random, shutil, subprocess, tempfile, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

IMAGE_EXTS={".jpg",".jpeg",".png",".webp",".bmp"}
EFFECTS={"Waveform Line":"waveform","Mirrored Waveform":"mirrored_waveform","Spectrum Bars":"spectrum","Radial / CQT Spectrum":"cqt","Pulsing Color Field":"pulse","Equalizer Bars":"equalizer","Plasma Effect":"plasma","Blooming Fractals":"fractals","Particle Emissions":"particles","Tesla Ball":"tesla"}
PALETTES={
"Neon Rainbow":{"wave":"cyan|magenta|yellow","tint":"0.00"},
"Fire":{"wave":"red|orange|yellow","tint":"0.08"},
"Electric Blue":{"wave":"cyan|blue|white","tint":"0.58"},
"Purple Neon":{"wave":"purple|magenta|white","tint":"0.78"},
"Gold":{"wave":"gold|orange|white","tint":"0.12"},
"Emerald":{"wave":"lime|green|white","tint":"0.35"},
"Cyberpunk":{"wave":"cyan|pink|purple","tint":"0.72"},
"Ice":{"wave":"white|cyan|blue","tint":"0.55"},
"Solar":{"wave":"yellow|orange|red","tint":"0.10"},
"Monochrome":{"wave":"white|gray|silver","tint":"0.00"},
}

def check_tool(n):
    try: subprocess.run([n,"-version"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True); return True
    except Exception: return False

def duration(p):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)],text=True).strip())

def imgs(folder):
    if not folder: return []
    p=Path(folder)
    if not p.exists(): return []
    return sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGE_EXTS],key=lambda x:x.name.lower())

def res(s):
    w,h=s.lower().split("x"); return int(w),int(h)

class CommandWindow:
    def __init__(self,parent,theme):
        self.win=tk.Toplevel(parent); self.win.title("FFmpeg Command Output"); self.win.geometry("900x500")
        bg="#111111" if theme=="Dark" else "#ffffff"; fg="#d6ffd6" if theme=="Dark" else "#000000"
        self.text=tk.Text(self.win,bg=bg,fg=fg,insertbackground=fg,wrap="word"); self.text.pack(fill="both",expand=True)
    def log(self,m):
        self.text.insert("end",m+"\n"); self.text.see("end"); self.win.update_idletasks()

def run(cmd,log,show=False,cw=None,progress=None,dur=None):
    si=None; flags=0
    if os.name=="nt":
        si=subprocess.STARTUPINFO(); si.dwFlags|=subprocess.STARTF_USESHOWWINDOW; flags=subprocess.CREATE_NO_WINDOW
    line=" ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
    log(line); 
    if show and cw: cw.log(line)
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",startupinfo=si,creationflags=flags)
    start=time.time()
    for l in p.stdout:
        l=l.rstrip(); log(l)
        if show and cw: cw.log(l)
        if progress and dur: progress(min(95,int((time.time()-start)/max(dur,1)*100)))
    rc=p.wait()
    if progress: progress(100 if rc==0 else 0)
    return rc

def bg_filter(effect,w,h,fps,bg_index=None,bg_mode="contain"):
    if bg_index is not None:
        if bg_mode=="cover": return f"[{bg_index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},format=rgba,eq=saturation=1.15:contrast=1.05[bg]"
        return f"[{bg_index}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps},format=rgba,eq=saturation=1.15:contrast=1.05[bg]"
    if effect=="plasma": return f"testsrc2=s={w}x{h}:rate={fps},boxblur=30:12,hue=h=90*t:s=2.2,eq=saturation=2.0:contrast=1.25,format=rgba[bg]"
    if effect=="fractals": return f"mandelbrot=s={w}x{h}:rate={fps},hue=h=45*t:s=1.8,eq=saturation=1.9:contrast=1.2,format=rgba[bg]"
    return f"color=c=black:s={w}x{h}:r={fps},format=rgba[bg]"

def layer(effect,i,w,h,fps,palette):
    p=PALETTES.get(palette,PALETTES["Neon Rainbow"]); colors=p["wave"]; tint=p["tint"]; lab=f"vis{i}"
    if effect=="waveform": return f"[0:a]showwaves=s={w}x{h}:mode=line:rate={fps}:colors={colors},format=rgba,colorchannelmixer=aa=0.95[{lab}]"
    if effect=="mirrored_waveform": return f"[0:a]showwaves=s={w}x{h}:mode=cline:rate={fps}:colors={colors},format=rgba,colorchannelmixer=aa=0.95[{lab}]"
    if effect=="spectrum": return f"[0:a]showspectrum=s={w}x{h}:mode=combined:color=rainbow:slide=scroll:scale=cbrt,format=rgba,colorchannelmixer=aa=0.88[{lab}]"
    if effect=="cqt": return f"[0:a]showcqt=s={w}x{h}:fps={fps}:bar_g=2:sono_g=2,format=rgba,colorchannelmixer=aa=0.90[{lab}]"
    if effect=="equalizer": return f"[0:a]showfreqs=s={w}x{h}:mode=bar:ascale=cbrt:fscale=log:win_size=2048:colors={colors},format=rgba,colorchannelmixer=aa=0.95[{lab}]"
    if effect=="pulse": return f"[0:a]showwaves=s={w}x{h}:mode=p2p:rate={fps}:colors={colors},boxblur=35:12,eq=brightness=0.08:saturation=2.0,format=rgba,colorchannelmixer=aa=0.90[{lab}]"
    if effect=="particles": return f"[0:a]showwaves=s={w}x{h}:mode=point:rate={fps}:colors={colors},boxblur=3:1,eq=brightness=0.15:contrast=1.8:saturation=2.0,format=rgba,colorchannelmixer=aa=0.98[{lab}]"
    if effect=="tesla": return f"[0:a]showcqt=s={w}x{h}:fps={fps}:bar_g=3:sono_g=1,edgedetect=low=0.03:high=0.22,hue=h={tint}:s=2.5,eq=brightness=0.10:contrast=1.6,format=rgba,colorchannelmixer=aa=0.95[{lab}]"
    if effect=="plasma": return f"[0:a]showwaves=s={w}x{h}:mode=p2p:rate={fps}:colors={colors},boxblur=18:6,format=rgba,colorchannelmixer=aa=0.55[{lab}]"
    if effect=="fractals": return f"[0:a]showwaves=s={w}x{h}:mode=line:rate={fps}:colors={colors},format=rgba,colorchannelmixer=aa=0.70[{lab}]"
    return f"[0:a]showwaves=s={w}x{h}:mode=line:rate={fps}:colors={colors},format=rgba[{lab}]"

def filt(effects,w,h,fps,bg_index=None,bg_mode="contain",palette="Neon Rainbow"):
    base=effects[0] if effects else "waveform"; parts=[bg_filter(base,w,h,fps,bg_index,bg_mode)]
    for i,e in enumerate(effects): parts.append(layer(e,i,w,h,fps,palette))
    cur="bg"
    for i in range(len(effects)):
        out="v" if i==len(effects)-1 else f"mix{i}"
        parts.append(f"[{cur}][vis{i}]overlay=0:0:format=auto[{out}]"); cur=out
    return ";".join(parts)+";[v]format=yuv420p[vout]"

def render_segment(audio,out,effects,resolution,fps,bg=None,bg_mode="contain",palette="Neon Rainbow",start=None,dur=None,log=print,show=False,cw=None,progress=None):
    w,h=res(resolution); cmd=["ffmpeg","-y"]
    if start is not None: cmd+=["-ss",str(start)]
    if dur is not None: cmd+=["-t",str(dur)]
    cmd+=["-i",str(audio)]
    bg_idx=None
    if bg:
        bg_idx=1; cmd+=["-loop","1"]
        if dur is not None: cmd+=["-t",str(dur)]
        cmd+=["-i",str(bg)]
    cmd+=["-filter_complex",filt(effects,w,h,fps,bg_idx,bg_mode,palette),"-map","[vout]","-map","0:a","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r",str(fps),"-c:a","aac","-shortest",str(out)]
    return run(cmd,log,show,cw,progress,dur)

def render_random(audio,out,pool,overlap,resolution,fps,section,bg_images,bg_mode,palette,preview,log,show,cw,progress):
    dur=duration(audio); dur=min(dur,preview) if preview else dur
    td=Path(tempfile.mkdtemp(prefix="audio_visualizer_"))
    try:
        clips=[]; start=0.0; idx=0; total=max(1,int((dur+section-0.01)//section))
        while start<dur:
            seg=min(section,dur-start); eff=random.sample(pool,min(overlap,len(pool))); bg=random.choice(bg_images) if bg_images else None
            clip=td/f"clip_{idx:04d}.mp4"; log(f"Rendering section {idx+1}: {', '.join(eff)}, start={start:.2f}, duration={seg:.2f}")
            def sp(p):
                if progress: progress(int(((idx+p/100)/total)*95))
            rc=render_segment(audio,clip,eff,resolution,fps,bg,bg_mode,palette,start,seg,log,show,cw,sp)
            if rc: return rc
            clips.append(clip); start+=section; idx+=1
        lf=td/"clips.txt"; lf.write_text("\n".join(f"file '{c.as_posix()}'" for c in clips),encoding="utf-8")
        return run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lf),"-c","copy",str(out)],log,show,cw,progress,3)
    finally:
        shutil.rmtree(td,ignore_errors=True)

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("Audio Reactive Video Maker v3"); self.geometry("980x830")
        self.audio=tk.StringVar(); self.output=tk.StringVar(value="audio_visualizer.mp4"); self.bg_image=tk.StringVar(); self.bg_folder=tk.StringVar()
        self.resolution=tk.StringVar(value="1920x1080"); self.fps=tk.StringVar(value="30"); self.bg_mode=tk.StringVar(value="contain")
        self.palette=tk.StringVar(value="Neon Rainbow"); self.mode=tk.StringVar(value="single"); self.single_effect=tk.StringVar(value="Waveform Line")
        self.overlap_count=tk.StringVar(value="1"); self.section_len=tk.StringVar(value="12"); self.preview_seconds=tk.StringVar(value="20")
        self.show_command_window=tk.BooleanVar(value=False); self.command_theme=tk.StringVar(value="Dark")
        self.effect_vars={n:tk.BooleanVar(value=n in ["Waveform Line","Spectrum Bars","Equalizer Bars"]) for n in EFFECTS}; self.last_render=None; self.build()
    def build(self):
        frm=ttk.Frame(self); frm.pack(fill="both",expand=True,padx=10,pady=10); frm.columnconfigure(1,weight=1)
        def row_file(r,label,var,cmd):
            ttk.Label(frm,text=label).grid(row=r,column=0,sticky="w",padx=8,pady=5); ttk.Entry(frm,textvariable=var).grid(row=r,column=1,sticky="ew",padx=8,pady=5); ttk.Button(frm,text="Browse",command=cmd).grid(row=r,column=2,padx=8,pady=5)
        row_file(0,"Audio file:",self.audio,self.pick_audio); row_file(1,"Output file:",self.output,self.pick_output); row_file(2,"Background image (optional):",self.bg_image,self.pick_bg_image); row_file(3,"Background folder for random mode:",self.bg_folder,self.pick_bg_folder)
        opts=ttk.LabelFrame(frm,text="Output Settings"); opts.grid(row=4,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        ttk.Label(opts,text="Resolution").grid(row=0,column=0,padx=6,pady=5); ttk.Combobox(opts,textvariable=self.resolution,values=["1280x720","1920x1080","2560x1440","3840x2160"],width=14).grid(row=0,column=1,padx=6)
        ttk.Label(opts,text="FPS").grid(row=0,column=2,padx=6); ttk.Combobox(opts,textvariable=self.fps,values=["24","30","60"],width=8).grid(row=0,column=3,padx=6)
        ttk.Label(opts,text="Background fit").grid(row=0,column=4,padx=6); ttk.Combobox(opts,textvariable=self.bg_mode,values=["contain","cover"],width=10).grid(row=0,column=5,padx=6)
        modes=ttk.LabelFrame(frm,text="Visual Mode"); modes.grid(row=5,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        ttk.Radiobutton(modes,text="Single effect for entire audio",variable=self.mode,value="single").grid(row=0,column=0,sticky="w",padx=8,pady=4)
        ttk.Radiobutton(modes,text="Random selected effects by section",variable=self.mode,value="random").grid(row=1,column=0,sticky="w",padx=8,pady=4)
        ttk.Label(modes,text="Single effect").grid(row=0,column=1,padx=8); ttk.Combobox(modes,textvariable=self.single_effect,values=list(EFFECTS.keys()),width=30).grid(row=0,column=2,padx=8)
        ttk.Label(modes,text="Section length seconds").grid(row=1,column=1,padx=8); ttk.Entry(modes,textvariable=self.section_len,width=10).grid(row=1,column=2,sticky="w",padx=8)
        ttk.Label(modes,text="Overlapping effects").grid(row=0,column=3,padx=8); ttk.Combobox(modes,textvariable=self.overlap_count,values=["1","2","3"],width=5).grid(row=0,column=4,padx=8)
        ttk.Label(modes,text="Color palette").grid(row=1,column=3,padx=8); ttk.Combobox(modes,textvariable=self.palette,values=list(PALETTES.keys()),width=16).grid(row=1,column=4,padx=8)
        effs=ttk.LabelFrame(frm,text="Effects Available for Random Mode"); effs.grid(row=6,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        for i,(n,v) in enumerate(self.effect_vars.items()): ttk.Checkbutton(effs,text=n,variable=v).grid(row=i//3,column=i%3,sticky="w",padx=10,pady=4)
        actions=ttk.LabelFrame(frm,text="Preview / Render"); actions.grid(row=7,column=0,columnspan=3,sticky="ew",padx=8,pady=8)
        ttk.Label(actions,text="Preview seconds").grid(row=0,column=0,padx=8,pady=5); ttk.Entry(actions,textvariable=self.preview_seconds,width=10).grid(row=0,column=1,padx=8)
        ttk.Checkbutton(actions,text="Show command output window",variable=self.show_command_window).grid(row=0,column=2,padx=8)
        ttk.Label(actions,text="Command theme").grid(row=0,column=3,padx=8); ttk.Combobox(actions,textvariable=self.command_theme,values=["Dark","Light"],width=8).grid(row=0,column=4,padx=8)
        ttk.Button(actions,text="Render Preview",command=self.render_preview).grid(row=1,column=0,padx=8,pady=5); ttk.Button(actions,text="Render Full Video",command=self.render_full).grid(row=1,column=1,padx=8,pady=5); ttk.Button(actions,text="Open Last Render",command=self.open_last_render).grid(row=1,column=2,padx=8,pady=5)
        self.progress=ttk.Progressbar(frm,orient="horizontal",length=600,mode="determinate"); self.progress.grid(row=8,column=0,columnspan=3,sticky="ew",padx=8,pady=6)
        self.log=tk.Text(frm,height=18,wrap="word"); self.log.grid(row=9,column=0,columnspan=3,sticky="nsew",padx=8,pady=8); frm.rowconfigure(9,weight=1)
    def log_msg(self,m): self.log.insert("end",m+"\n"); self.log.see("end"); self.update_idletasks()
    def set_progress(self,v): self.progress["value"]=max(0,min(100,v)); self.update_idletasks()
    def pick_audio(self):
        p=filedialog.askopenfilename(filetypes=[("Audio files","*.mp3 *.wav *.m4a *.aac *.flac *.ogg"),("All files","*.*")]); 
        if p: self.audio.set(p)
    def pick_output(self):
        p=filedialog.asksaveasfilename(defaultextension=".mp4",filetypes=[("MP4 video","*.mp4")]); 
        if p: self.output.set(p)
    def pick_bg_image(self):
        p=filedialog.askopenfilename(filetypes=[("Image files","*.jpg *.jpeg *.png *.webp *.bmp"),("All files","*.*")]); 
        if p: self.bg_image.set(p)
    def pick_bg_folder(self):
        p=filedialog.askdirectory(); 
        if p: self.bg_folder.set(p)
    def selected_effects(self): return [EFFECTS[n] for n,v in self.effect_vars.items() if v.get()]
    def validate(self):
        if not self.audio.get() or not Path(self.audio.get()).exists(): messagebox.showerror("Missing audio","Please select a valid audio file."); return False
        return True
    def render_preview(self):
        if self.validate(): self.start_render(str(Path(self.output.get()).with_name("preview_"+Path(self.output.get()).name)),True)
    def render_full(self):
        if self.validate(): self.start_render(self.output.get(),False)
    def open_last_render(self):
        if self.last_render and Path(self.last_render).exists(): os.startfile(self.last_render)
        else: messagebox.showinfo("No render","No rendered video found yet.")
    def ask_open_render(self,out):
        if messagebox.askyesno("Render Complete",f"Created:\n{out}\n\nOpen it now?"):
            try: os.startfile(out)
            except Exception as e: messagebox.showerror("Open failed",str(e))
    def start_render(self,out,preview):
        def work():
            self.log_msg("\n=== Render started ==="); self.set_progress(0)
            cw=CommandWindow(self,self.command_theme.get()) if self.show_command_window.get() else None
            try:
                fps=int(self.fps.get()); prev=float(self.preview_seconds.get()) if preview else None; overlap=max(1,min(3,int(self.overlap_count.get())))
                if self.mode.get()=="single":
                    sel=[EFFECTS[self.single_effect.get()]]
                    if overlap>1:
                        extra=[v for v in EFFECTS.values() if v not in sel]; sel+=random.sample(extra,min(overlap-1,len(extra)))
                    bg=self.bg_image.get().strip() or None
                    rc=render_segment(self.audio.get(),out,sel,self.resolution.get(),fps,bg,self.bg_mode.get(),self.palette.get(),None,prev,self.log_msg,self.show_command_window.get(),cw,self.set_progress)
                else:
                    effects=self.selected_effects()
                    if not effects: messagebox.showerror("No effects","Please select at least one random-mode effect."); return
                    rc=render_random(self.audio.get(),out,effects,overlap,self.resolution.get(),fps,float(self.section_len.get()),imgs(self.bg_folder.get().strip()),self.bg_mode.get(),self.palette.get(),prev,self.log_msg,self.show_command_window.get(),cw,self.set_progress)
                if rc==0: self.last_render=out; self.set_progress(100); self.log_msg(f"\nDone! Created: {out}"); self.ask_open_render(out)
                else: self.log_msg("\nRender failed."); messagebox.showerror("Render failed","FFmpeg returned an error. Check the log.")
            except Exception as e: self.log_msg(f"ERROR: {e}"); messagebox.showerror("Error",str(e))
        threading.Thread(target=work,daemon=True).start()

if __name__=="__main__":
    if not check_tool("ffmpeg") or not check_tool("ffprobe"):
        root=tk.Tk(); root.withdraw(); messagebox.showerror("Missing FFmpeg","FFmpeg and/or FFprobe were not found on PATH.")
    else:
        App().mainloop()

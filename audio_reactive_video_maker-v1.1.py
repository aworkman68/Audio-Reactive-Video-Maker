
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

EFFECTS = {
    "Waveform Line": "waveform",
    "Mirrored Waveform": "mirrored_waveform",
    "Spectrum Bars": "spectrum",
    "Radial / CQT Spectrum": "cqt",
    "Pulsing Color Field": "pulse",
    "Equalizer Bars": "equalizer",
    "Plasma Effect": "plasma",
    "Blooming Fractals": "fractals",
    "Particle Emissions": "particles",
    "Tesla Ball": "tesla",
}

PALETTES = {
    "Neon Rainbow": {"wave": "cyan|magenta|yellow", "fg": "cyan"},
    "Fire": {"wave": "red|orange|yellow", "fg": "orange"},
    "Electric Blue": {"wave": "cyan|blue|white", "fg": "cyan"},
    "Purple Neon": {"wave": "purple|magenta|white", "fg": "magenta"},
    "Gold": {"wave": "gold|orange|white", "fg": "gold"},
}

def check_tool(name):
    try:
        subprocess.run([name, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def ffprobe_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    return float(subprocess.check_output(cmd, text=True).strip())

def list_images(folder):
    if not folder:
        return []
    p = Path(folder)
    if not p.exists():
        return []
    return sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGE_EXTS],
                  key=lambda x: x.name.lower())

def res_tuple(text):
    w, h = text.lower().split("x")
    return int(w), int(h)

def run_cmd(cmd, log, show_command_window=False, progress_cb=None, duration=None):
    startupinfo = None
    creationflags = 0
    if os.name == "nt" and not show_command_window:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    log(" ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags
    )

    start_time = time.time()
    for line in proc.stdout:
        log(line.rstrip())
        if progress_cb and duration:
            pct = min(95, int((time.time() - start_time) / max(duration, 1) * 100))
            progress_cb(pct)

    rc = proc.wait()
    if progress_cb:
        progress_cb(100 if rc == 0 else 0)
    return rc

def audio_visual(effect, w, h, fps, palette):
    colors = palette["wave"]
    if effect == "waveform":
        return f"[0:a]showwaves=s={w}x{h}:mode=line:rate={fps}:colors={colors},format=rgba,colorchannelmixer=aa=0.88[vis]"
    if effect == "mirrored_waveform":
        return f"[0:a]showwaves=s={w}x{h}:mode=cline:rate={fps}:colors={colors},format=rgba,colorchannelmixer=aa=0.88[vis]"
    if effect == "spectrum":
        return f"[0:a]showspectrum=s={w}x{h}:mode=combined:color=rainbow:slide=scroll:scale=cbrt,format=rgba[vis]"
    if effect == "cqt":
        return f"[0:a]showcqt=s={w}x{h}:fps={fps}:bar_g=2:sono_g=2,format=rgba[vis]"
    if effect == "equalizer":
        return f"[0:a]showfreqs=s={w}x{h}:mode=bar:ascale=cbrt:fscale=log:win_size=2048:colors={colors},format=rgba[vis]"
    if effect == "pulse":
        return f"[0:a]showwaves=s={w}x{h}:mode=p2p:rate={fps}:colors={colors},boxblur=18:8,format=rgba,colorchannelmixer=aa=0.95[vis]"
    if effect == "particles":
        return f"[0:a]showwaves=s={w}x{h}:mode=point:rate={fps}:colors={colors},boxblur=6:2,format=rgba,colorchannelmixer=aa=0.85[vis]"
    if effect == "tesla":
        return f"[0:a]showcqt=s={w}x{h}:fps={fps}:bar_g=4:sono_g=1,edgedetect=low=0.05:high=0.25,format=rgba,colorchannelmixer=aa=0.9[vis]"
    return f"[0:a]showwaves=s={w}x{h}:mode=line:rate={fps}:colors={colors},format=rgba[vis]"

def background(effect, w, h, fps):
    if effect in ("plasma", "fractals"):
        return f"mandelbrot=s={w}x{h}:rate={fps},hue=h=60*t:s=1.8,eq=saturation=1.8:contrast=1.15[bg]"
    return f"color=c=black:s={w}x{h}:r={fps},format=rgba[bg]"

def visual_filter(effect, w, h, fps, bg_index=None, bg_mode="contain", palette_name="Neon Rainbow"):
    palette = PALETTES.get(palette_name, PALETTES["Neon Rainbow"])
    vis = audio_visual(effect, w, h, fps, palette)

    if bg_index is None:
        bg = background(effect, w, h, fps)
        return f"{bg};{vis};[bg][vis]overlay=0:0,format=yuv420p[v]"

    if bg_mode == "cover":
        bg = f"[{bg_index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},format=rgba[bg]"
    else:
        bg = f"[{bg_index}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps},format=rgba[bg]"
    bg += ";[bg]eq=saturation=1.15:contrast=1.05[bgc]"
    return f"{bg};{vis};[bgc][vis]overlay=0:0,format=yuv420p[v]"

def render_segment(audio, output, effect, resolution, fps, bg=None, bg_mode="contain",
                   palette="Neon Rainbow", start=None, duration=None, log=print,
                   show_command_window=False, progress_cb=None):
    w, h = res_tuple(resolution)
    cmd = ["ffmpeg", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-i", str(audio)]

    bg_index = None
    if bg:
        bg_index = 1
        cmd += ["-loop", "1"]
        if duration is not None:
            cmd += ["-t", str(duration)]
        cmd += ["-i", str(bg)]

    filt = visual_filter(effect, w, h, fps, bg_index, bg_mode, palette)
    cmd += ["-filter_complex", filt, "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac",
            "-shortest", str(output)]
    return run_cmd(cmd, log, show_command_window, progress_cb, duration)

def render_random(audio, output, effects, resolution, fps, section_len, bg_images, bg_mode,
                  palette, preview_seconds, log, show_command_window, progress_cb):
    duration = ffprobe_duration(audio)
    if preview_seconds:
        duration = min(duration, preview_seconds)

    tempdir = Path(tempfile.mkdtemp(prefix="audio_visualizer_"))
    try:
        clips = []
        start = 0.0
        idx = 0
        total_sections = max(1, int((duration + section_len - 0.01) // section_len))
        while start < duration:
            seg_dur = min(section_len, duration - start)
            effect = random.choice(effects)
            bg = random.choice(bg_images) if bg_images else None
            clip = tempdir / f"clip_{idx:04d}.mp4"
            log(f"Rendering section {idx+1}: {effect}, start={start:.2f}, duration={seg_dur:.2f}")

            def section_progress(p):
                if progress_cb:
                    progress_cb(int(((idx + p / 100) / total_sections) * 95))

            rc = render_segment(audio, clip, effect, resolution, fps, bg, bg_mode, palette,
                                start, seg_dur, log, show_command_window, section_progress)
            if rc != 0:
                return rc
            clips.append(clip)
            start += section_len
            idx += 1

        list_file = tempdir / "clips.txt"
        list_file.write_text("\n".join(f"file '{c.as_posix()}'" for c in clips), encoding="utf-8")
        return run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                        "-c", "copy", str(output)], log, show_command_window, progress_cb, duration=3)
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Audio Reactive Video Maker v2")
        self.geometry("940x800")

        self.audio = tk.StringVar()
        self.output = tk.StringVar(value="audio_visualizer.mp4")
        self.bg_image = tk.StringVar()
        self.bg_folder = tk.StringVar()
        self.resolution = tk.StringVar(value="1920x1080")
        self.fps = tk.StringVar(value="30")
        self.bg_mode = tk.StringVar(value="contain")
        self.palette = tk.StringVar(value="Neon Rainbow")
        self.mode = tk.StringVar(value="single")
        self.single_effect = tk.StringVar(value="Waveform Line")
        self.section_len = tk.StringVar(value="12")
        self.preview_seconds = tk.StringVar(value="20")
        self.show_command_window = tk.BooleanVar(value=False)
        self.effect_vars = {name: tk.BooleanVar(value=name in ["Waveform Line", "Spectrum Bars", "Equalizer Bars"]) for name in EFFECTS}
        self.last_render = None
        self.build()

    def build(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        def row_file(r, label, var, cmd):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=5)
            ttk.Entry(frm, textvariable=var).grid(row=r, column=1, sticky="ew", padx=8, pady=5)
            ttk.Button(frm, text="Browse", command=cmd).grid(row=r, column=2, padx=8, pady=5)

        row_file(0, "Audio file:", self.audio, self.pick_audio)
        row_file(1, "Output file:", self.output, self.pick_output)
        row_file(2, "Background image (optional):", self.bg_image, self.pick_bg_image)
        row_file(3, "Background folder for random mode:", self.bg_folder, self.pick_bg_folder)

        opts = ttk.LabelFrame(frm, text="Output Settings")
        opts.grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=8)
        ttk.Label(opts, text="Resolution").grid(row=0, column=0, padx=6, pady=5)
        ttk.Combobox(opts, textvariable=self.resolution, values=["1280x720","1920x1080","2560x1440","3840x2160"], width=14).grid(row=0,column=1,padx=6)
        ttk.Label(opts, text="FPS").grid(row=0, column=2, padx=6)
        ttk.Combobox(opts, textvariable=self.fps, values=["24","30","60"], width=8).grid(row=0,column=3,padx=6)
        ttk.Label(opts, text="Background fit").grid(row=0, column=4, padx=6)
        ttk.Combobox(opts, textvariable=self.bg_mode, values=["contain","cover"], width=10).grid(row=0,column=5,padx=6)
        ttk.Label(opts, text="Color palette").grid(row=0, column=6, padx=6)
        ttk.Combobox(opts, textvariable=self.palette, values=list(PALETTES.keys()), width=16).grid(row=0,column=7,padx=6)

        modes = ttk.LabelFrame(frm, text="Visual Mode")
        modes.grid(row=5, column=0, columnspan=3, sticky="ew", padx=8, pady=8)
        ttk.Radiobutton(modes, text="Single effect for entire audio", variable=self.mode, value="single").grid(row=0,column=0,sticky="w",padx=8,pady=4)
        ttk.Radiobutton(modes, text="Random selected effects by section", variable=self.mode, value="random").grid(row=1,column=0,sticky="w",padx=8,pady=4)
        ttk.Label(modes, text="Single effect").grid(row=0,column=1,padx=8)
        ttk.Combobox(modes, textvariable=self.single_effect, values=list(EFFECTS.keys()), width=30).grid(row=0,column=2,padx=8)
        ttk.Label(modes, text="Section length seconds").grid(row=1,column=1,padx=8)
        ttk.Entry(modes, textvariable=self.section_len, width=10).grid(row=1,column=2,sticky="w",padx=8)

        effs = ttk.LabelFrame(frm, text="Effects Available for Random Mode")
        effs.grid(row=6, column=0, columnspan=3, sticky="ew", padx=8, pady=8)
        for i, (name, var) in enumerate(self.effect_vars.items()):
            ttk.Checkbutton(effs, text=name, variable=var).grid(row=i//3, column=i%3, sticky="w", padx=10, pady=4)

        actions = ttk.LabelFrame(frm, text="Preview / Render")
        actions.grid(row=7, column=0, columnspan=3, sticky="ew", padx=8, pady=8)
        ttk.Label(actions, text="Preview seconds").grid(row=0,column=0,padx=8,pady=5)
        ttk.Entry(actions, textvariable=self.preview_seconds, width=10).grid(row=0,column=1,padx=8)
        ttk.Checkbutton(actions, text="Show command window", variable=self.show_command_window).grid(row=0,column=2,padx=8)
        ttk.Button(actions, text="Render Preview", command=self.render_preview).grid(row=0,column=3,padx=8)
        ttk.Button(actions, text="Render Full Video", command=self.render_full).grid(row=0,column=4,padx=8)
        ttk.Button(actions, text="Open Last Render", command=self.open_last_render).grid(row=0,column=5,padx=8)

        self.progress = ttk.Progressbar(frm, orient="horizontal", length=600, mode="determinate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew", padx=8, pady=6)

        self.log = tk.Text(frm, height=18, wrap="word")
        self.log.grid(row=9, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        frm.rowconfigure(9, weight=1)

    def log_msg(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.update_idletasks()

    def set_progress(self, value):
        self.progress["value"] = max(0, min(100, value))
        self.update_idletasks()

    def pick_audio(self):
        p = filedialog.askopenfilename(filetypes=[("Audio files","*.mp3 *.wav *.m4a *.aac *.flac *.ogg"),("All files","*.*")])
        if p: self.audio.set(p)

    def pick_output(self):
        p = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 video","*.mp4")])
        if p: self.output.set(p)

    def pick_bg_image(self):
        p = filedialog.askopenfilename(filetypes=[("Image files","*.jpg *.jpeg *.png *.webp *.bmp"),("All files","*.*")])
        if p: self.bg_image.set(p)

    def pick_bg_folder(self):
        p = filedialog.askdirectory()
        if p: self.bg_folder.set(p)

    def selected_effects(self):
        return [EFFECTS[n] for n, v in self.effect_vars.items() if v.get()]

    def validate(self):
        if not self.audio.get() or not Path(self.audio.get()).exists():
            messagebox.showerror("Missing audio", "Please select a valid audio file.")
            return False
        return True

    def render_preview(self):
        if self.validate():
            out = str(Path(self.output.get()).with_name("preview_" + Path(self.output.get()).name))
            self.start_render(out, preview=True)

    def render_full(self):
        if self.validate():
            self.start_render(self.output.get(), preview=False)

    def open_last_render(self):
        if self.last_render and Path(self.last_render).exists():
            os.startfile(self.last_render)
        else:
            messagebox.showinfo("No render", "No rendered video found yet.")

    def ask_open_render(self, output):
        if messagebox.askyesno("Render Complete", f"Created:\n{output}\n\nOpen it now?"):
            try:
                os.startfile(output)
            except Exception as e:
                messagebox.showerror("Open failed", str(e))

    def start_render(self, output, preview):
        def work():
            self.log_msg("\n=== Render started ===")
            self.set_progress(0)
            try:
                fps = int(self.fps.get())
                preview_dur = float(self.preview_seconds.get()) if preview else None
                if self.mode.get() == "single":
                    effect = EFFECTS[self.single_effect.get()]
                    bg = self.bg_image.get().strip() or None
                    rc = render_segment(self.audio.get(), output, effect, self.resolution.get(), fps,
                                        bg, self.bg_mode.get(), self.palette.get(), None, preview_dur,
                                        self.log_msg, self.show_command_window.get(), self.set_progress)
                else:
                    effects = self.selected_effects()
                    if not effects:
                        messagebox.showerror("No effects", "Please select at least one random-mode effect.")
                        return
                    imgs = list_images(self.bg_folder.get().strip())
                    rc = render_random(self.audio.get(), output, effects, self.resolution.get(), fps,
                                       float(self.section_len.get()), imgs, self.bg_mode.get(),
                                       self.palette.get(), preview_dur, self.log_msg,
                                       self.show_command_window.get(), self.set_progress)
                if rc == 0:
                    self.last_render = output
                    self.set_progress(100)
                    self.log_msg(f"\nDone! Created: {output}")
                    self.ask_open_render(output)
                else:
                    self.log_msg("\nRender failed.")
                    messagebox.showerror("Render failed", "FFmpeg returned an error. Check the log.")
            except Exception as e:
                self.log_msg(f"ERROR: {e}")
                messagebox.showerror("Error", str(e))
        threading.Thread(target=work, daemon=True).start()

if __name__ == "__main__":
    if not check_tool("ffmpeg") or not check_tool("ffprobe"):
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Missing FFmpeg", "FFmpeg and/or FFprobe were not found on PATH.")
    else:
        App().mainloop()

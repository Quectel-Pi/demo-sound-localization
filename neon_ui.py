"""Code-drawn cyberpunk desktop UI. No raster assets or animation loop required."""
import math
import time
import tkinter as tk

COLORS = {
    'bg': '#070B14', 'panel': '#0D1524', 'inset': '#0A111E',
    'border': '#203548', 'grid': '#142438', 'text': '#DEECF7',
    'muted': '#809AAF', 'cyan': '#40F2FF', 'pink': '#FA4C9B',
    'amber': '#FFD166', 'green': '#73F0BC', 'error': '#FF7488',
}


class NeonButton(tk.Canvas):
    def __init__(self, parent, text, command, width=88, accent='cyan'):
        self.accent = COLORS[accent]
        self.text = text
        self.command = command
        self.hover = False
        super().__init__(parent, width=width, height=34, bg=parent.cget('bg'),
                         highlightthickness=1, highlightbackground=parent.cget('bg'),
                         highlightcolor=self.accent, bd=0, cursor='hand2', takefocus=True)
        self.bind('<Configure>', lambda event: self.paint())
        self.bind('<Enter>', lambda event: self.set_hover(True))
        self.bind('<Leave>', lambda event: self.set_hover(False))
        self.bind('<ButtonRelease-1>', lambda event: self.invoke())
        self.bind('<Return>', lambda event: self.invoke())
        self.bind('<space>', lambda event: self.invoke())

    def set_hover(self, hover):
        self.hover = hover
        self.paint()

    def invoke(self):
        self.focus_set()
        self.command()

    def set_text(self, text):
        self.text = text
        self.paint()

    def paint(self):
        self.delete('all')
        w, h = self.winfo_width()-2, self.winfo_height()-2
        self.create_polygon(1, 9, 9, 1, w-1, 1, w-1, h-9, w-9, h-1, 1, h-1,
                            fill='#16374A' if self.hover else '#102331', outline=self.accent, width=1)
        self.create_text(w/2, h/2, text=self.text, fill=self.accent, font=('sans', 10, 'bold'))


class GateSlider(tk.Canvas):
    def __init__(self, parent, variable):
        self.variable = variable
        super().__init__(parent, height=34, bg=COLORS['panel'], bd=0, cursor='hand2',
                         highlightthickness=1, highlightbackground=COLORS['panel'],
                         highlightcolor=COLORS['pink'], takefocus=True)
        self.trace = variable.trace_add('write', lambda *args: self.paint())
        self.bind('<Configure>', lambda event: self.paint())
        self.bind('<Button-1>', self.select)
        self.bind('<B1-Motion>', self.select)
        self.bind('<Left>', lambda event: self.step(-1))
        self.bind('<Right>', lambda event: self.step(1))
        self.bind('<Down>', lambda event: self.step(-1))
        self.bind('<Up>', lambda event: self.step(1))
        self.bind('<Home>', lambda event: variable.set(-65))
        self.bind('<End>', lambda event: variable.set(-20))
        self.bind('<Destroy>', lambda event: variable.trace_remove('write', self.trace))

    def step(self, delta):
        self.variable.set(max(-65, min(-20, self.variable.get()+delta)))

    def select(self, event):
        self.focus_set()
        width = max(1, self.winfo_width()-20)
        fraction = max(0, min(1, (event.x-10)/width))
        self.variable.set(round(-65+45*fraction))

    def paint(self):
        self.delete('all')
        width, height = self.winfo_width(), self.winfo_height()
        x = 10+max(0, min(1, (self.variable.get()+65)/45))*max(1, width-20)
        y = height/2
        self.create_rectangle(10, y-2, width-10, y+2, fill='#26394A', outline='')
        self.create_rectangle(10, y-2, x, y+2, fill='#A43472', outline='')
        self.create_polygon(x-5, y-9, x+5, y-9, x+5, y+5, x+1, y+9, x-5, y+9,
                            fill=COLORS['pink'], outline=COLORS['pink'])


class CyberpunkView:
    def __init__(self, owner):
        self.owner = owner
        self.root = owner.root
        self.radar_size = None
        self.notice_until = 0
        self.static = []
        self.root.configure(bg=COLORS['bg'])
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=3)
        self.root.rowconfigure(2, weight=1)

        header = tk.Frame(self.root, bg=COLORS['bg'])
        header.grid(row=0, column=0, sticky='ew', padx=24, pady=(20, 16))
        self.text_label(header, 'title', 27, COLORS['cyan'], bold=True).pack(side='left')
        mode = 'demo' if owner.args.demo else ('replay' if owner.args.wav else 'live')
        self.mode_label = tk.Label(header, text='●  '+owner.tr(mode), bg='#102431', fg=COLORS['cyan'],
                                   font=('sans', 10), padx=14, pady=10)
        self.mode_label.pack(side='right')
        self.static.append((self.mode_label, mode, '●  '))
        self.text_button(header, 'language', owner.set_language, width=82).pack(side='right', padx=(0, 10))
        if not (owner.args.demo or owner.args.wav):
            self.text_button(header, 'retry', owner.retry_device, width=138).pack(side='right', padx=(0, 10))

        body = tk.Frame(self.root, bg=COLORS['bg'])
        body.grid(row=1, column=0, sticky='nsew', padx=24)
        body.columnconfigure(0, weight=5, uniform='panels')
        body.columnconfigure(1, weight=3, uniform='panels')
        body.rowconfigure(0, weight=1)
        radar = self.panel(body)
        radar.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        self.text_label(radar, 'direction', 11, COLORS['text'], bold=True).pack(anchor='w', padx=18, pady=(16, 0))
        owner.canvas = tk.Canvas(radar, bg=COLORS['panel'], bd=0, highlightthickness=0, height=340)
        owner.canvas.pack(fill='both', expand=True, padx=8, pady=8)
        self.text_label(radar, 'orientation', 10).pack(pady=(0, 14))

        sidebar = tk.Frame(body, bg=COLORS['bg'])
        sidebar.grid(row=0, column=1, sticky='nsew')
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)
        status = self.panel(sidebar)
        status.grid(row=0, column=0, sticky='nsew', pady=(0, 14))
        self.text_label(status, 'signal', 11, COLORS['text'], bold=True).pack(anchor='w', padx=18, pady=(16, 3))
        self.lock_label = self.label(status, owner.tr('waiting'), 11, COLORS['muted'])
        self.lock_label.pack(anchor='w', padx=18, pady=(4, 0))
        self.angle_label = self.label(status, '—', 31 if owner.sentence_mode else 49, COLORS['cyan'], bold=True, mono=True)
        self.angle_label.pack(anchor='w', padx=16)
        metrics = tk.Frame(status, bg=COLORS['panel'])
        metrics.pack(fill='x', padx=18, pady=(0, 9))
        self.voice_label = self.label(metrics, owner.tr('waiting'), 10, COLORS['pink'])
        self.voice_label.pack(side='left')
        self.confidence_label = self.label(metrics, owner.tr('consistency', value=0), 10)
        self.confidence_label.pack(side='right')
        level_row = tk.Frame(status, bg=COLORS['panel'])
        level_row.pack(fill='x', padx=18)
        self.text_label(level_row, 'input_level', 10).pack(side='left')
        self.level_label = self.label(level_row, '— dBFS', 12, COLORS['text'], mono=True)
        self.level_label.pack(side='right')
        self.meter = tk.Canvas(status, bg=COLORS['panel'], height=28, highlightthickness=0)
        self.meter.pack(fill='x', padx=18, pady=(5, 0))
        self.gate_hint = self.label(status, owner.tr('gate_hint'), 9)
        self.gate_hint.pack(anchor='w', padx=18, pady=(0, 12))

        gate = self.panel(sidebar)
        gate.grid(row=1, column=0, sticky='ew')
        gate_title = tk.Frame(gate, bg=COLORS['panel'])
        gate_title.pack(fill='x', padx=18, pady=(14, 3))
        self.text_label(gate_title, 'base_gate', 11, COLORS['text'], bold=True).pack(side='left')
        self.gate_label = self.label(gate_title, f'{owner.gate.get():.0f} dBFS', 12, COLORS['pink'], mono=True)
        self.gate_label.pack(side='right')
        adjust = tk.Frame(gate, bg=COLORS['panel'])
        adjust.pack(fill='x', padx=16)
        adjust.columnconfigure(1, weight=1)
        NeonButton(adjust, '−', lambda: self.adjust_gate(-1), width=34, accent='pink').grid(row=0, column=0)
        GateSlider(adjust, owner.gate).grid(row=0, column=1, sticky='ew', padx=8)
        NeonButton(adjust, '+', lambda: self.adjust_gate(1), width=34, accent='pink').grid(row=0, column=2)
        gate_bottom = tk.Frame(gate, bg=COLORS['panel'])
        gate_bottom.pack(fill='x', padx=18, pady=(3, 12))
        self.text_button(gate_bottom, 'save', owner.save, width=82, accent='pink').pack(side='right')

        transcript = self.panel(self.root)
        transcript.grid(row=2, column=0, sticky='nsew', padx=24, pady=(16, 0))
        transcript.columnconfigure(0, weight=1)
        transcript.rowconfigure(2, weight=1)
        title = tk.Frame(transcript, bg=COLORS['panel'])
        title.grid(row=0, column=0, sticky='ew', padx=18, pady=(12, 3))
        self.text_label(title, 'transcript', 11, COLORS['text'], bold=True).pack(side='left')
        self.text_button(title, 'clear', owner.clear_transcripts, width=64, accent='pink').pack(side='right')
        self.text_button(title, 'copy', owner.copy_transcripts, width=92).pack(side='right', padx=8)
        owner.asr_label = self.label(transcript, owner.tr(owner.asr_message_key), 10, COLORS['cyan'])
        owner.asr_label.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 6))
        owner.asr_label.configure(anchor='w', justify='left')
        transcript.bind('<Configure>', lambda event: owner.asr_label.configure(wraplength=max(200, event.width-40)))
        text_body = tk.Frame(transcript, bg=COLORS['inset'])
        text_body.grid(row=2, column=0, sticky='nsew', padx=18, pady=(0, 14))
        owner.transcript_text = tk.Text(text_body, height=3, wrap='word', font=('sans', 14),
            bg=COLORS['inset'], fg=COLORS['muted'], relief='flat', bd=0, padx=12, pady=8,
            insertbackground=COLORS['cyan'], selectbackground='#164959', selectforeground=COLORS['text'],
            highlightthickness=0)
        scroll = tk.Scrollbar(text_body, command=owner.transcript_text.yview, bg='#203548',
                              troughcolor=COLORS['inset'], activebackground=COLORS['cyan'], bd=0,
                              highlightthickness=0, width=10)
        scroll.pack(side='right', fill='y')
        owner.transcript_text.configure(yscrollcommand=scroll.set)
        owner.transcript_text.pack(fill='both', expand=True)
        owner.transcript_text.insert('end', owner.tr('waiting_transcript'))
        owner.transcript_text.configure(state='disabled')

        footer = tk.Frame(self.root, bg=COLORS['bg'])
        footer.grid(row=3, column=0, sticky='ew', padx=24, pady=(10, 14))
        owner.footer = self.label(footer, owner.tr('connecting'), 10)
        owner.footer.pack(side='left', fill='x', expand=True)
        owner.footer.configure(anchor='w')
        self.text_label(footer, 'offline', 9, COLORS['cyan'], mono=True).pack(side='right')

    def panel(self, parent):
        return tk.Frame(parent, bg=COLORS['panel'], highlightthickness=1, highlightbackground=COLORS['border'])

    def label(self, parent, text, size=10, color=None, bold=False, mono=False):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color or COLORS['muted'],
                        font=('DejaVu Sans Mono' if mono else 'sans', size, 'bold' if bold else 'normal'))

    def text_label(self, parent, key, size=10, color=None, bold=False, mono=False):
        widget = self.label(parent, self.owner.tr(key), size, color, bold, mono)
        self.static.append((widget, key, ''))
        return widget

    def text_button(self, parent, key, command, **options):
        widget = NeonButton(parent, self.owner.tr(key), command, **options)
        self.static.append((widget, key, ''))
        return widget

    def set_language(self):
        for widget, key, prefix in self.static:
            value = prefix+self.owner.tr(key)
            if isinstance(widget, NeonButton):
                widget.set_text(value)
            else:
                widget.configure(text=value)
        self.render()

    def adjust_gate(self, step):
        self.owner.gate.set(max(-65, min(-20, self.owner.gate.get()+step)))

    def notify(self, text, error=False):
        self.notice_until = time.monotonic()+4
        self.owner.footer.configure(text=text, fg=COLORS['error'] if error else COLORS['cyan'])

    def draw_static_radar(self, w, h):
        c = self.owner.canvas
        c.delete('all')
        cx, cy = w/2, h/2
        radius = max(45, min(w*0.36, (h-76)/2))
        self.radar_geometry = cx, cy, radius
        for y in range(16, h-10, 26):
            c.create_line(16, y, w-16, y, fill='#101D2D')
        for x in range(16, w-10, 26):
            c.create_line(x, 16, x, h-16, fill='#101D2D')
        for x, y, dx, dy in ((16, 16, 1, 1), (w-16, 16, -1, 1), (16, h-16, 1, -1), (w-16, h-16, -1, -1)):
            c.create_line(x+20*dx, y, x, y, x, y+20*dy, fill=COLORS['cyan'], width=2)
        for scale in (0.25, 0.5, 0.75, 1):
            r = radius*scale
            c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=COLORS['border'], width=1)
        for angle in range(0, 360, 30):
            a = math.radians(angle)
            c.create_line(cx, cy, cx+radius*math.sin(a), cy-radius*math.cos(a), fill=COLORS['grid'], dash=(2, 6))
        for angle in range(0, 360, 5):
            a = math.radians(angle)
            inner = radius-(10 if angle % 30 == 0 else 4)
            c.create_line(cx+inner*math.sin(a), cy-inner*math.cos(a), cx+radius*math.sin(a), cy-radius*math.cos(a),
                          fill=COLORS['cyan'] if angle % 30 == 0 else '#315064')
        for i, label in enumerate(('0°', '90°', '180°', '270°')):
            a = i*math.pi/2
            c.create_text(cx+(radius+24)*math.sin(a), cy-(radius+24)*math.cos(a), text=label,
                          fill=COLORS['muted'], font=('DejaVu Sans Mono', 10))

    def render(self):
        owner, c = self.owner, self.owner.canvas
        size = c.winfo_width(), c.winfo_height()
        if size != self.radar_size:
            self.radar_size = size
            self.draw_static_radar(*size)
        c.delete('dynamic')
        cx, cy, radius = self.radar_geometry
        if owner.alive:
            a = math.radians(owner.display_angle)
            if owner.sentence_mode:
                spread = owner.direction_half_width
                reach = radius*0.86
                c.create_arc(cx-reach, cy-reach, cx+reach, cy+reach,
                             start=90-owner.display_angle-spread, extent=2*spread,
                             style='pieslice', fill='#123A47', outline='#2BAFC0', width=1, tags='dynamic')
            u, v = (math.sin(a), -math.cos(a)), (math.cos(a), math.sin(a))
            def point(forward, sideways=0):
                return cx+radius*(forward*u[0]+sideways*v[0]), cy+radius*(forward*u[1]+sideways*v[1])
            vertices = [coordinate for p in (point(0.82), point(-0.14, 0.15), point(-0.025), point(-0.14, -0.15)) for coordinate in p]
            c.create_polygon(*vertices, fill='#11323F', outline='#163F51', width=7, tags='dynamic')
            c.create_polygon(*vertices, fill='#123A47', outline=COLORS['cyan'], width=2, tags='dynamic')
            tip = point(0.94)
            c.create_oval(tip[0]-4, tip[1]-4, tip[0]+4, tip[1]+4, fill=COLORS['pink'], outline='', tags='dynamic')
        else:
            c.create_line(cx-12, cy, cx+12, cy, fill='#315064', width=2, tags='dynamic')
            c.create_line(cx, cy-12, cx, cy+12, fill='#315064', width=2, tags='dynamic')
            c.create_text(cx, cy+40, text=owner.tr('source'), fill=COLORS['muted'], font=('sans', 12), tags='dynamic')
        status_key = 'sentence_locked' if owner.sentence_mode else 'tracking'
        status, color = (owner.tr(status_key), COLORS['cyan']) if owner.alive else (owner.tr('waiting'), COLORS['muted'])
        if owner.error:
            status, color = owner.tr('device_failed'), COLORS['error']
        elif owner.done:
            status, color = owner.tr('playback_ended'), COLORS['amber']
        self.lock_label.configure(text='●  '+status, fg=color)
        angle_text = (owner.tr('angle_range', angle=round(owner.display_angle) % 360,
                               half=owner.direction_half_width) if owner.sentence_mode else
                      f'{owner.display_angle:03.0f}°') if owner.alive else '—'
        self.angle_label.configure(text=angle_text, fg=color)
        speech = owner.latest.get('speech')
        self.voice_label.configure(text=owner.tr('speech') if speech else (owner.tr('waiting') if speech is not None else owner.tr('filter_off')),
                                   fg=COLORS['pink'] if speech else COLORS['muted'])
        consistency = owner.sentence_consistency if owner.sentence_mode and owner.alive else owner.latest['confidence']
        self.confidence_label.configure(text=owner.tr('consistency', value=consistency))
        db = owner.latest['dbfs']
        self.level_label.configure(text=f'{db:.1f} dBFS')
        threshold = owner.gate.get()
        self.gate_label.configure(text=f'{threshold:.0f} dBFS')
        effective = owner.latest.get('effective_gate_dbfs', threshold)
        self.gate_hint.configure(text=owner.tr('voice_gate', value=effective))
        meter = self.meter
        meter.delete('all')
        width = max(1, meter.winfo_width())
        filled = max(0, min(24, round((db+65)/65*24)))
        for i in range(24):
            fill = COLORS['cyan'] if i < 21 else COLORS['amber']
            meter.create_rectangle(i*width/24, 7, (i+1)*width/24-3, 18,
                                   fill=fill if i < filled else '#213040', outline='')
        mark = max(0, min(width-2, (threshold+65)/65*width))
        meter.create_line(mark, 2, mark, 23, fill=COLORS['pink'], width=2)
        if time.monotonic() >= self.notice_until:
            if owner.error:
                text, color = owner.tr('capture_error', error=owner.error), COLORS['error']
            elif owner.done:
                text, color = owner.tr('playback_complete'), COLORS['muted']
            else:
                prefix = owner.tr('demo_audio') if owner.args.demo else ''
                text, color = prefix+owner.tr('speak'), COLORS['muted']
            owner.footer.configure(text=text, fg=color)

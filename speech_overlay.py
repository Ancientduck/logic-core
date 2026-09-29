import tkinter as tk
import time

# ------------------------------------------------------------------
#  FADE & TIMING CONSTANTS
# ------------------------------------------------------------------
IDLE_FADE_DELAY_MS = 2000  # Pause for 2s AFTER speech finishes before fading
ACTIVE_ALPHA = 0.84        # Target opacity when speaking/active
FADED_ALPHA = 0.0          # Target opacity when faded out
FADE_STEP = 0.06           # Opacity step size per frame
FADE_INTERVAL_MS = 20      # Animation step interval (~50 FPS)

# ------------------------------------------------------------------
#  STYLE LAYER — JARVIS HUD
# ------------------------------------------------------------------
TRANSPARENCY_COLOR = "#081120"
TEXT_COLOR         = "#C4E9FF"
CLOSE_BTN_COLOR    = "#DFF3FF"
CLOSE_BTN_HOVER    = "#FF5555"

HUD_LINE  = "#38BDF8"   # Corner brackets
HUD_FAINT = "#1B3A57"   # Frame outline
HUD_DIM   = "#5E8CA8"   # Wordmark

FONT_FAMILY = "Cascadia Code"


class LOGICOverlay(tk.Toplevel):

    def __init__(self, master, text=""):
        super().__init__(master)

        self.title("LOGIC says")
        self.font = (FONT_FAMILY, 14)
        self.font_mark = (FONT_FAMILY, 9, "bold")
        self.font_x = (FONT_FAMILY, 12, "bold")

        self.configure(bg=TRANSPARENCY_COLOR)
        self.attributes("-topmost", True)

        # State management for fade logic
        self.target_alpha = ACTIVE_ALPHA
        self.attributes("-alpha", self.target_alpha)

        self.is_speaking = False
        self.last_activity = time.monotonic()

        self._anim_job = None
        self._idle_job = None

        self.is_dragging = False
        self.overlay_width = 600
        self.overlay_height = 250

        self.update_idletasks()
        screen_width = self.winfo_screenwidth()

        self.geometry(
            f"{self.overlay_width}x{self.overlay_height}+"
            f"{screen_width - self.overlay_width}+0"
        )

        self.overrideredirect(True)
        self.text_id = None
        self.create_overlay(text)

        # Start monitoring idle status
        self._schedule_idle_check()

    # ------------------------------------------------------------------
    #  AUDIO & ACTIVITY CONTROL API
    # ------------------------------------------------------------------
    def wake(self, event=None):
        """Called when speech starts or mouse moves over the canvas."""
        self.is_speaking = True
        self.last_activity = time.monotonic()
        if self.target_alpha != ACTIVE_ALPHA:
            self.target_alpha = ACTIVE_ALPHA
            self._start_animator()

    def mark_speech_finished(self):
        """Called when audio finish playback. Starts the countdown to fade out."""
        self.is_speaking = False
        self.last_activity = time.monotonic()

    def set_idle(self):
        """Alias for mark_speech_finished for API compatibility."""
        self.mark_speech_finished()

    # ------------------------------------------------------------------
    #  FADE ANIMATION LOGIC
    # ------------------------------------------------------------------
    def _schedule_idle_check(self):
        if self._idle_job is not None:
            self.after_cancel(self._idle_job)
        self._idle_job = self.after(100, self._check_idle)

    def _check_idle(self):
        if not self.winfo_exists():
            return

        # Fades out ONLY if audio is stopped AND delay time has elapsed
        if not self.is_speaking:
            elapsed = time.monotonic() - self.last_activity
            if elapsed >= (IDLE_FADE_DELAY_MS / 1000):
                if self.target_alpha != FADED_ALPHA:
                    self.target_alpha = FADED_ALPHA
                    self._start_animator()

        self._schedule_idle_check()

    def _start_animator(self):
        if self._anim_job is None:
            self._step_fade()

    def _step_fade(self):
        self._anim_job = None
        if not self.winfo_exists():
            return

        current = self.attributes("-alpha")
        if abs(current - self.target_alpha) > 0.02:
            if current < self.target_alpha:
                new_alpha = min(self.target_alpha, current + FADE_STEP)
            else:
                new_alpha = max(self.target_alpha, current - FADE_STEP)
            self.attributes("-alpha", new_alpha)
            self._anim_job = self.after(FADE_INTERVAL_MS, self._step_fade)
        else:
            self.attributes("-alpha", self.target_alpha)
            # Clear text once fully transparent
            if self.target_alpha == FADED_ALPHA:
                try:
                    self.canvas.itemconfig(self.text_id, text="")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    #  DRAG & WINDOW MANAGEMENT
    # ------------------------------------------------------------------
    def start_move(self, event):
        self.wake()
        self.offset_x = event.x
        self.offset_y = event.y

    def do_move(self, event):
        self.wake()
        if not self.is_dragging:
            self.is_dragging = True
            x = event.x_root - self.offset_x
            y = event.y_root - self.offset_y
            self.geometry(f"+{x}+{y}")
            self.reset_drag()

    def reset_drag(self):
        self.is_dragging = False

    # ------------------------------------------------------------------
    #  UI CREATION & UPDATING
    # ------------------------------------------------------------------
    def create_overlay(self, text):
        W, H = self.overlay_width, self.overlay_height
        self.canvas = tk.Canvas(
            self,
            width=self.overlay_width,
            height=self.overlay_height,
            bg=TRANSPARENCY_COLOR,
            highlightthickness=0
        )
        self.canvas.place(x=0, y=0)

        # Faint frame outline
        self.canvas.create_rectangle(10, 10, W - 11, H - 11,
                                     outline=HUD_FAINT, fill="")

        # Corner brackets
        m, a = 14, 26
        for cx, cy, dx, dy in [(m, m, 1, 1), (W - m, m, -1, 1),
                               (m, H - m, 1, -1), (W - m, H - m, -1, -1)]:
            self.canvas.create_line(cx, cy, cx + dx * a, cy, fill=HUD_LINE, width=2)
            self.canvas.create_line(cx, cy, cx, cy + dy * a, fill=HUD_LINE, width=2)

        # Wordmark
        self.canvas.create_oval(22, 22, 28, 28, fill=HUD_LINE, outline="")
        self.canvas.create_text(36, 25, text="L O G I C", anchor="w",
                                font=self.font_mark, fill=HUD_DIM)

        # Close button inside right bracket
        self.canvas.create_oval(W - 44, 24, W - 24, 42,
                                outline=HUD_LINE, width=1,
                                tags=("close_button", "close_ring"))
        self.canvas.create_text(W - 34, 32, text="×", font=self.font_x,
                                fill=CLOSE_BTN_COLOR, activefill=CLOSE_BTN_HOVER,
                                tags=("close_button", "close_glyph"))

        max_text_width = self.overlay_width - 48

        self.text_id = self.canvas.create_text(
            24, 48,
            font=self.font,
            fill=TEXT_COLOR,
            text=text,
            width=max_text_width,
            anchor="nw",
            justify="left"
        )

        # Event bindings
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)
        self.canvas.bind("<Motion>", self.wake)

        self.canvas.tag_bind("close_button", "<Button-1>", lambda e: self.destroy())
        self.canvas.tag_bind("close_button", "<Enter>", lambda e: (self.wake(), self.canvas.config(cursor="hand2")))
        self.canvas.tag_bind("close_button", "<Leave>", lambda e: self.canvas.config(cursor=""))

        self.canvas.tag_bind("close_button", "<Enter>",
                             lambda e: self.canvas.itemconfig("close_ring", outline=CLOSE_BTN_HOVER),
                             add="+")
        self.canvas.tag_bind("close_button", "<Leave>",
                             lambda e: self.canvas.itemconfig("close_ring", outline=HUD_LINE),
                             add="+")

    def update_text(self, new_text: str):
        if not self.winfo_exists():
            return
        self.wake()
        try:
            current = self.canvas.itemcget(self.text_id, "text")
            text = (current + " " if current else "") + new_text.strip()
            self.canvas.itemconfig(self.text_id, text=text)
            self.update_idletasks()

            # Wrap/reset frame text if overflowing height
            if self.canvas.bbox(self.text_id)[3] > self.overlay_height - 20:
                self.canvas.itemconfig(self.text_id, text=new_text.strip())
        except Exception:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    ov = LOGICOverlay(root, "LOGIC active. Ready for speech signals...")

    def simulate_audio_playback():
        print("Simulating audio stream...")
        root.after(1000, lambda: (ov.wake(), ov.update_text("Speaking sentence 1...")))
        root.after(4000, lambda: ov.update_text("Speaking sentence 2... still active!"))
        root.after(7000, lambda: (print("Audio finished."), ov.mark_speech_finished()))

    simulate_audio_playback()
    root.mainloop()
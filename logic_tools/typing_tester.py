import tkinter as tk
import time
import random
import os
import statistics

class TypingTester:
    def __init__(self, root):
        self.root = root
        self.root.title("LOGIC's Pure Biomechanical Ergonomics Unit")
        self.root.geometry("750x550")
        self.root.configure(bg="#1e1e1e")

        self.quotes = [
            "Efficiency is intelligent laziness, sir, though your frantic tapping may suggest otherwise.",
            "In the middle of difficulty lies opportunity to type faster and complain less.",
            "A disciplined mind and a fast keyboard are the sharpest tools in any digital domain.",
            "Do not look at the keys, sir. Look at the screen and let your fingers execute with ruthless precision."
        ]

        self.target_text = random.choice(self.quotes)
        self.start_time = None
        self.running = False
        self.active_presses = {}
        self.dwell_times = []
        self.total_keys_pressed = 0

        self.create_widgets()

    def create_widgets(self):
        title_label = tk.Label(self.root, text="BIOMECHANICAL DWELL ANALYSIS", font=("Helvetica", 16, "bold"), fg="#00ffcc", bg="#1e1e1e")
        title_label.pack(pady=20)

        self.quote_label = tk.Label(self.root, text=self.target_text, font=("Helvetica", 12), fg="#ffffff", bg="#2d2d2d", wraplength=650, justify="left", padx=15, pady=15)
        self.quote_label.pack(pady=10)

        self.input_area = tk.Text(self.root, height=5, width=70, font=("Helvetica", 12), bg="#2d2d2d", fg="#ffffff", insertbackground="white", wrap="word")
        self.input_area.pack(pady=15)

        self.input_area.bind("<<Paste>>", lambda e: "break")
        self.input_area.bind("<KeyPress>", self.record_key_press)
        self.input_area.bind("<KeyRelease>", self.record_key_release)

        self.result_label = tk.Label(self.root, text="", font=("Helvetica", 13, "bold"), fg="#00ffcc", bg="#1e1e1e")
        self.result_label.pack(pady=15)

        reset_btn = tk.Button(self.root, text="Reset", font=("Helvetica", 11), bg="#00ffcc", fg="#1e1e1e", command=self.reset_test, relief="flat", padx=10, pady=5)
        reset_btn.pack(pady=5)

    def record_key_press(self, event):
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "BackSpace"):
            return

        current_time = time.time()
        if not self.running:
            self.start_time = current_time
            self.running = True
            self.dwell_times = []
            self.total_keys_pressed = 0

        self.active_presses[event.keycode] = current_time

    def record_key_release(self, event):
        if event.keycode in self.active_presses:
            press_time = self.active_presses.pop(event.keycode)
            dwell = time.time() - press_time
            self.dwell_times.append(dwell)
            self.total_keys_pressed += 1

        self.check_completion()

    def check_completion(self):
        typed_text = self.input_area.get("1.0", "end-1c")
        if typed_text == self.target_text and self.running:
            self.running = False
            total_time = time.time() - self.start_time
            minutes = total_time / 60
            words = len(self.target_text.split())
            wpm = round(words / minutes) if minutes > 0 else 0

            verdict = "Human Biomechanical Signature Verified"
            avg_dwell = 0

            if self.dwell_times:
                avg_dwell = sum(self.dwell_times) / len(self.dwell_times)

            if avg_dwell < 0.002 or len(self.dwell_times) < (len(self.target_text) * 0.5):
                verdict = "AUTOMATED SCRIPT DETECTED (Zero Physical Dwell / Synthetic Injection)"

            result_str = f"WPM: {wpm} | Avg Dwell: {round(avg_dwell * 1000, 2)}ms\nVerdict: {verdict}"
            self.result_label.config(text=result_str)

            os.makedirs("logic_tools", exist_ok=True)
            with open("logic_tools/typing_result.txt", "w") as f:
                f.write(f"WPM: {wpm}\nAvg Dwell: {round(avg_dwell * 1000, 2)}ms\nVerdict: {verdict}\n")

    def reset_test(self):
        self.target_text = random.choice(self.quotes)
        self.quote_label.config(text=self.target_text)
        self.input_area.delete("1.0", "end")
        self.result_label.config(text="")
        self.running = False
        self.start_time = None
        self.active_presses = {}
        self.dwell_times = []
        self.total_keys_pressed = 0

if __name__ == "__main__":
    root = tk.Tk()
    app = TypingTester(root)
    root.mainloop()

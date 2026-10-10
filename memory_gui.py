
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import chromadb
import math
import time

class FuturisticMemoryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VINC.I  //  MEMORY MATRIX")
        self.root.geometry("1200x800")
        self.root.configure(bg="#050505")
        self.root.resizable(True, True)
        
        # Color palette
        self.bg = "#050505"
        self.panel_bg = "#0a0a0a"
        self.accent = "#00f0ff"
        self.accent_dim = "#003344"
        self.secondary = "#ff00aa"
        self.text = "#e0e0e0"
        self.muted = "#555555"
        self.success = "#00ff88"
        self.warning = "#ffaa00"
        self.danger = "#ff3366"
        
        self.particles = []
        self.animation_running = True
        self.hover_glow = 0
        
        self.create_widgets()
        self.connect_db()
        self.animate()
    
    def create_widgets(self):
        # Main canvas for background effects
        self.canvas = tk.Canvas(self.root, bg=self.bg, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # Grid overlay
        self.draw_grid()
        
        # Header
        self.header = tk.Frame(self.canvas, bg=self.bg)
        self.header_window = self.canvas.create_window(600, 40, window=self.header)
        
        tk.Label(self.header, text="VINC.I", font=("Segoe UI", 24, "bold"), 
                bg=self.bg, fg=self.accent).pack(side="left", padx=20)
        tk.Label(self.header, text="MEMORY MATRIX", font=("Segoe UI", 10), 
                bg=self.bg, fg=self.muted).pack(side="left", padx=(0, 20))
        
        self.status_label = tk.Label(self.header, text="● INITIALIZING", 
                                    font=("Consolas", 9), bg=self.bg, fg=self.warning)
        self.status_label.pack(side="right", padx=20)
        
        self.stats_label = tk.Label(self.header, text="MEMORIES: --", 
                                   font=("Consolas", 9), bg=self.bg, fg=self.muted)
        self.stats_label.pack(side="right", padx=20)
        
        # Left panel - Operations
        self.left_panel = tk.Frame(self.canvas, bg=self.panel_bg, width=300)
        self.left_window = self.canvas.create_window(160, 450, window=self.left_panel, height=700)
        
        # Panel border
        self.left_border = self.canvas.create_rectangle(10, 100, 310, 800, 
                                                       outline=self.accent_dim, width=1)
        
        tk.Label(self.left_panel, text="// OPERATIONS", font=("Consolas", 11, "bold"),
                bg=self.panel_bg, fg=self.accent).pack(pady=(20, 15), anchor="w", padx=20)
        
        # Add Memory Section
        self.create_section(self.left_panel, "ADD MEMORY")
        self.add_entry = self.create_modern_entry(self.left_panel)
        self.add_entry.pack(fill="x", padx=20, pady=5)
        self.add_btn = self.create_modern_button(self.left_panel, "▸  SAVE", self.add_memory, self.accent)
        self.add_btn.pack(fill="x", padx=20, pady=10)
        
        # Search Section
        self.create_section(self.left_panel, "SEARCH MATRIX")
        self.search_entry = self.create_modern_entry(self.left_panel)
        self.search_entry.pack(fill="x", padx=20, pady=5)
        self.search_btn = self.create_modern_button(self.left_panel, "▸  SCAN", self.search_memories, self.secondary)
        self.search_btn.pack(fill="x", padx=20, pady=10)
        
        # Delete Section
        self.create_section(self.left_panel, "PURGE DATA")
        self.delete_entry = self.create_modern_entry(self.left_panel)
        self.delete_entry.pack(fill="x", padx=20, pady=5)
        self.delete_btn = self.create_modern_button(self.left_panel, "▸  PURGE BY KEYWORD", self.delete_memory, self.danger)
        self.delete_btn.pack(fill="x", padx=20, pady=10)
        
        # Purge selected button
        self.purge_selected_btn = self.create_modern_button(
            self.left_panel, "▸  PURGE SELECTED", self.purge_selected, self.warning
        )
        self.purge_selected_btn.pack(fill="x", padx=20, pady=5)
        
        # Right panel - Memory display
        self.right_panel = tk.Frame(self.canvas, bg=self.panel_bg)
        self.right_window = self.canvas.create_window(700, 450, window=self.right_panel, width=850, height=700)
        
        self.right_border = self.canvas.create_rectangle(320, 100, 1190, 800,
                                                        outline=self.accent_dim, width=1)
        
        tk.Label(self.right_panel, text="// STORED MEMORIES", font=("Consolas", 11, "bold"),
                bg=self.panel_bg, fg=self.accent).pack(pady=(20, 10), anchor="w", padx=20)
        
        # Memory list with custom styling
        self.tree_frame = tk.Frame(self.right_panel, bg=self.panel_bg)
        self.tree_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.tree = ttk.Treeview(self.tree_frame, columns=("id", "memory", "sim"), 
                                show="headings", height=18, selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("memory", text="MEMORY CONTENT")
        self.tree.heading("sim", text="SIM")
        
        self.tree.column("id", width=80, anchor="center")
        self.tree.column("memory", width=600)
        self.tree.column("sim", width=80, anchor="center")
        
        # Custom scrollbar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Treeview", 
                       background=self.panel_bg,
                       foreground=self.text,
                       fieldbackground=self.panel_bg,
                       borderwidth=0)
        style.configure("Custom.Treeview.Heading",
                       background=self.panel_bg,
                       foreground=self.accent,
                       font=("Consolas", 9, "bold"),
                       borderwidth=0)
        style.map("Custom.Treeview", 
                 background=[("selected", self.accent_dim)],
                 foreground=[("selected", self.accent)])
        
        self.tree.configure(style="Custom.Treeview")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_memory_select)
        
        scroll = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        
        # Bottom status bar
        self.status_bar = tk.Frame(self.canvas, bg=self.panel_bg, height=30)
        self.status_bar_window = self.canvas.create_window(600, 780, window=self.status_bar, width=1180)
        
        self.status_text = tk.Label(self.status_bar, text="SYSTEM READY", 
                                   font=("Consolas", 8), bg=self.panel_bg, fg=self.muted)
        self.status_text.pack(side="left", padx=20, pady=5)
        
        self.time_label = tk.Label(self.status_bar, text="", 
                                  font=("Consolas", 8), bg=self.panel_bg, fg=self.muted)
        self.time_label.pack(side="right", padx=20, pady=5)
        self.update_time()
    
    def draw_grid(self):
        """Draw subtle background grid"""
        self.canvas.delete("grid")
        for x in range(0, 1200, 50):
            self.canvas.create_line(x, 0, x, 800, fill="#111", tags="grid")
        for y in range(0, 800, 50):
            self.canvas.create_line(0, y, 1200, y, fill="#111", tags="grid")
    
    def create_section(self, parent, title):
        """Create section divider"""
        frame = tk.Frame(parent, bg=self.panel_bg)
        frame.pack(fill="x", padx=20, pady=(15, 5))
        
        tk.Label(frame, text=title, font=("Consolas", 9, "bold"),
                bg=self.panel_bg, fg=self.accent).pack(anchor="w")
        tk.Frame(frame, height=1, bg=self.accent_dim).pack(fill="x", pady=(3, 0))
    
    def create_modern_entry(self, parent):
        """Create styled entry widget"""
        entry = tk.Entry(parent, font=("Consolas", 10), 
                        bg="#111", fg=self.text,
                        insertbackground=self.accent,
                        relief="flat", bd=0,
                        highlightthickness=1,
                        highlightcolor=self.accent_dim,
                        highlightbackground=self.muted)
        entry.configure(show="")
        return entry
    
    def create_modern_button(self, parent, text, command, color):
        """Create styled button with hover effect"""
        btn = tk.Button(parent, text=text, command=command,
                       font=("Consolas", 10, "bold"),
                       bg=color, fg=self.bg,
                       activebackground=color,
                       activeforeground=self.bg,
                       relief="flat", bd=0,
                       cursor="hand2",
                       padx=20, pady=8)
        
        def on_enter(e):
            btn.configure(bg=self.lighten_color(color, 20))
            btn.configure(relief="raised")
        
        def on_leave(e):
            btn.configure(bg=color)
            btn.configure(relief="flat")
        
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn
    
    def lighten_color(self, hex_color, percent):
        """Lighten a hex color"""
        hex_color = hex_color.lstrip("#")
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        lighter = tuple(min(255, c + int(255 * percent / 100)) for c in rgb)
        return f"#{lighter[0]:02x}{lighter[1]:02x}{lighter[2]:02x}"
    
    def connect_db(self):
        """Connect to ChromaDB in background"""
        def _connect():
            try:
                self.chroma = chromadb.PersistentClient(path=str(Path(__file__).resolve().parent / 'memory'))
                self.collection = self.chroma.get_or_create_collection("logic_memory")
                self.status_label.config(text="● ONLINE", fg=self.success)
                self.status_text.config(text="CHROMADB CONNECTED // MEMORY MATRIX ACTIVE")
                self.refresh_memories()
            except Exception as e:
                self.status_label.config(text="● ERROR", fg=self.danger)
                self.status_text.config(text=f"CONNECTION FAILED: {str(e)}")
        
        threading.Thread(target=_connect, daemon=True).start()
    
    def add_memory(self):
        text = self.add_entry.get().strip()
        if not text:
            return
        
        def _add():
            try:
                memory_id = str(__import__("uuid").uuid4())
                self.collection.add(embeddings=[[0.0]*768], documents=[text], ids=[memory_id])
                self.status_text.config(text=f"SAVED: {text[:50]}...")
                self.add_entry.delete(0, "end")
                self.refresh_memories()
            except Exception as e:
                self.status_text.config(text=f"ERROR: {str(e)}")
        
        threading.Thread(target=_add, daemon=True).start()
    
    def search_memories(self):
        query = self.search_entry.get().strip()
        if not query:
            self.refresh_memories()
            return
        
        def _search():
            try:
                results = self.collection.get()
                docs = results["documents"]
                ids = results["ids"]
                filtered = [(id, doc) for id, doc in zip(ids, docs) if query.lower() in doc.lower()]
                
                for item in self.tree.get_children():
                    self.tree.delete(item)
                
                if filtered:
                    for id, doc in filtered:
                        self.tree.insert("", "end", values=(id[:8], doc, "MATCH"))
                    self.status_text.config(text=f"FOUND {len(filtered)} MATCHES FOR: {query[:30]}")
                else:
                    self.tree.insert("", "end", values=("--", "NO MATCHES FOUND", "--"))
                    self.status_text.config(text=f"NO RESULTS FOR: {query[:30]}")
            except Exception as e:
                self.status_text.config(text=f"SEARCH ERROR: {str(e)}")
        
        threading.Thread(target=_search, daemon=True).start()
    
    def purge_selected(self):
        selected = self.tree.selection()
        if not selected:
            self.status_text.config(text="NO MEMORY SELECTED // CLICK A MEMORY FIRST")
            return
        
        item = self.tree.item(selected[0])
        memory_text = item["values"][1]
        
        if not messagebox.askyesno("CONFIRM PURGE", f"Delete this memory?\n\n{memory_text[:120]}..."):
            return
        
        def _purge():
            try:
                results = self.collection.get(include=["documents"])
                to_delete = [mid for mid, doc in zip(results["ids"], results["documents"]) 
                           if doc == memory_text]
                
                if to_delete:
                    self.collection.delete(ids=to_delete)
                    self.status_text.config(text=f"PURGED {len(to_delete)} MEMORY ENTRIES")
                    self.refresh_memories()
                else:
                    self.status_text.config(text="MEMORY NOT FOUND IN DATABASE")
            except Exception as e:
                self.status_text.config(text=f"PURGE ERROR: {str(e)}")
        
        threading.Thread(target=_purge, daemon=True).start()

    def delete_memory(self):
        keyword = self.delete_entry.get().strip()
        if not keyword:
            return
        
        def _delete():
            try:
                results = self.collection.get(include=["documents"])
                to_delete = [id for id, doc in zip(results["ids"], results["documents"]) 
                           if keyword.lower() in doc.lower()]
                
                if to_delete:
                    self.collection.delete(ids=to_delete)
                    self.status_text.config(text=f"PURGED {len(to_delete)} MEMORY ENTRIES")
                    self.delete_entry.delete(0, "end")
                    self.refresh_memories()
                else:
                    self.status_text.config(text="NO MATCHING DATA TO PURGE")
            except Exception as e:
                self.status_text.config(text=f"DELETE ERROR: {str(e)}")
        
        threading.Thread(target=_delete, daemon=True).start()
    
    def refresh_memories(self, memories=None):
        def _refresh():
            try:
                if memories is None:
                    results = self.collection.get()
                    ids = results["ids"]
                    docs = results["documents"]
                else:
                    ids = [str(i) for i in range(len(memories))]
                    docs = memories
                
                for item in self.tree.get_children():
                    self.tree.delete(item)
                
                for i, (id, doc) in enumerate(zip(ids, docs)):
                    self.tree.insert("", "end", values=(id[:8], doc, f"{i+1:03d}"))
                
                self.stats_label.config(text=f"ENTRIES: {len(docs)}")
                self.status_text.config(text="MEMORY MATRIX LOADED")
            except Exception as e:
                self.status_text.config(text=f"REFRESH ERROR: {str(e)}")
        
        threading.Thread(target=_refresh, daemon=True).start()
    
    def on_memory_select(self, event):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            memory_text = item["values"][1]
            self.status_text.config(text=f"SELECTED: {memory_text[:80]}...")

    def update_time(self):
        """Update time display"""
        current = time.strftime("%H:%M:%S")
        self.time_label.config(text=current)
        self.root.after(1000, self.update_time)
    
    def animate(self):
        """Animate background particles"""
        if not self.animation_running:
            return
        
        self.canvas.delete("particle")
        
        # Add new particles
        if len(self.particles) < 50:
            self.particles.append({
                "x": __import__("random").randint(0, 1200),
                "y": __import__("random").randint(0, 800),
                "vx": __import__("random").uniform(-0.3, 0.3),
                "vy": __import__("random").uniform(-0.3, 0.3),
                "size": __import__("random").uniform(1, 3),
                "alpha": __import__("random").uniform(0.1, 0.4)
            })
        
        # Update and draw particles
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            
            if p["x"] < 0 or p["x"] > 1200: p["vx"] *= -1
            if p["y"] < 0 or p["y"] > 800: p["vy"] *= -1
            
            alpha_hex = int(p["alpha"] * 255)
            color = f"#{alpha_hex:02x}{alpha_hex:02x}{alpha_hex:02x}"
            self.canvas.create_oval(p["x"]-p["size"], p["y"]-p["size"],
                                   p["x"]+p["size"], p["y"]+p["size"],
                                   fill=color, outline="", tags="particle")
        
        self.root.after(50, self.animate)
    
    def on_closing(self):
        self.animation_running = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FuturisticMemoryGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

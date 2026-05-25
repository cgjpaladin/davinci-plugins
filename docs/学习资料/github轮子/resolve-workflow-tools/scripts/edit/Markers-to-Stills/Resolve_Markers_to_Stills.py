import os
import time
import sys
import tkinter as tk
from tkinter import ttk

# --- GUI FOR USER INPUT ---
def get_user_config():
    """Opens a dialog to select marker color and export format."""
    root = tk.Tk()
    root.title("Resolve Still Exporter")
    root.geometry("320x220")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    # Styling
    style = ttk.Style()
    style.configure("TLabel", font=("Segoe UI", 10))
    style.configure("TButton", font=("Segoe UI", 10, "bold"))

    # Variables
    color_var = tk.StringVar(value="Blue")
    format_var = tk.StringVar(value="jpg")

    # UI Elements
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill="both", expand=True)

    ttk.Label(main_frame, text="Select Marker Color:").pack(anchor="w")
    colors = ["Blue", "Red", "Green", "Yellow", "Cyan", "Pink", "White", "Black"]
    color_menu = ttk.Combobox(main_frame, textvariable=color_var, values=colors, state="readonly")
    color_menu.pack(fill="x", pady=(5, 15))

    ttk.Label(main_frame, text="Select Export Format:").pack(anchor="w")
    format_menu = ttk.Combobox(main_frame, textvariable=format_var, values=["jpg", "png"], state="readonly")
    format_menu.pack(fill="x", pady=(5, 15))

    def on_submit():
        root.quit()

    ttk.Button(main_frame, text="RUN EXPORT", command=on_submit).pack(fill="x", pady=(10, 0))
    
    root.mainloop()
    
    selected_color = color_var.get()
    selected_format = format_var.get()
    root.destroy()
    return selected_color, selected_format

def frame_to_tc(frame_count, fps):
    """Converts frames to Timecode string."""
    f = int(frame_count % fps)
    s = int((frame_count / fps) % 60)
    m = int((frame_count / (fps * 60)) % 60)
    h = int((frame_count / (fps * 3600)) % 24)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

def main():
    # 1. UI Configuration
    target_color, target_format = get_user_config()

    # 2. Resolve Connection (Hybrid Method)
    resolve = None
    if "fusion" in globals():
        resolve = fusion.GetResolve()
    
    if not resolve:
        try:
            import DaVinciResolveScript as dvr_script
            resolve = dvr_script.scriptapp("Resolve")
        except ImportError:
            print("ERROR: API not found. Ensure Resolve is running.")
            return

    if not resolve:
        return
        
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    timeline = project.GetCurrentTimeline()
    gallery = project.GetGallery()
    album = gallery.GetCurrentStillAlbum()
    
    if not timeline or not album:
        print("ERROR: Active Timeline and Gallery Album are required.")
        return

    fps = float(timeline.GetSetting("timelineFrameRate"))
    start_frame = int(timeline.GetStartFrame())
    
    # 3. Path Setup (Desktop)
    export_dir = os.path.join(os.path.expanduser("~"), "Desktop", f"Resolve_Stills_{target_color}")
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)

    # 4. Processing
    resolve.OpenPage("color")
    time.sleep(0.5)

    markers = timeline.GetMarkers()
    if not markers:
        print("INFO: No markers found on the current timeline.")
        return

    sorted_frames = sorted(markers.keys())
    exported_count = 0

    print(f"[*] Starting export for {target_color} markers as {target_format.upper()}...")

    for frame_id in sorted_frames:
        info = markers[frame_id]
        
        if info.get('color') != target_color:
            continue

        exported_count += 1
        tc = frame_to_tc(start_frame + frame_id, fps)
        timeline.SetCurrentTimecode(tc)
        
        # Buffer for viewer refresh
        time.sleep(0.5)
        
        still = timeline.GrabStill()
        
        if still:
            # Filename sanitization
            raw_name = info.get('note') or info.get('name') or f"Still_{frame_id}"
            clean_name = "".join([c for c in raw_name if c.isalnum() or c in (' ', '_', '-')]).strip().replace(" ", "_")
            
            if not clean_name:
                clean_name = f"{target_color}_Still_{tc.replace(':', '.')}"
            
            success = album.ExportStills([still], export_dir, clean_name, target_format)
            
            if success:
                print(f" [OK] {tc} -> {clean_name}.{target_format}")
            else:
                print(f" [!] Failed to export still at {tc}")

    print(f"\nCompleted: {exported_count} stills exported to {export_dir}")

    # 5. OS-Specific folder opening
    if exported_count > 0:
        try:
            if sys.platform == "win32":
                os.startfile(export_dir)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", export_dir])
        except:
            pass

if __name__ == "__main__":
    main()

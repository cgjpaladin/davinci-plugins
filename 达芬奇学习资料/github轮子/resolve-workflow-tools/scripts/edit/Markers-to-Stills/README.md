DaVinci Resolve: Universal Still Exporter
A professional-grade Python automation tool for DaVinci Resolve that provides a graphical interface (GUI) to selectively export high-quality stills (JPG/PNG) based on timeline markers.

🚀 Key Features
Interactive GUI: No coding required to change settings; select marker colors and image formats via a pop-up window.

Color-Based Filtering: Specifically targets markers (Blue, Red, Green, etc.) to streamline look-book creation or VFX plate references.

Hybrid Execution: Works both as an internal script (from the Workspace > Scripts menu) and as an external script (via Terminal/VS Code).

Metadata-Driven Naming: Automatically names files based on marker notes/names, with intelligent character sanitization.

Cross-Platform Ready: Handles file paths and directory opening for both Windows and macOS.

Grade Accurate: Forces the UI to the Color Page to ensure all LUTs and nodes are rendered in the exported stills.

💻 Compatibility
DaVinci Resolve Studio: 18.x, 19.x, and 20.2.2 (Verified).

Python: 3.10 (Standard library).

OS: Windows 11 & macOS.

🛠️ Installation & Setup
1. Internal Resolve Menu (Recommended)
Place the .py file in the following directory to access it via Workspace > Scripts > Edit:

Windows: C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Edit\

macOS: /Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/

2. Enable Scripting
Ensure scripting is enabled in Resolve:

Go to Preferences > System > Control Panels.

Set External scripting using to Local.

🖥️ Usage
Open your project and ensure a Timeline is active.

Open a Gallery Album in the Color Page (where stills will be temporarily cached).

Run the script from the menu.

Choose your Marker Color and Format (JPG/PNG) in the pop-up window.

Click RUN EXPORT. The folder containing your stills will open automatically upon completion.

📜 License
This project is licensed under the MIT License - see the LICENSE file for details.

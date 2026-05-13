# Resolve Workflow Tools

A collection of professional automation scripts and tools for **DaVinci Resolve**, designed to streamline post-production workflows, look development, and technical color management.

---

## 🛠️ Project Overview

This repository serves as a centralized toolkit for Colorists, Online Editors, and Workflow Technologists. Each tool is built with a focus on reliability, cross-platform compatibility (Windows/macOS), and user experience.

## 📂 Repository Structure

The tools are organized according to their primary function within the DaVinci Resolve interface:

* **`scripts/edit/`**: Tools intended to be run from the Edit Page or the global Workspace menu.
* **`scripts/utility/`**: General maintenance and project management scripts.

---

## 🚀 Available Tools

| Tool Name | Category | Description |
| :--- | :--- | :--- |
| [**Resolve Markers to Stills**](./scripts/edit/Markers-to-Stills/) | `Color / Edit` | Interactive GUI to export high-quality stills (JPG/PNG) filtered by marker color. |
| *More tools coming soon...* | - | Stay tuned for future automation updates. |

---

## ⚙️ General Installation

To use these scripts within DaVinci Resolve:

1.  **Locate your Scripts folder**:
    * **Windows**: `%AppData%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit`
    * **macOS**: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit`
2.  **Copy the tool**: Copy the desired `.py` file into the folder above.
3.  **Enable Scripting**: In Resolve, go to `Preferences > System > Control Panels` and set **External scripting using** to **Local**.
4.  **Run**: Access the tool via the `Workspace > Scripts` menu.

## ⚖️ License

This project is licensed under the **MIT License**. You are free to use, modify, and distribute these tools in professional and personal environments. See the [LICENSE] file for details.

---

**Developed by Lucía Blanco** *Colorist & Workflow Technologist*

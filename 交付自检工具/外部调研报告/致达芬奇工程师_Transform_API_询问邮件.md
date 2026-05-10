Subject: Questions about DaVinci Resolve Scripting API — Transform Pipeline & Future API Access

Dear DaVinci Resolve Engineering Team,

I'm a post-production supervisor developing an internal delivery QC tool using the Resolve Scripting API (v20.3.2, Python 3.13). The tool inspects timeline clips for common delivery issues. I've run into a few questions that aren't answered in the public documentation, and I was hoping you could clarify.

---

## 1. Exact Transform Order in the Edit Page Inspector

The Inspector exposes Zoom (X/Y), Rotation Angle, Anchor Point (X/Y), Position X/Y (Pan/Tilt), Pitch, Yaw, and Flip. But the internal mathematical order in which these are applied is not documented.

I'm currently assuming: **Anchor Point → Scale → Rotate → Position**. However, I'm getting false positives in black border detection when clips are rotated (e.g., horizontal clips rotated 90° into a vertical timeline). This suggests my assumed order may not match Resolve's actual pipeline.

Could you confirm the exact transform order? Is it the same as Fusion's Transform node?

---

## 2. "Scale to Fit" / Mismatched Resolution Handling

When a clip's resolution doesn't match the timeline resolution, Resolve applies a "Mismatched resolution" scaling rule (Fit / Fill / Stretch / None). 

Is this base scaling applied **before** or **after** the Inspector's Zoom parameter? And is the relationship multiplicative (base_scale × Zoom) or something else?

---

## 3. RotationAngle Accumulated Values

On clips that I've rotated exactly -90°, `GetProperty("RotationAngle")` returns values like `-5156.6` instead of `-90.0`. Is this intentional (accumulated rotation over multiple operations), or is there a way to get the normalized effective rotation angle?

---

## 4. Future API — Audio / Fairlight

We'd love to check per-clip Volume (gain) from the Fairlight mixer, but `GetProperty()` returns an empty dict for audio clips. Are there plans to expose Fairlight parameters (clip gain, fader, EQ, pan) through the Scripting API in future versions?

Similarly, is there any plan to expose Fairlight bus routing or track-level FX chains as readable (currently write-only)?

---

## Context

We're a production company with ~20 Mac mini editing workstations. This tool is used internally for delivery QC, and I'd love to make it more accurate. Any clarity you can provide on the above would be greatly appreciated.

Thank you for your time, and for continuing to build such a capable API.

Best regards,
Bryan Chen (陈冠杰)
Post-Production Director

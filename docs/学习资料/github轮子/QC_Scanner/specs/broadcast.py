"""Broadcast spec thresholds for QC."""


BROADCAST_SPEC = {
    "name": "Zee Kannada / General Television",
    "loudness": {
        "target_lufs": -24,
        "tolerance": 1,
    },
    "black_level": {
        "min_ymin": 16,
        "max_ymax": 235,
    },
    "color_space": "Rec.709",
    "audio_channels": [1, 2, 6],  # Mono, stereo, 5.1
}

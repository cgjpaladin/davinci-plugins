"""SMPTE 429-2 DCI spec thresholds for QC."""


DCI_SPEC = {
    "name": "SMPTE 429-2 DCI",
    "loudness": {
        "target_lufs": -24,
        "tolerance": 1,
    },
    "black_level": {
        "min_ymin": 16,
        "max_ymax": 235,
    },
    "color_space": "DCI-P3",
    "audio_channels": [1, 2, 6],
}

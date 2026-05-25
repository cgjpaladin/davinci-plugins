"""Netflix OC-3.2 spec thresholds for QC."""


NETFLIX_SPEC = {
    "name": "Netflix OC-3.2",
    "loudness": {
        "target_lufs": -27,
        "tolerance": 2,
    },
    "black_level": {
        "min_ymin": 16,
        "max_ymax": 235,
    },
    "color_space": "Rec.709",
    "audio_channels": [1, 2, 6],  # Mono, stereo, 5.1
}

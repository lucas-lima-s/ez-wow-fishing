# How splash detection works

`SplashDetector` (in `src/wow_ez_fishing/detector.py`) is pure numpy: no I/O, no threads,
no wall clock. It takes arbitrary-sized chunks of mono float32 audio via `push()` and
buffers them internally into fixed-size analysis windows, so it doesn't care how the
caller chunks its input.

## Per-frame pipeline

For every `window_size`-sample frame, advanced by `hop_size` samples each step:

1. Apply a Hann window and take the real FFT: `spec = |rfft(hann * frame)|`.
2. Select the bins inside `[band_low_hz, band_high_hz]` and compute their RMS energy in
   dB: `band_db = 20 * log10(rms(spec[band]) + 1e-12)`.
3. Compute the **flux**: how far `band_db` has risen over the last
   `onset_lookback_frames` frames. This is what makes the detector care about *onsets*
   (sudden splashes) and ignore anything that changes slowly (a volume ramp) or stays
   constant (a sustained tone), even if it eventually reaches a high absolute level.
4. A frame **qualifies** when both hold: `band_db >= baseline_db + trigger_margin_db`
   *and* `flux_db >= onset_db`.
5. An **event fires** once `min_event_frames` consecutive frames qualify, timestamped at
   the start of the first qualifying frame in that run, and only if at least
   `refractory_s` has passed since the previous event.
6. Whenever a frame is *not* part of a qualifying run and not inside the refractory
   window, its `band_db` feeds an EWMA (`baseline_alpha`) that slowly tracks the ambient
   noise floor. The baseline **freezes** while `band_db` is more than
   `baseline_freeze_margin_db` above it, so a loud sustained event never drags the
   baseline upward and desensitizes the detector.

## Where `DETECTION_DURATION` went

The original prototype had one constant, `DETECTION_DURATION`, controlling how long each
`sd.rec()` blocking call captured before being peak-checked. That single knob is gone;
its role is now split across three independent, tunable parameters:

- `window_size` / `hop_size` control the **time-frequency resolution** of each analysis
  frame — how precisely, in time, an onset can be localized, and how much low-frequency
  content the FFT can resolve.
- `calibration_seconds` controls how much ambient audio is collected **once, at
  startup**, to prime the baseline before any casting begins.

None of the three plays the old constant's actual role (gating a single blocking peak
check), because the whole capture path is non-blocking now.

## Tuning from `calibrate` output

```bash
uv run ez-wow-fishing calibrate --seconds 10
```

prints the measured ambient baseline in dB and a per-octave energy table. Use the table
to pick `band_low_hz` / `band_high_hz`: choose the octave band(s) where a real splash
stands out clearly from the surrounding ambience (typically a few kHz for a "watery"
transient, but it depends on your in-game sound settings and any addons). Once the band
is set, `trigger_margin_db` should sit comfortably above the ambient baseline's frame to
frame jitter in that band — `calibrate` output is a starting point, not a promise; the
committed defaults (500–4000 Hz, `trigger_margin_db = 12`) are validated against
synthetic fixtures only, not a real game recording.

If detection is too eager (fires on non-splash game sounds), raise `trigger_margin_db`
or `onset_db`, or narrow the band. If it misses real splashes, do the opposite, or check
`calibrate`'s band table for whether the splash's actual energy falls partly outside the
configured band.

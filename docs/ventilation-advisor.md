# Ventilation advisor / smart hygrometer

Answers a genuinely useful question, "should I open the window right now?",
and gets it right by comparing **absolute** humidity indoors vs outdoors rather
than naively reacting to relative humidity.

## Why absolute humidity
Opening a window only dries a room if the outdoor air holds less water *in
absolute terms*. Cold winter air at 80% RH carries far less moisture than a
warm room at 55%, so venting dries the room; muggy summer air can be wetter than
indoors even at lower RH, so venting makes it worse. Relative humidity alone
can't tell these apart; absolute humidity (g/m3) can.

## Data flow
```
Pico DHT20 (indoor T, RH) --serial--> collector
                                          |  <-- Open-Meteo API (outdoor T, RH), no API key
                                          v
      advisor: AH(indoor) vs AH(outdoor), dew point, mold flag, recommendation
                                          v
                          SQLite --> Grafana   (later: Pi --> Pico LCD + RGB ring)
```

## The model (see collector/psychro.py)
- Saturation vapour pressure (Magnus): `es(T) = 6.112 * exp(17.62*T / (243.12+T))` hPa
- Vapour pressure: `e = es * RH/100`
- Absolute humidity: `AH = 216.7 * e / (T + 273.15)` g/m3
- Dew point: `Td = 243.12*a / (17.62-a)`, `a = ln(RH/100) + 17.62*T/(243.12+T)`

## Decision (see collector/advisor.py)
Thresholds are configurable; defaults:
- `TARGET_RH = 50%` — below this indoors, nothing to do (`comfortable`)
- `MOLD_RH = 60%` — at/above this indoors, raise the `mold_risk` flag
- `AH_MARGIN = 0.5 g/m3` — hysteresis; outdoor must be at least this much drier

| Condition | State | should_ventilate |
|-----------|-------|------------------|
| indoor RH <= TARGET_RH | `comfortable` | 0 |
| indoor RH > TARGET_RH and AH(out) < AH(in) - MARGIN | `ventilate` | 1 |
| indoor RH > TARGET_RH and outdoor not drier | `keep_closed` | 0 |
| no outdoor data | `unknown` | 0 |

`mold_risk` (indoor RH >= MOLD_RH) is an independent overlay.

## Stored columns
`outdoor_temp_c`, `outdoor_humidity_pct`, `indoor_abs_humidity_gm3`,
`outdoor_abs_humidity_gm3`, `dew_point_c`, `ventilation_state`,
`should_ventilate`, `mold_risk`. All nullable; populated only when the advisor
is enabled (`--advisor`) and an indoor reading is present.

## Enabling
```bash
python -m collector.collector --interval 60 --serial-port /dev/ttyACM0 \
    --advisor --lat 48.137 --lon 11.575        # lat/lon default to Munich
```
Outdoor data comes from Open-Meteo (free, no key). If the network is down the
advisor still reports indoor AH, dew point and mold risk; the ventilation state
becomes `unknown`.

## Physical display (implemented)
The recommendation is driven onto the kit's 16x2 I2C LCD (line 1: indoor/outdoor
readings, line 2: the verdict) and the 12-LED RGB ring (blue = open window,
amber = keep closed, green = comfortable, red = mold risk), over a two-way serial
protocol (Pi -> Pico command frames; see pico/main.py and pico/README.md).
Enable with `--pico-display` (or `PICO_DISPLAY=1` in the Buster runner) after
flashing the display firmware and wiring the LCD + ring.

## Follow-up ideas
A button press to log "I ventilated" so Grafana can show humidity dropping after
the action; use the slide potentiometer to set the target/mold thresholds live.

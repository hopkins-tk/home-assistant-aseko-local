> **Historical, superseded — do not implement from this table.** This was the first
> byte map, written before the per-model analyses. Several rows are wrong today
> (e.g. `max_refill_time` is bytes 76–77, not 94–95; the chlorine and pH− flow
> rates are the other way round), and bytes it lists as unknown have since been
> located. The current truth is the profiles, the [support matrix](../support_matrix.md)
> and the [device analyses](../device%20analyzes/). "Aqua Pro" in this table is not the
> ASIN Aqua Profi.

# Record definition coming from Aseko Asin Aqua

Name Decoder               | used bytes [^1] | note
---------------------------|------------|-------
serial number              | 0:3
probe info                 | 4
**unknown**                | 5
year                       | 6          | eg 25 (2000+year), NET = FF always
month                      | 7          | NET = FF always
day                        | 8          | NET = FF always
hour                       | 9          | NET = FF always
minute                     | 10         | NET = FF always
second                     | 11         | NET = FF always
**unknown**                | 12
**unknown**                | 13
ph value                   | 14:15
free_chlorine or redox           | 16:17      |
redox                      | 18:19      | Aqua Pro only clf and redox probes
salinity                   | 20         | Aqua Salt only
chlorine_production         | 21         | Aqua Salt only
free_chlorine mV                 | 20:21      | Aqua Net if clf probe, others?
**unknown**                | 22
air_temperature            | 23:24      | signed, /10 = °C; confirmed on Aqua Salt only. 0xFE70 (-40.0) / 0xFDC4 (-57.2) = no air probe
water_temperature          | 25:26
**unknown**                | 27
water_flow_probe           | 28
pump_or_electrolizer       | 29
**unknown**                | 30
**unknown**                | 31
**unknown**                | 32
**unknown**                | 33
**unknown**                | 34
**unknown**                | 35
**unknown**                | 36
**unknown**                | 37
**unknown**                | 38
**unknown**                | 39
**unknown**                | 40
**unknown**                | 41
**unknown**                | 42
**unknown**                | 43
**unknown**                | 44
**unknown**                | 45
**unknown**                | 46
**unknown**                | 47
**unknown**                | 48
**unknown**                | 49
**unknown**                | 50
**unknown**                | 51
ph_target                | 52
required_cl_free_or_redox  | 53         | if clf and redox probe then required clf
algaecide_dose_target          | 54
water_temperature_target | 55
start_1_time               | 56:57
stop_1_time                | 58:59
start_2_time               | 60:61
stop_2_time                | 62:63
**unknown**                | 64
**unknown**                | 65
**unknown**                | 66
**unknown**                | 67
backwash_interval      | 68
backwash_start_time              | 69:70
backwash_duration          | 71
**unknown**                | 72
**unknown**                | 73
startup_delay        | 74:75
**unknown**                | 76
**unknown**                | 77
**unknown**                | 78
**unknown**                | 79
**unknown**                | 80
**unknown**                | 81
**unknown**                | 82
**unknown**                | 83
**unknown**                | 84
**unknown**                | 85
**unknown**                | 86
**unknown**                | 87
**unknown**                | 88
**unknown**                | 89
**unknown**                | 90
**unknown**                | 91
pool_volume                | 92:93
max_refill_time           | 94:95     | ! duplicate
chlorine_flow_rate             | 95
**unknown**                | 96
ph_plus_flow_rate           | 97        |
**unknown**                | 98
ph_minus_flow_rate          | 99
**unknown**                | 100
flocculant_flow_rate              | 101
**unknown**                | 102
flowrate_algicid           | ??        | unknown byte
**unknown**                | 103
**unknown**                | 104
**unknown**                | 105
dosing_delay           | 106:107
**unknown**                | 108
**unknown**                | 109
**unknown**                | 110
**unknown**                | 111
**unknown**                | 112
**unknown**                | 113
**unknown**                | 114
max_ph_doses               | 115
**unknown**                | 116
**unknown**                | 118
**unknown**                | 119


[^1] means byte 0 until byte 3, in phyton [0:4]


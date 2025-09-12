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
cl_free or redox           | 16:17      |
redox                      | 18:19      | Aqua Pro only clf and redox probes
salinity                   | 20         | Aqua Salt only
electrolyzer_power         | 21         | Aqua Salt only
cl_free mV                 | 20:21      | Aqua Net if clf probe, others?
**unknown**                | 22
**unknown**                | 23
**unknown**                | 24
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
required_ph                | 52
required_cl_free_or_redox  | 53         | if clf and redox probe then required clf
required_algicide          | 54
required_water_temperature | 55
start_1_time               | 56:57
stop_1_time                | 58:59
start_2_time               | 60:61
stop_2_time                | 62:63
**unknown**                | 64
**unknown**                | 65
**unknown**                | 66
**unknown**                | 67
backwash_every_n_days      | 68
backwash_time              | 69:70
backwash_duration          | 71
**unknown**                | 72
**unknown**                | 73
delay_after_startup        | 74:75
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
max_filling_time           | 94:95     | ! duplicate
flowrate_chlor             | 95
**unknown**                | 96
flowrate_ph_plus           | 97        |
**unknown**                | 98
flowrate_ph_minus          | 99
**unknown**                | 100
flowrate_floc              | 101
**unknown**                | 102
flowrate_algicid           | ??        | unknown byte
**unknown**                | 103
**unknown**                | 104
**unknown**                | 105
delay_after_dose           | 106:107
**unknown**                | 108
**unknown**                | 109
**unknown**                | 110
**unknown**                | 111
**unknown**                | 112
**unknown**                | 113
**unknown**                | 114
**unknown**                | 115
**unknown**                | 116
**unknown**                | 118
**unknown**                | 119


[^1] means byte 0 until byte 3, in phyton [0:4]


"""v8 profile: ASIN AQUA Salt NET.

Takes over the NET layout minus the chlorine pump -- a SALT makes its
chlorine by electrolysis -- and adds what only a salt unit sends: salinity,
the electrolyser, and the third pump port, whose chemical ``fncs[6]`` names.

The salt readings come from Issue #131, where an owner labelled captures
with what the app showed at that moment, and from a second unit (Issue #131,
firmware 106) whose display was compared with one frame.  That unit's owner
ran it for days on the v1.9.x decoder patched for header 106 (Issue #169) and
timed a real algicide dose against ``outs[11]``.
"""

from __future__ import annotations

from ....models import AsekoDeviceType, AsekoProfileFlag
from ...evidence import assumed, confirmed, derived, observed
from ...features import (
    AlarmMaxDisinfectionDose,
    AlarmNoFlowToProbes,
    AlgaecideDoseTarget,
    AlgaecidePumpRunning,
    ChlorineFlowRate,
    ChlorineProductionMeasured,
    ChlorinePumpRunning,
    Configuration,
    DosingDelay,
    ElectrodePolarity,
    ElectrolysisRunning,
    FiltrationPeriod1End,
    FiltrationPeriod1Start,
    FiltrationSchedule,
    FlocculantDoseTarget,
    FlocculantPumpRunning,
    Ph,
    PhTarget,
    PoolVolume,
    Redox,
    RedoxTarget,
    Salinity,
    SerialNumber,
    StartupDelay,
    Timestamp,
    UnitClock,
    WaterTemperature,
)
from ...frames import Protocol
from ...profile import Profile
from .common import FEATURES

_NET_FEATURES = tuple(
    f for f in FEATURES if f not in (ChlorinePumpRunning, ChlorineFlowRate)
)

#: What a salt unit sends on top of the NET layout.
_SALT_ONLY = (
    Salinity,
    ChlorineProductionMeasured,
    ElectrolysisRunning,
    ElectrodePolarity,
    AlgaecidePumpRunning,
    AlgaecideDoseTarget,
    FlocculantPumpRunning,
    FlocculantDoseTarget,
    AlarmNoFlowToProbes,
    AlarmMaxDisinfectionDose,
    FiltrationPeriod1Start,
    FiltrationPeriod1End,
    FiltrationSchedule,
)

_THIRD_PUMP = observed(
    "outs[11] with the chemical from fncs[6] (10 algicide, 18 flocculant): "
    "the same unit read 10 with algicide configured and 18 after its owner "
    "switched the port on 2026-07-19 (Issue #131)"
)


SALT = Profile(
    name="v8 SALT",
    protocol=Protocol.V8,
    model=AsekoDeviceType.SALT,
    features=(*_NET_FEATURES, *_SALT_ONLY),
    flags=frozenset(
        {AsekoProfileFlag.DELAYS_IN_MINUTES, AsekoProfileFlag.ALGICIDE_OR_ACO}
    ),
    evidence={
        # the shared part is the NET layout, taken over unverified
        **dict.fromkeys(
            _NET_FEATURES,
            assumed(
                "only the header type (1xx) says SALT; the NET layout is taken "
                "over unverified"
            ),
        ),
        SerialNumber: confirmed("header token 2 on every captured frame"),
        UnitClock: confirmed(
            "ins[16] hour, ins[17] minute: 18:25 and 08:01 in captures their "
            "owner timestamped 18:22:49 and 07:58:59, so the unit ran about "
            "two minutes ahead (Issue #131).  ins[13-15] look like a date but "
            "read 24-7-9 on 15 July and 24-6-1 on 19 July, so no date is read"
        ),
        Timestamp: confirmed(
            "the same hour and minute, with the date from Home Assistant (Issue #131)"
        ),
        Configuration: derived("a probe is installed when its ains slot is not -500"),
        Ph: confirmed(
            "ains[0] / 100 = 7.09 while the unit's display read pH 7.1 in the "
            "same minute (Issue #131, firmware 106)"
        ),
        Redox: confirmed(
            "ains[6] = 542 mV, matching the unit's display in the same minute "
            "(Issue #131, firmware 106)"
        ),
        WaterTemperature: confirmed(
            "ins[0] / 10 = 29.5 C, matching the unit's display in the same "
            "minute (Issue #131, firmware 106)"
        ),
        PoolVolume: confirmed(
            "areqs[14] = 55 m3 on the unit whose owner gave its pool as 55 m3 "
            "(Issue #131); 49 matching the display on the firmware 106 unit "
            "(Issue #169)"
        ),
        StartupDelay: observed(
            "areqs[17] = 5, the 5 min the unit is set to (Issue #131); the "
            "NET v8 sends 2 for its 2 min"
        ),
        DosingDelay: observed(
            "areqs[18] = 5, the 5 min the unit is set to (Issue #131); the "
            "NET v8 sends 2 for its 2 min"
        ),
        PhTarget: confirmed(
            "areqs[0] / 10 = 7.1 while the unit's display read pH 7.1 "
            "(Issue #131, firmware 106)"
        ),
        RedoxTarget: confirmed(
            "areqs[1] * 10 = 720 mV while the unit's display read Rx 720 "
            "(Issue #131, firmware 106)"
        ),
        Salinity: confirmed(
            "ains[8] / 10 = 10.1 kg/m3 while the unit's display read 10.1 in "
            "the same minute (Issue #131, firmware 106)"
        ),
        ChlorineProductionMeasured: confirmed(
            "ains[9] = 19 and 20 g/h in captures their owner labelled 19 and "
            "20 g/h from the app, 0 with the electrolyser off (Issue #131)"
        ),
        ElectrolysisRunning: confirmed(
            "outs[14] is 0 in the captures labelled 'electrolyzer off' and 2 "
            "or 3 in those labelled on (Issue #131)"
        ),
        ElectrodePolarity: confirmed(
            "outs[14] = 2 in the captures labelled 'right' and 3 in those "
            "labelled 'left' (Issue #131)"
        ),
        AlgaecidePumpRunning: confirmed(
            "outs[11] went 1 and back to 0 exactly over the unit's algicide "
            "dose 00:03:47-00:06:24 on 2026-09-22, fncs[6] = 10 (Issue #169, "
            "firmware 106); fncs[6] routes the port as in Issue #131"
        ),
        FlocculantPumpRunning: _THIRD_PUMP,
        AlgaecideDoseTarget: confirmed(
            "areqs[4] = 5 with the port set to algicide 5 ml/m3/day, 0 after "
            "it was switched to flocculant (Issue #131); 2 matching the "
            "display and the app on the firmware 106 unit (Issue #169)"
        ),
        FlocculantDoseTarget: observed(
            "areqs[3] = 10 with the port set to flocculant 10 ml/h, 0 while "
            "it was algicide (Issue #131)"
        ),
        AlarmNoFlowToProbes: derived(
            "ins[12] bit 0x100, the flag the v8 decoder has always read; no "
            "capture shows it set"
        ),
        FiltrationPeriod1Start: confirmed(
            "reqs[5] = 8 while the app showed 'Filtration time 1' starting "
            "08:00; 0 on the firmware 106 unit (Issue #131)"
        ),
        FiltrationPeriod1End: confirmed(
            "reqs[7] = 20 while the app showed it stopping 20:00; 24 on the "
            "firmware 106 unit, whose app showed 24:00 (Issue #131)"
        ),
        FiltrationSchedule: confirmed(
            "reqs[5] to reqs[7]: 0 to 24 while the app showed 'FILTRATION "
            "NONSTOP 24H' and the display 'Timer 24dag', 8 to 20 while the "
            "app showed the timer (Issue #131); a v8 unit offers one period only"
        ),
        AlarmMaxDisinfectionDose: observed(
            "ins[12] bit 0x80 flipped 0 -> 128 while the unit showed 'Maximum "
            "disinfection dose exceeded' (Issue #151)"
        ),
    },
)

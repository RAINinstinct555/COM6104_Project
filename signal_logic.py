"""
signal_logic.py
Traffic Signal Calculation Logic Module
Reference: LLM-TrafficBrain framework (Paper 0379)
COM6104 Group Project — Traffic Intersection Simulation
"""

import re
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Time Parsing
# ---------------------------------------------------------------------------

def parse_time(time_str: str) -> Tuple[int, int]:
    """
    Parse a time string in either 12-hour or 24-hour format.

    Supported formats:
        '8:30 AM', '8:30AM', '07:30', '19:45', '7:00 PM'

    Returns:
        (hour_24, minute) as integers.

    Raises:
        ValueError if the format is unrecognised.
    """
    time_str = time_str.strip().upper()

    # 12-hour format: H:MM AM/PM  or  HH:MM AM/PM
    m12 = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$', time_str)
    if m12:
        hour = int(m12.group(1))
        minute = int(m12.group(2))
        period = m12.group(3)
        if period == 'PM' and hour != 12:
            hour += 12
        elif period == 'AM' and hour == 12:
            hour = 0
        return hour, minute

    # 24-hour format: H:MM  or  HH:MM
    m24 = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if m24:
        return int(m24.group(1)), int(m24.group(2))

    raise ValueError(
        f"Unrecognised time format: '{time_str}'. "
        "Use 12-hour (e.g. '8:30 AM') or 24-hour (e.g. '08:30') format."
    )


def is_peak_hour(hour: int, minute: int) -> bool:
    """
    Return True if the given time falls within a peak period.

    Peak periods:
        Morning peak : 07:00 – 09:30
        Evening peak : 18:00 – 20:30
    """
    total = hour * 60 + minute
    morning = (7 * 60, 9 * 60 + 30)   # 420 – 570
    evening = (18 * 60, 20 * 60 + 30)  # 1080 – 1230
    return morning[0] <= total <= morning[1] or evening[0] <= total <= evening[1]


# ---------------------------------------------------------------------------
# Base Timing
# ---------------------------------------------------------------------------

def get_base_timing(is_main: bool, is_peak: bool) -> Dict[str, int]:
    """
    Return the base {green, red} timing (seconds) for one road axis.

    Main road   | Off-peak: green=30, red=70  | Peak: green=50, red=60
    Non-main    | Off-peak: green=35, red=90  | Peak: green=45, red=80
    """
    if is_main:
        return {'green': 50, 'red': 60} if is_peak else {'green': 30, 'red': 70}
    return {'green': 45, 'red': 80} if is_peak else {'green': 35, 'red': 90}


# ---------------------------------------------------------------------------
# Queue-Based Adjustment
# ---------------------------------------------------------------------------

def apply_queue_adjustment(
    timing: Dict[str, int],
    queue: int,
    is_peak: bool,
) -> Dict[str, int]:
    """
    Adjust green/red timing according to vehicle queue length.

    Off-peak rules:
        queue > 50  →  green +30, red -10
        queue > 30  →  green +20, red unchanged
        queue > 20  →  green +10, red unchanged

    Peak rules:
        queue > 50  →  green +30, red unchanged
        queue > 30  →  green +20, red -10
        queue > 20  →  green +10, red -5
    """
    g = timing['green']
    r = timing['red']

    if is_peak:
        if queue > 50:
            g += 30
        elif queue > 30:
            g += 20
            r -= 10
        elif queue > 20:
            g += 10
            r -= 5
    else:
        if queue > 50:
            g += 30
            r -= 10
        elif queue > 30:
            g += 20
        elif queue > 20:
            g += 10

    return {'green': g, 'red': r}


# ---------------------------------------------------------------------------
# Main Calculation Function
# ---------------------------------------------------------------------------

def calculate_signal_timing(
    main_roads: List[str],
    queues: Dict[str, int],
    time_str: str,
    accident_direction: Optional[str] = None,
) -> Dict:
    """
    Calculate full traffic signal timing for a four-way intersection.

    Parameters
    ----------
    main_roads : list[str]
        Directions designated as main road, e.g. ['N', 'S'] or ['E', 'W']
        or all four ['N', 'S', 'E', 'W'].
    queues : dict
        Number of vehicles queued per direction.
        Expected keys: 'N', 'S', 'E', 'W'.
    time_str : str
        Current time in 12-hour or 24-hour format.
    accident_direction : str or None
        'N' or 'S'  → accident on N-S road
        'E' or 'W'  → accident on E-W road
        'C'         → accident at centre of intersection
        None/'none' → no accident

    Returns
    -------
    dict with keys:
        ns        : {red, green}  — N-S axis timing
        ew        : {red, green}  — E-W axis timing
        is_peak   : bool
        accident_mode : None | 'ns_road' | 'ew_road' | 'center'
        status    : str
        note      : str
    """
    hour, minute = parse_time(time_str)
    peak = is_peak_hour(hour, minute)

    main_upper = [d.upper() for d in main_roads]
    ns_main = 'N' in main_upper or 'S' in main_upper
    ew_main = 'E' in main_upper or 'W' in main_upper

    # --- Base timing ---
    ns_t = get_base_timing(ns_main, peak)
    ew_t = get_base_timing(ew_main, peak)

    # --- Queue adjustments (use the larger of the two queues per axis) ---
    ns_queue = max(queues.get('N', 0), queues.get('S', 0))
    ew_queue = max(queues.get('E', 0), queues.get('W', 0))
    ns_t = apply_queue_adjustment(ns_t, ns_queue, peak)
    ew_t = apply_queue_adjustment(ew_t, ew_queue, peak)

    # --- Accident handling ---
    acc = (accident_direction or 'none').strip().upper()
    accident_mode = None
    note = ''

    if acc not in ('NONE', ''):

        if acc == 'C':
            # All signals RED for 15 s; green = NULL during photo/removal phase.
            # After clearance: main road +10 s, non-main +5 s.
            ns_after = ns_t['green'] + (10 if ns_main else 5)
            ew_after = ew_t['green'] + (10 if ew_main else 5)
            return {
                'ns': {
                    'red': 15,
                    'green': 'NULL',
                    'green_after_clearance': ns_after,
                },
                'ew': {
                    'red': 15,
                    'green': 'NULL',
                    'green_after_clearance': ew_after,
                },
                'is_peak': peak,
                'accident_mode': 'center',
                'status': '⚠  ACCIDENT — ALL SIGNALS RED (15 s)',
                'note': (
                    'Centre blockage: all signals set to RED for 15 s '
                    'to allow accident vehicles to be photographed and moved. '
                    f'After clearance → N-S green: {ns_after} s, '
                    f'E-W green: {ew_after} s. '
                    'Traffic police may press ESC to restore normal operation.'
                ),
            }

        elif acc in ('N', 'S'):
            # N-S road has accident:
            #   E-W (non-accident) green +15 s
            #   N-S (accident)     green +5 s (off-peak) / +10 s (peak)
            ew_t['green'] += 15
            ext = 10 if peak else 5
            ns_t['green'] += ext
            accident_mode = 'ns_road'
            note = (
                f'Accident on N-S road. '
                f'E-W green extended +15 s. '
                f'N-S green extended +{ext} s ({"peak" if peak else "off-peak"}). '
                'Traffic police may press ESC to restore normal operation.'
            )

        elif acc in ('E', 'W'):
            # E-W road has accident:
            #   N-S (non-accident) green +15 s
            #   E-W (accident)     green +5 s (off-peak) / +10 s (peak)
            ns_t['green'] += 15
            ext = 10 if peak else 5
            ew_t['green'] += ext
            accident_mode = 'ew_road'
            note = (
                f'Accident on E-W road. '
                f'N-S green extended +15 s. '
                f'E-W green extended +{ext} s ({"peak" if peak else "off-peak"}). '
                'Traffic police may press ESC to restore normal operation.'
            )

    return {
        'ns': {'red': ns_t['red'], 'green': ns_t['green']},
        'ew': {'red': ew_t['red'], 'green': ew_t['green']},
        'is_peak': peak,
        'accident_mode': accident_mode,
        'status': 'NORMAL' if accident_mode is None else '⚠  ACCIDENT MODE',
        'note': note,
    }

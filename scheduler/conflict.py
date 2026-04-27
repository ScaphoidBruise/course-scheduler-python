def is_half_semester(session):
    if not session or not str(session).strip():
        return False
    s = str(session).upper()
    return "W1" in s or "W2" in s


def parse_days(days_str):
    if not days_str or not days_str.strip():
        return set()
    result = set()
    for char in days_str.strip().upper():
        if char in "MTWRF":
            result.add(char)
    return result


def parse_time(time_str):
    if not time_str or not time_str.strip():
        return None
    text = time_str.strip().upper()

    is_pm = "PM" in text
    is_am = "AM" in text
    text = text.replace("PM", "").replace("AM", "").strip()

    parts = text.split(":")
    if len(parts) != 2:
        return None

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None

    if is_pm and hours != 12:
        hours += 12
    if is_am and hours == 12:
        hours = 0

    return hours * 60 + minutes


def sections_conflict(section_a, section_b):
    """Online/async sections (no days or no times) never conflict."""
    days_a = parse_days(section_a.get("days", ""))
    days_b = parse_days(section_b.get("days", ""))

    if not days_a or not days_b:
        return False

    if not (days_a & days_b):
        return False

    # First and second 8-week sessions do not overlap (matches schedule.js).
    if is_half_semester(section_a.get("session")) and is_half_semester(
        section_b.get("session")
    ):
        sa = str(section_a.get("session", "")).upper()
        sb = str(section_b.get("session", "")).upper()
        a_w1 = "W1" in sa
        b_w1 = "W1" in sb
        if a_w1 != b_w1:
            return False

    start_a = parse_time(section_a.get("start_time", ""))
    end_a = parse_time(section_a.get("end_time", ""))
    start_b = parse_time(section_b.get("start_time", ""))
    end_b = parse_time(section_b.get("end_time", ""))

    if start_a is None or end_a is None or start_b is None or end_b is None:
        return False

    return start_a < end_b and start_b < end_a


def find_conflicts(new_section, schedule):
    return [s for s in schedule if sections_conflict(new_section, s)]

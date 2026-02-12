import re


def parse_eft_fit(eft_text):
    """
    Parse an EFT (EVE Fitting Tool) format fit.

    EFT format example:
    [Raven, PvE Raven]
    Ballistic Control System II
    Ballistic Control System II
    Cruise Missile Launcher II, Scourge Fury Cruise Missile
    [Empty High slot]

    Args:
        eft_text: The EFT format text

    Returns:
        dict: {
            'hull': str,           # Ship hull name
            'fit_name': str,       # Fit name
            'modules': list[str],  # List of module names (no ammo)
            'all_items': list[str] # Hull + all modules
        }
    """
    lines = eft_text.strip().split('\n')

    if not lines:
        return None

    # Parse header line: [Hull, Fit Name] or [Hull]
    header = lines[0].strip()
    header_match = re.match(r'\[([^\],]+)(?:,\s*([^\]]+))?\]', header)

    if not header_match:
        return None

    hull = header_match.group(1).strip()
    fit_name = header_match.group(2).strip() if header_match.group(2) else hull

    modules = []

    # Parse module lines
    for line in lines[1:]:
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip empty slot markers
        if line.startswith('[Empty'):
            continue

        # Remove ammo/charge (everything after the first comma)
        module = line.split(',')[0].strip()

        if module:
            modules.append(module)

    # Return parsed fit
    return {
        'hull': hull,
        'fit_name': fit_name,
        'modules': modules,
        'all_items': [hull] + modules
    }


def extract_item_names(eft_text):
    """
    Extract all item names (hull + modules) from an EFT fit.

    Args:
        eft_text: The EFT format text

    Returns:
        list[str]: List of all item names
    """
    parsed = parse_eft_fit(eft_text)
    if parsed:
        return parsed['all_items']
    return []


def is_bare_hull_query(text):
    """
    Check if the text is just a bare hull query like "[Raven]".

    Args:
        text: Input text to check

    Returns:
        str or None: Hull name if it's a bare hull query, None otherwise
    """
    text = text.strip()
    match = re.match(r'^\[([^\]]+)\]$', text)
    if match:
        return match.group(1).strip()
    return None

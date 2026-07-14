"""Current 0625 topic taxonomy and deterministic pilot classification rules."""

from __future__ import annotations

import re


DOMAINS = {
    "1": "Motion, forces and energy",
    "2": "Thermal physics",
    "3": "Waves",
    "4": "Electricity and magnetism",
    "5": "Nuclear physics",
    "6": "Space physics",
}


TOPICS = [
    ("1.1", "Physical quantities and measurement techniques"),
    ("1.2", "Motion"),
    ("1.3", "Mass and weight"),
    ("1.4", "Density"),
    ("1.5.1", "Effects of forces"),
    ("1.5.2", "Turning effect of forces"),
    ("1.5.3", "Centre of gravity"),
    ("1.6", "Momentum"),
    ("1.7.1", "Energy"),
    ("1.7.2", "Work"),
    ("1.7.3", "Energy resources"),
    ("1.7.4", "Power"),
    ("1.8", "Pressure"),
    ("2.1.1", "States of matter"),
    ("2.1.2", "Particle model"),
    ("2.1.3", "Gases and the absolute scale of temperature"),
    ("2.2.1", "Thermal expansion of solids, liquids and gases"),
    ("2.2.2", "Specific heat capacity"),
    ("2.2.3", "Melting, boiling and evaporation"),
    ("2.3.1", "Conduction"),
    ("2.3.2", "Convection"),
    ("2.3.3", "Radiation"),
    ("2.3.4", "Consequences of thermal energy transfer"),
    ("3.1", "General properties of waves"),
    ("3.2.1", "Reflection of light"),
    ("3.2.2", "Refraction of light"),
    ("3.2.3", "Thin lenses"),
    ("3.2.4", "Dispersion of light"),
    ("3.3", "Electromagnetic spectrum"),
    ("3.4", "Sound"),
    ("4.1", "Simple phenomena of magnetism"),
    ("4.2.1", "Electric charge"),
    ("4.2.2", "Electric current"),
    ("4.2.3", "Electromotive force and potential difference"),
    ("4.2.4", "Resistance"),
    ("4.2.5", "Electrical energy and electrical power"),
    ("4.3.1", "Circuit diagrams and circuit components"),
    ("4.3.2", "Series and parallel circuits"),
    ("4.3.3", "Action and use of circuit components"),
    ("4.4", "Electrical safety"),
    ("4.5.1", "Electromagnetic induction"),
    ("4.5.2", "The a.c. generator"),
    ("4.5.3", "Magnetic effect of a current"),
    ("4.5.4", "Force on a current-carrying conductor"),
    ("4.5.5", "The d.c. motor"),
    ("4.5.6", "The transformer"),
    ("5.1.1", "The atom"),
    ("5.1.2", "The nucleus"),
    ("5.2.1", "Detection of radioactivity"),
    ("5.2.2", "The three types of nuclear emission"),
    ("5.2.3", "Radioactive decay"),
    ("5.2.4", "Half-life"),
    ("5.2.5", "Safety precautions"),
    ("6.1.1", "The Earth"),
    ("6.1.2", "The Solar System"),
    ("6.2.1", "The Sun as a star"),
    ("6.2.2", "Stars"),
    ("6.2.3", "The Universe"),
]


KEYWORDS = {
    "1.1": [r"measuring cylinder", r"ruler", r"timer", r"oscillation", r"pendulum", r"measurement", r"scalar", r"vector quantit", r"two scalar quantities.*two vector quantities"],
    "1.2": [r"speed.?time", r"distance.?time", r"speed", r"velocity", r"acceleration", r"deceler", r"terminal velocity", r"distance travelled"],
    "1.3": [r"mass and weight", r"gravitational field strength", r"weight", r"balance"],
    "1.4": [r"density", r"mass.*volume", r"liquid.*layer"],
    "1.5.1": [r"resultant force", r"drag force", r"load.?extension", r"spring", r"hooke", r"force.*acceler"],
    "1.5.2": [r"moment", r"pivot", r"beam", r"see.?saw", r"turning effect"],
    "1.5.3": [r"centre of gravity", r"center of gravity", r"stability", r"topple"],
    "1.6": [r"momentum", r"impulse", r"collision", r"force.*time"],
    "1.7.1": [r"energy store", r"kinetic energy", r"gravitational potential", r"conservation of energy", r"sankey", r"efficien"],
    "1.7.2": [r"work done", r"force.*distance"],
    "1.7.3": [r"renewable", r"energy resource", r"source of energy.*resource", r"fossil", r"solar cell", r"hydroelectric", r"wind turbine", r"tidal", r"wave power"],
    "1.7.4": [r"power", r"energy.*time", r"work.*time"],
    "1.8": [r"pressure", r"depth.*liquid", r"force.*area"],
    "2.1.1": [r"change of state", r"solid.*liquid.*gas", r"condens", r"state of matter"],
    "2.1.2": [r"brownian", r"particle.*random", r"particle model", r"particles.*collid"],
    "2.1.3": [r"absolute.*temperature", r"kelvin", r"gas pressure", r"volume.*gas", r"pressure.*temperature"],
    "2.2.1": [r"thermal expansion", r"bimetal", r"expand.*heat"],
    "2.2.2": [r"specific heat", r"temperature rise", r"thermal capacity"],
    "2.2.3": [r"evaporation", r"boiling", r"melting", r"latent", r"cooling.*evapor"],
    "2.3.1": [r"conduction", r"thermal conductor", r"insulator.*thermal", r"free electron.*thermal"],
    "2.3.2": [r"convection", r"convection current", r"hot air rises"],
    "2.3.3": [r"infrared radiation", r"thermal radiation", r"black.*surface", r"emitter", r"absorber"],
    "2.3.4": [r"vacuum flask", r"insulation", r"rate.*thermal", r"greenhouse", r"cup.*coffee", r"covered with a lid"],
    "3.1": [r"wave speed", r"wavelength", r"frequency", r"amplitude", r"transverse", r"longitudinal", r"diffraction"],
    "3.2.1": [r"plane mirror", r"reflection", r"angle of incidence.*reflection"],
    "3.2.2": [r"refraction", r"critical angle", r"total internal", r"refractive index"],
    "3.2.3": [r"converging lens", r"thin lens", r"focal", r"real image", r"virtual image", r"magnif"],
    "3.2.4": [r"dispersion", r"spectrum.*colour", r"prism", r"monochromatic"],
    "3.3": [r"electromagnetic spectrum", r"microwave", r"infrared", r"ultraviolet", r"x.?ray", r"gamma ray", r"radio wave"],
    "3.4": [r"sound", r"echo", r"pitch", r"loudness", r"ultrasound", r"compression", r"rarefaction"],
    "4.1": [r"permanent magnet", r"magnetic field", r"magnetis", r"north pole", r"south pole"],
    "4.2.1": [r"electric charge", r"electrostatic", r"charged.*rod", r"positive ion", r"negative ion", r"point charge", r"electric field pattern"],
    "4.2.2": [r"electric current", r"ammeter", r"charge.*second", r"electron flow"],
    "4.2.3": [r"potential difference", r"electromotive", r"voltmeter", r"e\.m\.f", r"p\.d\."],
    "4.2.4": [r"resistance", r"ohm", r"current.?voltage", r"v.?i graph"],
    "4.2.5": [r"electrical power", r"electrical energy", r"kilowatt", r"kwh", r"\bkw\b", r"transfers energy at a rate"],
    "4.3.1": [r"circuit symbol", r"circuit diagram", r"which circuit", r"cell.*resistor", r"lamp.*circuit"],
    "4.3.2": [r"series circuit", r"parallel circuit", r"connected in parallel", r"connected in series", r"resistors in parallel", r"resistors in series"],
    "4.3.3": [r"thermistor", r"light.?dependent", r"potential divider", r"diode", r"variable resistor", r"switches on a lamp.*environment"],
    "4.4": [r"fuse", r"earth wire", r"live wire", r"electrical safety", r"circuit breaker", r"double.?insulated"],
    "4.5.1": [r"induc", r"wire is moved.*magnet", r"magnet.*coil", r"galvanometer"],
    "4.5.2": [r"a\.c\. generator", r"alternating.*generator", r"slip ring"],
    "4.5.3": [r"solenoid", r"field around.*wire", r"magnetic effect.*current"],
    "4.5.4": [r"current.?carrying conductor", r"force.*wire.*magnetic", r"fleming.*left"],
    "4.5.5": [r"d\.c\. motor", r"split.?ring", r"motor effect"],
    "4.5.6": [r"transformer", r"primary coil", r"secondary coil", r"turns ratio", r"step.?down", r"step.?up"],
    "5.1.1": [r"structure of an atom", r"electron.*nucleus", r"atom.*ion"],
    "5.1.2": [r"proton", r"neutron", r"isotope", r"nucleon", r"uranium nucleus", r"fission", r"fusion"],
    "5.2.1": [r"background radiation", r"detector", r"count rate", r"geiger"],
    "5.2.2": [r"alpha", r"beta", r"gamma", r"ionising", r"penetrat"],
    "5.2.3": [r"radioactive decay", r"unstable nucleus", r"spontaneous", r"random process", r"decays by emitting"],
    "5.2.4": [r"half.?life", r"count rate.*time", r"activity.*time"],
    "5.2.5": [r"exposure", r"radioactive.*safety", r"lead.*shield", r"source.*tongs"],
    "6.1.1": [r"earth.*axis", r"rotation of the earth", r"day and night", r"moon.*earth"],
    "6.1.2": [r"solar system", r"planet", r"orbit", r"gravitational field.*distance", r"orbital speed", r"orbital period"],
    "6.2.1": [r"sun.*star", r"sun.*fusion", r"energy.*sun"],
    "6.2.2": [r"life cycle.*star", r"red giant", r"supernova", r"white dwarf", r"black hole", r"protostar"],
    "6.2.3": [r"galax", r"redshift", r"hubble", r"universe", r"moving away.*earth"],
}


POSITIONAL_DOMAINS = (
    (range(1, 14), "1"),
    (range(14, 18), "2"),
    (range(18, 26), "3"),
    (range(26, 34), "4"),
    (range(34, 39), "5"),
    (range(39, 41), "6"),
)


def fallback_domain(question_number: int) -> str:
    for numbers, domain in POSITIONAL_DOMAINS:
        if question_number in numbers:
            return domain
    return ""


def classify_topic(text: str, question_number: int, use_position_hint: bool = True) -> dict:
    normalized = " ".join(text.lower().split())
    domain_hint = fallback_domain(question_number) if use_position_hint else ""
    scores: dict[str, float] = {}
    matches: dict[str, list[str]] = {}
    for ref, _title in TOPICS:
        score = 0.0
        found = []
        for pattern in KEYWORDS.get(ref, []):
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                found.append(pattern)
                score += 1.0 + min(1.0, len(pattern) / 30)
        if domain_hint and ref.split(".")[0] == domain_hint:
            score += 0.35
        if score > 0.35:
            scores[ref] = score
            matches[ref] = found

    candidates = [(score, ref) for ref, score in scores.items()]
    if candidates:
        best_score, best_ref = max(candidates)
        keyword_hits = len(matches.get(best_ref, []))
        confidence = min(0.97, 0.48 + keyword_hits * 0.16 + (0.08 if best_ref.startswith(domain_hint + ".") else 0))
        method = "keyword+position" if domain_hint and best_ref.startswith(domain_hint + ".") else "keyword"
    else:
        if domain_hint:
            best_ref = next(ref for ref, _ in TOPICS if ref.startswith(domain_hint + "."))
            confidence = 0.28
            method = "position-only"
        else:
            best_ref = "1.1"
            confidence = 0.12
            method = "unclassified-fallback"

    return {
        "topic_ref": best_ref,
        "domain_ref": best_ref.split(".")[0],
        "confidence": round(confidence, 2),
        "classification_method": method,
        "matched_patterns": matches.get(best_ref, []),
    }


def classify_question_metadata(text: str) -> dict:
    lower = " ".join(text.lower().split())
    has_visual = any(word in lower for word in ("diagram", "graph", "table", "circuit", "shown", "figure"))
    has_numbers = len(re.findall(r"(?<![a-z])\d+(?:\.\d+)?", lower)) >= 2
    is_practical = any(word in lower for word in ("student", "apparatus", "experiment", "measure", "investigation"))
    if "explain" in lower:
        command = "explain"
    elif "calculate" in lower or (lower.startswith("what is") and has_numbers):
        command = "calculate"
    elif "determine" in lower:
        command = "determine"
    elif lower.startswith("which"):
        command = "identify"
    elif lower.startswith("what"):
        command = "give"
    else:
        command = "interpret"

    if is_practical:
        qtype = "practical-context"
    elif "graph" in lower:
        qtype = "graph"
    elif has_numbers:
        qtype = "calculation"
    elif has_visual:
        qtype = "visual-concept"
    else:
        qtype = "concept"

    ao = "AO2" if qtype in {"graph", "calculation", "practical-context"} else "AO1"
    complexity = sum((has_visual, has_numbers, "not correct" in lower, len(text) > 700))
    difficulty = "high" if complexity >= 3 else "medium" if complexity >= 1 else "foundation"
    return {
        "has_visual": has_visual,
        "question_type": qtype,
        "command_word": command,
        "ao": ao,
        "difficulty": difficulty,
    }


TOPIC_TITLE = dict(TOPICS)

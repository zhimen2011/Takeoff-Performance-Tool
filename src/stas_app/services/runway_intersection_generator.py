"""Generate AIRPORT2 intersection runway blocks from #INT records."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from collections.abc import Sequence

from stas_app.models.runway_database import AirportBlock, RunwayMasterDatabase


EOSID_TEXT_SEPARATOR = " " * 21
MAX_RUNWAY_ID_LENGTH = 8
DATE_SUFFIX_PATTERN = re.compile(r"\s*\d{2}\s+[A-Z]{3}\s+\d{4}\s*$")
INT_LINE_PATTERN = re.compile(r"^#INT\s+'([^']+)'\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)")
RUNWAY_ID_PATTERN = re.compile(r"'([^']+)'")


@dataclass(frozen=True)
class RunwayRecordBlock:
    """One runway record inside an airport block."""

    record_type: str
    runway_id: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class IntersectionRecord:
    """Parsed #INT data used to build a shortened runway."""

    raw_line: str
    name: str
    offset: Decimal
    lineup: str


def generate_intersections_for_database(
    database: RunwayMasterDatabase,
    text_separator: str = EOSID_TEXT_SEPARATOR,
) -> RunwayMasterDatabase:
    """Return a database whose AIRPORT2 blocks include generated intersection runways."""

    airports = {
        icao: generate_intersections_for_airport_block(
            block,
            text_separator=text_separator,
        )
        for icao, block in database.airports.items()
    }
    return RunwayMasterDatabase(
        preamble_lines=database.preamble_lines,
        airports=airports,
        airport_order=database.airport_order,
        profile=database.profile,
    )


def generate_intersections_for_airport_block(
    block: AirportBlock,
    text_separator: str = EOSID_TEXT_SEPARATOR,
) -> AirportBlock:
    """Clean AIRPORT2 runway text and append generated intersection runway blocks."""

    if block.record_type != "AIRPORT2":
        return block

    normalized_lines = _normalize_airport_block_lines(block.raw_lines, text_separator)
    _validate_existing_intersection_runway_ids(block.icao, normalized_lines)
    existing_runway_ids = set(_parse_runway_ids_from_lines(normalized_lines))
    generated_lines: list[str] = []

    for record in _iter_runway_record_blocks(normalized_lines):
        if record.record_type != "RWYU" or _looks_like_intersection_runway(record.runway_id):
            continue

        for int_line in _intersection_lines(record.lines):
            intersection = _parse_intersection_record(int_line)
            for intersection_name in split_intersection_names(intersection.name):
                generated_id = build_intersection_runway_id(record.runway_id, intersection_name)
                _validate_intersection_runway_id(
                    generated_id,
                    airport_icao=block.icao,
                    main_runway_id=record.runway_id,
                    int_line=int_line,
                )
                if generated_id in existing_runway_ids:
                    continue

                generated_block = generate_runway_intersection_blocks(
                    main_rwy_block=record.lines,
                    int_line=int_line,
                    airport_format=block.record_type,
                    text_separator=text_separator,
                    intersection_name=intersection_name,
                    airport_icao=block.icao,
                )
                generated_lines.extend(generated_block)
                existing_runway_ids.add(generated_id)

    if not generated_lines and normalized_lines == block.raw_lines:
        return block

    raw_lines = tuple(normalized_lines) + tuple(generated_lines)
    return AirportBlock(
        icao=block.icao,
        record_type=block.record_type,
        raw_lines=raw_lines,
        runway_ids=_parse_runway_ids_from_lines(raw_lines),
    )


def generate_runway_intersection_blocks(
    main_rwy_block: str | Sequence[str],
    int_line: str,
    airport_format: str,
    text_separator: str = EOSID_TEXT_SEPARATOR,
    intersection_name: str | None = None,
    airport_icao: str = "",
) -> list[str]:
    """Build one generated intersection runway block as STAS runway-data lines."""

    lines = _normalize_lines(main_rwy_block)
    runway_record = _extract_runway_record(lines)
    intersection = _parse_intersection_record(int_line)
    name = intersection_name if intersection_name is not None else intersection.name

    new_runway_id = build_intersection_runway_id(
        runway_record.runway_id,
        name,
        airport_format=airport_format,
    )
    _validate_intersection_runway_id(
        new_runway_id,
        airport_icao=airport_icao,
        main_runway_id=runway_record.runway_id,
        int_line=int_line,
    )
    rwyu_line = _build_rwyu_line(runway_record.lines[0], intersection.lineup)
    runway_line = _build_runway_line(runway_record.lines[1], new_runway_id, intersection.offset)
    obstacle_lines = _obstacle_lines(runway_record.lines)
    text_lines = _build_text_lines(runway_record.lines, text_separator)

    return [rwyu_line, runway_line, *obstacle_lines, *text_lines, intersection.raw_line]


def build_intersection_runway_id(
    runway_id: str,
    intersection_name: str,
    airport_format: str = "AIRPORT2",
) -> str:
    """Return the generated runway id for one intersection and main runway."""

    name = intersection_name.strip()
    generated = f"{name}-{runway_id.strip()}"
    if len(generated) > MAX_RUNWAY_ID_LENGTH:
        generated = generated.replace(" ", "")
    return generated


def split_intersection_names(intersection_name: str) -> tuple[str, ...]:
    """Split a #INT name into individual intersection labels."""

    parts = [part.strip() for part in re.split(r"[-/]", intersection_name) if part.strip()]
    if not parts:
        parts = [intersection_name.strip()]

    names: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part and part not in seen:
            names.append(part)
            seen.add(part)
    return tuple(names)


def _normalize_lines(main_rwy_block: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(main_rwy_block, str):
        return tuple(line.rstrip("\r\n") for line in main_rwy_block.splitlines() if line.strip())
    return tuple(str(line).rstrip("\r\n") for line in main_rwy_block if str(line).strip())


def _normalize_airport_block_lines(lines: tuple[str, ...], text_separator: str) -> tuple[str, ...]:
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip().startswith("RWY"):
            normalized.append(line)
            index += 1
            continue

        end = index + 1
        while end < len(lines) and not lines[end].strip().startswith("RWY"):
            end += 1

        normalized.extend(_normalize_runway_record_lines(tuple(lines[index:end]), text_separator))
        index = end

    return tuple(normalized)


def _normalize_runway_record_lines(lines: tuple[str, ...], text_separator: str) -> tuple[str, ...]:
    text_line_index = _text_line_index(lines)
    if text_line_index is None:
        return _expand_compound_intersection_runway_record(lines)

    normalized = list(lines[:text_line_index])
    normalized.extend(_build_text_lines(lines, text_separator))

    index = text_line_index + 1
    while index < len(lines) and lines[index].strip().startswith("H "):
        index += 1

    normalized.extend(lines[index:])
    return _expand_compound_intersection_runway_record(tuple(normalized))


def _expand_compound_intersection_runway_record(lines: tuple[str, ...]) -> tuple[str, ...]:
    try:
        record = _extract_runway_record(lines)
    except ValueError:
        return lines

    expanded_ids = _split_existing_intersection_runway_ids(record.runway_id)
    if expanded_ids == (record.runway_id,):
        return lines

    expanded_lines: list[str] = []
    for runway_id in expanded_ids:
        record_lines = list(lines)
        record_lines[1] = _replace_runway_id(record_lines[1], runway_id)
        expanded_lines.extend(record_lines)
    return tuple(expanded_lines)


def _split_existing_intersection_runway_ids(runway_id: str) -> tuple[str, ...]:
    if "-" not in runway_id:
        return (runway_id,)

    intersection_part, main_runway_id = runway_id.rsplit("-", maxsplit=1)
    intersection_names = split_intersection_names(intersection_part)
    if len(intersection_names) <= 1:
        return (runway_id,)

    expanded_ids: list[str] = []
    seen: set[str] = set()
    for intersection_name in intersection_names:
        expanded_id = build_intersection_runway_id(main_runway_id, intersection_name)
        if expanded_id not in seen:
            expanded_ids.append(expanded_id)
            seen.add(expanded_id)
    return tuple(expanded_ids)


def _replace_runway_id(runway_line: str, new_runway_id: str) -> str:
    return RUNWAY_ID_PATTERN.sub(lambda _match: f"'{new_runway_id}'", runway_line, count=1)


def _iter_runway_record_blocks(lines: tuple[str, ...]) -> tuple[RunwayRecordBlock, ...]:
    records: list[RunwayRecordBlock] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("RWY"):
            index += 1
            continue

        end = index + 1
        while end < len(lines) and not lines[end].strip().startswith("RWY"):
            end += 1

        record_lines = tuple(lines[index:end])
        try:
            records.append(_extract_runway_record(record_lines))
        except ValueError:
            pass
        index = end

    return tuple(records)


def _extract_runway_record(lines: tuple[str, ...]) -> RunwayRecordBlock:
    if len(lines) < 2:
        raise ValueError("Runway block must contain a runway type line and a runway data line")

    record_type = lines[0].split()[0]
    runway_id = _parse_runway_id(lines[1])
    if not runway_id:
        raise ValueError(f"Runway data line does not contain a runway id: {lines[1]}")

    return RunwayRecordBlock(record_type=record_type, runway_id=runway_id, lines=lines)


def _parse_runway_id(line: str) -> str:
    match = RUNWAY_ID_PATTERN.search(line)
    return match.group(1).strip() if match else ""


def _intersection_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(line for line in lines if line.strip().startswith("#INT"))


def _parse_intersection_record(int_line: str) -> IntersectionRecord:
    stripped = int_line.strip()
    match = INT_LINE_PATTERN.match(stripped)
    if not match:
        raise ValueError(f"Invalid #INT line: {int_line}")

    try:
        offset = Decimal(match.group(2))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid #INT distance: {int_line}") from exc

    return IntersectionRecord(
        raw_line=int_line,
        name=match.group(1).strip(),
        offset=offset,
        lineup=match.group(3).strip(),
    )


def _build_rwyu_line(rwyu_line: str, lineup: str) -> str:
    fields = rwyu_line.split()
    if len(fields) < 2:
        raise ValueError(f"Invalid RWYU line: {rwyu_line}")

    fields[1] = lineup
    return " ".join(fields)


def _build_runway_line(runway_line: str, new_runway_id: str, offset: Decimal) -> str:
    fields = _runway_numeric_fields(runway_line)
    if len(fields) < 5:
        raise ValueError(f"Runway data line does not contain distance fields: {runway_line}")

    for field_index in (1, 2, 3):
        fields[field_index] = _format_decimal(_decimal_value(fields[field_index], runway_line) - offset)

    if any(_decimal_value(fields[field_index], runway_line) < 0 for field_index in (1, 2, 3)):
        raise ValueError(f"Intersection offset is longer than available runway distance: {runway_line}")

    return f"'{new_runway_id}'  " + "  ".join(fields)


def _runway_numeric_fields(runway_line: str) -> list[str]:
    match = RUNWAY_ID_PATTERN.search(runway_line)
    if not match:
        raise ValueError(f"Runway data line does not contain a runway id: {runway_line}")
    return runway_line[match.end() :].split()


def _decimal_value(value: str, source_line: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric field {value!r} in runway line: {source_line}") from exc


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def _validate_intersection_runway_id(
    runway_id: str,
    airport_icao: str = "",
    main_runway_id: str = "",
    int_line: str = "",
) -> None:
    if len(runway_id) <= MAX_RUNWAY_ID_LENGTH:
        return

    details = [
        f"Intersection runway id exceeds STAS {MAX_RUNWAY_ID_LENGTH}-character limit",
        f"generated={runway_id}",
        f"length={len(runway_id)}",
        f"max={MAX_RUNWAY_ID_LENGTH}",
    ]
    if airport_icao:
        details.append(f"airport={airport_icao}")
    if main_runway_id:
        details.append(f"main_runway={main_runway_id}")
    if int_line:
        details.append(f"int_line={int_line.strip()}")
    details.append("Review the runway data and import it again.")
    raise ValueError("; ".join(details))


def _validate_existing_intersection_runway_ids(airport_icao: str, lines: tuple[str, ...]) -> None:
    for record in _iter_runway_record_blocks(lines):
        if not _looks_like_intersection_runway(record.runway_id):
            continue

        _validate_intersection_runway_id(
            record.runway_id,
            airport_icao=airport_icao,
            main_runway_id=_main_runway_id_from_intersection_id(record.runway_id),
        )


def _main_runway_id_from_intersection_id(runway_id: str) -> str:
    if "-" in runway_id:
        return runway_id.rsplit("-", maxsplit=1)[-1].strip()
    if "/" in runway_id:
        return runway_id.rsplit("/", maxsplit=1)[-1].strip()
    return ""


def _obstacle_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    if len(lines) < 2:
        return ()

    fields = _runway_numeric_fields(lines[1])
    obstacle_count = 0
    if len(fields) >= 9:
        try:
            obstacle_count = max(0, int(fields[8]))
        except ValueError:
            obstacle_count = 0

    return tuple(lines[2 : 2 + obstacle_count])


def _build_text_lines(lines: tuple[str, ...], text_separator: str) -> tuple[str, ...]:
    text_line_index = _text_line_index(lines)
    if text_line_index is None:
        return ()

    base_text = _clean_base_text(lines[text_line_index])
    eosid_lines = _continuous_eosid_lines(lines, text_line_index + 1)
    eosid_text = " ".join(line.strip()[2:].strip() for line in eosid_lines)
    if base_text and eosid_text:
        return (f"'{base_text}{text_separator}{eosid_text}'",)

    if base_text:
        return (f"'{base_text}'",)

    return ()


def _text_line_index(lines: tuple[str, ...]) -> int | None:
    for index, line in enumerate(lines[2:], start=2):
        stripped = line.strip()
        if stripped.startswith("'") and "'" in stripped[1:]:
            return index
    return None


def _clean_base_text(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        text = stripped[1:-1]
    else:
        match = RUNWAY_ID_PATTERN.search(stripped)
        text = match.group(1) if match else stripped
    return DATE_SUFFIX_PATTERN.sub("", text).rstrip()


def _continuous_eosid_lines(lines: tuple[str, ...], start_index: int) -> tuple[str, ...]:
    eosid_lines: list[str] = []
    index = start_index
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped.startswith("H "):
            break
        eosid_lines.append(stripped)
        index += 1
    return tuple(eosid_lines)


def _parse_runway_ids_from_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    runway_ids: list[str] = []
    seen: set[str] = set()
    for index, line in enumerate(lines[:-1]):
        if not line.strip().startswith("RWY"):
            continue

        runway_id = _parse_runway_id(lines[index + 1])
        if runway_id and runway_id not in seen:
            runway_ids.append(runway_id)
            seen.add(runway_id)
    return tuple(runway_ids)


def _looks_like_intersection_runway(runway_id: str) -> bool:
    return "-" in runway_id or "/" in runway_id

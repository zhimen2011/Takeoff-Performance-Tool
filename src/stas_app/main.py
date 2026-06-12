"""Minimal command-line entry point for local STAS integration checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from stas_app.models.request import PerformanceRequest
from stas_app.services.app_factory import create_performance_service
from stas_app.storage.config_repository import ConfigError, load_app_config


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "calculate":
        return _run_calculation(args)

    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="STAS local integration helper")
    subparsers = parser.add_subparsers(dest="command")

    calculate = subparsers.add_parser("calculate", help="run one performance calculation")
    calculate.add_argument("--config", default="config/app.local.toml", help="application TOML config path")
    calculate.add_argument("--base-dir", default=".", help="base directory for relative config paths")
    calculate.add_argument("--aircraft", required=True, help="aircraft code, for example 738 or 777F")
    calculate.add_argument("--airport", required=True, help="airport ICAO code")
    calculate.add_argument("--runway", action="append", default=[], help="runway identifier; can be repeated")
    calculate.add_argument("--scenario-id", default="", help="optional scenario identifier for output folders")
    calculate.add_argument("--runway-condition", default="DRY", help="runway condition, for example DRY, WET, or SLUSH")
    calculate.add_argument("--contamination-depth", default="", help="contamination depth in the template depth unit")
    calculate.add_argument("--bleed", default="", help="air conditioning/bleed selection, for example ON, AUTO, or OFF")
    calculate.add_argument("--anti-icing", default="0", help="anti-icing selection, for example OFF, ENG, or ENG_WING")
    calculate.add_argument("--derate", default="", help="direct derate value written to POPT(25)")
    calculate.add_argument("--temperature-range", default="", help="temperature range override")
    calculate.add_argument("--wind-range", default="", help="wind range override")
    calculate.add_argument("--qnh", default="", help="QNH reference override")
    calculate.add_argument("--thrust-option", default=None, help="aircraft thrust option label")
    calculate.add_argument("--manual-report-template", default="", help="manual takeoff report template id")
    calculate.add_argument("--report-date", default="", help="optional report DATED override, for example 19-MAY-2026")
    return parser


def _run_calculation(args: argparse.Namespace) -> int:
    try:
        config = load_app_config(args.config, base_dir=args.base_dir)
        service = create_performance_service(config)
        result = service.calculate(_build_request(args))
    except (ConfigError, FileNotFoundError, NotADirectoryError, OSError, ValueError) as exc:
        print(f"配置或启动失败：{exc}", file=sys.stderr)
        return 2

    if not result.succeeded:
        print(f"计算失败：{result.error_message}", file=sys.stderr)
        if result.stas_run:
            _print_stas_paths(result.stas_run.run_dir, result.stas_run.raw_output_path)
        return 1

    print("计算完成")
    if result.stas_run:
        _print_stas_paths(result.stas_run.run_dir, result.stas_run.raw_output_path)
    if result.word_report and result.word_report.succeeded and result.word_report.output_path:
        print(f"临时起飞分析 Word：{result.word_report.output_path}")
    if result.pdf_report and result.pdf_report.succeeded and result.pdf_report.output_path:
        print(f"临时起飞分析 PDF：{result.pdf_report.output_path}")
    if result.manual_word_report and result.manual_word_report.succeeded and result.manual_word_report.output_path:
        print(f"手册起飞分析 Word：{result.manual_word_report.output_path}")
    if result.manual_pdf_report and result.manual_pdf_report.succeeded and result.manual_pdf_report.output_path:
        print(f"手册起飞分析 PDF：{result.manual_pdf_report.output_path}")
    for warning in result.warnings:
        print(f"警告：{warning}", file=sys.stderr)
    return 0


def _build_request(args: argparse.Namespace) -> PerformanceRequest:
    return PerformanceRequest(
        aircraft_code=args.aircraft,
        airport_code=args.airport,
        runways=tuple(args.runway),
        scenario_id=args.scenario_id,
        runway_condition=args.runway_condition,
        contamination_depth=args.contamination_depth,
        bleed=args.bleed,
        anti_icing=args.anti_icing,
        derate=args.derate,
        temperature_range=args.temperature_range,
        wind_range=args.wind_range,
        qnh_ref=args.qnh,
        thrust_option=args.thrust_option,
        manual_report_template_id=args.manual_report_template,
        report_date_override=args.report_date,
    )


def _print_stas_paths(run_dir: Path, raw_output_path: Path | None) -> None:
    print(f"输出目录：{run_dir}")
    if raw_output_path:
        print(f"STAS 原始输出：{raw_output_path}")


if __name__ == "__main__":
    raise SystemExit(main())

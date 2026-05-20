#!/usr/bin/env python3
"""Торговый помощник — анализ криптовалютных пар."""

from __future__ import annotations

import sys

from colorama import Fore, Style, init

from data_fetcher import BinanceDataError
from engine import analyze_pair
from formatter import format_analysis

init(autoreset=True)


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def print_banner() -> None:
    print(f"\n{Fore.CYAN}{'═' * 50}")
    print(f"  🤖 ТОРГОВЫЙ ПОМОЩНИК")
    print(f"  Анализ: тренд | волатильность | фандинг")
    print(f"{'═' * 50}{Style.RESET_ALL}\n")


def run_interactive() -> None:
    print_banner()
    print("Введите торговую пару (например ETH/USDT) или 'exit' для выхода.\n")

    while True:
        try:
            pair = input(f"{Fore.GREEN}Пара > {Style.RESET_ALL}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nДо свидания!")
            break

        if not pair:
            continue
        if pair.lower() in ("exit", "quit", "q", "выход"):
            print("До свидания!")
            break

        try:
            print(f"\n{Fore.YELLOW}Загрузка данных...{Style.RESET_ALL}")
            analysis = analyze_pair(pair)
            _safe_print(format_analysis(analysis))
        except BinanceDataError as e:
            print(f"{Fore.RED}Ошибка: {e}{Style.RESET_ALL}\n")
        except Exception as e:
            print(f"{Fore.RED}Не удалось получить данные: {e}{Style.RESET_ALL}\n")


def run_single(pair: str) -> int:
    _configure_stdout()
    try:
        analysis = analyze_pair(pair)
        _safe_print(format_analysis(analysis))
        return 0
    except BinanceDataError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Не удалось получить данные: {e}", file=sys.stderr)
        return 1


def main() -> None:
    _configure_stdout()
    if len(sys.argv) > 1:
        sys.exit(run_single(" ".join(sys.argv[1:])))
    run_interactive()


if __name__ == "__main__":
    main()

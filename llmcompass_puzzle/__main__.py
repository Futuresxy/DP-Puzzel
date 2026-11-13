"""Unified entry point for the integrated LLMCompass-Puzzle workspace."""
import argparse
import runpy
import sys

COMMANDS = {
    'area': 'characterize', 'reference': 'replay', 'resources': 'system_audit',
    'dse': 'system_search', 'summarize': 'summarize_system', 'findings': 'system_findings',
    'plot': 'system_figure', 'export': 'export_handoff',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, usage='python -m llmcompass_puzzle COMMAND [OPTIONS]')
    parser.add_argument('command', choices=COMMANDS)
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        parser.print_help()
        return
    args = parser.parse_args(sys.argv[1:2])
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    runpy.run_module(f'llmcompass_puzzle.{COMMANDS[args.command]}', run_name='__main__')


if __name__ == '__main__':
    main()

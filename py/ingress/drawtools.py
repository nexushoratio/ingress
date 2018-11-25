"""Functions for working with IITC drawtools files."""


def register_shared_parsers(ctx):
    """Parser registration API."""
    dt_parser = ctx.argparse.ArgumentParser(add_help=False)
    dt_parser.add_argument(
        '-d',
        '--drawtools',
        action='store',
        required=True,
        help='IITC drawtools json file to use')

    ctx.shared_parsers['dt_parser'] = dt_parser


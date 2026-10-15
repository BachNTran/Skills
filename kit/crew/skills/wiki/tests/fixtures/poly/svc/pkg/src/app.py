"""Command-line entry for the pkg fixture."""
import pkg.core as c
from pkg import Engine


def main() -> int:
    """Run one engine pass and print the row count."""
    eng = c.Engine(c.Store())
    other = Engine(c.Store())
    print(eng.run(3, True), other.ready)
    return 0


if __name__ == "__main__":
    main()
